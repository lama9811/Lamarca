import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from google.genai import errors as genai_errors

from ..models import Profile
from ..services.gemini import generate_blog_html
from ..services.transcripts import (
    TranscriptError,
    TranscriptNotFound,
    extract_video_id,
    fetch_transcript,
)


@require_POST
@login_required
def generate_blog(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    url = data.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'YouTube URL is required.'}, status=400)

    video_id = extract_video_id(url)
    if not video_id:
        return JsonResponse(
            {'error': 'Could not parse a valid YouTube URL. Try a standard youtube.com/watch?v= link.'},
            status=400,
        )

    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.total_remaining <= 0:
        return JsonResponse(
            {'error': "You're out of credits.", 'out_of_credits': True},
            status=402,
        )

    try:
        transcript = fetch_transcript(video_id)
    except TranscriptNotFound as e:
        return JsonResponse({'error': str(e)}, status=422)
    except TranscriptError as e:
        return JsonResponse({'error': str(e)}, status=422)

    use_voice = bool(data.get('use_voice')) and profile.has_voice
    voice_samples = profile.voice_samples if use_voice else None

    try:
        blog_html = generate_blog_html(
            transcript,
            voice_samples=voice_samples,
            video_id=video_id,
        )
    except genai_errors.ClientError as e:
        if getattr(e, 'code', None) == 429:
            return JsonResponse({'error': 'Rate limited. Please try again in a moment.'}, status=429)
        return JsonResponse({'error': f'Gemini API error: {e}'}, status=400)
    except genai_errors.APIError as e:
        return JsonResponse({'error': f'Gemini API error: {e}'}, status=502)
    except Exception as e:
        return JsonResponse({'error': f'Generation failed: {str(e)}'}, status=500)

    # Charge a credit only after a successful generation. Spend free first, then paid.
    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(pk=profile.pk)
        if profile.free_remaining > 0:
            profile.free_used += 1
        else:
            profile.credit_balance = max(0, profile.credit_balance - 1)
        profile.lifetime_generations += 1
        profile.save()

    return JsonResponse({
        'blog': blog_html,
        'remaining': profile.total_remaining,
    })

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from google.genai import errors as genai_errors

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

    try:
        transcript = fetch_transcript(video_id)
    except TranscriptNotFound as e:
        return JsonResponse({'error': str(e)}, status=422)
    except TranscriptError as e:
        return JsonResponse({'error': str(e)}, status=422)

    try:
        blog_html = generate_blog_html(transcript)
    except genai_errors.ClientError as e:
        if getattr(e, 'code', None) == 429:
            return JsonResponse({'error': 'Rate limited. Please try again in a moment.'}, status=429)
        return JsonResponse({'error': f'Gemini API error: {e}'}, status=400)
    except genai_errors.APIError as e:
        return JsonResponse({'error': f'Gemini API error: {e}'}, status=502)
    except Exception as e:
        return JsonResponse({'error': f'Generation failed: {str(e)}'}, status=500)

    return JsonResponse({'blog': blog_html})

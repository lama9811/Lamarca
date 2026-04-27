import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import Profile

# Per-sample limits keep prompts reasonable and prevent abuse.
SAMPLE_MIN_CHARS = 200
SAMPLE_MAX_CHARS = 4000
MAX_SAMPLES = 3


def _get_profile(user) -> Profile:
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


@login_required
def voices(request):
    profile = _get_profile(request.user)
    # Pad samples list to MAX_SAMPLES so the template can show empty slots.
    samples = list(profile.voice_samples or [])
    while len(samples) < MAX_SAMPLES:
        samples.append('')

    return render(request, 'voices.html', {
        'profile': profile,
        'samples': samples,
        'sample_min': SAMPLE_MIN_CHARS,
        'sample_max': SAMPLE_MAX_CHARS,
    })


@login_required
@require_POST
def save_voice(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    raw_samples = data.get('samples', [])
    if not isinstance(raw_samples, list):
        return JsonResponse({'error': 'Invalid samples format.'}, status=400)

    cleaned = []
    for sample in raw_samples[:MAX_SAMPLES]:
        if not isinstance(sample, str):
            continue
        s = sample.strip()
        if not s:
            continue
        if len(s) < SAMPLE_MIN_CHARS:
            return JsonResponse(
                {'error': f'Each sample must be at least {SAMPLE_MIN_CHARS} characters '
                          'so we have enough text to learn your voice.'},
                status=400,
            )
        if len(s) > SAMPLE_MAX_CHARS:
            s = s[:SAMPLE_MAX_CHARS]
        cleaned.append(s)

    profile = _get_profile(request.user)
    profile.voice_samples = cleaned
    profile.save(update_fields=['voice_samples', 'updated_at'])

    return JsonResponse({
        'ok': True,
        'has_voice': profile.has_voice,
        'sample_count': len(cleaned),
    })

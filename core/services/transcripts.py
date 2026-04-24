"""YouTube transcript fetching via Supadata."""
import re

import requests
from django.conf import settings


TRANSCRIPT_CHAR_LIMIT = 12000


class TranscriptError(Exception):
    """Raised when a transcript cannot be fetched."""


class TranscriptNotFound(TranscriptError):
    """No captions available for the video."""


def extract_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video ID from any youtube.com or youtu.be URL."""
    match = re.search(r'(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def fetch_transcript(video_id: str) -> str:
    """Fetch transcript text for a YouTube video, trimmed to fit model context."""
    try:
        resp = requests.get(
            'https://api.supadata.ai/v1/youtube/transcript',
            params={'url': f'https://www.youtube.com/watch?v={video_id}', 'text': 'true'},
            headers={'x-api-key': settings.SUPADATA_API_KEY},
            timeout=30,
        )
    except requests.RequestException as e:
        raise TranscriptError(f'Could not fetch transcript: {e}') from e

    if resp.status_code == 404:
        raise TranscriptNotFound(
            'No captions found for this video. Try a video that has captions/subtitles enabled.'
        )
    if resp.status_code != 200:
        raise TranscriptError('Could not fetch transcript. Make sure the video is public and has captions.')

    data = resp.json()
    transcript = data.get('content') or data.get('transcript') or data.get('text') or ''
    if not transcript:
        raise TranscriptError(f'No transcript content returned. API response keys: {list(data.keys())}')

    return transcript[:TRANSCRIPT_CHAR_LIMIT]

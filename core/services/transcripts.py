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


def _format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


def fetch_transcript(video_id: str) -> str:
    """Fetch transcript text with timestamp markers, trimmed to fit model context.

    Output intersperses [M:SS] markers every ~8 seconds so the LLM can
    preserve them as inline citations. Example:
        [0:12]
        So the first thing I want to talk about is...
        [0:34]
        But here's the catch...
    """
    try:
        resp = requests.get(
            'https://api.supadata.ai/v1/youtube/transcript',
            params={'url': f'https://www.youtube.com/watch?v={video_id}'},
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
    segments = data.get('content') or data.get('transcript') or []

    # If the API returned plain text (older path or `text=true` is the default
    # in some accounts), pass through unchanged.
    if isinstance(segments, str):
        return segments[:TRANSCRIPT_CHAR_LIMIT]

    if not segments:
        raise TranscriptError(f'No transcript content returned. API response keys: {list(data.keys())}')

    # Build a transcript with timestamp markers every ~8 seconds.
    lines = []
    last_marker_time = -100.0
    buffer = []
    for seg in segments:
        text = (seg.get('text') or '').strip()
        if not text:
            continue
        # Supadata can return 'offset' (ms) or 'start' (sec)
        offset = seg.get('offset', seg.get('start', 0))
        if offset > 1000:
            offset = offset / 1000.0

        if offset - last_marker_time >= 8:
            if buffer:
                lines.append(' '.join(buffer))
                buffer = []
            lines.append(f'[{_format_timestamp(offset)}]')
            last_marker_time = offset
        buffer.append(text)

    if buffer:
        lines.append(' '.join(buffer))

    transcript = '\n'.join(lines)
    return transcript[:TRANSCRIPT_CHAR_LIMIT]

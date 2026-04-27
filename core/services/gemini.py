"""Gemini blog generation."""
import re
from typing import List, Optional

from google import genai
from google.genai import types
from django.conf import settings


MODEL = 'gemini-2.5-flash'
MAX_OUTPUT_TOKENS = 8000

BASE_PROMPT = """You are an editor at Lamarca, a literary blog magazine. Your job:
turn the YouTube transcript below into a polished, publishable blog draft.

Output rules:
- Return ONLY clean HTML — no markdown, no code fences, no commentary.
- Use these tags: <h1> for the title (just one), <h2>/<h3> for sections,
  <p> for paragraphs, <ul>/<li> for lists, <strong> for emphasis,
  <em> for italics, <blockquote> for pull-quotes, <cite> for the
  speaker attribution inside a pull-quote.
- Structure: arresting title → 1-paragraph hook → 3-5 sections with
  <h2> subheadings → conclusion. 700-1200 words total.

Citations:
- The transcript has [M:SS] timestamp markers. When you reference a
  specific point the speaker made, append the matching timestamp inline,
  formatted EXACTLY as <a href="#t-MMSS">[M:SS]</a> where MMSS is the
  digits with no colon (e.g. <a href="#t-0342">[3:42]</a>). Use 2-4
  citations total — only on the strongest claims, not every paragraph.

Pull-quotes:
- Pick 1 or 2 of the most quotable sentences directly from the transcript.
- Render each as <blockquote>"the quote"<cite>— [M:SS]</cite></blockquote>.
- Don't paraphrase pull-quotes — they must be the speaker's actual words."""


VOICE_PROMPT_FRAGMENT = """

Voice mimicry — IMPORTANT:
The user has provided samples of their own writing below. Match their voice:
sentence rhythm, vocabulary, level of formality, signature phrases. Do not
mention the samples in the output. Just absorb the style and write the new
draft as if it came from the same author.

USER'S WRITING SAMPLES:
{samples}
END OF SAMPLES."""


def _build_prompt(voice_samples: Optional[List[str]] = None) -> str:
    if voice_samples and any(s.strip() for s in voice_samples):
        joined = '\n\n--- SAMPLE ---\n\n'.join(s.strip() for s in voice_samples if s.strip())
        return BASE_PROMPT + VOICE_PROMPT_FRAGMENT.format(samples=joined)
    return BASE_PROMPT


def _parse_label_to_seconds(label: str) -> int:
    """'3:42' -> 222; '1:03:42' -> 3822."""
    parts = [int(p) for p in label.split(':')]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def _rewrite_citations(html: str, video_id: str) -> str:
    """Turn citation anchors and pull-quote timestamps into YouTube deep-links."""

    def _replace_anchor(match: 're.Match') -> str:
        label = match.group('label')
        seconds = _parse_label_to_seconds(label)
        return (
            f'<a href="https://www.youtube.com/watch?v={video_id}&t={seconds}s" '
            f'target="_blank" rel="noopener" class="ts-cite">[{label}]</a>'
        )

    # Inline anchors the AI was instructed to produce
    html = re.sub(
        r'<a href="#t-\d+">\[(?P<label>\d+:\d{2}(?::\d{2})?)\]</a>',
        _replace_anchor,
        html,
    )

    # Pull-quote attribution lines: <cite>— [3:42]</cite>
    def _replace_cite(match: 're.Match') -> str:
        prefix = match.group('prefix')
        label = match.group('label')
        seconds = _parse_label_to_seconds(label)
        return (
            f'<cite>{prefix}<a href="https://www.youtube.com/watch?v={video_id}&t={seconds}s" '
            f'target="_blank" rel="noopener" class="ts-cite">[{label}]</a></cite>'
        )

    html = re.sub(
        r'<cite>(?P<prefix>[^<\[]*)\[(?P<label>\d+:\d{2}(?::\d{2})?)\]</cite>',
        _replace_cite,
        html,
    )

    return html


def generate_blog_html(transcript: str, *, voice_samples: Optional[List[str]] = None,
                       video_id: str = '') -> str:
    """Generate a blog post from a transcript, optionally in the user's voice.

    When `video_id` is provided, citation anchors are rewritten into clickable
    YouTube deep-links so readers can jump to the moment in the source video.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    system_prompt = _build_prompt(voice_samples)

    response = client.models.generate_content(
        model=MODEL,
        contents=f'Convert this transcript into a blog post:\n\n{transcript}',
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.7,
        ),
    )

    html = response.text or ''
    if video_id:
        html = _rewrite_citations(html, video_id)
    return html

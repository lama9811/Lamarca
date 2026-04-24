"""Gemini blog generation."""
from google import genai
from google.genai import types
from django.conf import settings


MODEL = 'gemini-2.5-flash'
MAX_OUTPUT_TOKENS = 8000

SYSTEM_PROMPT = (
    'You are a professional blog writer. '
    'Convert the YouTube transcript the user provides into a polished, engaging blog post. '
    'Return ONLY clean HTML — no markdown, no code fences. '
    'Use these tags: <h1> for the title, <h2>/<h3> for sections, '
    '<p> for paragraphs, <ul>/<li> for lists, <strong> for emphasis. '
    'Structure: compelling title → introduction → 3-5 sections with subheadings → conclusion.'
)


def generate_blog_html(transcript: str) -> str:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    response = client.models.generate_content(
        model=MODEL,
        contents=f'Convert this transcript into a blog post:\n\n{transcript}',
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.7,
        ),
    )

    return response.text

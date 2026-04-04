import json
import re

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import resend
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST


from .models import EmailVerification


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_video_id(url):
    """Return the 11-char YouTube video ID from any youtube.com or youtu.be URL."""
    match = re.search(r'(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


# ── Public pages ──────────────────────────────────────────────────────────────

def home(request):
    return render(request, 'home.html')


# ── Auth ──────────────────────────────────────────────────────────────────────

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm_password', '')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'register.html')
        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'register.html')
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'register.html')
        existing = User.objects.filter(email=email).first()
        if existing:
            if not existing.is_active:
                # Previous unverified attempt — clean it up and allow re-registration
                existing.delete()
            else:
                messages.error(request, 'An account with this email already exists.')
                return render(request, 'register.html')

        user = User.objects.create_user(username=email, email=email, password=password)
        user.is_active = False
        user.save()

        verification = EmailVerification.objects.create(user=user)
        verification.generate_code()

        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            'from': settings.DEFAULT_FROM_EMAIL,
            'to': [email],
            'subject': 'Your Lamarca verification code',
            'html': f'<p>Your verification code is: <strong>{verification.code}</strong></p><p>This code expires in 5 minutes.</p>',
        })

        request.session['pending_user_id'] = user.id
        return redirect('verify_email')

    return render(request, 'register.html')


def verify_email(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('register')

    if request.method == 'POST':
        entered_code = request.POST.get('code', '').strip()
        try:
            user = User.objects.get(id=user_id)
            verification = user.email_verification
        except (User.DoesNotExist, EmailVerification.DoesNotExist):
            messages.error(request, 'Session expired. Please register again.')
            return redirect('register')

        if verification.is_expired():
            messages.error(request, 'Code expired. Please register again.')
            user.delete()
            return redirect('register')

        if entered_code == verification.code:
            verification.is_verified = True
            verification.save()
            user.is_active = True
            user.save()
            del request.session['pending_user_id']
            login(request, user)
            messages.success(request, 'Email verified! Welcome to Lamarca.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Incorrect code. Please try again.')

    return render(request, 'verify_email.html')


def resend_code(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('register')

    try:
        user = User.objects.get(id=user_id)
        verification = user.email_verification
        verification.generate_code()
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            'from': settings.DEFAULT_FROM_EMAIL,
            'to': [user.email],
            'subject': 'Your new Lamarca verification code',
            'html': f'<p>Your new verification code is: <strong>{verification.code}</strong></p><p>This code expires in 5 minutes.</p>',
        })
        messages.success(request, 'A new code has been sent.')
    except (User.DoesNotExist, EmailVerification.DoesNotExist):
        return redirect('register')

    return redirect('verify_email')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)

        if user is not None:
            if not user.is_active:
                request.session['pending_user_id'] = user.id
                messages.warning(request, 'Please verify your email first.')
                return redirect('verify_email')
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid email or password.')

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')


# ── API: Generate blog ─────────────────────────────────────────────────────────

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

    video_id = _extract_video_id(url)
    if not video_id:
        return JsonResponse({'error': 'Could not parse a valid YouTube URL. Try a standard youtube.com/watch?v= link.'}, status=400)

    # ── Fetch transcript ───────────────────────────────────────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        # Try English first, then fall back to any available language
        try:
            transcript_data = YouTubeTranscriptApi.fetch(video_id, languages=['en'])
        except Exception:
            transcript_data = YouTubeTranscriptApi.fetch(video_id)
        transcript = ' '.join(chunk.text for chunk in transcript_data)
    except TranscriptsDisabled:
        return JsonResponse({'error': 'This video has captions disabled. Please try a different video.'}, status=422)
    except NoTranscriptFound:
        return JsonResponse({'error': 'No captions found for this video. Try a video that has captions/subtitles enabled.'}, status=422)
    except Exception as e:
        return JsonResponse({'error': f'Could not fetch transcript: {str(e)}. Make sure the video is public and has captions.'}, status=422)

    # Trim to ~12 000 chars to stay within token limits
    transcript = transcript[:12000]

    # ── Generate with OpenAI ───────────────────────────────────────────────────
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are a professional blog writer. '
                        'Convert the YouTube transcript the user provides into a polished, engaging blog post. '
                        'Return ONLY clean HTML — no markdown, no code fences. '
                        'Use these tags: <h1> for the title, <h2>/<h3> for sections, '
                        '<p> for paragraphs, <ul>/<li> for lists, <strong> for emphasis. '
                        'Structure: compelling title → introduction → 3-5 sections with subheadings → conclusion.'
                    ),
                },
                {
                    'role': 'user',
                    'content': f'Convert this transcript into a blog post:\n\n{transcript}',
                },
            ],
            max_tokens=2000,
            temperature=0.7,
        )
        blog_html = response.choices[0].message.content
        return JsonResponse({'blog': blog_html})

    except Exception as e:
        return JsonResponse({'error': f'OpenAI error: {str(e)}'}, status=500)

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from google.auth.transport import requests as grequests
from google.oauth2 import id_token

from ..models import EmailVerification
from ..services.email import send_email


def _is_allowed_email(email: str) -> bool:
    return email.lower().endswith('@' + settings.ALLOWED_EMAIL_DOMAIN)


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm_password', '')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})
        if not _is_allowed_email(email):
            messages.error(request, f'Only @{settings.ALLOWED_EMAIL_DOMAIN} addresses can sign up.')
            return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})
        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})

        existing = User.objects.filter(email=email).first()
        if existing:
            if not existing.is_active:
                existing.delete()
            else:
                messages.error(request, 'An account with this email already exists.')
                return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})

        user = User.objects.create_user(username=email, email=email, password=password)
        user.is_active = False
        user.save()

        verification = EmailVerification.objects.create(user=user)
        verification.generate_code()

        try:
            send_email(
                email,
                'Your Lamarca verification code',
                f'<p>Your verification code is: <strong>{verification.code}</strong></p>'
                f'<p>This code expires in 5 minutes.</p>',
            )
        except Exception as e:
            user.delete()
            messages.error(request, f'Failed to send verification email: {str(e)}')
            return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})

        request.session['pending_user_id'] = user.id
        return redirect('verify_email')

    return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})


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
        send_email(
            user.email,
            'Your new Lamarca verification code',
            f'<p>Your new verification code is: <strong>{verification.code}</strong></p>'
            f'<p>This code expires in 5 minutes.</p>',
        )
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

    return render(request, 'login.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})


def logout_view(request):
    logout(request)
    return redirect('login')


@require_POST
def google_signin(request):
    """Verify a Google ID token, enforce @gmail.com, find-or-create the user, log in."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    credential = data.get('credential', '')
    if not credential:
        return JsonResponse({'error': 'Missing Google credential.'}, status=400)

    if not settings.GOOGLE_CLIENT_ID:
        return JsonResponse(
            {'error': 'Google Sign-In is not configured on the server.'}, status=500
        )

    try:
        payload = id_token.verify_oauth2_token(
            credential, grequests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        return JsonResponse({'error': f'Invalid Google credential: {e}'}, status=400)

    email = payload.get('email', '').lower()
    email_verified = payload.get('email_verified', False)

    if not email or not email_verified:
        return JsonResponse({'error': 'Google account email not verified.'}, status=400)

    if not _is_allowed_email(email):
        return JsonResponse(
            {'error': f'Only @{settings.ALLOWED_EMAIL_DOMAIN} accounts can sign up.'},
            status=403,
        )

    user, _created = User.objects.get_or_create(
        username=email,
        defaults={'email': email, 'is_active': True},
    )
    if not user.is_active:
        user.is_active = True
        user.save()

    login(request, user)
    return JsonResponse({'redirect': '/dashboard/'})

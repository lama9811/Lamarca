import json

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from google.auth.transport import requests as grequests
from google.oauth2 import id_token


def _is_allowed_email(email: str) -> bool:
    return email.lower().endswith('@' + settings.ALLOWED_EMAIL_DOMAIN)


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'register.html', {'google_client_id': settings.GOOGLE_CLIENT_ID})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
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

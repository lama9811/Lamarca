from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Profile


def home(request):
    return render(request, 'home.html', {
        'packs': settings.STRIPE_CREDIT_PACKS,
        'free_generations': settings.FREE_GENERATIONS,
    })


@login_required
def dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, 'dashboard.html', {'profile': profile})

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Profile


def home(request):
    return render(request, 'home.html')


@login_required
def dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, 'dashboard.html', {'profile': profile})

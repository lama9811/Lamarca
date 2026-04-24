from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('', views.home, name='home'),

    # Auth
    path('register/', views.register, name='register'),
    path('verify/', views.verify_email, name='verify_email'),
    path('verify/resend/', views.resend_code, name='resend_code'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('auth/google/', views.google_signin, name='google_signin'),

    # App
    path('dashboard/', views.dashboard, name='dashboard'),

    # API
    path('api/generate/', views.generate_blog, name='generate_blog'),
]

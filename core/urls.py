from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('', views.home, name='home'),

    # Auth
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('auth/google/', views.google_signin, name='google_signin'),

    # App
    path('dashboard/', views.dashboard, name='dashboard'),
    path('voices/', views.voices, name='voices'),
    path('voices/save/', views.save_voice, name='save_voice'),

    # Billing
    path('billing/', views.billing, name='billing'),
    path('billing/buy/', views.buy_credits, name='buy_credits'),
    path('billing/success/', views.billing_success, name='billing_success'),
    path('billing/diagnostic/', views.diagnostic, name='diagnostic'),
    path('webhooks/stripe/', views.stripe_webhook, name='stripe_webhook'),

    # API
    path('api/generate/', views.generate_blog, name='generate_blog'),
]

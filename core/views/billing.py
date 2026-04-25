import json
import logging

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..models import Profile
from ..services.stripe_service import create_checkout_session, construct_webhook_event

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_profile(user) -> Profile:
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


@login_required
def billing(request):
    profile = _get_profile(request.user)
    return render(request, 'billing.html', {
        'profile': profile,
        'packs': settings.STRIPE_CREDIT_PACKS,
    })


@login_required
@require_POST
def buy_credits(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    price_id = data.get('price_id', '').strip()
    if not price_id or price_id not in settings.STRIPE_PRICE_TO_CREDITS:
        return JsonResponse({'error': 'Unknown credit pack.'}, status=400)

    try:
        session = create_checkout_session(
            user=request.user,
            price_id=price_id,
            success_url=request.build_absolute_uri(reverse('billing_success')) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(reverse('billing')),
        )
    except stripe.StripeError as e:
        logger.exception('Stripe checkout session creation failed')
        return JsonResponse({'error': f'Payment error: {e.user_message or str(e)}'}, status=502)

    return JsonResponse({'url': session.url})


@login_required
def billing_success(request):
    """Landing page after Stripe redirects the user back. The webhook is the
    source of truth for the credit balance — this page is just UX confirmation."""
    profile = _get_profile(request.user)
    return render(request, 'billing_success.html', {'profile': profile})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = construct_webhook_event(payload, sig_header)
    except ValueError:
        logger.warning('Stripe webhook: malformed payload')
        return HttpResponse(status=400)
    except stripe.SignatureVerificationError:
        logger.warning('Stripe webhook: bad signature')
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        _handle_checkout_completed(event['data']['object'])

    return HttpResponse(status=200)


@transaction.atomic
def _handle_checkout_completed(session):
    user_id = session.get('client_reference_id')
    if not user_id:
        logger.error('Webhook: checkout.session.completed missing client_reference_id (session=%s)', session.get('id'))
        return

    try:
        user = User.objects.select_for_update().get(pk=int(user_id))
    except (User.DoesNotExist, ValueError, TypeError):
        logger.error('Webhook: unknown user_id=%s', user_id)
        return

    # Pull the price ID from the line items so we know which pack was purchased.
    # Stripe doesn't expand line_items by default — re-fetch with expansion.
    line_items = stripe.checkout.Session.list_line_items(session['id'], limit=10)
    credits_to_grant = 0
    for item in line_items.data:
        price_id = item.price.id if item.price else None
        if price_id and price_id in settings.STRIPE_PRICE_TO_CREDITS:
            credits_to_grant += settings.STRIPE_PRICE_TO_CREDITS[price_id] * item.quantity

    if credits_to_grant <= 0:
        logger.error('Webhook: no recognized price IDs in session=%s', session.get('id'))
        return

    profile, _ = Profile.objects.select_for_update().get_or_create(user=user)
    profile.credit_balance += credits_to_grant
    profile.lifetime_credits_purchased += credits_to_grant
    customer_id = session.get('customer')
    if customer_id and not profile.stripe_customer_id:
        profile.stripe_customer_id = customer_id
    profile.save()
    logger.info('Granted %d credits to user %s (session=%s)', credits_to_grant, user.id, session.get('id'))

"""Thin wrapper around the Stripe SDK so views stay clean."""
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(*, user, price_id: str, success_url: str, cancel_url: str):
    """Create a one-time Checkout Session for the given user + price."""
    kwargs = {
        'mode': 'payment',
        'line_items': [{'price': price_id, 'quantity': 1}],
        'success_url': success_url,
        'cancel_url': cancel_url,
        # client_reference_id lets the webhook trace the payment back to a user
        # without trusting anything the browser sends.
        'client_reference_id': str(user.id),
    }
    # Reuse Stripe customer if we already have one
    if user.profile.stripe_customer_id:
        kwargs['customer'] = user.profile.stripe_customer_id
    elif user.email:
        kwargs['customer_email'] = user.email

    return stripe.checkout.Session.create(**kwargs)


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verify and parse a webhook payload. Raises stripe.error.SignatureVerificationError on bad sig."""
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )

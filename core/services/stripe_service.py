"""Thin wrapper around the Stripe SDK so views stay clean."""
import logging
from typing import Optional

import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


def resolve_to_price_id(value: str, expected_amount_dollars: Optional[float] = None) -> str:
    """If `value` is a Stripe Price ID (price_...), return it unchanged.
    If it's a Product ID (prod_...), find the matching Price for that Product
    and return its ID. Useful so the app works whether the user pasted a
    Price ID or a Product ID into Vercel env vars.

    `expected_amount_dollars` lets us pick the right price when a Product
    has multiple prices ($1 vs $5 vs $10 etc.). Falls back to the first
    active price if no amount-match is found.

    Returns '' if resolution fails — caller should handle that.
    """
    if not value:
        return ''
    if value.startswith('price_'):
        return value
    if not value.startswith('prod_'):
        # Unknown format — return unchanged so Stripe will reject with a clear error.
        return value
    if not settings.STRIPE_SECRET_KEY.startswith(('sk_test_', 'sk_live_')):
        # Can't query Stripe without a valid key.
        return value

    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        prices = stripe.Price.list(product=value, active=True, limit=20)
    except stripe.StripeError as e:
        logger.warning('Could not list prices for product %s: %s', value, e)
        return value

    if not prices.data:
        logger.warning('Product %s has no active prices', value)
        return value

    # Try to match expected dollar amount first
    if expected_amount_dollars is not None:
        cents = int(round(expected_amount_dollars * 100))
        for p in prices.data:
            if p.unit_amount == cents:
                return p.id

    # Fall back to first active price
    return prices.data[0].id


def create_checkout_session(*, user, price_id: str, success_url: str, cancel_url: str,
                            metadata: Optional[dict] = None):
    """Create a one-time Checkout Session for the given user + price.

    `metadata` is attached to the Session so the webhook can read it back
    (e.g., the number of credits this pack grants) without having to look
    anything up by price_id.
    """
    kwargs = {
        'mode': 'payment',
        'line_items': [{'price': price_id, 'quantity': 1}],
        'success_url': success_url,
        'cancel_url': cancel_url,
        # client_reference_id lets the webhook trace the payment back to a user
        # without trusting anything the browser sends.
        'client_reference_id': str(user.id),
    }
    if metadata:
        kwargs['metadata'] = {k: str(v) for k, v in metadata.items()}
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

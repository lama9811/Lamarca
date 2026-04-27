"""Live diagnostic page so the developer can see exactly what's wrong
with Stripe configuration without having to read server logs."""
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def _check(name: str, value: str, expected_prefix: str, what: str) -> dict:
    """Build a row of diagnostic info for one env var."""
    if not value:
        return {
            'name': name,
            'status': 'fail',
            'detail': 'Not set on Vercel.',
            'fix': f'Add {name} to Vercel env vars (Production). It should be {what}.',
        }
    if not value.startswith(expected_prefix):
        masked = value[:8] + '…' if len(value) > 8 else value
        return {
            'name': name,
            'status': 'fail',
            'detail': f'Value starts with "{masked}" but should start with "{expected_prefix}".',
            'fix': f'Replace the Vercel env var with the correct value: {what}.',
        }
    masked = value[:10] + '…' + value[-4:] if len(value) > 14 else value
    return {
        'name': name,
        'status': 'ok',
        'detail': f'Set, looks valid: {masked}',
        'fix': '',
    }


def _ping_stripe() -> dict:
    """Try a real Stripe API call to confirm the secret key actually works."""
    if not settings.STRIPE_SECRET_KEY:
        return {
            'name': 'Stripe API ping',
            'status': 'skip',
            'detail': 'Skipped — STRIPE_SECRET_KEY not set.',
            'fix': '',
        }
    if not settings.STRIPE_SECRET_KEY.startswith(('sk_test_', 'sk_live_')):
        return {
            'name': 'Stripe API ping',
            'status': 'skip',
            'detail': 'Skipped — key format invalid (see STRIPE_SECRET_KEY row).',
            'fix': '',
        }
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        account = stripe.Account.retrieve()
        mode = 'TEST' if settings.STRIPE_SECRET_KEY.startswith('sk_test_') else 'LIVE'
        return {
            'name': 'Stripe API ping',
            'status': 'ok',
            'detail': f'Connected to Stripe account {account.id} in {mode} mode.',
            'fix': '',
        }
    except stripe.AuthenticationError as e:
        return {
            'name': 'Stripe API ping',
            'status': 'fail',
            'detail': f'Stripe rejected the secret key: {e.user_message or "authentication failed"}',
            'fix': 'Re-copy the test secret key from https://dashboard.stripe.com/test/apikeys and paste into Vercel.',
        }
    except stripe.StripeError as e:
        return {
            'name': 'Stripe API ping',
            'status': 'fail',
            'detail': f'Stripe error: {e.user_message or str(e)[:100]}',
            'fix': 'Check Stripe dashboard status.',
        }


def _check_price_in_stripe(name: str, price_id: str) -> dict:
    """For a configured price ID, verify it actually exists in Stripe."""
    if not price_id or not price_id.startswith('price_'):
        return None  # skip — covered by env var check above
    if not settings.STRIPE_SECRET_KEY.startswith(('sk_test_', 'sk_live_')):
        return None  # can't query without a valid key
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        price = stripe.Price.retrieve(price_id)
        amount = price.unit_amount / 100 if price.unit_amount else 0
        return {
            'name': f'{name} → Stripe',
            'status': 'ok',
            'detail': f'Found in Stripe: {price.currency.upper()} {amount:.2f}, recurring={bool(price.recurring)}',
            'fix': '',
        }
    except stripe.InvalidRequestError as e:
        return {
            'name': f'{name} → Stripe',
            'status': 'fail',
            'detail': f'Stripe says this Price ID does not exist: {e.user_message or str(e)[:100]}',
            'fix': f'In Vercel, replace {name} with a valid Price ID from your Stripe Products page.',
        }
    except stripe.StripeError:
        return None


@login_required
def diagnostic(request):
    """Show the developer everything they need to debug Stripe config."""
    rows = [
        _check('STRIPE_SECRET_KEY', settings.STRIPE_SECRET_KEY,
               'sk_test_', 'a test secret key from Stripe (starts with sk_test_)'),
        _check('STRIPE_PUBLISHABLE_KEY', settings.STRIPE_PUBLISHABLE_KEY,
               'pk_test_', 'a test publishable key from Stripe (starts with pk_test_)'),
        _check('STRIPE_WEBHOOK_SECRET', settings.STRIPE_WEBHOOK_SECRET,
               'whsec_', 'the webhook signing secret from Stripe (starts with whsec_)'),
        _check('STRIPE_PRICE_1_CREDIT (or _CREDITS)',
               settings.STRIPE_CREDIT_PACKS[0].get('price_id', ''),
               'price_', 'the Price ID for the $1 / 1-credit pack (starts with price_)'),
        _check('STRIPE_PRICE_5_CREDITS (or _CREDIT)',
               settings.STRIPE_CREDIT_PACKS[1].get('price_id', ''),
               'price_', 'the Price ID for the $5 / 5-credit pack (starts with price_)'),
        _check('STRIPE_PRICE_12_CREDITS (or _10_CREDIT)',
               settings.STRIPE_CREDIT_PACKS[2].get('price_id', ''),
               'price_', 'the Price ID for the $10 / 12-credit pack (starts with price_)'),
    ]

    rows.append(_ping_stripe())

    # Live Stripe lookups for each price ID (only if format check passes)
    for i, env_name in enumerate(['STRIPE_PRICE_1_CREDIT', 'STRIPE_PRICE_5_CREDITS', 'STRIPE_PRICE_12_CREDITS']):
        result = _check_price_in_stripe(env_name, settings.STRIPE_CREDIT_PACKS[i].get('price_id', ''))
        if result:
            rows.append(result)

    all_ok = all(r['status'] == 'ok' for r in rows if r['status'] != 'skip')

    return render(request, 'diagnostic.html', {
        'rows': rows,
        'all_ok': all_ok,
        'canonical_host': getattr(settings, 'CANONICAL_HOST', '') or '(not set)',
    })

from django.conf import settings
from django.http import HttpResponseRedirect


class CanonicalHostRedirectMiddleware:
    """Bounce requests on Vercel deploy-hash URLs to the canonical host.

    Vercel gives every deployment a unique URL like
    ``lamarca-abc123-projects.vercel.app``. When a developer clicks "Visit"
    in the dashboard, Vercel opens that hash URL — but Google Sign-In and
    other third parties only know about the canonical host (``lamarca.vercel.app``),
    so the user gets confusing errors.

    With ``CANONICAL_HOST`` set, this middleware 302-redirects any GET to a
    non-canonical Vercel host to the same path on the canonical host.
    Webhooks (POST) are left alone so Stripe etc. keep working.
    Add ``?preview=1`` to any URL to bypass the redirect for that request,
    so you can still test a specific preview deploy on its real URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical_host = getattr(settings, 'CANONICAL_HOST', '').strip()

    def __call__(self, request):
        if self._should_redirect(request):
            return HttpResponseRedirect(
                f'https://{self.canonical_host}{request.get_full_path()}'
            )
        return self.get_response(request)

    def _should_redirect(self, request) -> bool:
        if not self.canonical_host:
            return False
        if request.method != 'GET':
            return False
        if 'preview' in request.GET:
            return False
        host = request.get_host().split(':')[0].lower()
        if host == self.canonical_host.lower():
            return False
        # Only redirect Vercel deploy URLs — leave anything else (custom domains,
        # localhost, tests) alone so we don't accidentally trap unknown traffic.
        return host.endswith('.vercel.app')

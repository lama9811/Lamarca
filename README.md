# Lamarca

> YouTube videos, rewritten as a draft you'd actually publish — in your voice, with citations to the source.

[**Live demo →**](https://lamarca.vercel.app)

Lamarca turns any YouTube link into a polished blog post. What makes it different from every other "transcript-to-blog" tool is **whose voice it speaks in**: paste a few paragraphs of your own writing and Lamarca learns your style. The output reads like you wrote it, with clickable timestamps that link back to the exact moment in the video.

---

## Why this exists

YouTube content is invisible to Google search. Reading is 3–5× faster than watching. And creators who only publish videos miss ~70% of the audience that searches before clicking. Lamarca takes the 4–8 hours of writing a blog from a video down to **30 seconds and one credit**.

The space already has tools that do a worse job:

| Tool | What it lacks |
|---|---|
| ChatGPT | Generic tone, no voice fidelity, no source links |
| Castmagic | Subscription-only, business-y output |
| 2short.ai | Focused on social clips, weak long-form |

Lamarca's wedge is the four things missing in those: **voice fidelity, source verifiability, editorial design, pay-as-you-go pricing**.

---

## What's unique

### Voice cloning from 3 samples
Users paste 1–3 paragraphs of their own past writing on `/voices/`. Future drafts are generated with explicit style-mimicry instructions to Gemini, absorbing sentence rhythm, vocabulary, and signature phrases.

### Timestamped citations
Each draft includes 2–4 clickable `[3:42]` pills next to the strongest claims. Click one → opens YouTube at that exact second. Readers trust drafts that show their work; SEO rewards content with citations to the source.

### Pull-quotes
The model picks 1–2 verbatim sentences from the speaker, rendered as styled `<blockquote>` elements with timestamp attribution. Like a magazine, not a content mill.

### Editorial design
Cream paper, Fraunces typography, Caveat handwritten accents. Looks like a literary magazine, not a SaaS dashboard.

### Pay-as-you-go
Three credit packs: $1 / 1 credit, $5 / 5 credits, $10 / 12 credits. No subscription, credits never expire. Three free generations on signup.

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django 6.0, Python 3.13 |
| Database | PostgreSQL on [Neon](https://neon.tech) (serverless) |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| Auth | Google Sign-In (OAuth 2.0 via Google Identity Services) |
| Payments | Stripe Checkout + webhooks |
| Transcripts | [Supadata](https://supadata.ai) YouTube API |
| Static files | WhiteNoise (no `collectstatic` step on deploy) |
| Hosting | Vercel (`@vercel/python` runtime) |
| Styling | Hand-rolled CSS, no framework — design language defined in `theme/templates/base.html` |

---

## Architecture

```
┌──────────────┐         ┌──────────────────────────────────────┐
│   Browser    │         │              Vercel                  │
│              │         │  ┌──────────────────────────────┐    │
│  /dashboard  │ ──POST─►│  │ Django (lamarca_ai/wsgi.py) │    │
│  /billing    │         │  │                              │    │
│  /voices     │         │  │  • core.views.api            │    │
└──────────────┘         │  │  • core.views.billing        │    │
       │                 │  │  • core.views.voices         │    │
       ▼                 │  │  • core.middleware.Canonical │    │
┌──────────────┐         │  └──────────────────────────────┘    │
│  Stripe      │ ─POST──►│       /webhooks/stripe/              │
│  Checkout    │         │       (HMAC-verified)                │
└──────────────┘         └──────────────────────────────────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                    ┌──────────┐    ┌─────────┐    ┌──────────┐
                    │   Neon   │    │ Gemini  │    │ Supadata │
                    │ Postgres │    │   API   │    │   API    │
                    └──────────┘    └─────────┘    └──────────┘
```

### Request flow for a generation

1. User submits a YouTube URL → `POST /api/generate/` (Django, login required)
2. `core.services.transcripts.fetch_transcript()` → Supadata API → returns transcript with `[M:SS]` markers
3. `core.services.gemini.generate_blog_html()` → Gemini with system prompt that includes user's voice samples (if saved) and instructions for citations + pull-quotes
4. Post-processing rewrites `[M:SS]` anchors into real `youtube.com/watch?v=…&t=Ns` deep-links
5. One credit decremented atomically (free credits spent first, then paid balance)
6. HTML returned to the browser, rendered in the editorial-style draft card

### Payment flow

1. User clicks Buy → `POST /billing/buy/`
2. View resolves env-configured ID to a Price ID (auto-resolves Stripe Product IDs to Price IDs as a forgiveness layer)
3. Creates a Stripe Checkout Session with `metadata.credits` set
4. Browser redirects to `checkout.stripe.com/c/pay/cs_test_…`
5. Stripe processes payment → POSTs `checkout.session.completed` to `/webhooks/stripe/`
6. Webhook verifies HMAC signature with `STRIPE_WEBHOOK_SECRET`, reads metadata.credits, atomically grants credits to the user's Profile

---

## Notable engineering decisions

A few things worth highlighting if you're reading this as a recruiter or curious developer:

- **Auto-resolve Product IDs to Price IDs** — when a user pastes a `prod_…` (Product) into a Vercel env var instead of `price_…` (Price), the app queries Stripe at checkout time, finds the matching Price, and uses it. Forgiveness layer that makes the app work despite a common Stripe setup mistake. See `core/services/stripe_service.py`.

- **Live diagnostic page** at `/billing/diagnostic/` — pings Stripe with the configured key, validates each env var format, lists every Stripe Price in the user's account with click-to-copy IDs, and detects common paste mistakes (env var name pasted instead of value, KEY=VALUE format, quoted strings, leading whitespace).

- **Canonical-host redirect middleware** — Vercel deploy-hash URLs (`lamarca-abc123-….vercel.app`) break Google OAuth because Google requires the origin to be pre-registered. Custom Django middleware bounces any `*.vercel.app` request that isn't the canonical host to `lamarca.vercel.app` so OAuth always sees the registered origin. `?preview=1` query param escapes the redirect for actually testing preview deploys. See `core/middleware.py`.

- **COOP override for Google Sign-In** — Django 6's default `Cross-Origin-Opener-Policy: same-origin` breaks the Google Identity Services popup callback. `SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'` fixes it without weakening the rest of the security headers.

- **Stripe webhook reliability** — the webhook reads `metadata.credits` from the Session as the source of truth (not the Price ID lookup), so credits are granted correctly even if Vercel env vars change between checkout and webhook delivery.

---

## Local development

### Prerequisites
- Python 3.13
- A Stripe Test Mode account
- A Neon (or any Postgres) database
- A Google Cloud OAuth Client ID
- A Gemini API key
- A Supadata API key

### Setup

```bash
# Clone
git clone https://github.com/lama9811/Lamarca.git
cd "Lamarca"

# Virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Environment
cp .env.example .env  # then fill in values (see below)

# Database
python manage.py migrate

# Run
python manage.py runserver 8000
```

Open http://localhost:8000.

### Required environment variables

```bash
# Database
DATABASE_URL=postgresql://...                    # from Neon

# Auth
GOOGLE_CLIENT_ID=...apps.googleusercontent.com   # from Google Cloud Console
SECRET_KEY=...                                   # Django: python -c "import secrets; print(secrets.token_urlsafe(64))"

# AI
GEMINI_API_KEY=...                               # from aistudio.google.com/app/apikey
SUPADATA_API_KEY=sd_...                          # from supadata.ai

# Stripe (Test Mode)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_1_CREDIT=price_...                  # also accepts STRIPE_PRICE_1_CREDITS
STRIPE_PRICE_5_CREDITS=price_...                 # also accepts STRIPE_PRICE_5_CREDIT
STRIPE_PRICE_12_CREDITS=price_...                # also accepts STRIPE_PRICE_10_CREDIT

# Production-only
DEBUG=False
CANONICAL_HOST=lamarca.vercel.app                # for the redirect middleware
```

### Webhook in development

Use the Stripe CLI to forward events to localhost:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe/
```

The CLI prints a `whsec_…` signing secret — use it as your local `STRIPE_WEBHOOK_SECRET`.

### Test cards

| Card | Result |
|---|---|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 9995` | Insufficient funds |
| `4000 0027 6000 3184` | 3D Secure challenge |

Any future expiry, any 3-digit CVC, any 5-digit ZIP.

---

## Project structure

```
.
├── core/                       # The single Django app
│   ├── middleware.py           # CanonicalHostRedirectMiddleware
│   ├── models.py               # Profile (credit balance, voice samples)
│   ├── urls.py
│   ├── migrations/
│   ├── services/
│   │   ├── gemini.py           # Blog generation with voice + citations
│   │   ├── stripe_service.py   # Checkout sessions, prod→price resolver
│   │   └── transcripts.py      # Supadata fetch with timestamp markers
│   ├── templates/              # Editorial-style HTML
│   │   ├── billing.html
│   │   ├── billing_success.html
│   │   ├── dashboard.html
│   │   ├── diagnostic.html
│   │   ├── home.html
│   │   ├── login.html
│   │   ├── register.html
│   │   └── voices.html
│   └── views/
│       ├── api.py              # /api/generate/
│       ├── auth.py             # Google Sign-In
│       ├── billing.py          # Stripe checkout + webhook
│       ├── diagnostic.py       # Live config check
│       ├── pages.py
│       └── voices.py           # Voice sample management
│
├── lamarca_ai/                 # Django project config
│   ├── settings.py             # All env-driven config
│   ├── urls.py
│   └── wsgi.py
│
├── theme/
│   └── templates/
│       └── base.html           # Site-wide layout + design tokens
│
├── requirements.txt
├── vercel.json                 # @vercel/python entry
└── manage.py
```

---

## Roadmap

The next three features that would push Lamarca from "interesting demo" to "indispensable for creators":

- **Direct publish** — one-click to Substack / Medium / Ghost / dev.to
- **Auto-generated hero image** — Imagen or DALL-E illustration in the editorial palette
- **Multi-platform spin-out** — from one draft, generate Twitter thread + LinkedIn post + newsletter (in the same voice)

---

## License

MIT

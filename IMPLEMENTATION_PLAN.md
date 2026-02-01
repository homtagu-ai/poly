# PolyHunter — Implementation Plan

> What's left to build, how to merge the landing page, and how to get a working user journey without Stripe.

---

## Table of Contents
1. [What's Left to Build](#1-whats-left-to-build)
2. [Merging the Landing Page into the Main Project](#2-merging-the-landing-page-into-the-main-project)
3. [Test Account with Full Access (No Stripe Needed)](#3-test-account-with-full-access-no-stripe-needed)
4. [Stripe Setup Guide (Separate)](#4-stripe-setup-guide-separate---see-stripe_setupmd)
5. [Implementation Order](#5-implementation-order)

---

## 1. What's Left to Build

### Status Overview

| Component | Status | What's Needed |
|-----------|--------|---------------|
| Flask app (dashboard, analyzer, markets, whales, calculator) | DONE | Already running on EC2 |
| Landing page HTML/CSS | DONE (separate project) | Merge into main project |
| Supabase project | NOT STARTED | Create project, tables, triggers, RLS |
| Registration page (`/register`) | NOT STARTED | Build HTML + Supabase JS auth |
| Login page (`/login`) | NOT STARTED | Build HTML + Supabase JS auth |
| Auth gating (protect routes) | NOT STARTED | Supabase session check on every page |
| Persistent upgrade popup | NOT STARTED | JS component in `base.html` |
| Test account (bypass paywall) | NOT STARTED | Supabase manual profile row |
| Stripe integration | NOT STARTED (no access yet) | Separate doc — do last |
| Klaviyo email flows | NOT STARTED | Set up after auth works |
| Stape tracking | NOT STARTED | Set up after full flow works |
| Meta Ads campaigns | NOT STARTED | Set up after tracking works |
| DNS (`polyhunter.ai`) | NOT STARTED | Point domain to EC2 IP |

### Build Order (What to Do First → Last)

```
Phase 1: Supabase + Auth pages          ← START HERE (no Stripe needed)
Phase 2: Merge landing page into project
Phase 3: Auth gating + upgrade popup
Phase 4: Test account setup
Phase 5: Klaviyo email flows
Phase 6: DNS + SSL + deploy
Phase 7: Stape tracking
Phase 8: Stripe integration              ← DO LAST (when you have access)
Phase 9: Meta Ads campaigns
```

---

## 2. Merging the Landing Page into the Main Project

### Current Situation

```
C:\Users\Misha\Desktop\PolySnap Landing\     ← Separate project (landing page)
    index.html
    nav-template.html
    LANDING_PAGE_SPEC.md
    *.png (logos, mascot images)

C:\Users\Misha\Desktop\PolySnap Bot MVP\     ← Main project (Flask app)
    polyscalping/
        server.py
        templates/
            base.html
            dashboard.html
            analyzer.html
            markets.html
            whales.html
            calculator.html
        static/
            images/
```

### How to Merge

**Step 1: Copy landing page assets into the main project**

```
polyscalping/
    templates/
        landing.html        ← NEW (from PolySnap Landing/index.html)
        register.html       ← NEW (build from scratch)
        login.html          ← NEW (build from scratch)
        base.html           ← existing (shared nav, particles, styles)
        base_public.html    ← NEW (public pages base — no app nav, no auth check)
        dashboard.html      ← existing
        analyzer.html       ← existing
        ...
    static/
        images/
            polyhunter-logo.png   ← copy from landing project
            566456.png            ← copy from landing project (shark logo)
            mascot.png            ← copy from landing project
```

**Step 2: Add new Flask routes in `server.py`**

```python
# --- PUBLIC ROUTES (no auth) ---

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/login")
def login():
    return render_template("login.html")

# --- APP ROUTES (auth required) ---

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/analyzer")
def analyzer_page():
    return render_template("analyzer.html")

@app.route("/markets")
def markets():
    return render_template("markets.html")

# ... whales, calculator stay the same
```

**Note:** Currently `/` serves the dashboard. After merge, `/` becomes the landing page and dashboard moves to `/dashboard`.

**Step 3: Create two base templates**

The key trick for keeping landing page and app pages separate while in the same project:

### `base_public.html` — For landing, register, login

```
- Simpler nav (Logo + "Features" + "Pricing" + "Login" + "Get Started")
- Particles background (same as app)
- NO app navigation (no Dashboard/Markets/Whales/etc links)
- NO auth check JavaScript
- NO upgrade popup
- Landing-specific CSS (hero styles, feature grid, email capture form)
```

### `base.html` — For app pages (existing, modify slightly)

```
- Full app nav (Dashboard, Markets, Whales, Calculator, Analyzer)
- Particles background
- Auth check on load (redirect to /login if not authenticated)
- Upgrade popup logic (check subscription, show popup if free)
- All existing app CSS
```

### How Templates Inherit

```
base_public.html          base.html (existing)
    |                         |
    ├── landing.html          ├── dashboard.html
    ├── register.html         ├── analyzer.html
    └── login.html            ├── markets.html
                              ├── whales.html
                              └── calculator.html
```

**landing.html:**
```html
{% extends "base_public.html" %}
{% block content %}
    <!-- Hero, features, pricing, email capture, footer -->
{% endblock %}
```

**dashboard.html (updated):**
```html
{% extends "base.html" %}
{% block content %}
    <!-- existing dashboard content -->
{% endblock %}
```

### Why This Approach Works

1. **One project, one deploy** — everything pushes to same EC2
2. **Separate concerns** — landing page styles don't leak into app, app nav doesn't show on landing
3. **Shared particles/fonts** — both base templates include the same particles canvas and font imports
4. **Easy to edit** — working on the landing page? Edit `landing.html` and `base_public.html`. Working on the app? Edit app templates and `base.html`. They don't interfere.
5. **Jinja2 template inheritance** — Flask's built-in way to share common elements

### Prompt Tip for Editing

When you ask Claude (or any AI) to edit files, differentiate like this:

- **Landing page work:** "Edit `landing.html` — change the hero headline" or "Edit `base_public.html` — update the public nav"
- **App work:** "Edit `dashboard.html` — add a new stats card" or "Edit `base.html` — change the app nav"
- **Auth pages:** "Edit `register.html` — add the verification code input"

The file names make it obvious which context you're in. No confusion.

---

## 3. Test Account with Full Access (No Stripe Needed)

### The Problem

You want to test the full user journey (register → login → see dashboard without paywall) but Stripe isn't set up yet. The upgrade popup would block everything.

### The Solution: Manual Supabase Profile Override

After setting up Supabase and creating your test account through the normal registration flow, manually set it as a paid subscriber directly in Supabase.

### Step-by-Step

**1. Create your Supabase project** at [supabase.com](https://supabase.com)

**2. Run the table creation SQL** (from `MARKETING_FUNNEL_ANALYSIS.md` Section 6)

**3. Register a test account** through your `/register` page normally (this creates the `auth.users` entry and auto-creates the `profiles` row via the DB trigger)

**4. In Supabase Dashboard → SQL Editor, run:**

```sql
-- Find your test user
SELECT id, email, username, is_subscribed FROM profiles;

-- Override to full access (replace YOUR_USER_ID with the actual UUID)
UPDATE profiles
SET
    is_subscribed = TRUE,
    subscription_status = 'active',
    stripe_customer_id = 'TEST_ACCOUNT'
WHERE email = 'your-test@email.com';
```

**That's it.** Now when your app checks `is_subscribed`, this account returns `true` and the upgrade popup never shows.

### How the App Code Handles It

The popup logic (from `MARKETING_FUNNEL_ANALYSIS.md`) already works with this:

```javascript
// This runs on every page load
const { data: profile } = await supabase
    .from('profiles')
    .select('is_subscribed, subscription_status')
    .eq('id', user.id)
    .single();

if (!profile?.is_subscribed) {
    showUpgradePopup();  // Won't fire for test account
}
```

Since we set `is_subscribed = TRUE` manually, the popup never appears for the test account.

### Multiple Test Accounts

You can create as many test accounts as needed:

```sql
-- Give full access to multiple test emails
UPDATE profiles
SET is_subscribed = TRUE, subscription_status = 'active', stripe_customer_id = 'TEST_ACCOUNT'
WHERE email IN ('test1@email.com', 'test2@email.com', 'demo@polyhunter.ai');
```

### Testing the Free User Experience

To test what free users see (with the upgrade popup), simply register a NEW account and don't run the SQL override. That account will see the paywall on every page as intended.

### What Happens When Stripe Is Ready

Once you set up Stripe later:
1. The webhook will handle real subscriptions automatically
2. Your test account keeps working (it's already marked as subscribed)
3. Optionally clean up test accounts: `UPDATE profiles SET stripe_customer_id = NULL WHERE stripe_customer_id = 'TEST_ACCOUNT';`

---

## 4. Stripe Setup Guide (Separate — See `STRIPE_SETUP.md`)

The complete Stripe integration guide is in a separate document: **`STRIPE_SETUP.md`**

This covers:
- Creating Stripe account and product/price
- Checkout session creation
- Webhook handler
- Testing with Stripe CLI
- Going live

---

## 5. Implementation Order

### Phase 1: Supabase Setup (Day 1)

- [ ] Create Supabase project
- [ ] Run table creation SQL (profiles, subscriptions, email_leads)
- [ ] Create DB trigger for auto-profile on signup
- [ ] Enable RLS policies
- [ ] Enable email OTP in Auth settings
- [ ] Set up Google OAuth provider
- [ ] Get project URL + anon key + service role key
- [ ] Add Supabase env vars to `.env`

### Phase 2: Merge Landing Page + Build Auth Pages (Days 2-3)

- [ ] Copy landing page assets into `polyscalping/static/images/`
- [ ] Create `base_public.html` (public pages base template)
- [ ] Convert landing `index.html` → `landing.html` (extends `base_public.html`)
- [ ] Build `register.html` (extends `base_public.html`)
- [ ] Build `login.html` (extends `base_public.html`)
- [ ] Update `server.py`: change `/` route to landing, add `/dashboard`, `/register`, `/login`
- [ ] Add Supabase JS SDK (`<script>` tag) to both base templates
- [ ] Wire up registration form → Supabase `signUp()` + `verifyOtp()`
- [ ] Wire up login form → Supabase `signInWithPassword()`
- [ ] Wire up Google OAuth button

### Phase 3: Auth Gating + Upgrade Popup (Day 4)

- [ ] Add auth check to `base.html` — redirect to `/login` if no session
- [ ] Build persistent upgrade popup component
- [ ] Add subscription check logic (read `profiles.is_subscribed`)
- [ ] Add "Upgrade Now" button → placeholder (Stripe not ready yet, show "Coming Soon" or redirect to landing)
- [ ] Test: unauthenticated user → redirected to `/login`
- [ ] Test: free user → sees upgrade popup on every page
- [ ] Test: logged-in user nav shows username/email

### Phase 4: Test Account (Day 4, after Phase 3)

- [ ] Register test account through `/register`
- [ ] Run SQL override in Supabase (`is_subscribed = TRUE`)
- [ ] Verify: test account sees full dashboard without popup
- [ ] Verify: new free account sees upgrade popup

### Phase 5: Klaviyo Email Flows (Day 5)

- [ ] Create Klaviyo account
- [ ] Create Welcome list
- [ ] Build 3-email welcome flow
- [ ] Build `/api/capture-email` endpoint in `server.py`
- [ ] Wire landing page email form → `/api/capture-email`
- [ ] Add `sync_to_klaviyo()` function
- [ ] Add `update_klaviyo_registered()` function
- [ ] Test: email capture → Klaviyo email → register link works

### Phase 6: DNS + SSL + Deploy (Day 6)

- [ ] Point `polyhunter.ai` DNS A record → `44.207.97.34`
- [ ] Install Certbot on EC2, get SSL cert for `polyhunter.ai`
- [ ] Update Nginx config for HTTPS + `polyhunter.ai`
- [ ] Update Supabase redirect URLs to `https://polyhunter.ai/...`
- [ ] Deploy and test full flow on production domain
- [ ] Update Supabase Auth settings (site URL = `https://polyhunter.ai`)

### Phase 7: Stape Tracking (Day 7)

- [ ] Create Stape account
- [ ] Set up sGTM container
- [ ] Configure Meta CAPI tag
- [ ] Configure Google Ads tag
- [ ] Add `track_event()` function to `server.py`
- [ ] Wire tracking to all funnel steps
- [ ] Verify events in Meta Events Manager

### Phase 8: Stripe Integration (When You Get Access)

- [ ] See `STRIPE_SETUP.md` for complete guide
- [ ] Create product + price in Stripe Dashboard
- [ ] Add Stripe Python package to `requirements.txt`
- [ ] Build `/api/stripe/create-checkout` route
- [ ] Build `/api/stripe/webhook` route
- [ ] Update upgrade popup button to trigger real Stripe checkout
- [ ] Register webhook URL in Stripe Dashboard
- [ ] Test with Stripe CLI locally
- [ ] Deploy and test with real Stripe test mode cards

### Phase 9: Meta Ads (After Everything Works)

- [ ] Set up Meta Business Manager
- [ ] Create Pixel
- [ ] Connect CAPI via Stape
- [ ] Create campaign structure
- [ ] Set UTM parameters
- [ ] Launch test campaigns
- [ ] Optimize for Lead → CompleteRegistration → Purchase

---

## Quick Start: What to Do Right Now

**You can start building TODAY without Stripe:**

1. **Create Supabase project** → get URL + keys
2. **Merge landing page** into main project
3. **Build register + login pages**
4. **Add auth gating** to app pages
5. **Create test account** with manual SQL override
6. **Test the full journey**: landing → register (with email code) → login → dashboard (no popup for test account) / dashboard with popup (for free account)

This gives you a fully working authenticated app. Stripe plugs in later as just one API route + one webhook.

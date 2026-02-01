# PolyHunter Marketing Funnel & Payment Integration

## Table of Contents
1. [Domain & Architecture Overview](#1-domain--architecture-overview)
2. [User Journey (Step-by-Step)](#2-user-journey-step-by-step)
3. [Tech Stack & Roles](#3-tech-stack--roles)
4. [Supabase Auth: Signup with Email Code Verification](#4-supabase-auth-signup-with-email-code-verification)
5. [Stripe Integration & Upgrade Paywall](#5-stripe-integration--upgrade-paywall)
6. [Database Schema](#6-database-schema)
7. [Klaviyo Email Flows](#7-klaviyo-email-flows)
8. [Stape Server-Side Tracking](#8-stape-server-side-tracking)
9. [Meta Ads Integration](#9-meta-ads-integration)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Environment Variables](#11-environment-variables)
    
---

## 1. Domain & Architecture Overview

### URL Structure

| URL | Purpose |
|-----|---------|
| `https://polyhunter.ai/` | Landing page (marketing, email capture, SEO) |
| `https://polyhunter.ai/register` | Signup page (username, email, password, code verification) |
| `https://polyhunter.ai/login` | Login page |
| `https://polyhunter.ai/dashboard` | Main dashboard (post-login, auth required) |
| `https://polyhunter.ai/analyzer` | Event Analyzer tool (auth required) |
| `https://polyhunter.ai/markets` | Markets browser (auth required) |

### High-Level Architecture

```
                    polyhunter.ai/ (Landing)
                          |
                    [Email capture]
                          |
                    Klaviyo welcome email
                          |
                          v
              polyhunter.ai/register
         (username + email + password + code)
                          |
                  [Email verification code]
                          |
                          v
              polyhunter.ai/login
              (saved credentials visible)
                          |
                          v
              polyhunter.ai/dashboard
          +-----------------------------------+
          |  PERSISTENT UPGRADE POPUP/BANNER  |
          |  visible on EVERY page until paid |
          +-----------------------------------+
                          |
                    [User clicks Upgrade]
                          |
                          v
                  Stripe Checkout (hosted)
                          |
                    [Payment confirmed]
                          |
                          v
               Webhook -> Supabase updated
               Popup removed, features unlocked
```

### Key Architecture Decisions

1. **Single-domain architecture** — Everything runs on `polyhunter.ai` via Flask. Landing page at `/`, auth pages at `/register` and `/login`, app pages at `/dashboard`, `/analyzer`, `/markets`. One deploy, one server, shared cookies/sessions.
2. **Email code verification** — Supabase sends a 6-digit OTP code to the user's email during signup. No magic links, no separate email service needed for verification.
3. **Persistent upgrade popup** — Free users see a sticky upgrade prompt on EVERY page. Not a one-time dismissable modal — it stays until they pay.
4. **Saved login details** — After registration, the user can see their username/email on the login page (browser-saved credentials). The login page is a simple email + password form.

---

## 2. User Journey (Step-by-Step)

### Step 1: Ad Click → Landing Page

User sees a Meta/Google ad → clicks → lands on `https://polyhunter.ai`

**Landing page has:**
- Hero section with value proposition
- Feature showcase (Analyzer, Whale Tracking, etc.)
- Email capture form (prominent CTA)
- Social proof / results
- UTM params captured from ad URL

**Tracking:** `PageView` event fires via Stape

### Step 2: Email Capture

User enters email on landing page → submitted to backend:
- Saved to Supabase `email_leads` table (with UTM params)
- Synced to Klaviyo (triggers welcome flow)
- `Lead` event fired to Stape → Meta CAPI

**User sees:** "Check your email to create your account!"

### Step 3: Klaviyo Welcome Email

Klaviyo sends automated welcome email:
- Subject: "Your PolyHunter account is ready"
- CTA button links to: `https://polyhunter.ai/register?email={{ email|urlencode }}`
- `{{ email }}` is native Klaviyo personalization (always works, no dynamic tokens)
- Follow-up reminders at 24h and 72h if user hasn't registered

### Step 4: Registration Page (`/register`)

User lands on registration page. Based on the TrendIQ-style UX:

**Form fields:**
1. **Username** — "Choose a display name"
2. **Email** — pre-filled from `?email=` query param
3. **Password** — "Create a password"
4. **Send Code button** — triggers Supabase OTP to email
5. **Verification Code** — "Enter 6-digit code"
6. **Terms checkbox** — "I agree to Terms of Service and Privacy Policy"
7. **Marketing checkbox** — "I agree to receive marketing emails from PolyHunter"
8. **Create Account button**
9. **"or" divider**
10. **Sign up with Google** (Supabase OAuth)

**Flow:**
1. User fills username, email, password
2. Clicks "Send Code" → Supabase sends 6-digit OTP to email
3. User enters the code from their inbox
4. Clicks "Create Account"
5. Supabase verifies code + creates account
6. `profiles` row auto-created via DB trigger (username stored)
7. Backend matches email in `email_leads` → marks `converted_to_user = TRUE`
8. `CompleteRegistration` event fired to Stape → Meta CAPI
9. Klaviyo profile updated with "Registered" event (stops reminder emails)
10. Redirects to `/login`

### Step 5: Login Page (`/login`)

Simple login form:
- Email field
- Password field
- "Log In" button
- "Sign up with Google" option
- Link to register if no account

**Key:** Browser auto-fills saved credentials from registration (username/email visible). User just clicks login.

### Step 6: Dashboard with Persistent Upgrade Popup

User lands on `polyhunter.ai/dashboard` (auth required). **Every page** shows:

**Persistent upgrade popup/banner:**
- NOT dismissable (or re-appears on next page load)
- Shows on dashboard, analyzer, markets, whales, calculator — ALL pages
- Content: "Unlock Premium Features — Get unlimited AI analysis, real-time signals, and more"
- CTA: "Upgrade Now" button (styled prominently, e.g., orange/gradient)
- Optional: show pricing inline ($XX/month)

**The user CAN see the dashboard UI** behind/around the popup:
- Navigation works
- Page content is visible (blurred or partially obscured)
- This lets them see the value of what they're paying for (product-led conversion)

### Step 7: Stripe Checkout

User clicks "Upgrade Now" → `POST /api/stripe/create-checkout`:
- Creates Stripe Checkout Session
- Redirects to Stripe hosted checkout page
- `InitiateCheckout` event fired to Stape

User enters payment info on Stripe's secure page.

### Step 8: Payment Confirmed → Features Unlocked

Stripe processes payment → fires `checkout.session.completed` webhook:
1. Flask webhook handler receives it
2. Updates Supabase: `is_subscribed = true`, `status = 'active'`
3. `Purchase` event fired to Stape → Meta CAPI (with value)
4. User redirected to `/dashboard?session_id=xxx`
5. Dashboard checks subscription → popup removed, all features unlocked

---

## 3. Tech Stack & Roles

| Tool | Role | Why |
|------|------|-----|
| **Supabase** | Auth (email+password+OTP code, Google OAuth), user DB, subscription status, Row Level Security | Built-in OTP verification, free tier generous, Postgres DB |
| **Stripe** | Payment processing, subscription management, hosted checkout, customer portal | Industry standard, PCI compliant, handles billing lifecycle |
| **Klaviyo** | Email automation (welcome flow, nurture sequences, upgrade reminders) | Best-in-class email marketing, flow builder, good deliverability |
| **Stape** | Server-side ad tracking (Meta CAPI, Google Ads API) | Bypasses ad blockers, reliable attribution, iOS 14+ compliant |
| **Meta Ads** | Paid acquisition, lookalike audiences, retargeting | Primary ad channel, CAPI integration via Stape |
| **Flask (server.py)** | Backend API, webhook handler, subscription gating | Already running on EC2, minimal additions needed |

---

## 4. Supabase Auth: Signup with Email Code Verification

### How OTP Code Verification Works

Supabase supports **email OTP (One-Time Password)** natively. Instead of magic links, the user receives a 6-digit code.

### Registration Flow (Code)

```javascript
// 1. User clicks "Send Code" — request OTP
const { error } = await supabase.auth.signUp({
    email: emailInput.value,
    password: passwordInput.value,
    options: {
        data: {
            username: usernameInput.value,
            agreed_to_terms: termsCheckbox.checked,
            agreed_to_marketing: marketingCheckbox.checked
        }
    }
});
// Supabase sends 6-digit code to user's email

// 2. User enters the code — verify OTP
const { data, error } = await supabase.auth.verifyOtp({
    email: emailInput.value,
    token: codeInput.value,
    type: 'signup'
});

// 3. On success → redirect to login
if (data.user) {
    window.location.href = '/login';
}
```

### Supabase Dashboard Config

In Supabase Dashboard → Authentication → Settings:
- **Enable email confirmations**: ON
- **Enable email OTP**: ON (if available) or use the default confirmation flow
- **Confirm email template**: Customize to show 6-digit code
- **Redirect URL**: `https://polyhunter.ai/login`

### Google OAuth Setup

```javascript
// "Sign up with Google" button
async function signUpWithGoogle() {
    const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
            redirectTo: 'https://polyhunter.ai/dashboard'
        }
    });
}
```

In Supabase Dashboard → Authentication → Providers → Google:
- Add Google OAuth credentials (Client ID + Secret from Google Cloud Console)
- Set redirect URL: `https://polyhunter.ai/auth/callback`

### Login Flow

```javascript
// Simple email + password login
const { data, error } = await supabase.auth.signInWithPassword({
    email: emailInput.value,
    password: passwordInput.value
});

if (data.user) {
    window.location.href = '/dashboard';
}
```

---

## 5. Stripe Integration & Upgrade Paywall

### 5.1 Persistent Upgrade Popup (Frontend)

This popup renders on EVERY page for free users. It is NOT a one-time modal.

```javascript
// Runs on every page load (in base.html)
async function checkSubscriptionAndShowPopup() {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
        window.location.href = '/login';
        return;
    }

    const { data: profile } = await supabase
        .from('profiles')
        .select('is_subscribed, subscription_status, username')
        .eq('id', user.id)
        .single();

    if (!profile?.is_subscribed) {
        showUpgradePopup();
    }
}

function showUpgradePopup() {
    // Create persistent popup overlay
    const popup = document.createElement('div');
    popup.id = 'upgrade-popup';
    popup.innerHTML = `
        <div class="upgrade-popup-overlay">
            <div class="upgrade-popup-card">
                <h2>Unlock Premium Features</h2>
                <p>Get unlimited AI analysis, real-time signals, and more</p>
                <button class="upgrade-btn" onclick="startCheckout()">Upgrade Now</button>
            </div>
        </div>
    `;
    document.body.appendChild(popup);
}
```

**CSS for popup** — semi-transparent overlay, card centered, cannot be dismissed:

```css
.upgrade-popup-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
}

.upgrade-popup-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 32px;
    max-width: 420px;
    text-align: center;
}

.upgrade-btn {
    background: linear-gradient(135deg, #f97316, #ef4444);
    color: white;
    padding: 14px 32px;
    border: none;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
}
```

### 5.2 Stripe Checkout Session

```python
# server.py
import stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@app.route('/api/stripe/create-checkout', methods=['POST'])
def create_checkout():
    data = request.json
    user_id = data['user_id']
    email = data['email']

    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=['card'],
        line_items=[{
            'price': os.getenv('STRIPE_PRICE_ID'),
            'quantity': 1,
        }],
        mode='subscription',
        success_url='https://polyhunter.ai/dashboard?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://polyhunter.ai/dashboard',
        metadata={
            'supabase_user_id': user_id
        }
    )
    return jsonify({'checkout_url': session.url})
```

### 5.3 Webhook Handler

```python
from supabase import create_client

supabase_client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_ROLE_KEY')
)

STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return 'Invalid signature', 400

    # --- CHECKOUT COMPLETED ---
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        supabase_user_id = session['metadata']['supabase_user_id']
        stripe_customer_id = session['customer']
        stripe_subscription_id = session['subscription']

        supabase_client.table('subscriptions').upsert({
            'user_id': supabase_user_id,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'status': 'active',
            'plan': 'pro',
        }).execute()

        supabase_client.table('profiles').update({
            'is_subscribed': True,
            'subscription_status': 'active',
            'stripe_customer_id': stripe_customer_id
        }).eq('id', supabase_user_id).execute()

        # Fire purchase event to Stape
        track_event('Purchase',
            user_data={'email': session.get('customer_email', '')},
            custom_data={'value': 29.00, 'currency': 'USD'}
        )

    # --- SUBSCRIPTION UPDATED ---
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        stripe_sub_id = subscription['id']
        status = subscription['status']

        supabase_client.table('subscriptions').update({
            'status': status,
            'current_period_end': subscription['current_period_end']
        }).eq('stripe_subscription_id', stripe_sub_id).execute()

        is_active = status in ('active', 'trialing')
        result = supabase_client.table('subscriptions')\
            .select('user_id').eq('stripe_subscription_id', stripe_sub_id).execute()
        if result.data:
            supabase_client.table('profiles').update({
                'is_subscribed': is_active,
                'subscription_status': status
            }).eq('id', result.data[0]['user_id']).execute()

    # --- SUBSCRIPTION DELETED ---
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_sub_id = subscription['id']

        supabase_client.table('subscriptions').update({
            'status': 'canceled'
        }).eq('stripe_subscription_id', stripe_sub_id).execute()

        result = supabase_client.table('subscriptions')\
            .select('user_id').eq('stripe_subscription_id', stripe_sub_id).execute()
        if result.data:
            supabase_client.table('profiles').update({
                'is_subscribed': False,
                'subscription_status': 'canceled'
            }).eq('id', result.data[0]['user_id']).execute()

    # --- PAYMENT FAILED ---
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_sub_id = invoice.get('subscription')
        if stripe_sub_id:
            supabase_client.table('subscriptions').update({
                'status': 'past_due'
            }).eq('stripe_subscription_id', stripe_sub_id).execute()

    return jsonify({'received': True}), 200
```

### 5.4 Route Protection Decorator

```python
from functools import wraps

def require_subscription(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Not authenticated'}), 401

        token = auth_header.split(' ')[1]
        user = supabase_client.auth.get_user(token)
        if not user:
            return jsonify({'error': 'Invalid token'}), 401

        user_id = user.user.id
        result = supabase_client.table('profiles')\
            .select('is_subscribed').eq('id', user_id).single().execute()

        if not result.data or not result.data.get('is_subscribed'):
            return jsonify({'error': 'Subscription required', 'upgrade': True}), 403

        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated

# Usage:
@app.route('/api/analyze', methods=['POST'])
@require_subscription
def start_analysis():
    # ... existing analysis code
```

---

## 6. Database Schema

### Supabase Tables

```sql
-- profiles table (extends Supabase auth.users)
CREATE TABLE public.profiles (
    id UUID REFERENCES auth.users(id) PRIMARY KEY,
    email TEXT,
    username TEXT,
    is_subscribed BOOLEAN DEFAULT FALSE,
    subscription_status TEXT DEFAULT 'none',  -- none, active, past_due, canceled
    stripe_customer_id TEXT,
    agreed_to_terms BOOLEAN DEFAULT FALSE,
    agreed_to_marketing BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- subscriptions table (detailed Stripe data)
CREATE TABLE public.subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT UNIQUE,
    status TEXT DEFAULT 'inactive',  -- active, past_due, canceled, trialing
    plan TEXT DEFAULT 'free',        -- free, pro
    current_period_end BIGINT,       -- Unix timestamp from Stripe
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- email_leads table (landing page captures)
CREATE TABLE public.email_leads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    source TEXT,           -- 'meta_ad', 'google_ad', 'organic'
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    converted_to_user BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can read own subscription" ON public.subscriptions
    FOR SELECT USING (auth.uid() = user_id);
```

### Auto-create profile on signup (trigger):

```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, username, agreed_to_terms, agreed_to_marketing)
    VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data->>'username',
        COALESCE((NEW.raw_user_meta_data->>'agreed_to_terms')::boolean, false),
        COALESCE((NEW.raw_user_meta_data->>'agreed_to_marketing')::boolean, false)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

---

## 7. Klaviyo Email Flows

### Why No Dynamic Tokens

Klaviyo CANNOT generate dynamic verification links or tokens at send time. It only interpolates stored profile properties like `{{ email }}`.

**Solution:** Registration link is a static URL with email pre-filled:
```
https://polyhunter.ai/register?email={{ email|urlencode }}
```

Attribution is done by email matching (landing page email = registration email).

### Klaviyo Setup

1. Create Klaviyo account (free up to 250 contacts)
2. Create List: "PolyHunter Welcome"
3. Create Flow triggered by "Added to List: PolyHunter Welcome":
   - **Email 1 (Immediate):** Welcome + registration link
     - Subject: "Your PolyHunter account is ready"
     - CTA: `https://polyhunter.ai/register?email={{ email|urlencode }}`
   - **Email 2 (24h, if not registered):** Reminder + feature highlights
   - **Email 3 (72h, if not registered):** Last chance + urgency
4. Add flow filter on Emails 2 & 3: "Has NOT done Registered"

### Server: Sync Leads to Klaviyo

```python
KLAVIYO_API_KEY = os.getenv('KLAVIYO_PRIVATE_API_KEY')
KLAVIYO_WELCOME_LIST_ID = os.getenv('KLAVIYO_WELCOME_LIST_ID')

def sync_to_klaviyo(email, utm_data=None):
    headers = {
        'Authorization': f'Klaviyo-API-Key {KLAVIYO_API_KEY}',
        'Content-Type': 'application/json',
        'revision': '2024-10-15'
    }

    profile_payload = {
        'data': {
            'type': 'profile',
            'attributes': {
                'email': email,
                'properties': {
                    'utm_source': (utm_data or {}).get('utm_source', ''),
                    'utm_medium': (utm_data or {}).get('utm_medium', ''),
                    'utm_campaign': (utm_data or {}).get('utm_campaign', ''),
                    'lead_source': 'landing_page'
                }
            }
        }
    }
    try:
        resp = requests.post(
            'https://a.klaviyo.com/api/profiles/',
            headers=headers, json=profile_payload, timeout=5
        )
        profile_id = resp.json().get('data', {}).get('id')

        if profile_id and KLAVIYO_WELCOME_LIST_ID:
            list_payload = {
                'data': [{'type': 'profile', 'id': profile_id}]
            }
            requests.post(
                f'https://a.klaviyo.com/api/lists/{KLAVIYO_WELCOME_LIST_ID}/relationships/profiles/',
                headers=headers, json=list_payload, timeout=5
            )
    except Exception as e:
        print(f"Klaviyo sync error: {e}")

def update_klaviyo_registered(email):
    """Fire 'Registered' event to stop reminder emails"""
    headers = {
        'Authorization': f'Klaviyo-API-Key {KLAVIYO_API_KEY}',
        'Content-Type': 'application/json',
        'revision': '2024-10-15'
    }
    event_payload = {
        'data': {
            'type': 'event',
            'attributes': {
                'metric': {'data': {'type': 'metric', 'attributes': {'name': 'Registered'}}},
                'profile': {'data': {'type': 'profile', 'attributes': {'email': email}}},
                'properties': {}
            }
        }
    }
    try:
        requests.post('https://a.klaviyo.com/api/events/', headers=headers, json=event_payload, timeout=5)
    except Exception:
        pass
```

### Landing Page Email Capture Endpoint

```python
@app.route('/api/capture-email', methods=['POST'])
def capture_email():
    email = request.json.get('email')
    utm = request.json.get('utm', {})

    # Save to Supabase
    supabase_client.table('email_leads').upsert({
        'email': email,
        'source': utm.get('utm_source', 'direct'),
        'utm_source': utm.get('utm_source'),
        'utm_medium': utm.get('utm_medium'),
        'utm_campaign': utm.get('utm_campaign'),
    }).execute()

    # Sync to Klaviyo (triggers welcome email)
    sync_to_klaviyo(email, utm)

    # Track Lead event via Stape
    track_event('Lead', user_data={'email': email})

    return jsonify({'success': True})
```

---

## 8. Stape Server-Side Tracking

### Architecture

```
User Browser                    Flask Server              Stape (sGTM)
    |                               |                         |
    |-- Lands on page ------------->|                         |
    |                               |-- PageView ------------>|-- Meta CAPI
    |                               |                         |-- Google Ads
    |-- Submits email ------------->|                         |
    |                               |-- Lead ----------------->|-- Meta: Lead
    |-- Registers ----------------->|                         |
    |                               |-- CompleteRegistration ->|-- Meta: CompleteRegistration
    |-- Clicks Upgrade ------------>|                         |
    |                               |-- InitiateCheckout ----->|-- Meta: InitiateCheckout
    |-- Pays (Stripe webhook) ----->|                         |
    |                               |-- Purchase ------------->|-- Meta: Purchase ($value)
```

### Conversion Events

| Event | Trigger | Value |
|-------|---------|-------|
| `PageView` | Landing page load | — |
| `Lead` | Email captured on landing page | — |
| `CompleteRegistration` | User verifies code + account created | — |
| `InitiateCheckout` | User clicks "Upgrade Now" | — |
| `Purchase` | Stripe webhook confirms payment | Subscription price |

### Server-Side Event Firing

```python
STAPE_ENDPOINT = os.getenv('STAPE_ENDPOINT')

def track_event(event_name, user_data=None, custom_data=None):
    payload = {
        'event_name': event_name,
        'user_data': user_data or {},
        'custom_data': custom_data or {},
    }
    try:
        requests.post(STAPE_ENDPOINT, json=payload, timeout=3)
    except Exception:
        pass  # Never block on tracking failures
```

### Stape Setup

1. Create account at stape.io
2. Set up sGTM container (Stape hosts it)
3. Configure tags in sGTM:
   - **Meta Conversions API tag** (Pixel ID + Access Token)
   - **Google Ads Conversion tag** (Conversion ID + Label)
4. Set sGTM endpoint URL as `STAPE_ENDPOINT` env variable

---

## 9. Meta Ads Integration

### Campaign Structure

```
Campaign: PolyHunter Launch
├── Ad Set: Crypto Traders (Interest targeting)
│   ├── Ad 1: "AI-Powered Prediction Market Analysis"
│   └── Ad 2: "Whale Tracking + Kelly Sizing"
├── Ad Set: Polymarket Users (Lookalike)
│   └── Ad 1: "Get an Edge on Polymarket"
└── Ad Set: Retargeting (Website visitors)
    └── Ad 1: "Complete Your PolyHunter Setup"
```

### Conversion Optimization

- **Top of funnel:** Optimize for `Lead` (email capture)
- **Mid funnel:** Optimize for `CompleteRegistration`
- **Bottom funnel:** Optimize for `Purchase` (once enough data)

### UTM Parameter Structure

```
https://polyhunter.ai/?utm_source=meta&utm_medium=cpc&utm_campaign=launch_crypto&utm_content=whale_tracking_v1
```

### Meta CAPI via Stape

All events fire server-side through Stape → Meta Conversions API:
- Bypasses ad blockers
- iOS 14+ compliant
- Better attribution and match rates
- Required for optimal ad delivery

---

## 10. Implementation Roadmap

### Phase 1: Domain & Infrastructure (Day 1)
- [ ] Configure DNS: `polyhunter.ai` → EC2 IP
- [ ] SSL certificate for `polyhunter.ai`
- [ ] Nginx config: proxy all routes to Flask on EC2
- [ ] Set up Supabase project

### Phase 2: Auth System (Days 2-3)
- [ ] Create Supabase tables (profiles, subscriptions, email_leads)
- [ ] Create DB trigger for auto-profile creation (with username)
- [ ] Enable Row Level Security policies
- [ ] Build `/register` page (username, email, password, send code, verify code, terms)
- [ ] Build `/login` page (email + password)
- [ ] Implement Supabase OTP email verification
- [ ] Set up Google OAuth in Supabase
- [ ] Add Supabase JS SDK to frontend
- [ ] Add auth state checking to all pages

### Phase 3: Stripe & Paywall (Days 4-5)
- [ ] Create Stripe account, product, and price
- [ ] Add `stripe` + `supabase` Python packages to requirements.txt
- [ ] Build `/api/stripe/create-checkout` route
- [ ] Build `/api/stripe/webhook` route
- [ ] Build persistent upgrade popup component (shows on every page for free users)
- [ ] Add `@require_subscription` decorator to protected API routes
- [ ] Test webhook locally: `stripe listen --forward-to localhost:5050/api/stripe/webhook`

### Phase 4: Landing Page & Klaviyo (Days 6-8)
- [ ] Design and build landing page at `polyhunter.ai/` (Flask route)
- [ ] Build `/api/capture-email` endpoint
- [ ] Set up Klaviyo account, create Welcome list, get API key
- [ ] Create Klaviyo welcome flow (3 emails, static registration link)
- [ ] Add "Has NOT done Registered" filter on reminder emails
- [ ] Implement `sync_to_klaviyo()` and `update_klaviyo_registered()`
- [ ] Test: landing page → Klaviyo email → register → login → upgrade popup

### Phase 5: Stape + Meta Ads (Day 9)
- [ ] Set up Stape account & sGTM container
- [ ] Configure Meta CAPI tag in sGTM
- [ ] Configure Google Ads conversion tag
- [ ] Add `track_event()` calls at every funnel step
- [ ] Verify events in Meta Events Manager
- [ ] Set up Meta ad campaigns with proper UTM params
- [ ] Configure conversion optimization (Lead → CompleteRegistration → Purchase)

### Phase 6: Deploy & End-to-End Test (Day 10)
- [ ] Add all env vars to EC2 (see Section 11)
- [ ] Deploy to production
- [ ] Register Stripe webhook URL (production)
- [ ] Full E2E test: Meta ad → landing → email → Klaviyo → register (code verify) → login → dashboard → upgrade popup → Stripe pay → features unlocked
- [ ] Verify all Stape tracking events fire correctly
- [ ] Verify Klaviyo flow stops after registration
- [ ] Verify subscription gating works on all protected routes

---

## 11. Environment Variables

Add to EC2 `.env` file:

```bash
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

# Stripe
STRIPE_SECRET_KEY=sk_live_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
STRIPE_PRICE_ID=price_xxxxx

# Klaviyo
KLAVIYO_PRIVATE_API_KEY=pk_xxxxx
KLAVIYO_WELCOME_LIST_ID=xxxxx

# Stape
STAPE_ENDPOINT=https://xxxxx.stape.io/data

# App URL (single domain — Flask serves everything)
APP_URL=https://polyhunter.ai
```

---

## Summary

```
Meta Ad → polyhunter.ai/ (landing, email capture)
    → Klaviyo welcome email (static link, no tokens)
    → polyhunter.ai/register (username + email + password + 6-digit code)
    → polyhunter.ai/login (saved credentials)
    → polyhunter.ai/dashboard (persistent upgrade popup on ALL pages)
    → polyhunter.ai/analyzer, /markets (auth required, popup until paid)
    → Stripe Checkout → Payment
    → Webhook → Supabase updated → Popup gone, features unlocked
```

**Key differences from previous version:**
1. **Single-domain architecture** — `polyhunter.ai` serves everything (landing at `/`, app at `/dashboard`, `/analyzer`, `/markets`)
2. **Email OTP code verification** — 6-digit code sent to email during signup (not magic links)
3. **Username field** — collected at registration, stored in profiles
4. **Persistent upgrade popup** — shown on every page, not dismissable, until user pays
5. **Terms + Marketing checkboxes** — GDPR-friendly, stored in profiles table
6. **Google OAuth** — alternative signup method via Supabase
7. **Branding** — all references updated from PolySnap to PolyHunter
8. **All URLs** — single domain `polyhunter.ai` with route-based separation

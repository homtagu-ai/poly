# Stripe Setup Guide — PolyHunter

> Standalone guide for integrating Stripe payments. Do this AFTER auth, landing page, and Supabase are working. Everything else in the app functions without Stripe.

---

## 1. Create Stripe Account & Product

### 1.1 Sign Up

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com) → Create account
2. Complete business verification (can use test mode while pending)
3. Note: You start in **Test Mode** by default (toggle in top-right of dashboard)

### 1.2 Create Product + Price

In Stripe Dashboard → **Products** → **Add Product**:

| Field | Value |
|-------|-------|
| Name | PolyHunter Pro |
| Description | Unlimited AI analysis, real-time signals, whale tracking |
| Pricing model | Standard pricing |
| Price | $29.00 / month (or your chosen price) |
| Billing period | Monthly |
| Currency | USD |

After creating, copy the **Price ID** (starts with `price_`). You'll need it.

### 1.3 Get API Keys

Stripe Dashboard → **Developers** → **API Keys**:

| Key | What It Is | Where It Goes |
|-----|------------|---------------|
| Publishable key (`pk_test_...`) | Frontend — NOT needed for server-side checkout | Not used (we use Stripe hosted checkout) |
| Secret key (`sk_test_...`) | Backend — creates checkout sessions | `.env` as `STRIPE_SECRET_KEY` |

---

## 2. Install Dependencies

On your local machine and EC2:

```bash
pip install stripe
```

Add to `requirements.txt`:
```
stripe>=7.0.0
```

---

## 3. Backend Code

### 3.1 Add to `server.py` — Imports & Config

```python
import stripe

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
```

### 3.2 Create Checkout Session Route

```python
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

### 3.3 Webhook Handler

```python
from supabase import create_client

supabase_client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_ROLE_KEY')
)

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

        # Create subscription record
        supabase_client.table('subscriptions').upsert({
            'user_id': supabase_user_id,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'status': 'active',
            'plan': 'pro',
        }).execute()

        # Update profile — removes upgrade popup
        supabase_client.table('profiles').update({
            'is_subscribed': True,
            'subscription_status': 'active',
            'stripe_customer_id': stripe_customer_id
        }).eq('id', supabase_user_id).execute()

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
        result = supabase_client.table('subscriptions') \
            .select('user_id').eq('stripe_subscription_id', stripe_sub_id).execute()
        if result.data:
            supabase_client.table('profiles').update({
                'is_subscribed': is_active,
                'subscription_status': status
            }).eq('id', result.data[0]['user_id']).execute()

    # --- SUBSCRIPTION DELETED (canceled) ---
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_sub_id = subscription['id']

        supabase_client.table('subscriptions').update({
            'status': 'canceled'
        }).eq('stripe_subscription_id', stripe_sub_id).execute()

        result = supabase_client.table('subscriptions') \
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

### 3.4 Frontend — Upgrade Button

In the upgrade popup (runs on every page for free users):

```javascript
async function startCheckout() {
    const { data: { user } } = await supabase.auth.getUser();

    const response = await fetch('/api/stripe/create-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: user.id,
            email: user.email
        })
    });

    const { checkout_url } = await response.json();
    window.location.href = checkout_url;  // Redirect to Stripe hosted checkout
}
```

---

## 4. Register Webhook in Stripe

### For Local Testing

Install Stripe CLI:
```bash
# macOS
brew install stripe/stripe-cli/stripe

# Windows (download from https://stripe.com/docs/stripe-cli)
```

Forward webhooks to your local server:
```bash
stripe login
stripe listen --forward-to localhost:5050/api/stripe/webhook
```

This prints a webhook signing secret (`whsec_...`). Add it to `.env`:
```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
```

### For Production

1. Stripe Dashboard → **Developers** → **Webhooks** → **Add endpoint**
2. Endpoint URL: `https://polyhunter.ai/api/stripe/webhook`
3. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the webhook signing secret → add to EC2 `.env` as `STRIPE_WEBHOOK_SECRET`

---

## 5. Environment Variables

Add these to your `.env` file (both local and EC2):

```bash
# Stripe
STRIPE_SECRET_KEY=sk_test_xxxxx          # From Stripe Dashboard → API Keys
STRIPE_WEBHOOK_SECRET=whsec_xxxxx        # From webhook setup (local or production)
STRIPE_PRICE_ID=price_xxxxx              # From the product you created
```

---

## 6. Testing Checklist

### With Stripe CLI (Local)

```bash
# Terminal 1: Run your Flask app
python -m polyscalping.server

# Terminal 2: Forward Stripe webhooks
stripe listen --forward-to localhost:5050/api/stripe/webhook

# Terminal 3: Trigger a test event
stripe trigger checkout.session.completed
```

### Manual Testing

1. Log in as a free user (should see upgrade popup)
2. Click "Upgrade Now"
3. Should redirect to Stripe Checkout page
4. Use test card: `4242 4242 4242 4242` (any future expiry, any CVC)
5. Complete payment
6. Should redirect back to `/dashboard?session_id=...`
7. Webhook fires → Supabase updated → popup should disappear
8. Refresh page → confirm popup is still gone

### Test Card Numbers

| Card | Result |
|------|--------|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 3220` | Requires 3D Secure auth |
| `4000 0000 0000 9995` | Declined (insufficient funds) |
| `4000 0000 0000 0341` | Attaches but fails on charge |

Use any future date for expiry and any 3-digit CVC.

---

## 7. Going Live

When you're ready for real payments:

1. Complete Stripe business verification
2. Toggle to **Live Mode** in Stripe Dashboard
3. Create the same product/price in Live Mode (or copy from test)
4. Replace `.env` values:
   - `STRIPE_SECRET_KEY` → `sk_live_xxxxx`
   - `STRIPE_PRICE_ID` → `price_xxxxx` (live mode price)
   - `STRIPE_WEBHOOK_SECRET` → new webhook secret for production endpoint
5. Register production webhook URL: `https://polyhunter.ai/api/stripe/webhook`
6. Deploy to EC2
7. Test with a real card (you can refund immediately)

---

## Summary: What Stripe Plugs Into

```
User clicks "Upgrade Now" (popup on every page)
    → POST /api/stripe/create-checkout
    → Redirect to Stripe hosted checkout
    → User pays
    → Stripe fires webhook → POST /api/stripe/webhook
    → Handler updates Supabase: is_subscribed = TRUE
    → User redirected to /dashboard
    → Popup check: is_subscribed? YES → no popup
    → Features fully unlocked
```

**Total code additions:** ~100 lines in `server.py` (2 routes + 1 import). Everything else is Stripe Dashboard configuration.

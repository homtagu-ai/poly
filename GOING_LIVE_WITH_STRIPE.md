# Going Live with Stripe — PolyHunter

> Follow this guide when you're ready to switch from "all users = paid (testing)" to real Stripe payments. Currently every new signup gets `is_subscribed = TRUE` automatically. This guide flips that off and connects Stripe so only paying users get access.

---

## Step 1: Update Supabase DB Trigger (1 minute)

Go to **Supabase Dashboard** → **SQL Editor** → paste and run:

```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, username, is_subscribed, subscription_status)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)),
        FALSE,          -- PRODUCTION: new users are NOT paid
        'none'          -- PRODUCTION: no subscription
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

That's it for Supabase. New signups will now see the upgrade popup on every page.

> **Note:** Existing test users who already have `is_subscribed = TRUE` will keep their access. To reset them, run:
> ```sql
> UPDATE public.profiles SET is_subscribed = FALSE, subscription_status = 'none';
> ```

---

## Step 2: Create Stripe Account & Product (10 minutes)

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com) and create an account
2. You start in **Test Mode** by default (toggle in top-right)
3. Go to **Products** → **Add Product**:
   - Name: `PolyHunter Pro`
   - Price: `$29.00 / month` (or your price)
   - Billing period: Monthly
4. Copy the **Price ID** (starts with `price_`)
5. Go to **Developers** → **API Keys** → copy the **Secret key** (`sk_test_...`)

---

## Step 3: Add Stripe env vars to `.env` (1 minute)

Add these 3 lines to your `.env` file (both local and on EC2):

```bash
STRIPE_SECRET_KEY=sk_test_xxxxx
STRIPE_PRICE_ID=price_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx    # You'll get this in Step 5
```

---

## Step 4: Install stripe package (1 minute)

```bash
pip install stripe
```

Also add `stripe>=7.0.0` to `requirements.txt`.

On EC2:
```bash
ssh -i your-key.pem ubuntu@44.207.97.34
cd /home/ubuntu/poly
pip install stripe
```

---

## Step 5: Add Stripe routes to server.py

Add these to `server.py`. There are 2 routes + 1 import to add:

### 5.1 — At the top of server.py, add imports:

```python
import stripe
from supabase import create_client

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

supabase_client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_ROLE_KEY')
)
```

### 5.2 — Add checkout route:

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

### 5.3 — Add webhook route:

```python
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

    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_sub_id = invoice.get('subscription')
        if stripe_sub_id:
            supabase_client.table('subscriptions').update({
                'status': 'past_due'
            }).eq('stripe_subscription_id', stripe_sub_id).execute()

    return jsonify({'received': True}), 200
```

---

## Step 6: Update the upgrade popup in base.html

The `startCheckout()` function in `base.html` currently shows a placeholder alert. Replace it with the real Stripe redirect:

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
    window.location.href = checkout_url;
}
```

---

## Step 7: Register Stripe Webhook (5 minutes)

### For local testing first:

```bash
# Install Stripe CLI: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:5050/api/stripe/webhook
```

Copy the `whsec_...` secret it prints → put in `.env` as `STRIPE_WEBHOOK_SECRET`.

### For production:

1. Stripe Dashboard → **Developers** → **Webhooks** → **Add endpoint**
2. URL: `https://polyhunter.ai/api/stripe/webhook`
3. Select these events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the signing secret → add to EC2 `.env` as `STRIPE_WEBHOOK_SECRET`

---

## Step 8: Deploy to EC2

```bash
# Push code
git add -A && git commit -m "Add Stripe integration" && git push origin main

# Deploy
ssh -i your-key.pem ubuntu@44.207.97.34
cd /home/ubuntu/poly
git pull origin main
pip install stripe
sudo systemctl restart polysnap
```

Also update the `.env` on EC2 with the 3 Stripe vars.

---

## Step 9: Test the Full Flow

1. Register a new account → should see upgrade popup on dashboard
2. Click "Upgrade Now" → redirected to Stripe Checkout
3. Use test card: `4242 4242 4242 4242` (any future date, any CVC)
4. Complete payment → redirected back to dashboard
5. Popup should disappear (webhook updated Supabase)
6. Refresh page → popup still gone

### Other test cards:

| Card | Result |
|------|--------|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 3220` | Requires 3D Secure |
| `4000 0000 0000 9995` | Declined |

---

## Step 10: Go Live (Real Payments)

When testing is done and you want real money:

1. Complete Stripe business verification
2. Toggle to **Live Mode** in Stripe Dashboard (top-right toggle)
3. Create the same product/price in Live Mode
4. Update EC2 `.env`:
   - `STRIPE_SECRET_KEY` → `sk_live_xxxxx`
   - `STRIPE_PRICE_ID` → live mode `price_xxxxx`
   - `STRIPE_WEBHOOK_SECRET` → new secret from live webhook endpoint
5. Register production webhook: `https://polyhunter.ai/api/stripe/webhook`
6. Restart: `sudo systemctl restart polysnap`
7. Test with a real card (refund immediately after)

---

## Quick Summary

```
TESTING MODE (current):
  New user signs up → is_subscribed = TRUE → no popup → full access

PRODUCTION MODE (after this guide):
  New user signs up → is_subscribed = FALSE → sees upgrade popup
  User clicks "Upgrade Now" → Stripe Checkout → pays $29/mo
  Stripe webhook fires → updates Supabase → is_subscribed = TRUE
  Popup disappears → full access unlocked
```

**Total changes to go live:**
1. One SQL query in Supabase (change TRUE → FALSE in trigger)
2. Three env vars added to `.env`
3. `pip install stripe`
4. ~100 lines added to `server.py` (2 routes)
5. One function updated in `base.html` (startCheckout)
6. Register webhook in Stripe Dashboard

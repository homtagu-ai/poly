# PolyHunter (poly-hunter.com) — Deployment Guide for Hosting Ukraine

## Your Hosting Details (from panel)

| Setting | Value |
|---------|-------|
| **Domain** | www.poly-hunter.com |
| **Account** | te605656 |
| **Service Address** | 3375654.te605656.web.hosting-test.net |
| **IPv4** | 185.68.16.118 |
| **IPv6** | 2a00:7a60:0:1076::1 |
| **Assigned Local IP** | **127.1.7.92** |
| **Assigned Port** | **3000** |
| **Root Directory** | /home/te605656/poly-hunter.com/www/ |

---

## Architecture

```
User (poly-hunter.com)
    ↓
Hosting Proxy (80/443 + SSL)
    ↓
127.1.7.92:3000
    ↓
Flask App (polyscalping/server.py)
    ↓
External APIs (Polymarket, Supabase, Anthropic, etc.)
```

No Nginx, no Gunicorn, no systemd needed — the hosting handles proxying, SSL, and process supervision.

---

## CRITICAL: Change Web Server Mode First

Your panel currently shows **Node.js** selected. You MUST switch to **"Проксування трафіку (налаштування)"** because your app is Python/Flask, not Node.js.

1. Go to **Налаштування сайту** → **Основні налаштування**
2. Under **Веб-сервер**, select **"Проксування трафіку (налаштування)"**
3. Set **Проксування трафіку** to **"За IP-адресою"**
4. Leave **Кореневий каталог** empty (use default `/home/te605656/poly-hunter.com/www/`)
5. Set **Переадресація HTTPS** to **"Переадресовувати запити з HTTP на HTTPS"**
6. **Save changes**

---

## Step-by-Step Deployment

### Step 1: Set Python Version

1. Go to **Конфігурація Linux** in the hosting panel
2. Set Python to **3.10**
3. Save

### Step 2: Upload Project Files

Upload via **Файл-менеджер** or **SFTP/SSH** to `/home/te605656/poly-hunter.com/www/`:

```
/home/te605656/poly-hunter.com/www/
├── polyscalping/
│   ├── __init__.py
│   ├── server.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── landing.html
│   │   ├── register.html
│   │   ├── login.html
│   │   ├── forgot-password.html
│   │   ├── dashboard.html
│   │   ├── markets.html
│   │   ├── whales.html
│   │   ├── analyzer.html
│   │   ├── calculator.html
│   │   └── settings.html
│   └── static/
│       └── images/
│           ├── polyhunter-logo.png
│           ├── mascot.png
│           ├── mascot-alt.png
│           ├── analyzer-icon.png
│           └── atom-loader.png
├── requirements.txt
├── .env
└── start.sh
```

### Files to EXCLUDE from upload:
- `deploy/` (entire folder — EC2-specific)
- `venv/` , `__pycache__/`
- `.git/` , `.claude/`
- `*.md` files (docs only)
- `index.html` (standalone, not needed)
- `flask_output.log`, `result.json`
- Root-level `*.png` screenshots
- `GOING_LIVE_WITH_STRIPE.md`, `STRIPE_SETUP.md`, etc.

### Step 3: SSH & Create Virtual Environment

```bash
ssh te605656@your-server-address
cd /home/te605656/poly-hunter.com/www/

# Create venv
python3.10 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies (all at once)
pip install -r requirements.txt

# If memory fails, install in batches:
pip install flask flask-cors python-dotenv
pip install requests httpx aiohttp
pip install pytz python-slugify python-dateutil
pip install numpy scipy pandas
pip install yfinance
pip install web3 eth-account
pip install openai anthropic

deactivate
```

### Step 4: Verify .env on Server

The `.env` file should already contain (uploaded in Step 2):

```env
HOST=127.1.7.92
PORT=3000
DEBUG=false
ENVIRONMENT=production

# Your API keys (already in the file)
ANTHROPIC_API_KEY=sk-ant-...
POLYGONSCAN_API_KEY=...
ETHERSCAN_API_KEY=...
THE_ODDS_API_KEY=...
OPENROUTER_API_KEY=...
SUPABASE_URL=https://lstxuhtxwhwiveawlhip.supabase.co
SUPABASE_ANON_KEY=eyJ...
ALLOWED_ORIGINS=https://poly-hunter.com,https://www.poly-hunter.com
```

### Step 5: Make start.sh Executable

```bash
chmod +x /home/te605656/poly-hunter.com/www/start.sh
```

### Step 6: Configure Startup Command in Panel

Go to **Налаштування веб-застосунку** and set the **Команда для запуску**:

```
source .venv/bin/activate && python3.10 polyscalping/server.py
```

The panel should show the launch parameters:
- `--port=3000`
- `--host=127.1.7.92`

These are passed via `process.env.PORT` and `process.env.HOST` which our `server.py` now reads.

### Step 7: Start & Verify

1. Click **Запустити** (or **Перезапустити** if already running)
2. Status should show **"Запущено"** (green badge)
3. **Команда для запуску** should show **"Присутня"** (green badge)
4. Visit https://poly-hunter.com
5. Check **Логи помилок сайту** if something is wrong

---

## SSL Setup

1. Go to **Налаштування SSL** in the panel
2. Enable **Let's Encrypt** free certificate
3. After SSL is active, enable **HTTP → HTTPS redirect**:
   - In **Основні налаштування** → **Переадресація HTTPS**
   - Select **"Переадресовувати запити з HTTP на HTTPS"**

---

## Code Changes Already Made

### server.py (line 1695-1708)
```python
# BEFORE (EC2):
app.run(host="0.0.0.0", port=port, debug=debug)

# AFTER (Hosting Ukraine):
host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", 5050))
app.run(host=host, port=port, debug=debug)
```

### .env
```env
# ADDED:
HOST=127.1.7.92
PORT=3000
DEBUG=false
ENVIRONMENT=production
ALLOWED_ORIGINS=https://poly-hunter.com,https://www.poly-hunter.com
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| **502 Bad Gateway** | App not running on 127.1.7.92:3000 | Check HOST/PORT in .env match panel values |
| **Exit Code 9** | Wrong host/port binding | Verify .env has `HOST=127.1.7.92` `PORT=3000` |
| **ModuleNotFoundError** | venv not activated | Ensure startup command starts with `source .venv/bin/activate &&` |
| **Static files 404** | Wrong folder structure | Verify `polyscalping/static/` exists with images |
| **CORS errors** | Origins mismatch | Update `ALLOWED_ORIGINS` in .env |
| **pip install fails** | Memory limit | Install packages in batches (see Step 3) |
| **Site shows Node.js default** | Wrong web server mode | Switch from Node.js to "Проксування трафіку" |

### Check Logs
- **Panel:** Логи помилок сайту
- **SSH:** `cat ~/.system/nodejs/logs/poly-hunter.com.log` (path may vary for proxy mode)

---

## Updating the App

1. Upload changed files via SFTP/SSH to `/home/te605656/poly-hunter.com/www/`
2. Click **Перезапустити** in the web application panel
3. Verify site loads

---

## Key Differences: EC2 vs Hosting Ukraine

| Aspect | EC2 (old) | Hosting Ukraine (new) |
|--------|-----------|----------------------|
| Process Manager | systemd + Gunicorn | Built-in supervisor |
| Reverse Proxy | Nginx | Built-in proxy |
| SSL | Manual Let's Encrypt | Panel toggle |
| Bind Address | 127.0.0.1:5050 | 127.1.7.92:3000 |
| Workers | Gunicorn 2 workers | Single Flask process |
| Static Files | Nginx direct | Flask serves |
| Deploy | git pull + systemctl | SFTP + panel restart |
| Logs | Custom file path | Panel viewer |

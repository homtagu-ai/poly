# Gunicorn configuration for PolyHunter
# Adapts to hosting environment via PORT env var

import os

# Ukrainian hosting proxy expects port 3000; fall back to 5050 for local dev
_port = os.getenv("PORT", "3000")
_bind_ip = os.getenv("BIND_IP", "127.0.0.1")
bind = f"{_bind_ip}:{_port}"

workers = 2
worker_class = "sync"
timeout = 120
keepalive = 5

# Logging — detect hosting paths
_home = os.path.expanduser("~")
_app_dir = os.getenv("APP_DIR", os.path.join(_home, "poly-hunter.com", "www"))
_log_dir = os.path.join(_app_dir, "logs")
os.makedirs(_log_dir, exist_ok=True)

accesslog = os.path.join(_log_dir, "gunicorn-access.log")
errorlog = os.path.join(_log_dir, "gunicorn-error.log")
loglevel = "info"

# Restart workers after this many requests (prevents memory leaks)
max_requests = 500
max_requests_jitter = 50

# Graceful restart timeout
graceful_timeout = 30

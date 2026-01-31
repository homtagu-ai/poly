# Gunicorn configuration for PolySnap on t3.micro (1GB RAM)

bind = "127.0.0.1:5050"
workers = 2
worker_class = "sync"
timeout = 120
keepalive = 5

# Logging
accesslog = "/home/ubuntu/poly/logs/gunicorn-access.log"
errorlog = "/home/ubuntu/poly/logs/gunicorn-error.log"
loglevel = "info"

# Restart workers after this many requests (prevents memory leaks)
max_requests = 500
max_requests_jitter = 50

# Graceful restart timeout
graceful_timeout = 30

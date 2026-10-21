bind = "0.0.0.0:8000"
# Keep the in-memory login limiter in one process.
workers = 1
worker_class = "gthread"
threads = 4
timeout = 60
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = ""

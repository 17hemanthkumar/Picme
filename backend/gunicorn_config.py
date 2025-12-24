"""
Gunicorn configuration file for production deployment.

This configuration provides:
- Appropriate number of workers for handling concurrent requests
- Timeout for long-running face recognition operations
- Logging to stdout for container log aggregation
- Graceful shutdown handling
"""

import os
import multiprocessing

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
# Use 2-4 workers for better performance
# Can be overridden with GUNICORN_WORKERS environment variable
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
worker_class = 'sync'
worker_connections = 1000
timeout = 120  # 120 seconds (2 minutes) - reduced from 300 for faster timeouts
keepalive = 2  # Reduced from 5 for faster connection recycling

# Graceful shutdown
graceful_timeout = 30
max_requests = 1000  # Restart workers after 1000 requests to prevent memory leaks
max_requests_jitter = 50  # Add randomness to prevent all workers restarting at once

# Logging
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stdout
loglevel = 'warning'  # Changed from 'info' to 'warning' for better performance
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'picme-gunicorn'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed in future)
# keyfile = None
# certfile = None


def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting PicMe application server")


def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading PicMe application server")


def when_ready(server):
    """Called just after the server is started."""
    server.log.info("PicMe application server is ready. Listening on: %s", bind)


def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down PicMe application server")


def worker_int(worker):
    """Called when a worker receives the SIGINT or SIGQUIT signal."""
    worker.log.info("Worker received INT or QUIT signal")


def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")

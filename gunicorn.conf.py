"""Gunicorn configuration for IT Asset Manager."""
bind = "127.0.0.1:5000"
workers = 3
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"

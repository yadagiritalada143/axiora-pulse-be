"""
app/core/limiter.py
────────────────────────────────────────────────────────────────────────────────
Global slowapi limiter instance to prevent circular imports between routers and main.py.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

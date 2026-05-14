"""API response cache — in-process SimpleCache via Flask-Caching."""
import hashlib
import json

from flask import request
from flask_caching import Cache

cache = Cache(config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 30,
    'CACHE_THRESHOLD': 256,
})


def make_cache_key():
    """Cache key from request path + sorted JSON body hash."""
    data = request.get_json(silent=True) or {}
    body = json.dumps(data, sort_keys=True)
    body_hash = hashlib.md5(body.encode()).hexdigest()
    return f"{request.path}:{body_hash}"

# -*- coding: utf-8 -*-
"""HTTP transport for the Lemmy API client."""

import copy
import hashlib
import json
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

from .errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    InvalidResponseError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)

try:
    from ..__version__ import __version__
except ImportError:  # pragma: no cover - only when running a module directly
    __version__ = 'unknown'

DEFAULT_USER_AGENT = 'tuil/{}'.format(__version__)
DEFAULT_TIMEOUT = 10.0
DEFAULT_CACHE_TTL = 300
MAX_CACHE_ENTRIES = 256


def normalize_instance(instance):
    """Return an instance URL such as ``https://lemmy.ml``.

    Accepts a bare hostname, a URL with a trailing slash and URLs that already
    include an API path.
    """

    if not instance or not str(instance).strip():
        raise ValueError('A Lemmy instance is required')

    value = str(instance).strip()
    if '://' not in value:
        value = 'https://' + value

    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https'):
        raise ValueError('Unsupported URL scheme: {!r}'.format(parts.scheme))
    if not parts.netloc:
        raise ValueError('Invalid Lemmy instance: {!r}'.format(instance))

    path = parts.path.rstrip('/')
    for suffix in ('/api/v3', '/api/v4'):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break

    return '{}://{}{}'.format(parts.scheme, parts.netloc, path)


def _prepare_params(params):
    if not params:
        return {}
    prepared = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            prepared[key] = 'true' if value else 'false'
        else:
            prepared[key] = value
    return prepared


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class LemmyHTTP(object):
    """Thin JSON/HTTP layer with JWT auth, retries and a small GET cache."""

    def __init__(self, instance, *, token=None, api_version=3,
                 timeout=DEFAULT_TIMEOUT, max_retries=2,
                 cache_ttl=DEFAULT_CACHE_TTL, user_agent=None,
                 session=None, verify=True):
        self.instance = normalize_instance(instance)
        self.api_version = int(api_version)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.cache_ttl = max(0, cache_ttl or 0)
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.verify = verify
        self._token = token
        self._cache = OrderedDict()
        self._owns_session = session is None
        self.session = session or requests.Session()

    def url_for(self, api_version=None):
        version = self.api_version if api_version is None else api_version
        return '{}/api/v{}'.format(self.instance, version)

    @property
    def api_url(self):
        return self.url_for()

    @property
    def token(self):
        return self._token

    def set_token(self, token):
        if token != self._token:
            self._token = token
            self.clear_cache()

    def clear_token(self):
        self.set_token(None)

    def clear_cache(self):
        self._cache.clear()

    def close(self):
        if self._owns_session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def get(self, path, params=None, *, cache=True, api_version=None):
        return self.request(
            'GET', path, params=params, cache=cache,
            api_version=api_version)

    def post(self, path, data=None, *, params=None, api_version=None):
        return self.request(
            'POST', path, params=params, json_body=data,
            api_version=api_version)

    def put(self, path, data=None, *, params=None, api_version=None):
        return self.request(
            'PUT', path, params=params, json_body=data,
            api_version=api_version)

    def delete(self, path, data=None, *, params=None, api_version=None):
        return self.request(
            'DELETE', path, params=params, json_body=data,
            api_version=api_version)

    def request(self, method, path, *, params=None, json_body=None,
                cache=None, api_version=None):
        method = method.upper()
        if cache is None:
            cache = method == 'GET'
        version = self.api_version if api_version is None else api_version

        prepared_params = _prepare_params(params)
        cache_key = self._cache_key(method, path, prepared_params, version)
        if cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        url = self.url_for(version) + path
        headers = {
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
        }
        if self._token:
            headers['Authorization'] = 'Bearer {}'.format(self._token)

        attempt = 0
        while True:
            try:
                response = self.session.request(
                    method, url, params=prepared_params or None,
                    json=json_body, headers=headers, timeout=self.timeout,
                    verify=self.verify)
            except requests.exceptions.Timeout as exc:
                if method == 'GET' and attempt < self.max_retries:
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise NetworkError(
                    'Timed out while contacting {}'.format(self.instance),
                    url=url, original=exc) from exc
            except requests.exceptions.RequestException as exc:
                if method == 'GET' and attempt < self.max_retries:
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise NetworkError(
                    'Could not contact {}: {}'.format(self.instance, exc),
                    url=url, original=exc) from exc

            if response.status_code >= 400:
                if (method == 'GET' and attempt < self.max_retries
                        and self._retryable_status(response.status_code)):
                    retry_after = _retry_after_seconds(
                        response.headers.get('Retry-After'))
                    self._sleep(retry_after if retry_after is not None
                               else self._backoff(attempt))
                    attempt += 1
                    continue
                raise self._error_from_response(response, url)

            data = self._decode_response(response, url)
            if method == 'GET':
                if cache:
                    self._cache_put(cache_key, data)
            else:
                # A successful write can change anything the UI has cached:
                # vote counts, read state, subscriptions, inbox counters.
                self.clear_cache()
            return data

    def _decode_response(self, response, url):
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                '{} returned invalid JSON'.format(self.instance),
                status_code=response.status_code,
                payload=response.text[:500],
                url=url) from exc

    def _error_from_response(self, response, url):
        payload = None
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            code = payload.get('error')
            message = (payload.get('message') or payload.get('cause')
                       or payload.get('error'))
        else:
            code = None
            message = None

        if not message:
            message = response.reason or response.text or 'HTTP error'
        text = '{} (HTTP {})'.format(message, response.status_code)

        kwargs = {
            'status_code': response.status_code,
            'code': code,
            'payload': payload,
            'url': url,
        }
        status = response.status_code
        if status == 400:
            return BadRequestError(text, **kwargs)
        if status == 401:
            return AuthenticationError(text, **kwargs)
        if status == 403:
            return PermissionDeniedError(text, **kwargs)
        if status == 404:
            return NotFoundError(text, **kwargs)
        if status == 429:
            retry_after = _retry_after_seconds(
                response.headers.get('Retry-After'))
            return RateLimitError(text, retry_after=retry_after, **kwargs)
        if 500 <= status < 600:
            return ServerError(text, **kwargs)
        return APIError(text, **kwargs)

    def _cache_key(self, method, path, params, api_version):
        token = ''
        if self._token:
            token = hashlib.sha256(
                self._token.encode('utf-8')).hexdigest()[:16]
        encoded = json.dumps(
            params, sort_keys=True, separators=(',', ':'), default=str)
        return (method, path, encoded, token, api_version)

    def _cache_get(self, key):
        if not self.cache_ttl:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= time.monotonic():
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return copy.deepcopy(value)

    def _cache_put(self, key, value):
        if not self.cache_ttl:
            return
        self._cache[key] = (time.monotonic() + self.cache_ttl,
                            copy.deepcopy(value))
        self._cache.move_to_end(key)
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)

    @staticmethod
    def _retryable_status(status):
        return status == 429 or status in (500, 502, 503, 504)

    @staticmethod
    def _backoff(attempt):
        return min(2 ** attempt, 5)

    @staticmethod
    def _sleep(seconds):
        if seconds and seconds > 0:
            time.sleep(seconds)

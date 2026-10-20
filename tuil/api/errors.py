# -*- coding: utf-8 -*-
"""Exceptions raised by the Lemmy API client."""


class LemmyError(Exception):
    """Base class for all errors raised by :mod:`tuil.api`."""


class NetworkError(LemmyError):
    """The instance could not be reached or did not answer in time."""

    def __init__(self, message, *, url=None, original=None):
        super().__init__(message)
        self.url = url
        self.original = original


class APIError(LemmyError):
    """An HTTP request reached the instance but was rejected."""

    def __init__(self, message, *, status_code=None, code=None, payload=None,
                 url=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.payload = payload
        self.url = url


class BadRequestError(APIError):
    """The request was malformed (HTTP 400)."""


class AuthenticationError(APIError):
    """Authentication is required or the credentials were rejected (HTTP 401)."""


class PermissionDeniedError(APIError):
    """The authenticated user is not allowed to perform the action (HTTP 403)."""


class NotFoundError(APIError):
    """The requested object does not exist (HTTP 404)."""


class RateLimitError(APIError):
    """The instance asked us to slow down (HTTP 429)."""

    def __init__(self, message, *, retry_after=None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(APIError):
    """The instance failed to handle the request (HTTP 5xx)."""


class InvalidResponseError(APIError):
    """The instance returned something that was not valid JSON."""


class UnsupportedFeatureError(LemmyError):
    """The operation is not available in the selected API version."""

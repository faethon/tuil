# -*- coding: utf-8 -*-
"""Authentication helpers for Lemmy instances.

Lemmy uses a username/email and password to issue a JWT.  The token is kept in
memory on the API client and, when persistence is enabled, stored with the
instance URL so that it can never be replayed against a different instance.
"""

from __future__ import unicode_literals

import logging

from .api.errors import AuthenticationError

_logger = logging.getLogger(__name__)


class AuthHelper(object):

    def __init__(self, client, terminal, config):
        self.client = client
        self.term = terminal
        self.config = config

    def restore(self):
        """Restore a saved session without prompting.

        Returns ``True`` when a usable token was restored.  An expired or
        rejected token is deleted and treated as a normal anonymous start.
        """
        token = self.config.refresh_token
        if not token:
            return False

        saved_instance = self.config.token_instance
        if saved_instance and saved_instance.rstrip('/') != self.client.instance:
            # The token belongs to another instance.  Keep it for that
            # instance instead of sending it to the current one.
            return False

        self.client.set_token(token)
        try:
            with self.term.loader('Logging in', catch_exception=False):
                user = self.client.me(refresh=True)
        except AuthenticationError:
            _logger.info('Stored Lemmy token was rejected; logging out')
            self.client.logout()
            self.config.delete_refresh_token()
            return False
        except Exception:
            self.client.logout()
            raise

        if not user:
            self.client.logout()
            self.config.delete_refresh_token()
            return False

        self.config.token_instance = self.client.instance
        self._welcome(user.name)
        return True

    def authorize(self):
        """Prompt for credentials and start a new session."""
        username = self.term.prompt_input('Username or email: ')
        if not username:
            return False
        password = self.term.prompt_input('Password: ')
        if not password:
            return False

        with self.term.loader('Logging in', delay=0):
            user = self.client.login(username, password)

        if self.term.loader.exception:
            return False

        self.config.refresh_token = self.client.token
        self.config.token_instance = self.client.instance
        if self.config['persistent']:
            self.config.save_refresh_token()
        self._welcome(user.name if user else username)
        return True

    def clear_oauth_data(self):
        """Log out and remove any persisted credentials."""
        self.client.logout()
        self.config.delete_refresh_token()

    def _welcome(self, username):
        self.term.show_notification(
            'Welcome, {0}'.format(username), timeout=1)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os
import tempfile
from contextlib import contextmanager

import pytest

from tuil.api.errors import AuthenticationError
from tuil.auth import AuthHelper
from tuil.config import Config as TuilConfig


class Loader(object):
    exception = None

    @contextmanager
    def __call__(self, *args, **kwargs):
        yield


class Terminal(object):

    def __init__(self):
        self.loader = Loader()
        self.notifications = []
        self.inputs = []

    def show_notification(self, message, **kwargs):
        self.notifications.append(message)

    def prompt_input(self, prompt, key=False):
        return self.inputs.pop(0)


class Client(object):
    instance = 'https://lemmy.ml'

    def __init__(self):
        self.token = None
        self.rejected = False
        self.login_count = 0
        self.logout_count = 0

    @property
    def is_logged_in(self):
        return bool(self.token)

    def set_token(self, token):
        self.token = token

    def me(self, refresh=False):
        if self.rejected:
            raise AuthenticationError('invalid token')
        return type('User', (), {'name': 'alice'})()

    def login(self, username, password):
        self.login_count += 1
        self.token = 'new-jwt'
        return type('User', (), {'name': username})()

    def logout(self):
        self.logout_count += 1
        self.token = None


class Config(dict):
    persistent = True

    def __init__(self):
        super(Config, self).__init__(persistent=True)
        self.refresh_token = None
        self.token_instance = None
        self.saved = 0
        self.deleted = 0

    def save_refresh_token(self):
        self.saved += 1

    def delete_refresh_token(self):
        self.deleted += 1
        self.refresh_token = None
        self.token_instance = None


def test_restore_saved_session():
    client = Client()
    term = Terminal()
    config = Config()
    config.refresh_token = 'saved-jwt'
    config.token_instance = 'https://lemmy.ml'

    assert AuthHelper(client, term, config).restore() is True
    assert client.token == 'saved-jwt'
    assert term.notifications == ['Welcome, alice']


def test_restore_does_not_reuse_token_on_another_instance():
    client = Client()
    term = Terminal()
    config = Config()
    config.refresh_token = 'saved-jwt'
    config.token_instance = 'https://lemmy.world'

    assert AuthHelper(client, term, config).restore() is False
    assert client.token is None
    assert config.refresh_token == 'saved-jwt'


def test_restore_discards_rejected_token():
    client = Client()
    client.rejected = True
    term = Terminal()
    config = Config()
    config.refresh_token = 'expired-jwt'
    config.token_instance = 'https://lemmy.ml'

    assert AuthHelper(client, term, config).restore() is False
    assert client.token is None
    assert config.deleted == 1
    assert config.refresh_token is None


def test_authorize_prompts_and_saves_token():
    client = Client()
    term = Terminal()
    term.inputs = ['alice', 'secret']
    config = Config()

    assert AuthHelper(client, term, config).authorize() is True
    assert client.login_count == 1
    assert config.refresh_token == 'new-jwt'
    assert config.token_instance == 'https://lemmy.ml'
    assert config.saved == 1
    assert term.notifications == ['Welcome, alice']


def test_clear_auth_removes_credentials():
    client = Client()
    client.token = 'jwt'
    config = Config()
    config.refresh_token = 'jwt'
    config.token_instance = 'https://lemmy.ml'

    AuthHelper(client, Terminal(), config).clear_oauth_data()
    assert client.token is None
    assert client.logout_count == 1
    assert config.deleted == 1


def test_config_token_is_bound_to_instance():
    with tempfile.TemporaryDirectory() as tmp:
        token_file = os.path.join(tmp, 'token')
        config = TuilConfig(token_file=token_file)
        config.token_file = token_file
        config['instance'] = 'https://lemmy.ml'
        config.refresh_token = 'secret'
        config.save_refresh_token()

        with open(token_file) as fp:
            assert json.load(fp) == {
                'instance': 'https://lemmy.ml', 'token': 'secret'}

        other = TuilConfig(token_file=token_file)
        other.token_file = token_file
        other.load_refresh_token()
        assert other.refresh_token == 'secret'
        assert other.token_instance == 'https://lemmy.ml'

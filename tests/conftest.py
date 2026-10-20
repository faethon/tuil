# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import curses
import logging
from functools import partial

import pytest

from tuil.config import Config
from tuil.terminal import Terminal

try:
    from unittest import mock
except ImportError:
    import mock

# Turn on autospec by default for convenience
patch = partial(mock.patch, autospec=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')


class MockStdscr(mock.MagicMock):
    """
    Extend mock to mimic curses.stdscr by keeping track of the terminal
    coordinates and allowing for the creation of subwindows with the same
    properties as stdscr.
    """

    # ``curses.textpad`` decodes key presses using the window's encoding.
    # Python 3.14 requires this to be a real string instead of a Mock.
    encoding = 'utf-8'

    def instr(self, *args):
        # curses.textpad reads the contents of the window when gathering
        # input. Return blank cells instead of a Mock object.
        return b' '

    def getyx(self):
        return self.y, self.x

    def getbegyx(self):
        return 0, 0

    def getmaxyx(self):
        return self.nlines, self.ncols

    def derwin(self, *args):
        """
        derwin()
        derwin(begin_y, begin_x)
        derwin(nlines, ncols, begin_y, begin_x)
        """

        if 'subwin' not in dir(self):
            self.attach_mock(MockStdscr(), 'subwin')

        if len(args) == 0:
            nlines = self.nlines
            ncols = self.ncols
        elif len(args) == 2:
            nlines = self.nlines - args[0]
            ncols = self.ncols - args[1]
        else:
            nlines = min(self.nlines - args[2], args[0])
            ncols = min(self.ncols - args[3], args[1])

        self.subwin.nlines = nlines
        self.subwin.ncols = ncols
        self.subwin.x = 0
        self.subwin.y = 0
        return self.subwin


class FakeClient(object):
    """Minimal client used by page tests that do not touch the network."""

    instance = 'https://lemmy.ml'

    def __init__(self):
        self.logged_in = False
        self.token = None
        self.cache_cleared = False

    @property
    def user(self):
        if not self.logged_in:
            return None
        user = mock.MagicMock()
        user.name = 'tester'
        return user

    def is_oauth_session(self):
        return self.logged_in

    @property
    def is_logged_in(self):
        return self.logged_in

    def me(self, refresh=False):
        return self.user

    def clear_cache(self):
        self.cache_cleared = True

    def close(self):
        pass


class FakeAuth(object):

    def __init__(self, client):
        self.client = client
        self.config = None

    def authorize(self):
        self.client.logged_in = True
        self.client.token = 'test-token'
        return True

    def restore(self):
        return False

    def clear_oauth_data(self):
        self.client.logged_in = False
        self.client.token = None


@pytest.fixture()
def config():
    conf = Config()
    with mock.patch.object(conf, 'save_history'),          \
            mock.patch.object(conf, 'delete_history'),     \
            mock.patch.object(conf, 'save_refresh_token'), \
            mock.patch.object(conf, 'delete_refresh_token'):

        def delete_refresh_token():
            # Skip the os.remove
            conf.refresh_token = None
            conf.token_instance = None
        conf.delete_refresh_token.side_effect = delete_refresh_token

        yield conf


@pytest.fixture()
def stdscr():
    with patch('curses.initscr'),               \
            patch('curses.echo'),               \
            patch('curses.flash'),              \
            patch('curses.endwin'),             \
            patch('curses.newwin'),             \
            patch('curses.noecho'),             \
            patch('curses.cbreak'),             \
            patch('curses.doupdate'),           \
            patch('curses.nocbreak'),           \
            patch('curses.curs_set'),           \
            patch('curses.init_pair'),          \
            patch('curses.color_pair'),         \
            patch('curses.has_colors'),         \
            patch('curses.start_color'),        \
            patch('curses.use_default_colors'):
        out = MockStdscr(nlines=40, ncols=80, x=0, y=0)
        curses.initscr.return_value = out
        curses.newwin.side_effect = lambda *args: out.derwin(*args)
        curses.color_pair.return_value = 23
        curses.has_colors.return_value = True
        curses.ACS_VLINE = 0
        curses.COLORS = 256
        curses.COLOR_PAIRS = 256
        yield out


@pytest.fixture()
def terminal(stdscr, config):
    term = Terminal(stdscr, config=config)
    term.set_theme()
    # Disable the python 3.4 addch patch so that the mock stdscr calls are
    # always made the same way
    term.addch = lambda window, *args: window.addch(*args)
    return term


@pytest.fixture()
def reddit():
    return FakeClient()


@pytest.fixture()
def oauth(reddit, terminal, config):
    helper = FakeAuth(reddit)
    helper.config = config
    return helper

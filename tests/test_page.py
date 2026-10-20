# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import curses
from contextlib import contextmanager

import pytest

from tuil.page import Page, PageController, logged_in
from tuil.subreddit_page import SubredditPage

try:
    from unittest import mock
except ImportError:
    import mock


def test_page_logged_in(terminal):

    page = mock.MagicMock()
    page.term = terminal

    @logged_in
    def func(_):
        raise RuntimeError()

    # Logged in runs the function
    page.reddit.is_oauth_session.return_value = True
    with pytest.raises(RuntimeError):
        func(page)
    message = 'Not logged in'.encode('utf-8')
    with pytest.raises(AssertionError):
        terminal.stdscr.subwin.addstr.assert_called_with(1, 1, message)

    # Logged out skips the function and displays a message
    page.reddit.is_oauth_session.return_value = False
    func(page)
    message = 'Not logged in'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_called_with(1, 1, message)


def test_page_unauthenticated(reddit, terminal, config, oauth):

    page = Page(reddit, terminal, config, oauth)
    page.controller = PageController(page, keymap=config.keymap)
    with mock.patch.object(page, 'refresh_content'), \
            mock.patch.object(page, 'content'),      \
            mock.patch.object(page, 'nav'),          \
            mock.patch.object(page, 'draw'):

        # Loop
        def func(_):
            page.active = False
        with mock.patch.object(page, 'controller'):
            page.controller.trigger = mock.MagicMock(side_effect=func)
            page.loop()
        assert page.draw.called

        # Quit, confirm
        terminal.stdscr.getch.return_value = ord('y')
        with mock.patch('sys.exit') as sys_exit:
            page.controller.trigger('q')
        assert sys_exit.called

        # Quit, deny
        terminal.stdscr.getch.return_value = terminal.ESCAPE
        with mock.patch('sys.exit') as sys_exit:
            page.controller.trigger('q')
        assert not sys_exit.called

        # Force quit
        terminal.stdscr.getch.return_value = terminal.ESCAPE
        with mock.patch('sys.exit') as sys_exit:
            page.controller.trigger('Q')
        assert sys_exit.called

        # Show help
        with mock.patch('subprocess.Popen') as Popen:
            page.controller.trigger('?')
        assert Popen.called

        logged_in_methods = [
            'a',  # Upvote
            'z',  # Downvote
            'd',  # Delete
            'e',  # Edit
            'i',  # Get inbox
            'C',  # Private message
        ]
        for ch in logged_in_methods:
            page.controller.trigger(ch)
            message = 'Not logged in'.encode('utf-8')
            terminal.stdscr.subwin.addstr.assert_called_with(1, 1, message)
            terminal.stdscr.subwin.addstr.reset_mock()


def test_page_edit_private_message(reddit, terminal, config, oauth):
    reddit.logged_in = True
    page = Page(reddit, terminal, config, oauth)
    message = mock.MagicMock()
    data = {
        'type': 'Message',
        'author': 'tester',
        'body': 'old body',
        'object': message,
    }
    page.get_selected_item = lambda: data

    @contextmanager
    def editor(_info):
        yield 'new body'

    with mock.patch.object(terminal, 'open_editor', side_effect=editor), \
            mock.patch.object(page, 'reload_page'), \
            mock.patch('tuil.page.time.sleep'):
        page.edit()

    message.edit.assert_called_once_with('new body')


def test_page_identity_text(reddit, terminal, config, oauth):
    page = Page(reddit, terminal, config, oauth)

    assert page._identity_text() == 'lemmy.ml'

    reddit.logged_in = True
    assert page._identity_text() == 'tester@lemmy.ml'

    config['hide_username'] = True
    assert page._identity_text() == 'Logged in@lemmy.ml'


def test_page_content_title_member_count(reddit, terminal, config, oauth):
    page = Page(reddit, terminal, config, oauth)
    page.content = mock.MagicMock()
    page.content.name = '/c/linux'
    page.content.query = None
    page.content.community = None

    page.content.member_count = 68180
    assert page._content_title() == '/c/linux (68,180 members)'

    page.content.member_count = 1
    assert page._content_title() == '/c/linux (1 member)'

    page.content.member_count = None
    assert page._content_title() == '/c/linux'

    page.content.member_count = 68180
    page.content.community = mock.MagicMock(subscription='Subscribed')
    assert page._content_title() == '/c/linux ✓ joined (68,180 members)'

    config['ascii'] = True
    assert page._content_title() == '/c/linux v joined (68,180 members)'

    config['ascii'] = False
    page.content.community.subscription = 'Pending'
    assert page._content_title() == (
        '/c/linux join pending (68,180 members)')

    page.content.community.subscription = 'NotSubscribed'
    assert page._content_title() == '/c/linux not joined (68,180 members)'


def test_subreddit_join_skips_existing_member():
    page = mock.MagicMock()
    page.reddit.is_oauth_session.return_value = True
    page.content.name = '/c/linux'
    page.content.community = mock.MagicMock(subscribed=True)

    SubredditPage.subreddit_subscribe(page)

    page.reddit.follow_community.assert_not_called()
    page.term.show_notification.assert_called_with(
        'Already joined linux', 1)


def test_subreddit_join_updates_membership():
    page = mock.MagicMock()
    page.reddit.is_oauth_session.return_value = True
    page.reddit.follow_community.return_value = mock.MagicMock()
    page.content.name = '/c/linux'
    community = mock.MagicMock(subscribed=False)
    page.content.community = community
    page.term.loader.exception = None

    SubredditPage.subreddit_subscribe(page)

    page.reddit.follow_community.assert_called_once_with(community, True)
    assert page.content.community is page.reddit.follow_community.return_value
    page.term.show_notification.assert_called_with('Joined linux', 1)


def test_page_open_subreddit_uses_qualified_name(reddit, terminal, config,
                                                 oauth):
    page = Page(reddit, terminal, config, oauth)
    page.get_selected_item = lambda: {
        'subreddit': 'linux',
        'subreddit_qualified': 'linux@lemmy.ml',
    }

    with mock.patch.object(page, 'open_subreddit_page') as open_page:
        page.open_subreddit()

    open_page.assert_called_once_with('linux@lemmy.ml')


def test_page_community_search(reddit, terminal, config, oauth):
    page = Page(reddit, terminal, config, oauth)

    with mock.patch.object(
            terminal, 'prompt_input', return_value='linux'), \
            mock.patch.object(page, 'open_subscription_page') as open_page:
        page.community_search()

    open_page.assert_called_once_with('search', query='linux')


def test_page_prompt_comment(reddit, terminal, config, oauth):
    page = Page(reddit, terminal, config, oauth)

    with mock.patch.object(
            terminal, 'prompt_input',
            return_value='https://lemmy.ml/comment/321'), \
            mock.patch.object(page, 'open_submission_page') as open_page:
        page.prompt()

    open_page.assert_called_once_with('https://lemmy.ml/comment/321')


def test_page_authenticated(reddit, terminal, config, oauth):
    class TestPage(Page):
        def refresh_content(self, order=None, name=None):
            pass

    page = TestPage(reddit, terminal, config, oauth)
    page.controller = PageController(page, keymap=config.keymap)
    # Login
    page.controller.trigger('u')
    assert reddit.is_oauth_session()

    # Logout
    terminal.stdscr.getch.return_value = ord('y')
    page.controller.trigger('u')
    assert not reddit.is_oauth_session()


def test_page_cycle_theme(reddit, terminal, config, oauth):

    page = Page(reddit, terminal, config, oauth)
    page.controller = PageController(page, keymap=config.keymap)

    page.term.set_theme()
    assert page.term.theme.name == 'default'

    with mock.patch.object(terminal, 'show_notification'), \
            mock.patch.object(page, 'draw'):

        # Next theme
        page.controller.trigger(curses.KEY_F3)
        assert page.term.theme.name == 'monochrome'
        terminal.show_notification.assert_called_with(
            'monochrome (built-in)', timeout=1)

        # Previous theme
        page.controller.trigger(curses.KEY_F2)
        assert page.term.theme.name == 'default'
        terminal.show_notification.assert_called_with(
            'default (built-in)', timeout=1)

        # Previous - will loop to one of the 256 color themes
        page.controller.trigger(curses.KEY_F2)
        assert page.term.theme.source in ('preset', 'installed')

        # Reset
        page.term.set_theme()

        # Will skip over any installed themes that aren't supported
        curses.has_colors.return_value = False
        page.controller.trigger(curses.KEY_F2)
        assert page.term.theme.required_colors == 0

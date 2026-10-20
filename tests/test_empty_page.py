# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pytest

from tuil.docs import FOOTER_EMPTY
from tuil.empty_page import EmptyPage

try:
    from unittest import mock
except ImportError:
    import mock



def test_empty_page_construct(reddit, terminal, config, oauth):
    window = terminal.stdscr.subwin

    with terminal.loader():
        page = EmptyPage(reddit, terminal, config, oauth)
    assert terminal.loader.exception is None

    page.draw()

    #  Title
    title = 'Empty Page'.encode('utf-8')
    window.addstr.assert_any_call(0, 0, title)

    # Banner
    menu = FOOTER_EMPTY.strip()
    window.addstr.assert_any_call(0, 0, menu.encode('utf-8'))

    # Footer - The text is longer than the default terminal width
    text = FOOTER_EMPTY.strip()[:79]
    window.addstr.assert_any_call(0, 0, text.encode('utf-8'))

    # Reload with a smaller terminal window
    terminal.stdscr.ncols = 20
    terminal.stdscr.nlines = 10
    with terminal.loader():
        page = EmptyPage(reddit, terminal, config, oauth)
    assert terminal.loader.exception is None
    page.draw()

    assert page.content.range == (0, -1)


def test_empty_page_open_inbox(reddit, terminal, config, oauth):
    with terminal.loader():
        page = EmptyPage(reddit, terminal, config, oauth)
    with mock.patch.object(terminal, 'show_notification') as show_notification:
        page.controller.trigger('i')
        assert page.active
        show_notification.assert_called_with('Not logged in')

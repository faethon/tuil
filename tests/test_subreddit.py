# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import curses
from collections import OrderedDict
import os.path
import sys

import six
import pytest

from tuir import __version__
from tuir.subreddit_page import SubredditPage
from tuir.packages.praw.errors import NotFound, HTTPException
from requests.exceptions import ReadTimeout

try:
    from unittest import mock
except ImportError:
    import mock


PROMPTS = OrderedDict([
    ('prompt_1', 'comments/571dw3'),
    ('prompt_2', '///comments/571dw3'),
    ('prompt_3', '/comments/571dw3'),
    ('prompt_4', '/r/pics/comments/571dw3/'),
    ('prompt_5', 'https://www.reddit.com/r/pics/comments/571dw3/at_disneyland'),
])


def test_subreddit_page_construct_default(reddit, terminal, config, oauth):
    config['look_and_feel'] = 'default'

    window = terminal.stdscr.subwin

    with terminal.loader():
        page = SubredditPage(reddit, terminal, config, oauth, '/r/python')
    assert terminal.loader.exception is None
    page.draw()

    # Title
    title = '/r/python'.encode('utf-8')
    window.addstr.assert_any_call(0, 0, title)

    # Banner
    menu = '[1]hot     [2]top     [3]rising     [4]new     [5]controversial     [6]gilded'.encode('utf-8')
    window.addstr.assert_any_call(0, 0, menu)

    # Submission
    text = page.content.get(0)['split_title'][0].encode('utf-8')
    window.subwin.addstr.assert_any_call(0, 1, text, 2097152)

    # Cursor should have been drawn
    window.subwin.addch.assert_any_call(0, 0, ' ', curses.A_REVERSE)

    # Reload with a smaller terminal window
    terminal.stdscr.ncols = 20
    terminal.stdscr.nlines = 10
    with terminal.loader():
        page = SubredditPage(reddit, terminal, config, oauth, '/r/python')
    assert terminal.loader.exception is None
    page.draw()


def test_subreddit_refresh(subreddit_page, terminal):

    # Refresh the page with default values
    subreddit_page.controller.trigger('r')
    assert subreddit_page.content.order is None
    assert subreddit_page.content.name == '/r/python'
    assert terminal.loader.exception is None

    # Refresh with the order in the name
    subreddit_page.refresh_content(order='ignore', name='/r/front/hot')
    assert subreddit_page.content.order == 'hot'
    assert subreddit_page.content.name == '/r/front'
    assert terminal.loader.exception is None


def test_subreddit_reload_page(subreddit_page, terminal, reddit):

    cache = reddit.handler.cache
    assert len(cache) == 1

    # A plain refresh_content() will use whatever is in the praw cache
    # instead of making a new request to reddit
    list(cache.values())[0].status_code = 503
    subreddit_page.refresh_content()
    assert isinstance(terminal.loader.exception, HTTPException)

    cache = reddit.handler.cache
    assert len(cache) == 1

    # But if we manually trigger a page refresh, it should clear the cache
    # and reload the page instead of returning the cached 503 response
    list(cache.values())[0].status_code = 503
    subreddit_page.controller.trigger('r')
    assert terminal.loader.exception is None


def test_subreddit_title(subreddit_page, terminal, capsys):
    subreddit_page.content.name = 'hello ❤'

    with mock.patch.dict('os.environ', {'DISPLAY': ':1'}):
        terminal.config['ascii'] = True
        subreddit_page.draw()
        out, _ = capsys.readouterr()
        assert isinstance(out, six.text_type)
        assert out == '\x1b]2;hello ? - tuir {}\x07'.format(__version__)

        terminal.config['ascii'] = False
        subreddit_page.draw()
        out, _ = capsys.readouterr()
        assert isinstance(out, six.text_type)
        assert out == '\x1b]2;hello ❤ - tuir {}\x07'.format(__version__)

    with mock.patch.dict('os.environ', {'DISPLAY': ''}):
        subreddit_page.draw()
        out, _ = capsys.readouterr()
        assert not out

    with mock.patch.dict('os.environ', {'INSIDE_EMACS': '25.3.1,term:0.96'}):
        subreddit_page.draw()
        out, _ = capsys.readouterr()
        assert not out


def test_subreddit_search(subreddit_page, terminal):
    window = terminal.stdscr.subwin

    # Search the current subreddit
    with mock.patch.object(terminal, 'prompt_input'):
        terminal.prompt_input.return_value = 'search term'
        subreddit_page.controller.trigger('f')
        assert subreddit_page.content.name == '/r/python'
        assert terminal.prompt_input.called
        assert not terminal.loader.exception

        # The page title should display the query
        subreddit_page.draw()
        title = 'Searching /r/python: search term'.encode('utf-8')
        window.addstr.assert_any_call(0, 0, title)

    # Ordering the results should preserve the query
    window.addstr.reset_mock()
    subreddit_page.refresh_content(order='hot')
    subreddit_page.refresh_content(order='top-all')
    subreddit_page.refresh_content(order='new')
    assert subreddit_page.content.name == '/r/python'
    assert subreddit_page.content.query == 'search term'
    assert not terminal.loader.exception

    # Searching with an empty query shouldn't crash
    with mock.patch.object(terminal, 'prompt_input'):
        terminal.prompt_input.return_value = None
        subreddit_page.controller.trigger('f')
        assert not terminal.loader.exception

    # Changing to a new subreddit should clear the query
    window.addstr.reset_mock()
    subreddit_page.refresh_content(name='/r/learnpython')
    assert subreddit_page.content.query is None


def test_subreddit_prompt(subreddit_page, terminal):

    # Prompt for a different subreddit
    with mock.patch.object(terminal, 'prompt_input'):
        terminal.prompt_input.return_value = 'front/top'
        subreddit_page.controller.trigger('/')

        subreddit_page.handle_selected_page()
        assert not subreddit_page.active
        assert subreddit_page.selected_page
        assert subreddit_page.selected_page.content.name == '/r/front'
        assert subreddit_page.selected_page.content.order == 'top'


@pytest.mark.parametrize('prompt', PROMPTS.values(), ids=list(PROMPTS))
def test_subreddit_prompt_submission(subreddit_page, terminal, prompt):

    url = 'https://www.reddit.com/comments/571dw3'

    with mock.patch.object(subreddit_page, 'open_submission_page'), \
            mock.patch.object(terminal, 'prompt_input'):

        terminal.prompt_input.return_value = prompt
        subreddit_page.open_submission_page.return_value = 'MockPage'
        subreddit_page.controller.trigger('/')

        subreddit_page.open_submission_page.assert_called_with(url)
        assert not terminal.loader.exception
        assert subreddit_page.selected_page == 'MockPage'


def test_subreddit_prompt_submission_invalid(subreddit_page, terminal):

    with mock.patch.object(terminal, 'prompt_input'):
        terminal.prompt_input.return_value = 'comments/571dw3fakeid'
        subreddit_page.controller.trigger('/')
        assert isinstance(terminal.loader.exception, NotFound)


def test_subreddit_order(subreddit_page):

    # /r/python doesn't always have rising submissions, so use a larger sub
    subreddit_page.refresh_content(name='all')

    subreddit_page.content.query = ''
    subreddit_page.controller.trigger('1')
    assert subreddit_page.content.order == 'hot'
    subreddit_page.controller.trigger('3')
    assert subreddit_page.content.order == 'rising'
    subreddit_page.controller.trigger('4')
    assert subreddit_page.content.order == 'new'
    subreddit_page.controller.trigger('6')
    assert subreddit_page.content.order == 'gilded'

    subreddit_page.content.query = 'search text'
    subreddit_page.controller.trigger('1')
    assert subreddit_page.content.order == 'relevance'
    subreddit_page.controller.trigger('4')
    assert subreddit_page.content.order == 'new'

    # Shouldn't be able to sort queries by gilded
    subreddit_page.controller.trigger('6')
    assert curses.flash.called
    assert subreddit_page.content.order == 'new'


def test_subreddit_order_top(subreddit_page, terminal):

    # Sort by top
    with mock.patch.object(terminal, 'show_notification'):
        # Invalid selection
        terminal.show_notification.return_value = ord('x')
        subreddit_page.controller.trigger('2')
        terminal.show_notification.assert_called_with('Invalid option')
        assert subreddit_page.content.order is None

        # Valid selection - sort by week
        terminal.show_notification.reset_mock()
        terminal.show_notification.return_value = ord('3')
        subreddit_page.controller.trigger('2')
        assert subreddit_page.content.order == 'top-week'


def test_subreddit_order_controversial(subreddit_page, terminal):

    # Sort by controversial
    with mock.patch.object(terminal, 'show_notification'):
        # Invalid selection
        terminal.show_notification.return_value = ord('x')
        subreddit_page.controller.trigger('5')
        terminal.show_notification.assert_called_with('Invalid option')
        assert subreddit_page.content.order is None

        # Valid selection - sort by default
        terminal.show_notification.reset_mock()
        terminal.show_notification.return_value = ord('\n')
        subreddit_page.controller.trigger('5')
        assert subreddit_page.content.order == 'controversial'


def test_subreddit_order_search(subreddit_page, terminal):

    # Search the current subreddit
    with mock.patch.object(terminal, 'prompt_input'):
        terminal.prompt_input.return_value = 'search term'
        subreddit_page.controller.trigger('f')
        assert subreddit_page.content.name == '/r/python'
        assert terminal.prompt_input.called
        assert not terminal.loader.exception

    # Sort by relevance
    subreddit_page.controller.trigger('1')
    assert subreddit_page.content.order == 'relevance'

    # Sort by top
    with mock.patch.object(terminal, 'show_notification'):
        terminal.show_notification.reset_mock()
        terminal.show_notification.return_value = ord('6')
        subreddit_page.controller.trigger('2')
        assert subreddit_page.content.order == 'top-all'

    # Sort by comments
    with mock.patch.object(terminal, 'show_notification'):
        terminal.show_notification.reset_mock()
        terminal.show_notification.return_value = ord('6')
        subreddit_page.controller.trigger('3')
        assert subreddit_page.content.order == 'comments-all'

    # Sort by new
    subreddit_page.controller.trigger('4')
    assert subreddit_page.content.order == 'new'


def test_subreddit_open(subreddit_page, terminal, config):

    # Open the selected submission
    data = subreddit_page.content.get(subreddit_page.nav.absolute_index)
    with mock.patch.object(config.history, 'add'):
        data['url_type'] = 'selfpost'
        subreddit_page.controller.trigger('l')
        assert not terminal.loader.exception
        assert subreddit_page.selected_page
        assert subreddit_page.active
        config.history.add.assert_called_with(data['url_full'])

    # Open the selected link externally
    data = subreddit_page.content.get(subreddit_page.nav.absolute_index)
    with mock.patch.object(terminal, 'open_link'), \
            mock.patch.object(config.history, 'add'):
        data['url_type'] = 'external'
        subreddit_page.controller.trigger('o')
        assert terminal.open_link.called
        config.history.add.assert_called_with(data['url_full'])

    # Open the selected link within tuir
    data = subreddit_page.content.get(subreddit_page.nav.absolute_index)
    with mock.patch.object(subreddit_page, 'open_submission'), \
            mock.patch.object(config.history, 'add'):
        data['url_type'] = 'selfpost'
        subreddit_page.controller.trigger('o')
        assert subreddit_page.open_submission.called


def test_subreddit_open_xpost(subreddit_page, config):

    data = subreddit_page.content.get(subreddit_page.nav.absolute_index)

    # Open an x-post subreddit, see /r/TinySubredditoftheDay for an example
    with mock.patch.object(subreddit_page, 'refresh_content'):
        data['url_type'] = 'x-post subreddit'
        data['xpost_subreddit'] = 'goodbye'
        subreddit_page.controller.trigger('o')
        subreddit_page.refresh_content.assert_called_with(
            name='goodbye', order='ignore')

    # Open an x-post submission, see /r/bestof for an example
    with mock.patch.object(subreddit_page, 'open_submission'):
        data['url_type'] = 'x-post submission'
        data['url_full'] = 'www.test.com'
        subreddit_page.controller.trigger('o')
        subreddit_page.open_submission.assert_called_with(url='www.test.com')


def test_subreddit_unauthenticated(subreddit_page, terminal):

    # Unauthenticated commands
    methods = [
        'a',  # Upvote
        'z',  # Downvote
        'c',  # Post
        'e',  # Edit
        'd',  # Delete
        's',  # Subscriptions
    ]
    for ch in methods:
        subreddit_page.controller.trigger(ch)
        text = 'Not logged in'.encode('utf-8')
        terminal.stdscr.subwin.addstr.assert_called_with(1, 1, text)


def test_subreddit_post(subreddit_page, terminal, reddit, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # Post a submission to an invalid subreddit
    subreddit_page.refresh_content(name='front')
    subreddit_page.controller.trigger('c')
    text = "Can't post to /r/front".encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_called_with(1, 1, text)

    # Post a submission with a title but with no body
    subreddit_page.refresh_content(name='python')
    with mock.patch.object(terminal, 'open_editor'):
        terminal.open_editor.return_value.__enter__.return_value = 'title'
        subreddit_page.controller.trigger('c')
        text = 'Missing body'.encode('utf-8')
        terminal.stdscr.subwin.addstr.assert_called_with(1, 1, text)

    # Post a fake submission
    url = 'https://www.reddit.com/r/Python/comments/2xmo63/'
    submission = reddit.get_submission(url)
    with mock.patch.object(terminal, 'open_editor'),  \
            mock.patch.object(reddit, 'submit'),      \
            mock.patch('time.sleep'):
        terminal.open_editor.return_value.__enter__.return_value = 'test\ncont'
        reddit.submit.return_value = submission
        subreddit_page.controller.trigger('c')
        assert reddit.submit.called
        assert subreddit_page.selected_page.content._submission == submission
        assert subreddit_page.active


def test_subreddit_open_subscriptions(subreddit_page, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # Open subscriptions
    subreddit_page.controller.trigger('s')
    assert subreddit_page.selected_page
    assert subreddit_page.active

    with mock.patch('tuir.page.Page.loop') as loop:
        subreddit_page.handle_selected_page()
        assert loop.called


def test_subreddit_get_inbox_timeout(subreddit_page, refresh_token, terminal, vcr):
    if vcr.record_mode == 'none':
        pytest.skip('Unable to test ReadTimeout exceptions using a cassette')

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    subreddit_page.reddit.config.timeout = 0.00000001
    subreddit_page.controller.trigger('i')
    text = 'HTTP request timed out'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_called_with(1, 1, text)
    assert isinstance(terminal.loader.exception, ReadTimeout)


def test_subreddit_open_multireddits(subreddit_page, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # Open multireddits
    subreddit_page.controller.trigger('S')
    assert subreddit_page.selected_page
    assert subreddit_page.active

    with mock.patch('tuir.page.Page.loop') as loop:
        subreddit_page.handle_selected_page()
        assert loop.called


def test_subreddit_private_user_pages(subreddit_page, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    subreddit_page.refresh_content(name='/u/me/saved')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/hidden')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/upvoted')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/downvoted')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/overview')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/submitted')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/me/comments')
    subreddit_page.draw()


def test_subreddit_user_pages(subreddit_page, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # Pick a user that has a lot of recent comments, so we can make sure that
    # SavedComment objects have all of the properties necessary to be drawn
    # on the submission page.

    # Should default to the overview page
    subreddit_page.refresh_content(name='/u/spez')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/spez/overview')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/spez/submitted')
    subreddit_page.draw()

    subreddit_page.refresh_content(name='/u/spez/comments')
    subreddit_page.draw()


def test_subreddit_draw_header(subreddit_page, refresh_token, terminal):

    # /r/front alias should be renamed in the header
    subreddit_page.refresh_content(name='/r/front')
    subreddit_page.draw()
    text = 'Front Page'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    subreddit_page.refresh_content(name='/r/front/new')
    subreddit_page.draw()
    text = 'Front Page'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    # Log in to check the user submissions page
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # /u/me alias should be renamed in the header
    subreddit_page.refresh_content(name='/u/me')
    subreddit_page.draw()
    text = 'My Overview'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    subreddit_page.refresh_content(name='/u/me/new')
    subreddit_page.draw()
    text = 'My Overview'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    # /u/saved alias should be renamed in the header
    subreddit_page.refresh_content(name='/u/me/saved')
    subreddit_page.draw()
    text = 'My Saved Content'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    # /u/upvoted alias should be renamed in the header
    subreddit_page.refresh_content(name='/u/me/upvoted')
    subreddit_page.draw()
    text = 'My Upvoted Content'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    # /u/downvoted alias should be renamed in the header
    subreddit_page.refresh_content(name='/u/me/downvoted')
    subreddit_page.draw()
    text = 'My Downvoted Content'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)

    # /u/hidden alias should be renamed in the header
    subreddit_page.refresh_content(name='/u/me/hidden')
    subreddit_page.draw()
    text = 'My Hidden Content'.encode('utf-8')
    terminal.stdscr.subwin.addstr.assert_any_call(0, 0, text)


def test_subreddit_frontpage_toggle(subreddit_page, terminal):
    with mock.patch.object(terminal, 'prompt_input'):

        terminal.prompt_input.return_value = 'aww'
        subreddit_page.controller.trigger('/')
        subreddit_page.handle_selected_page()

        new_page = subreddit_page.selected_page
        assert new_page is not None
        assert new_page.content.name == '/r/aww'

        new_page.controller.trigger('p')
        assert new_page.toggled_subreddit == '/r/aww'
        assert new_page.content.name == '/r/front'


def test_subreddit_hide_submission(subreddit_page, refresh_token):

    # Log in
    subreddit_page.config.refresh_token = refresh_token
    subreddit_page.oauth.authorize()

    # The api won't return hidden posts in the submission listing, so the
    # first post should always have hidden set to false
    data = subreddit_page.get_selected_item()
    assert data['hidden'] is False

    # Hide the first submission by pressing the space key
    subreddit_page.controller.trigger(0x20)
    assert subreddit_page.term.loader.exception is None
    data = subreddit_page.get_selected_item()
    assert data['hidden'] is True

    # Make sure that the status was actually updated on the server side
    data['object'].refresh()
    assert data['object'].hidden is True

    # Now undo the hide by pressing space again
    subreddit_page.controller.trigger(0x20)
    assert subreddit_page.term.loader.exception is None
    data = subreddit_page.get_selected_item()
    assert data['hidden'] is False

    # Make sure that the status was actually updated on the server side
    data['object'].refresh()
    assert data['object'].hidden is False


def test_subreddit_handle_selected_page(subreddit_page, subscription_page):

    # Method should be a no-op if selected_page is unset
    subreddit_page.active = True
    subreddit_page.handle_selected_page()
    assert subreddit_page.selected_page is None
    assert subreddit_page.active

    # Open the subscription page and select a subreddit from the list of
    # subscriptions
    with mock.patch.object(subscription_page, 'loop', return_value=subreddit_page):
        subreddit_page.selected_page = subscription_page
        subreddit_page.handle_selected_page()
        assert subreddit_page.selected_page == subreddit_page
        assert subreddit_page.active

    # Now when handle_select_page() is called again, the current subreddit
    # should be closed so the selected page can be opened
    subreddit_page.handle_selected_page()
    assert subreddit_page.selected_page == subreddit_page
    assert not subreddit_page.active

    subreddit_page.selected_page.name = 'This should raise a RuntimeError'
    with pytest.raises(RuntimeError):
        subreddit_page.handle_selected_page()


def test_subreddit_page_loop_pre_select(subreddit_page, submission_page):

    # Set the selected_page before entering the loop(). This will cause the
    # selected page to immediately open. If the selected page returns a
    # different subreddit page (e.g. the user enters a subreddit into the
    # prompt before they hit the `h` key), the initial loop should be closed
    # immediately
    subreddit_page.selected_page = submission_page
    with mock.patch.object(submission_page, 'loop', return_value=subreddit_page):
        selected_page = subreddit_page.loop()

        assert not subreddit_page.active
        assert selected_page == subreddit_page


def test_subreddit_page_loop(subreddit_page, stdscr, terminal):

    stdscr.getch.return_value = ord('/')

    with mock.patch.object(terminal, 'prompt_input', return_value='all'):
        new_page = subreddit_page.loop()
        assert new_page.content.name == '/r/all'


def test_subreddit_page__submission_attr(config, terminal, subreddit_page):
    data = {}
    data['url_full'] = 'www.test.com'

    config.history = []
    terminal.attr = mock.Mock()

    subreddit_page._submission_attr(data)
    terminal.attr.assert_called_with('SubmissionTitle')

    config.history.append(data['url_full'])

    subreddit_page._submission_attr(data)
    terminal.attr.assert_called_with('SubmissionTitleSeen')


def test_subreddit_page__url_str(config, terminal, subreddit_page):
    data = {
            'url_type': 'selfpost',
            'url': 'self.AskReddit',
            'url_full': 'https://www.reddit.com/r/AskReddit/comments/99eh6b/without_saying_what_the_category_is_what_are_your/'
    }

    assert subreddit_page._url_str(data) == 'self.AskReddit'

    data['url_type'] = 'x-post subreddit'

    assert subreddit_page._url_str(data) == 'self.AskReddit'

    data['url_type'] = 'external'

    assert subreddit_page._url_str(data) == 'www.reddit.com'


def test_subreddit_page__url_attr(config, terminal, subreddit_page):
    data = {}
    data['url_full'] = 'www.test.com'

    config.history = []
    terminal.attr = mock.Mock()

    subreddit_page._url_attr(data)
    terminal.attr.assert_called_with('Link')

    config.history.append(data['url_full'])

    subreddit_page._url_attr(data)
    terminal.attr.assert_called_with('LinkSeen')


def test_subreddit_page__gold_str(config, terminal, subreddit_page):
    data = {}
    data['gold'] = 0

    goldstr = subreddit_page._gold_str(data)
    assert goldstr == ''

    data['gold'] = 1
    goldstr = subreddit_page._gold_str(data)
    assert goldstr == terminal.gilded

    data['gold'] = 2
    goldstr = subreddit_page._gold_str(data)
    assert goldstr == terminal.gilded + 'x2'


def test_subreddit_page__draw_item_format(terminal, subreddit_page):
    data = {
            'index': '1',
            'title': 'Without saying what the category is, what are your top five?',
            'score': '144655',
            'likes': True,
            'comments': '26584',
            'created': '10month',
            'edited': '(edit 5month)',
            'author': 'reddit_user',
            'subreddit': 'AskReddit',
            'url': 'self.AskReddit',
            'url_type': 'selfpost',
            'url_full': 'https://www.reddit.com/r/AskReddit/comments/99eh6b/without_saying_what_the_category_is_what_are_your/',
            'gold': 1,
            'saved': True,
            'hidden': True,
            'stickied': True,
            'nsfw': True,
            'flair': 'Serious Replies Only'
    }

    expected_str = {
            '%i': '1',
            '%t': 'Without saying what the category is, what are your top five?',
            '%s': '144655',
            '%v': '▲',
            '%c': '26584',
            '%r': '10month',
            '%e': '(edit 5month)',
            '%a': 'reddit_user',
            '%S': '/r/AskReddit',
            '%u': 'self.AskReddit',
            '%U': 'self.AskReddit',
            '%A': '[saved]',
            '%h': '[hidden]',
            '%T': '[stickied]',
            '%g': '✪',
            '%n': 'NSFW',
            '%f': 'Serious Replies Only',
    }

    expected_attr = {
            '%i': terminal.attr('SubmissionTitle'),
            '%t': terminal.attr('SubmissionTitle'),
            '%s': terminal.attr('Score'),
            '%v': terminal.attr('Upvote'),
            '%c': terminal.attr('CommentCount'),
            '%r': terminal.attr('Created'),
            '%e': terminal.attr('Created'),
            '%a': terminal.attr('SubmissionAuthor'),
            '%S': terminal.attr('SubmissionSubreddit'),
            '%u': terminal.attr('Link'),
            '%U': terminal.attr('Link'),
            '%A': terminal.attr('Saved'),
            '%h': terminal.attr('Hidden'),
            '%T': terminal.attr('Stickied'),
            '%g': terminal.attr('Gold'),
            '%n': terminal.attr('NSFW'),
            '%f': terminal.attr('SubmissionFlair')
    }

    win = terminal.stdscr.subwin

    with mock.patch.object(terminal, 'add_line'):
        # Loop through each individual format specifier and check for the desired behavior.
        for fmt in filter(None, '%i %t %s %v %c %r %e %a %S %u %U %A %h %T %g %n %f %F'.split()):
                subreddit_page.config['subreddit_format'] = fmt
                subreddit_page.FORMAT_LIST = subreddit_page._create_format_list()
                subreddit_page._draw_item_format(win, data, 0, 0)

                try:
                    if fmt == '%F':

                        # Make sure each of the things that %F should print are printed
                        # flair
                        terminal.add_line.assert_any_call(win, expected_str['%f'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%f'])

                        # saved
                        terminal.add_line.assert_any_call(win, expected_str['%A'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%A'])

                        # hidden
                        terminal.add_line.assert_any_call(win, expected_str['%h'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%h'])

                        # stickied
                        terminal.add_line.assert_any_call(win, expected_str['%T'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%T'])

                        # gold
                        terminal.add_line.assert_any_call(win, expected_str['%g'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%g'])

                        # nsfw
                        terminal.add_line.assert_any_call(win, expected_str['%n'],
                                                          row=mock.ANY, col=mock.ANY,
                                                          attr=expected_attr['%n'])
                    else:
                        terminal.add_line.assert_called_with(win, expected_str[fmt],
                                                             row=0, col=1,
                                                             attr=expected_attr[fmt])
                except:
                    sys.stderr.write("Failed on {0}\n".format(fmt))
                    raise

        terminal.add_line.reset_mock()

        # Ensure spaces aren't printed consecutively if data is absent
        data['gold'] = 0
        subreddit_page.config['subreddit_format'] = ' %g '
        subreddit_page.FORMAT_LIST = subreddit_page._create_format_list()
        subreddit_page._draw_item_format(win, data, 0, 0)

        assert terminal.add_line.call_count == 1

        terminal.add_line.reset_mock()

        # Test for correct handling of separators
        subreddit_page.config['subreddit_format'] = ' | '
        subreddit_page.FORMAT_LIST = subreddit_page._create_format_list()
        subreddit_page._draw_item_format(win, data, 0, 0)

        # Should be called thrice - ' ', '|', ' '
        assert terminal.add_line.call_count == 3


class MockPopen():
    def __init__(*args, **kwargs): pass
    def communicate(self): return '', ''
    def poll(self): pass


class MockProcess():
    def __init__(self, target, args=None):
        self._target = target
        self._args = args or []
    def start(self):
        self._target(*self._args)
    def join(self, _=None): pass
    def is_alive(self): pass
    def terminate(self): pass


def test_subreddit_open_in_browser(subreddit_page, terminal):
    subreddit_page.refresh_content(order='ignore', name='/r/front/hot')
    terminal.config.MAILCAP = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tuir', 'templates', 'mailcap')
    with mock.patch('os.system'), \
            mock.patch('tuir.terminal.Process', side_effect=MockProcess), \
            mock.patch('webbrowser.open_new_tab') as new_tab:
        for i in range(8):
            subreddit_page.controller.trigger('o')
            with mock.patch.object(subreddit_page, 'clear_input_queue'):
                subreddit_page.controller.trigger('j')
                subreddit_page.controller.trigger('j')
                subreddit_page.controller.trigger('j')
        assert [list(i.args) for i in new_tab.mock_calls] == [
            ['https://i.redd.it/czlc1ff2tqlz.jpg'],
            ['https://i.imgur.com/ok9H05N.gifv'],
            ['https://twitter.com/DOOM/status/908094489276928001'],
            ['https://i.imgur.com/qrWbOue.gifv'],
            ['https://i.redd.it/3lld01w00qlz.gif'],
            ['https://i.imgur.com/Kt6HUl8.jpg'],
            ['https://i.redd.it/2rbvjstdfplz.jpg'],
            ['https://twitter.com/elonmusk/status/908108029777686528'],
        ]


def test_subreddit_open_with_mailcap(subreddit_page, terminal):
    subreddit_page.refresh_content(order='ignore', name='/r/front/hot')
    terminal.config['enable_media'] = True
    terminal.config.MAILCAP = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tuir', 'templates', 'mailcap')
    with mock.patch('os.system'), \
            mock.patch('tuir.terminal.Process', side_effect=MockProcess), \
            mock.patch('subprocess.Popen', side_effect=MockPopen) as popen, \
            mock.patch('webbrowser.open_new_tab') as new_tab, \
            mock.patch('six.moves.input'):
        for i in range(8):
            subreddit_page.controller.trigger('o')
            with mock.patch.object(subreddit_page, 'clear_input_queue'):
                subreddit_page.controller.trigger('j')
                subreddit_page.controller.trigger('j')
                subreddit_page.controller.trigger('j')
        assert [list(i.args) for i in new_tab.mock_calls] == [
            ['https://twitter.com/DOOM/status/908094489276928001'],
            ['https://twitter.com/elonmusk/status/908108029777686528'],
        ]
        assert [list(i.args) for i in popen.mock_calls] == [
            [["curl -s 'https://i.redd.it/czlc1ff2tqlz.jpg' | convert -resize 80x80 - jpg:/tmp/tuir.jpg && img2xterm /tmp/tuir.jpg"]],
            [["mpv -vo drm -quiet 'https://i.imgur.com/ok9H05N.mp4'"]],
            [["mpv -vo drm -quiet 'https://i.imgur.com/qrWbOue.mp4'"]],
            [["curl -s 'https://i.redd.it/3lld01w00qlz.gif' | convert -resize 80x80 - jpg:/tmp/tuir.jpg && img2xterm /tmp/tuir.jpg"]],
            [["curl -s 'https://i.imgur.com/Kt6HUl8.jpg' | convert -resize 80x80 - jpg:/tmp/tuir.jpg && img2xterm /tmp/tuir.jpg"]],
            [["curl -s 'https://i.redd.it/2rbvjstdfplz.jpg' | convert -resize 80x80 - jpg:/tmp/tuir.jpg && img2xterm /tmp/tuir.jpg"]],
        ]

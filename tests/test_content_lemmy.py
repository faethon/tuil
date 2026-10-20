# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from tuil import exceptions
from tuil.api import (
    Comment,
    Community,
    Notification,
    Post,
    PrivateMessage,
)
from tuil.api.paging import Pager
from tuil.content import (
    Content,
    InboxContent,
    SubmissionContent,
    SubredditContent,
    SubscriptionContent,
)

FIXTURES = Path(__file__).parent / 'api' / 'fixtures'


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def post_data(index=0):
    return fixture('post_list.json')['posts'][index]


def comment_data(index=0):
    return fixture('comment_list.json')['comments'][index]


class FakeClient(object):
    instance = 'https://lemmy.ml'

    def __init__(self, logged_in=False, v4=False):
        self.logged_in = logged_in
        self.v4 = v4
        self.calls = []
        self.posts = [Post(self, post_data(i)) for i in (0, 2)]
        self.comments = [Comment(self, comment_data(i)) for i in range(6)]
        self.post = Post(self, post_data(0))
        self.communities = [
            Community(self, item)
            for item in fixture('community_list.json')['communities']]
        self.community = Community(
            self, fixture('community.json')['community_view'])

    @property
    def is_logged_in(self):
        return self.logged_in

    def supports_v4(self):
        return self.v4

    def me(self, refresh=False):
        if not self.logged_in:
            return None
        from tuil.api import User
        return User(self, {'person': {'id': 1, 'name': 'alice'}})

    def list_posts(self, **kwargs):
        self.calls.append(('list_posts', kwargs))
        return iter(self.posts)

    def list_user_posts(self, user, **kwargs):
        self.calls.append(('list_user_posts', user, kwargs))
        return iter(self.posts)

    def list_saved(self, **kwargs):
        self.calls.append(('list_saved', kwargs))
        return iter(self.posts + self.comments)

    def list_liked(self, **kwargs):
        self.calls.append(('list_liked', kwargs))
        return iter(self.posts + self.comments)

    def list_hidden(self, **kwargs):
        self.calls.append(('list_hidden', kwargs))
        return iter(self.posts)

    def list_user_comments(self, user, **kwargs):
        self.calls.append(('list_user_comments', user, kwargs))
        return iter(self.comments)

    def list_user_content(self, user, **kwargs):
        self.calls.append(('list_user_content', user, kwargs))
        return iter(self.posts + self.comments)

    def list_comments(self, **kwargs):
        self.calls.append(('list_comments', kwargs))
        return iter(self.comments)

    def get_community(self, community):
        self.calls.append(('get_community', community))
        return self.community

    def get_post(self, post_id, comment_id=None):
        self.calls.append(('get_post', post_id, comment_id))
        return self.post

    def get_comment(self, comment_id):
        self.calls.append(('get_comment', comment_id))
        return self.comments[0]

    def search(self, query, **kwargs):
        self.calls.append(('search', query, kwargs))
        return type('Results', (), {
            'posts': self.posts,
            'communities': self.communities,
        })()


class Loader(object):
    exception = None

    @contextmanager
    def __call__(self, *args, **kwargs):
        yield


@pytest.fixture()
def config():
    return {'look_and_feel': 'default', 'post_format': None}


def test_subscription_search_qualifies_and_deduplicates():
    client = FakeClient()
    first = client.communities[0]
    client.communities = [first, first, client.communities[1]]

    content = SubscriptionContent.from_search(client, Loader(), 'tech')

    assert content.name == 'Search Communities: tech'
    assert client.calls[0] == (
        'search', 'tech',
        {'type_': 'Communities', 'page': 1, 'limit': 50})
    assert content.get(0)['name'] == '/c/technology@lemmy.world'
    assert content.get(0)['title'] == 'Technology (88,892 members)'
    assert content.get(1)['name'] == '/c/piracy@lemmy.dbzer0.com'
    with pytest.raises(IndexError):
        content.get(2)

    content.sort('members')
    assert content.get(0)['name'] == '/c/technology@lemmy.world'
    assert content.get(1)['name'] == '/c/piracy@lemmy.dbzer0.com'

    content.sort('name')
    assert content.get(0)['name'] == '/c/piracy@lemmy.dbzer0.com'
    assert content.get(1)['name'] == '/c/technology@lemmy.world'


def test_subscription_search_rejects_empty_results():
    client = FakeClient()
    client.communities = []

    with pytest.raises(exceptions.SubscriptionError):
        SubscriptionContent.from_search(client, Loader(), 'missing')


def test_strip_submission_link_and_selfpost():
    client = FakeClient()
    link = Content.strip_submission(Post(client, post_data(0)))
    assert link['type'] == 'Submission'
    assert link['url_type'] == 'external'
    assert link['url_full'].endswith('.webm')
    assert link['comments'] == 0

    selfpost = Content.strip_submission(Post(client, post_data(2)))
    assert selfpost['url_type'] == 'selfpost'
    assert selfpost['url_full'] == selfpost['permalink']
    assert selfpost['text']
    assert selfpost['subreddit']


def test_strip_comment_and_edited_marker():
    comment = Content.strip_comment(Comment(FakeClient(), comment_data(0)), level=2)
    assert comment['type'] == 'Comment'
    assert comment['level'] == 2
    assert comment['body']
    assert comment['likes'] is None


def test_flatten_comments_assigns_nested_levels():
    client = FakeClient()
    comments = [Comment(client, comment_data(i)) for i in range(8)]
    flat = Content.flatten_comments(comments)
    levels = {c.id: c.nested_level for c in flat}
    assert levels[2273497] == 0
    assert levels[2273642] == 1
    assert levels[2277204] == 2
    assert levels[2274384] == 0


def test_submission_content_loads_and_toggles_comments():
    client = FakeClient()
    content = SubmissionContent(client, client.post, Loader())
    assert content.range == (-1, 5)
    assert content.get(-1)['type'] == 'Submission'
    assert content.get(1)['level'] == 1
    content.toggle(1)
    assert content.get(1)['type'] == 'HiddenComment'
    content.toggle(1)
    assert content.get(1)['type'] == 'Comment'


@pytest.mark.parametrize('url,post_id,comment_id', [
    ('https://lemmy.ml/post/123', 123, None),
    ('/post/456', 456, None),
    ('https://other.example/c/linux/p/789/name', 789, None),
    ('https://lemmy.ml/comment/321', None, 321),
    ('42', 42, None),
])
def test_parse_submission_url(url, post_id, comment_id):
    assert SubmissionContent._parse_url(FakeClient(), url) == (post_id, comment_id)


def test_parse_submission_url_rejects_unknown():
    with pytest.raises(exceptions.SubmissionError):
        SubmissionContent._parse_url(FakeClient(), 'https://lemmy.ml/c/linux')


@pytest.mark.parametrize('name,kind,resource,room,order,period,display', [
    ('linux', 'community', 'linux', None, None, None, '/c/linux'),
    ('/c/linux/top-week', 'community', 'linux', None, 'top', 'week',
     '/c/linux'),
    ('/r/all/new', 'listing', 'all', None, 'new', None, '/c/all'),
    ('front/top-all', 'listing', 'front', None, 'top', 'all', '/c/front'),
    ('u/alice/comments', 'user', 'alice', 'comments', 'new', None,
     '/u/alice/comments'),
    ('u/alice/top-month', 'user', 'alice', 'overview', 'top', 'month',
     '/u/alice'),
    ('u/me/saved', 'user', 'me', 'saved', 'new', None, '/u/me/saved'),
])
def test_parse_names(name, kind, resource, room, order, period, display):
    parsed = SubredditContent._parse_name(name)
    assert parsed['kind'] == kind
    assert parsed['resource'] == resource
    assert parsed['room'] == room
    assert parsed['order'] == order
    assert parsed['period'] == period
    assert parsed['display_name'] == display


@pytest.mark.parametrize('name', [
    'u/alice/m/friends',
    'domain/example.com',
    'all/gilded',
    'linux/invalid-order',
])
def test_parse_names_rejects_unsupported(name):
    with pytest.raises(exceptions.SubredditError):
        SubredditContent._parse_name(name)


@pytest.mark.parametrize('order,period,expected', [
    (None, None, 'Hot'),
    ('hot', None, 'Hot'),
    ('top', 'day', 'TopDay'),
    ('top', 'all', 'TopAll'),
    ('rising', None, 'Active'),
    ('controversial', 'week', 'Controversial'),
    ('new', None, 'New'),
])
def test_post_sort(order, period, expected):
    assert SubredditContent._post_sort(order, period) == expected


def test_listing_front_is_local_when_anonymous(config):
    client = FakeClient()
    content = SubredditContent.from_name(client, config, 'front', Loader())
    assert content.name == '/c/front'
    assert content.order is None
    assert client.calls[-1] == (
        'list_posts', {'type_': 'Local', 'sort': 'Hot', 'page_size': 50})


def test_listing_preserves_full_sort_order(config):
    client = FakeClient()
    content = SubredditContent.from_name(
        client, config, '/c/all', Loader(), order='top-week')
    assert content.order == 'top-week'
    assert client.calls[-1][1]['sort'] == 'TopWeek'


def test_listing_subscribed_requires_login(config):
    with pytest.raises(exceptions.AccountError):
        SubredditContent.from_name(
            FakeClient(), config, 'subscribed', Loader())


def test_community_and_user_listings(config):
    client = FakeClient()
    content = SubredditContent.from_name(client, config, 'linux', Loader())
    assert content.name == '/c/linux'
    assert content.member_count == 68180
    assert client.calls[-1][1]['community'] == 'linux'

    content = SubredditContent.from_name(
        client, config, 'u/alice/comments', Loader())
    assert content.name == '/u/alice/comments'
    assert client.calls[-1][0] == 'list_user_comments'
    assert client.calls[-1][1] == 'alice'


def test_private_user_rooms_require_the_same_user(config):
    client = FakeClient()
    with pytest.raises(exceptions.SubredditError):
        SubredditContent.from_name(
            client, config, 'u/alice/saved', Loader())

    client = FakeClient(logged_in=True)
    content = SubredditContent.from_name(
        client, config, 'u/me/saved', Loader())
    assert content.name == '/u/alice/saved'
    assert client.calls[-1][0] == 'list_posts'


def test_saved_content_uses_v4_backend(config):
    client = FakeClient(logged_in=True, v4=True)
    content = SubredditContent.from_name(
        client, config, 'u/me/saved', Loader())
    assert client.calls[-1][0] == 'list_saved'
    assert content.get(0)['type'] == 'Submission'
    assert content.get(2)['type'] == 'SavedComment'


def test_liked_and_hidden_content_use_v4(config):
    client = FakeClient(logged_in=True, v4=True)
    content = SubredditContent.from_name(
        client, config, 'u/me/upvoted', Loader())
    assert client.calls[-1][0] == 'list_liked'
    assert client.calls[-1][1]['like_type'] == 'liked_only'
    assert content.get(2)['type'] == 'SavedComment'

    content = SubredditContent.from_name(
        client, config, 'u/me/hidden', Loader())
    assert client.calls[-1][0] == 'list_hidden'
    assert content.get(0)['type'] == 'Submission'


def test_hidden_content_requires_v4(config):
    client = FakeClient(logged_in=True)
    with pytest.raises(exceptions.SubredditError):
        SubredditContent.from_name(
            client, config, 'u/me/hidden', Loader())


def test_search_is_paginated(config):
    client = FakeClient()
    content = SubredditContent.from_name(
        client, config, 'linux', Loader(), query='kernel')
    assert content.query == 'kernel'
    assert content.get(0)['type'] == 'Submission'
    assert client.calls[-1][0] == 'search'
    assert client.calls[-1][2]['community'] == 'linux'


def test_saved_comment_in_user_listing_is_rendered(config):
    client = FakeClient()
    content = SubredditContent.from_name(
        client, config, 'u/alice/comments', Loader())
    data = content.get(0)
    assert data['type'] == 'SavedComment'
    assert '[Comment]' in data['title']
    assert data['body'] == data['text']
    assert data['html'] == data['body']


def test_sent_message_detection():
    sent = type('Message', (), {
        'is_private_message': True,
        'creator_id': 7,
    })()
    received = type('Message', (), {
        'is_private_message': True,
        'creator_id': 2,
    })()
    comment = type('Comment', (), {'creator_id': 7})()

    assert InboxContent._is_sent_message(sent, 7) is True
    assert InboxContent._is_sent_message(received, 7) is False
    assert InboxContent._is_sent_message(comment, 7) is False
    assert InboxContent._is_sent_message(sent, None) is False

    comment_reply = type('Item', (), {'data_type': 'comment'})()
    post_reply = type('Item', (), {'data_type': 'post'})()
    items = [comment_reply, post_reply, sent, received]
    assert InboxContent._filter_items(items, 'comments', 7, True) == [
        comment_reply]
    assert InboxContent._filter_items(items, 'posts', 7, True) == [
        post_reply]
    assert InboxContent._filter_items(items, 'all', 7, True) == [
        comment_reply, post_reply, received]


def test_strip_private_message():
    message = PrivateMessage(FakeClient(logged_in=True), {
        'private_message': {
            'id': 7,
            'content': 'Hello there',
            'read': False,
            'published': '2026-10-20T08:00:00Z',
        },
        'creator': {'id': 2, 'name': 'bob'},
        'recipient': {'id': 1, 'name': 'alice'},
    })
    data = Content.strip_message(message, username='alice')
    assert data['type'] == 'Message'
    assert data['subject'] == 'Private message'
    assert data['author'] == 'bob'
    assert data['is_new'] is True
    assert data['was_comment'] is False


def test_strip_v4_notification():
    client = FakeClient(logged_in=True)
    view = comment_data(0)
    comment = dict(view['comment'])
    comment['published_at'] = comment.pop('published')
    comment.update(view['counts'])
    notification = Notification(client, {
        'notification': {
            'id': 12,
            'creator_id': view['creator']['id'],
            'recipient_id': 1,
            'kind': 'mention',
            'read': False,
            'published_at': '2026-10-20T09:45:00Z',
        },
        'data': {
            'type_': 'comment',
            'comment': comment,
            'creator': view['creator'],
            'post': view['post'],
            'community': view['community'],
        },
    })
    data = Content.strip_message(notification, username='alice')
    assert data['type'] == 'InboxComment'
    assert data['subject'] == 'mention'
    assert data['author'] == view['creator']['name']
    assert data['subreddit_name'] == view['community']['name']
    assert data['permalink'].endswith('/comment/{}'.format(comment['id']))


def test_pager_in_content_is_consumed_lazily():
    client = FakeClient()
    pager = Pager(lambda page: (client.posts, False))
    content = SubredditContent(
        {'look_and_feel': 'compact', 'post_format': None},
        '/c/front', pager, Loader(), client=client)
    assert content.get(0)['n_rows'] == 2

# -*- coding: utf-8 -*-
"""Tests for the Lemmy API client.

Live response shapes are captured in ``fixtures/``.  Write endpoints use small
synthetic responses built from those shapes; the test suite never touches the
network.
"""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from tuil.api import (
    AuthenticationError,
    BadRequestError,
    InvalidResponseError,
    LemmyClient,
    NotFoundError,
    RateLimitError,
    ServerError,
    normalize_instance,
)
from tuil.api.models import image_proxy_target
from tuil.api.paging import Pager

FIXTURES = Path(__file__).parent / 'fixtures'
INSTANCE = 'https://lemmy.ml'
API = INSTANCE + '/api/v3'
API4 = INSTANCE + '/api/v4'


def fixture(name):
    with open(FIXTURES / name, encoding='utf-8') as fp:
        return json.load(fp)


def post_view(index=0):
    return fixture('post_list.json')['posts'][index]


def comment_view(index=0):
    return fixture('comment_list.json')['comments'][index]


def community_view():
    return fixture('community.json')['community_view']


def user_view():
    return fixture('user.json')['person_view']


def site_with_user():
    data = fixture('site.json')
    user = fixture('user.json')
    data = dict(data)
    data['my_user'] = {
        'local_user_view': {
            'person': user['person_view']['person'],
            'counts': user['person_view']['counts'],
        },
        'follows': [],
        'moderates': [],
        'community_blocks': [],
        'instance_blocks': [],
        'person_blocks': [],
        'discussion_languages': [0, 1],
    }
    return data


def reply_view():
    data = dict(comment_view())
    data['comment_reply'] = {
        'id': 77,
        'recipient_id': user_view()['person']['id'],
        'comment_id': data['comment']['id'],
        'read': False,
        'published': data['comment']['published'],
    }
    data['recipient'] = user_view()['person']
    return data


def mention_view():
    data = reply_view()
    data.pop('comment_reply')
    data['person_mention'] = {
        'id': 88,
        'recipient_id': user_view()['person']['id'],
        'comment_id': data['comment']['id'],
        'read': False,
        'published': data['comment']['published'],
    }
    return data


def message_view():
    person = user_view()['person']
    other = dict(person)
    other['id'] = person['id'] + 1
    other['name'] = 'other_user'
    return {
        'private_message': {
            'id': 99,
            'creator_id': other['id'],
            'recipient_id': person['id'],
            'content': 'hello from the other side',
            'deleted': False,
            'read': False,
            'published': '2026-10-20T09:00:00Z',
            'updated': None,
            'ap_id': 'https://lemmy.ml/private_message/99',
            'local': True,
        },
        'creator': other,
        'recipient': person,
    }


def add_json(method, path, payload, **kwargs):
    responses.add(method, API + path, json=payload, **kwargs)


def request_query(request):
    return parse_qs(urlsplit(request.url).query)


def test_normalize_instance():
    assert normalize_instance('lemmy.ml') == 'https://lemmy.ml'
    assert normalize_instance('https://lemmy.ml/') == 'https://lemmy.ml'
    assert normalize_instance('https://lemmy.ml/api/v3') == 'https://lemmy.ml'
    assert normalize_instance('http://localhost:8536/') == 'http://localhost:8536'
    with pytest.raises(ValueError):
        normalize_instance('ftp://lemmy.ml')
    with pytest.raises(ValueError):
        normalize_instance('')


@responses.activate
def test_site_metadata():
    add_json(responses.GET, '/site', fixture('site.json'))
    client = LemmyClient('lemmy.ml')
    site = client.site()

    assert site.version == '0.19.20'
    assert site.name == 'Lemmy'
    assert site.default_language_id == 0
    assert site.enable_downvotes is True
    assert site.enable_nsfw is True
    assert site.federation_enabled is True
    assert len(site.admins) == 6
    assert site.admins[0].name
    assert site.my_user is None
    assert client.me() is None
    assert client.user_id is None
    assert len(responses.calls) == 1


@responses.activate
def test_list_posts_and_model_properties():
    add_json(responses.GET, '/post/list', fixture('post_list.json'))
    client = LemmyClient('lemmy.ml')
    posts = client.list_posts(
        type_='Local', sort='Hot', page_size=5, max_items=5).take(10)

    assert len(posts) == 5
    query = request_query(responses.calls[0].request)
    assert query['type_'] == ['Local']
    assert query['sort'] == ['Hot']
    assert query['page'] == ['1']
    assert query['limit'] == ['5']

    post = posts[0]
    assert post.id == 54255716
    assert post.title == 'wait so mp4 works'
    assert post.author == 'neketos851'
    assert post.community_name == 'test'
    assert post.score == 1
    assert post.upvotes == 1
    assert post.comments_count == 0
    assert post.created_utc > 0
    assert post.permalink == INSTANCE + '/post/54255716'
    assert post.saved is False
    assert post.read is False
    assert post.likes is None
    assert post.is_self is False

    assert posts[1].link_url.startswith('https://pixelfed.social/')
    assert '/api/v3/image_proxy' in posts[1].url

    self_post = posts[2]
    assert self_post.url is None
    assert self_post.is_self is True


@responses.activate
def test_post_pagination_is_lazy_and_capped():
    pages = {
        1: {'posts': [post_view(0), post_view(1)]},
        2: {'posts': [post_view(2)]},
    }
    seen_pages = []

    def callback(request):
        page = int(request_query(request)['page'][0])
        seen_pages.append(page)
        return (200, {'Content-Type': 'application/json'},
                json.dumps(pages.get(page, {'posts': []})))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API + '/post/list') + r'\?.*'),
        callback=callback)
    client = LemmyClient('lemmy.ml')
    posts = client.list_posts(page_size=2).take(10)

    assert [post.id for post in posts] == [
        post_view(0)['post']['id'],
        post_view(1)['post']['id'],
        post_view(2)['post']['id'],
    ]
    assert seen_pages == [1, 2]

    seen_pages[:] = []
    posts = LemmyClient('lemmy.ml').list_posts(
        page_size=2, max_items=2).take(10)
    assert len(posts) == 2
    assert seen_pages == [1]


def test_pager_skips_empty_pages_with_more():
    assert Pager(lambda page: [1]).take(0) == []
    pages = {
        1: ([], True),
        2: (['a'], True),
        3: (['b'], False),
    }
    pager = Pager(lambda page: pages[page])
    assert list(pager) == ['a', 'b']


@responses.activate
def test_comments_path_depth_and_parent():
    add_json(responses.GET, '/comment/list', fixture('comment_list.json'))
    client = LemmyClient('lemmy.ml')
    comments = client.list_comments(
        post=2821112, sort='Top', max_depth=8, page_size=8,
        max_items=8).take(20)

    assert len(comments) == 8
    first = comments[0]
    assert first.id == 2273497
    assert first.post_id == 2821112
    assert first.path == '0.2273497'
    assert first.depth == 1
    assert first.parent_id is None
    assert first.author
    assert first.community_name
    assert first.score > 0
    assert first.permalink == INSTANCE + '/comment/2273497'
    assert isinstance(first.is_op, bool)

    nested = [item for item in comments if item.depth == 2][0]
    assert nested.parent_id in [item.id for item in comments]
    assert nested.depth == 2

    query = request_query(responses.calls[0].request)
    assert query['post_id'] == ['2821112']
    assert query['sort'] == ['Top']
    assert query['max_depth'] == ['8']
    assert query['limit'] == ['8']


@responses.activate
def test_get_comment():
    view = comment_view()
    add_json(responses.GET, '/comment', {'comment_view': view})
    client = LemmyClient('lemmy.ml')
    comment = client.get_comment(view['comment']['id'])
    assert comment.id == view['comment']['id']
    assert request_query(responses.calls[0].request)['id'] == [
        str(view['comment']['id'])]


@responses.activate
def test_community_details():
    add_json(responses.GET, '/community', fixture('community.json'))
    client = LemmyClient('lemmy.ml')
    community = client.get_community('linux')

    assert community.id == community_view()['community']['id']
    assert community.name == 'linux'
    assert community.title == 'Linux'
    assert community.subscribers == 68180
    assert community.subscribed is False
    assert len(community.moderators) == 6
    assert community.moderators[0].name == 'AgreeableLandscape'
    assert community.permalink == INSTANCE + '/c/linux'
    assert request_query(responses.calls[0].request)['name'] == ['linux']


@responses.activate
def test_user_details_and_content():
    add_json(responses.GET, '/user', fixture('user.json'))
    client = LemmyClient('lemmy.ml')
    user = client.get_user('dessalines')

    assert user.id == 34
    assert user.name == 'dessalines'
    assert user.post_count == 1118
    assert user.comment_count == 9016
    assert user.permalink == INSTANCE + '/u/dessalines'
    assert len(user.recent_posts) == 3
    assert len(user.recent_comments) == 3
    assert len(user.moderates) == 3
    assert user.recent_posts[0].author == 'dessalines'
    query = request_query(responses.calls[0].request)
    assert query['username'] == ['dessalines']
    assert query['limit'] == ['50']


@responses.activate
def test_user_content_pager_continues_past_empty_kind():
    pages = {
        1: {'posts': [post_view(0), post_view(1)], 'comments': [comment_view(0)]},
        2: {'posts': [], 'comments': [comment_view(1)]},
        3: {'posts': [], 'comments': []},
    }
    seen = []

    def callback(request):
        page = int(request_query(request)['page'][0])
        seen.append(page)
        return (200, {'Content-Type': 'application/json'},
                json.dumps(pages[page]))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API + '/user') + r'\?.*'),
        callback=callback)
    client = LemmyClient('lemmy.ml')
    posts = client.list_user_posts('dessalines', page_size=2).take(10)

    assert len(posts) == 2
    assert seen == [1, 2, 3]


@responses.activate
def test_user_content_pager_combines_posts_and_comments():
    pages = {
        1: {'posts': [post_view(0)], 'comments': [comment_view(0)]},
        2: {'posts': [], 'comments': []},
    }
    seen = []

    def callback(request):
        page = int(request_query(request)['page'][0])
        seen.append(page)
        return (200, {'Content-Type': 'application/json'},
                json.dumps(pages[page]))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API + '/user') + r'\?.*'),
        callback=callback)
    client = LemmyClient('lemmy.ml')
    items = client.list_user_content('dessalines', page_size=2).take(10)

    assert len(items) == 2
    assert items[0].title == post_view(0)['post']['name']
    assert items[1].content == comment_view(0)['comment']['content']
    assert seen == [1, 2]


@responses.activate
def test_search_results():
    add_json(responses.GET, '/search', fixture('search.json'))
    client = LemmyClient('lemmy.ml')
    results = client.search(
        'linux', type_='Posts', sort='TopAll', listing_type='All', limit=3)

    assert results.type == 'Posts'
    assert len(results.posts) == 3
    assert results.comments == []
    assert results.communities == []
    assert results.users == []
    assert results.total == 3
    assert results.posts[0].title == 'It either runs on Linux or refund'
    query = request_query(responses.calls[0].request)
    assert query['q'] == ['linux']
    assert query['type_'] == ['Posts']
    assert query['sort'] == ['TopAll']
    assert query['listing_type'] == ['All']
    assert query['limit'] == ['3']

    with pytest.raises(ValueError):
        client.search('')


@responses.activate
def test_login_and_authenticated_request():
    add_json(responses.POST, '/user/login', {
        'jwt': 'test-jwt',
        'registration_created': False,
        'verify_email_sent': False,
    })
    add_json(responses.GET, '/site', site_with_user())
    add_json(responses.GET, '/post/list', {'posts': []})
    client = LemmyClient('lemmy.ml')

    user = client.login('dessalines', 'secret', totp_2fa_token=None)
    assert user.name == 'dessalines'
    assert client.is_logged_in is True
    assert client.token == 'test-jwt'
    assert client.user_id == 34
    assert client.me().name == 'dessalines'

    login_call = next(
        call for call in responses.calls
        if call.request.method == 'POST'
    )
    login_body = json.loads(login_call.request.body)
    assert login_body == {
        'username_or_email': 'dessalines',
        'password': 'secret',
        'totp_2fa_token': None,
    }

    list(client.list_posts(page_size=1).take(1))
    auth = responses.calls[-1].request.headers['Authorization']
    assert auth == 'Bearer test-jwt'

    client.logout()
    assert client.is_logged_in is False
    assert client.token is None


@responses.activate
def test_v4_login_uses_account_endpoint():
    add_json4(responses.POST, '/account/auth/login', {
        'jwt': 'v4-jwt',
        'registration_created': False,
        'verify_email_sent': False,
    })
    add_json4(responses.GET, '/site', site_with_user())
    add_json4(responses.POST, '/account/auth/logout', {'success': True})
    client = LemmyClient('lemmy.ml', api_version=4)

    user = client.login('dessalines', 'secret', totp_2fa_token=None)

    assert user.name == 'dessalines'
    assert client.token == 'v4-jwt'
    login_body = json.loads(responses.calls[0].request.body)
    assert login_body == {
        'username_or_email': 'dessalines',
        'password': 'secret',
        'totp_2fa_token': None,
        'stay_logged_in': True,
    }

    client.logout()
    assert client.is_logged_in is False
    assert responses.calls[-1].request.url == (
        INSTANCE + '/api/v4/account/auth/logout')


@responses.activate
def test_set_token_marks_client_logged_in():
    client = LemmyClient('lemmy.ml')
    assert client.is_logged_in is False
    client.set_token('jwt')
    assert client.is_logged_in is True
    client.logout()
    assert client.is_logged_in is False


@responses.activate
def test_http_errors_are_mapped():
    add_json(responses.GET, '/site', {
        'error': 'incorrect_login', 'message': 'incorrect login',
    }, status=401)
    client = LemmyClient('lemmy.ml')
    with pytest.raises(AuthenticationError) as excinfo:
        client.site()
    assert excinfo.value.status_code == 401
    assert excinfo.value.code == 'incorrect_login'

    responses.reset()
    add_json(responses.GET, '/site', {'error': 'not_found'}, status=404)
    with pytest.raises(NotFoundError):
        LemmyClient('lemmy.ml').site()

    responses.reset()
    add_json(responses.GET, '/site', {'error': 'bad'}, status=400)
    with pytest.raises(BadRequestError):
        LemmyClient('lemmy.ml').site()


@responses.activate
def test_rate_limit_and_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr('tuil.api.http.time.sleep',
                        lambda seconds: sleeps.append(seconds))
    add_json(responses.GET, '/site', {'error': 'rate_limited'},
             status=429, headers={'Retry-After': '2'})
    with pytest.raises(RateLimitError) as excinfo:
        LemmyClient('lemmy.ml', max_retries=0).site()
    assert excinfo.value.retry_after == 2
    assert sleeps == []

    responses.reset()
    add_json(responses.GET, '/site', {'error': 'oops'}, status=500)
    add_json(responses.GET, '/site', fixture('site.json'))
    site = LemmyClient('lemmy.ml', max_retries=1).site()
    assert site.version == '0.19.20'
    assert sleeps == [1]
    assert len(responses.calls) == 2


@responses.activate
def test_server_error_without_retries():
    add_json(responses.GET, '/site', {'error': 'oops'}, status=503)
    with pytest.raises(ServerError):
        LemmyClient('lemmy.ml', max_retries=0).site()


@responses.activate
def test_invalid_json():
    responses.add(responses.GET, API + '/site', body='not json',
                  status=200, content_type='text/plain')
    with pytest.raises(InvalidResponseError):
        LemmyClient('lemmy.ml').site()


@responses.activate
def test_get_cache_and_invalidation():
    add_json(responses.GET, '/site', fixture('site.json'))
    add_json(responses.POST, '/post/like', {'post_view': post_view()})
    add_json(responses.GET, '/site', fixture('site.json'))
    client = LemmyClient('lemmy.ml')

    client.site()
    client.site()
    assert len(responses.calls) == 1

    client.vote_post(post_view()['post']['id'], 1)
    client.site()
    assert len(responses.calls) == 3

    client.clear_cache()
    client.site()
    assert len(responses.calls) == 4


@responses.activate
def test_vote_save_and_read_state():
    post_id = post_view()['post']['id']
    add_json(responses.POST, '/post/like', {'post_view': post_view()})
    add_json(responses.PUT, '/post/save', {'post_view': post_view()})
    add_json(responses.GET, '/site', fixture('site.json'))
    add_json(responses.POST, '/post/mark_as_read', {})
    client = LemmyClient('lemmy.ml')

    post = client.vote_post(post_id, 1)
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': post_id, 'score': 1}
    assert post.id == post_id
    with pytest.raises(ValueError):
        client.vote_post(post_id, 2)

    client.save_post(post_id, False)
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': post_id, 'save': False}

    assert client.mark_post_read(post_id, False) == {}
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': post_id, 'read': False}


@responses.activate
def test_comment_actions():
    view = comment_view()
    comment_id = view['comment']['id']
    add_json(responses.POST, '/comment/like', {'comment_view': view})
    add_json(responses.PUT, '/comment/save', {'comment_view': view})
    add_json(responses.POST, '/comment', {'comment_view': view})
    add_json(responses.PUT, '/comment', {'comment_view': view})
    add_json(responses.POST, '/comment/delete', {'comment_view': view})
    client = LemmyClient('lemmy.ml')

    client.vote_comment(comment_id, -1)
    assert json.loads(responses.calls[-1].request.body) == {
        'comment_id': comment_id, 'score': -1}

    client.save_comment(comment_id)
    assert json.loads(responses.calls[-1].request.body) == {
        'comment_id': comment_id, 'save': True}

    client.create_comment(view['post']['id'], 'hello', parent_id=comment_id,
                          language_id=0)
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': view['post']['id'],
        'content': 'hello',
        'parent_id': comment_id,
        'language_id': 0,
    }

    client.edit_comment(comment_id, 'edited', language_id=0)
    assert json.loads(responses.calls[-1].request.body) == {
        'comment_id': comment_id, 'content': 'edited', 'language_id': 0}

    client.delete_comment(comment_id)
    assert json.loads(responses.calls[-1].request.body) == {
        'comment_id': comment_id, 'deleted': True}


@responses.activate
def test_create_and_edit_post_and_follow():
    view = post_view()
    community = community_view()
    add_json(responses.POST, '/post', {'post_view': view})
    add_json(responses.POST, '/post/delete', {'post_view': view})
    add_json(responses.POST, '/community/follow',
             {'community_view': community})
    client = LemmyClient('lemmy.ml')

    post = client.create_post(
        892, 'Title', url='https://example.com', nsfw=True, language_id=0)
    assert post.id == view['post']['id']
    assert json.loads(responses.calls[-1].request.body) == {
        'name': 'Title', 'community_id': 892, 'nsfw': True,
        'url': 'https://example.com', 'language_id': 0}

    client.edit_post(view['post']['id'], name='New title', body='text')
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': view['post']['id'], 'name': 'New title', 'body': 'text'}

    client.delete_post(view['post']['id'])
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': view['post']['id'], 'deleted': True}

    followed = client.follow_community(892, True)
    assert followed.name == 'linux'
    assert json.loads(responses.calls[-1].request.body) == {
        'community_id': 892, 'follow': True}

    with pytest.raises(ValueError):
        client.create_post(892, '')


@responses.activate
def test_inbox():
    reply = reply_view()
    mention = mention_view()
    message = message_view()
    add_json(responses.GET, '/site', fixture('site.json'))
    add_json(responses.GET, '/user/replies', {'replies': [reply]})
    add_json(responses.GET, '/user/mention', {'mentions': [mention]})
    add_json(responses.GET, '/private_message/list',
             {'private_messages': [message]})
    add_json(responses.GET, '/user/unread_count',
             {'replies': 1, 'mentions': 2, 'private_messages': 3})
    add_json(responses.POST, '/comment/mark_as_read',
             {'comment_reply_view': reply})
    add_json(responses.POST, '/user/mention/mark_as_read',
             {'person_mention_view': mention})
    add_json(responses.POST, '/private_message/mark_as_read',
             {'private_message_view': message})
    add_json(responses.POST, '/private_message',
             {'private_message_view': message})
    client = LemmyClient('lemmy.ml')

    replies = client.list_replies(unread_only=True).take(1)
    assert replies[0].id == 77
    assert replies[0].comment_id == reply['comment']['id']
    assert replies[0].post_id == reply['post']['id']
    assert replies[0].score > 0
    assert replies[0].permalink.endswith('/comment/{}'.format(
        reply['comment']['id']))
    assert request_query(responses.calls[-1].request)['unread_only'] == [
        'true']

    replies[0].mark_read()
    assert json.loads(responses.calls[-1].request.body) == {
        'comment_reply_id': 77, 'read': True}

    mentions = client.list_mentions().take(1)
    assert mentions[0].id == 88
    mentions[0].mark_read()
    assert json.loads(responses.calls[-1].request.body) == {
        'person_mention_id': 88, 'read': True}

    messages = client.list_messages().take(1)
    assert messages[0].id == 99
    assert messages[0].creator.name == 'other_user'
    messages[0].mark_read()
    assert json.loads(responses.calls[-1].request.body) == {
        'private_message_id': 99, 'read': True}

    count = client.unread_count()
    assert count.replies == 1
    assert count.mentions == 2
    assert count.private_messages == 3
    assert count.total == 6

    sent = client.send_message(34, 'hi')
    assert sent.id == 99
    assert json.loads(responses.calls[-1].request.body) == {
        'content': 'hi', 'recipient_id': 34}


@responses.activate
def test_model_read_state_updates_locally():
    from tuil.api.models import Post
    view = post_view()
    add_json(responses.GET, '/site', fixture('site.json'))
    add_json(responses.POST, '/post/mark_as_read', {})
    client = LemmyClient('lemmy.ml')
    post = Post(client, view)
    post.mark_read(True)
    assert post.read is True
    post.mark_unread()
    assert post.read is False


def test_image_proxy_target():
    url = ('https://lemmy.ml/api/v3/image_proxy?url=https%3A%2F%2F'
           'example.com%2Fimage.jpg')
    assert image_proxy_target(url) == 'https://example.com/image.jpg'
    assert image_proxy_target(
        'https://lemmy.ml/api/v4/image/proxy?url=https%3A%2F%2F'
        'example.com%2Fimage.jpg') == 'https://example.com/image.jpg'
    assert image_proxy_target('https://example.com/a.jpg') == \
        'https://example.com/a.jpg'
    assert image_proxy_target(None) is None


def v4_post_item():
    view = post_view()
    post = dict(view['post'])
    post['published_at'] = post.pop('published')
    post.update(view['counts'])
    return {
        'type_': 'post',
        'post': post,
        'creator': view['creator'],
        'community': view['community'],
        'post_actions': {
            'read_at': '2026-10-20T09:30:00Z',
            'saved_at': '2026-10-20T09:30:00Z',
            'vote_is_upvote': True,
        },
    }


def v4_comment_item():
    view = comment_view()
    comment = dict(view['comment'])
    comment['published_at'] = comment.pop('published')
    comment.update(view['counts'])
    return {
        'type_': 'comment',
        'comment': comment,
        'creator': view['creator'],
        'post': view['post'],
        'community': view['community'],
        'comment_actions': {
            'saved_at': '2026-10-20T09:30:00Z',
            'vote_is_upvote': False,
        },
    }


def v4_notification(item, *, kind='reply', notification_id=501, read=False):
    data = dict(item)
    data['type_'] = item['type_']
    return {
        'notification': {
            'id': notification_id,
            'creator_id': item['creator']['id'],
            'recipient_id': user_view()['person']['id'],
            'kind': kind,
            'read': read,
            'published_at': '2026-10-20T09:45:00Z',
            'post_id': item.get('post', {}).get('id'),
            'comment_id': item.get('comment', {}).get('id'),
        },
        'data': data,
    }


def add_json4(method, path, payload, **kwargs):
    responses.add(method, INSTANCE + '/api/v4' + path, json=payload, **kwargs)


@responses.activate
def test_v4_inbox_notifications():
    comment = v4_notification(v4_comment_item())
    add_json4(responses.GET, '/account/notification/list', {
        'items': [comment],
        'next_page': 'cursor-2',
    })
    add_json4(responses.POST, '/account/notification/mark_as_read',
              {'success': True})
    client = LemmyClient('lemmy.ml', api_version=4)

    replies = client.list_replies(unread_only=True).take(1)
    assert len(replies) == 1
    reply = replies[0]
    assert reply.id == 501
    assert reply.kind == 'reply'
    assert reply.comment.content
    assert reply.post_id == comment['data']['post']['id']
    assert reply.community_name
    assert reply.created_utc is not None
    assert reply.my_vote == -1
    assert reply.saved is True

    query = request_query(responses.calls[-1].request)
    assert query['type_'] == ['reply']
    assert query['unread_only'] == ['true']

    reply.mark_read()
    assert json.loads(responses.calls[-1].request.body) == {
        'notification_id': 501, 'read': True}
    assert responses.calls[-1].request.url.endswith(
        '/api/v4/account/notification/mark_as_read')


@responses.activate
def test_v4_messages_and_unread_count():
    message = message_view()
    item = {
        'type_': 'private_message',
        'private_message': dict(message['private_message']),
        'creator': message['creator'],
        'recipient': message['recipient'],
    }
    item['private_message']['published_at'] = \
        item['private_message'].pop('published')
    notification = v4_notification(
        item, kind='private_message', notification_id=601)
    add_json4(responses.GET, '/account/notification/list', {
        'items': [notification],
    })
    add_json4(responses.GET, '/account/unread_counts', {
        'notification_count': 7,
        'report_count': 0,
        'pending_follow_count': 0,
        'registration_application_count': 0,
    })
    add_json4(responses.POST, '/account/notification/mark_as_read/all',
              {'success': True})
    client = LemmyClient('lemmy.ml', api_version=4)

    messages = client.list_messages().take(1)
    assert messages[0].is_private_message
    assert messages[0].content == 'hello from the other side'
    assert messages[0].creator.name == 'other_user'
    assert messages[0].recipient.name == user_view()['person']['name']

    count = client.unread_count()
    assert count.notifications == 7
    assert count.total == 7

    client.mark_all_read()
    assert responses.calls[-1].request.url.endswith(
        '/api/v4/account/notification/mark_as_read/all')


@responses.activate
def test_v4_saved_uses_cursor_pagination():
    add_json4(responses.GET, '/account/saved', {
        'items': [v4_post_item()],
        'next_page': 'cursor-2',
    })
    add_json4(responses.GET, '/account/saved', {
        'items': [v4_comment_item()],
    })
    client = LemmyClient('lemmy.ml', api_version=4)

    saved = client.list_saved(page_size=1).take(2)
    assert len(saved) == 2
    assert type(saved[0]).__name__ == 'Post'
    assert type(saved[1]).__name__ == 'Comment'
    assert saved[0].score == 1
    assert saved[0].saved is True
    assert saved[0].read is True
    assert saved[1].score > 0
    assert saved[1].saved is True

    queries = [request_query(call.request) for call in responses.calls]
    assert queries[0]['limit'] == ['1']
    assert 'page_cursor' not in queries[0]
    assert queries[1]['page_cursor'] == ['cursor-2']


@responses.activate
def test_v4_version_detection():
    add_json(responses.GET, '/site', {
        'version': '1.0.0-nightly',
        'site_view': {},
        'admins': [],
        'all_languages': [],
        'discussion_languages': [],
    })
    client = LemmyClient('lemmy.ml')
    assert client.supports_v4() is True
    # The version lookup is cached.
    assert client.supports_v4() is True
    assert len(responses.calls) == 1


@responses.activate
def test_v3_browsing_resolves_community_name_through_search():
    community = dict(post_view()['community'])

    def community_callback(request):
        query = request_query(request)
        if 'name' in query:
            return (400, {'Content-Type': 'application/json'},
                    json.dumps({'error': 'couldnt_find_community'}))
        return (200, {'Content-Type': 'application/json'},
                json.dumps({'community_view': {'community': community}}))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API + '/community') + r'\?.*'),
        callback=community_callback)
    add_json(responses.GET, '/search', {
        'communities': [{'community': community}],
    })
    add_json(responses.GET, '/post/list', {
        'posts': [post_view()],
    })
    client = LemmyClient('lemmy.ml')

    posts = client.list_posts(
        type_='All', sort='Hot', community='test', page_size=1).take(1)

    assert posts[0].community_name == community['name']
    queries = [request_query(call.request) for call in responses.calls]
    assert queries[0]['name'] == ['test']
    assert queries[1]['type_'] == ['Communities']
    assert queries[2]['id'] == [str(community['id'])]
    assert queries[3]['community_id'] == [str(community['id'])]


@responses.activate
def test_v3_user_content_resolves_remote_username():
    person = user_view()['person']
    data = fixture('user.json')

    def user_callback(request):
        query = request_query(request)
        if 'username' in query:
            return (404, {'Content-Type': 'application/json'},
                    json.dumps({'error': 'couldnt_find_person'}))
        return (200, {'Content-Type': 'application/json'}, json.dumps(data))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API + '/user') + r'\?.*'),
        callback=user_callback)
    add_json(responses.GET, '/search', {
        'users': [{'person': person}],
    })
    client = LemmyClient('lemmy.ml')

    items = client.list_user_content('dessalines', page_size=2).take(2)

    assert items
    queries = [request_query(call.request) for call in responses.calls]
    assert queries[0]['username'] == ['dessalines']
    assert queries[1]['type_'] == ['Users']
    assert queries[2]['person_id'] == [str(person['id'])]
    assert 'username' not in queries[2]


@responses.activate
def test_v4_browsing_resolves_community_and_sorts():
    community = dict(post_view()['community'])

    def community_callback(request):
        query = request_query(request)
        if 'name' in query:
            return (404, {'Content-Type': 'application/json'},
                    json.dumps({'error': 'not_found'}))
        return (200, {'Content-Type': 'application/json'},
                json.dumps({'community_view': {'community': community}}))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API4 + '/community') + r'\?.*'),
        callback=community_callback)
    add_json4(responses.GET, '/search', {
        'communities': [{'community': community}],
    })
    add_json4(responses.GET, '/post/list', {
        'items': [v4_post_item()],
    })
    client = LemmyClient('lemmy.ml', api_version=4)

    posts = client.list_posts(
        type_='All', sort='TopDay', community='test', page_size=1).take(1)

    assert posts[0].title == post_view(0)['post']['name']
    assert posts[0].community_id == community['id']
    queries = [request_query(call.request) for call in responses.calls]
    assert queries[0]['name'] == ['test']
    assert queries[1]['type_'] == ['communities']
    assert queries[2]['id'] == [str(community['id'])]
    assert queries[3]['community_id'] == [str(community['id'])]
    assert queries[3]['type_'] == ['all']
    assert queries[3]['sort'] == ['top']
    assert queries[3]['time_range_seconds'] == ['86400']
    assert queries[3]['show_read'] == ['true']


@responses.activate
def test_community_cache_preserves_listing_data():
    add_json4(responses.GET, '/post/list', {
        'items': [v4_post_item()],
    })
    client = LemmyClient('lemmy.ml', api_version=4)

    client.list_posts(page_size=1).take(1)
    community = client.get_community(post_view(0)['community']['name'])

    assert community.id == post_view(0)['community']['id']
    assert community.name == post_view(0)['community']['name']
    assert community.title == post_view(0)['community']['title']


@responses.activate
def test_v4_person_content_resolves_remote_username():
    person = user_view()['person']

    def person_callback(request):
        query = request_query(request)
        if 'username' in query:
            return (404, {'Content-Type': 'application/json'},
                    json.dumps({'error': 'not_found'}))
        return (200, {'Content-Type': 'application/json'},
                json.dumps({'person_view': {'person': person}}))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API4 + '/person') + r'\?.*'),
        callback=person_callback)
    add_json4(responses.GET, '/search', {
        'persons': [{'person': person}],
    })
    add_json4(responses.GET, '/person/content', {
        'items': [v4_post_item(), v4_comment_item()],
        'next_page': 'person-2',
    })
    client = LemmyClient('lemmy.ml', api_version=4)

    items = client.list_user_content('dessalines', page_size=2).take(2)

    assert type(items[0]).__name__ == 'Post'
    assert type(items[1]).__name__ == 'Comment'
    queries = [request_query(call.request) for call in responses.calls]
    assert queries[0]['username'] == ['dessalines']
    assert queries[1]['type_'] == ['users']
    assert queries[2]['person_id'] == [str(person['id'])]
    assert queries[3]['person_id'] == [str(person['id'])]
    assert queries[3]['type_'] == ['all']


@responses.activate
def test_v4_hidden_and_liked_content():
    hidden_post = v4_post_item()
    hidden_post['post_actions']['hidden_at'] = '2026-10-20T10:00:00Z'
    liked_post = v4_post_item()
    liked_comment = v4_comment_item()
    add_json4(responses.GET, '/account/hidden', {
        'items': [hidden_post],
    })
    add_json4(responses.GET, '/account/liked', {
        'items': [liked_post, liked_comment],
        'next_page': 'liked-2',
    })
    add_json4(responses.POST, '/post/hide', {
        'post_view': hidden_post,
    })
    client = LemmyClient('lemmy.ml', api_version=4)

    hidden = client.list_hidden().take(1)
    assert hidden[0].hidden is True
    assert hidden[0].id == hidden_post['post']['id']

    liked = client.list_liked(
        like_type='disliked_only', type_='comments', page_size=2).take(2)
    assert type(liked[0]).__name__ == 'Post'
    assert type(liked[1]).__name__ == 'Comment'
    query = request_query(responses.calls[-1].request)
    assert query['like_type'] == ['disliked_only']
    assert query['type_'] == ['comments']

    hidden[0].unhide()
    assert json.loads(responses.calls[-1].request.body) == {
        'post_id': hidden[0].id, 'hide': False}


@responses.activate
def test_v4_private_message_writes():
    view = message_view()
    add_json4(responses.POST, '/private_message',
              {'private_message_view': view})
    add_json4(responses.PUT, '/private_message',
              {'private_message_view': view})
    add_json4(responses.DELETE, '/private_message',
              {'private_message_view': view})
    client = LemmyClient('lemmy.ml', api_version=4)
    recipient_id = view['recipient']['id']

    message = client.send_message(recipient_id, 'hello')
    assert message.content == view['private_message']['content']
    assert json.loads(responses.calls[-1].request.body) == {
        'content': 'hello', 'recipient_id': recipient_id}

    client.edit_message(message.id, 'edited')
    assert json.loads(responses.calls[-1].request.body) == {
        'private_message_id': message.id, 'content': 'edited'}

    client.delete_message(message.id)
    assert responses.calls[-1].request.method == 'DELETE'
    assert json.loads(responses.calls[-1].request.body) == {
        'private_message_id': message.id, 'deleted': True}

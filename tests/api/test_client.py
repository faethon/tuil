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

    login_body = json.loads(responses.calls[0].request.body)
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
    assert image_proxy_target('https://example.com/a.jpg') == \
        'https://example.com/a.jpg'
    assert image_proxy_target(None) is None

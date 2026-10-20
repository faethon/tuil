# -*- coding: utf-8 -*-
"""A small, dependency-light client for the Lemmy API.

The client uses API v3 on Lemmy 0.19 and switches the affected endpoints to
v4 on Lemmy 1.0.  Every list method returns a
:class:`~tuil.api.paging.Pager`; pages are fetched lazily.
"""

import re

from .errors import InvalidResponseError
from .http import LemmyHTTP
from .models import (
    Comment,
    Community,
    Mention,
    Notification,
    Post,
    PrivateMessage,
    Reply,
    SearchResults,
    Site,
    UnreadCount,
    User,
)
from .paging import Pager

POST_SORTS = (
    'Active', 'Hot', 'New', 'Old', 'TopSixHour', 'TopTwelveHour',
    'TopDay', 'TopWeek', 'TopMonth', 'TopYear', 'TopAll', 'MostComments',
    'NewComments', 'TopThreeMonths', 'TopSixMonths', 'TopNineMonths',
    'Controversial', 'Scaled',
)
COMMENT_SORTS = ('Hot', 'Top', 'New', 'Old', 'Controversial')
LISTING_TYPES = ('All', 'Local', 'Subscribed', 'ModeratorView')
SEARCH_TYPES = ('All', 'Comments', 'Posts', 'Communities', 'Users', 'Url')

MAX_PAGE_SIZE = 50


class LemmyClient(object):
    """Client for one Lemmy instance."""

    def __init__(self, instance, *, token=None, timeout=10.0, max_retries=2,
                 cache_ttl=300, user_agent=None, session=None, verify=True,
                 api_version=3):
        self._http = LemmyHTTP(
            instance, token=token, api_version=api_version, timeout=timeout,
            max_retries=max_retries, cache_ttl=cache_ttl,
            user_agent=user_agent, session=session, verify=verify)
        self._my_user = None
        self._my_user_loaded = False
        self._server_major = None
        self._v4_capable = None

    @property
    def instance(self):
        return self._http.instance

    @property
    def api_url(self):
        return self._http.api_url

    @property
    def token(self):
        return self._http.token

    @property
    def is_logged_in(self):
        return bool(self.token)

    def is_oauth_session(self):
        """Compatibility alias used by the page layer."""
        return self.is_logged_in

    @property
    def user(self):
        """Return the logged-in user, or ``None`` for an anonymous client."""
        return self.me()

    def set_token(self, token):
        self._http.set_token(token)
        self._invalidate_me()

    def clear_cache(self):
        self._http.clear_cache()

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __repr__(self):
        return '<LemmyClient {!r}>'.format(self.instance)

    # ------------------------------------------------------------------
    # Authentication and instance metadata
    # ------------------------------------------------------------------

    def login(self, username_or_email, password, totp_2fa_token=None):
        """Log in and return the authenticated :class:`User`.

        The JWT is kept in memory on this client.  Persisting it is the job of
        the application layer.
        """
        payload = self._http.post('/user/login', {
            'username_or_email': username_or_email,
            'password': password,
            'totp_2fa_token': totp_2fa_token,
        })
        jwt = payload.get('jwt')
        if not jwt:
            raise InvalidResponseError(
                'Login response did not contain a JWT',
                payload=payload, url=self.api_url + '/user/login')
        self._http.set_token(jwt)
        self._invalidate_me()
        return self.me(refresh=True)

    def logout(self):
        self._http.clear_token()
        self._invalidate_me()

    def _invalidate_me(self):
        self._my_user = None
        self._my_user_loaded = False

    def me(self, refresh=False):
        """Return the logged-in user, or None for an anonymous client."""
        if refresh or not self._my_user_loaded:
            self._my_user = self.site().my_user
            self._my_user_loaded = True
        return self._my_user

    @property
    def user_id(self):
        try:
            user = self.me()
        except Exception:  # pragma: no cover - network failure during UI action
            return None
        return user.id if user else None

    def site(self):
        """Fetch instance metadata, including the logged-in user if any."""
        return Site(self, self._http.get('/site'))

    get_site = site

    def version(self):
        return self.site().version

    def supports_v4(self):
        """Return True when the instance speaks the Lemmy 1.0 API."""
        if self._http.api_version >= 4:
            return True
        if self._v4_capable is None:
            version = self.version() or ''
            match = re.match(r'\s*(\d+)', str(version))
            self._server_major = int(match.group(1)) if match else 0
            self._v4_capable = self._server_major >= 1
        return self._v4_capable

    # ------------------------------------------------------------------
    # Posts and comments
    # ------------------------------------------------------------------

    def list_posts(self, *, type_=None, sort=None, community=None,
                   creator=None, saved_only=None, liked_only=None,
                   disliked_only=None, page_size=50, max_items=None):
        """Iterate over posts.

        ``community`` and ``creator`` may be model instances, numeric ids or
        (for communities) names.  Community names are passed to Lemmy without
        an extra lookup.
        """
        self._check_page_size(page_size)
        params = {
            'type_': type_,
            'sort': sort,
            'saved_only': saved_only,
            'liked_only': liked_only,
            'disliked_only': disliked_only,
        }
        if community is not None:
            if isinstance(community, Community):
                params['community_id'] = community.id
            elif isinstance(community, int):
                params['community_id'] = community
            elif str(community).isdigit():
                params['community_id'] = int(community)
            else:
                params['community_name'] = str(community)
        if creator is not None:
            if isinstance(creator, User):
                params['creator_id'] = creator.id
            elif isinstance(creator, int):
                params['creator_id'] = creator
            elif str(creator).isdigit():
                params['creator_id'] = int(creator)
            else:
                params['creator_username'] = str(creator)

        return self._pager(
            '/post/list', 'posts', params, page_size, max_items,
            lambda item: Post(self, item))

    def get_post(self, post_id, comment_id=None):
        post_id = self._post_id(post_id)
        params = {'id': post_id}
        if comment_id is not None:
            params['comment_id'] = self._comment_id(comment_id)
        data = self._http.get('/post', params=params)
        return Post(self, data.get('post_view') or {})

    def list_comments(self, *, post=None, community=None, sort=None,
                      max_depth=None, parent_id=None, saved_only=None,
                      liked_only=None, disliked_only=None, page_size=50,
                      max_items=None):
        """Iterate over a post's comments in tree order."""
        self._check_page_size(page_size)
        params = {
            'sort': sort,
            'max_depth': max_depth,
            'saved_only': saved_only,
            'liked_only': liked_only,
            'disliked_only': disliked_only,
        }
        if post is not None:
            params['post_id'] = self._post_id(post)
        if parent_id is not None:
            params['parent_id'] = self._comment_id(parent_id)
        if community is not None:
            if isinstance(community, Community):
                params['community_id'] = community.id
            elif isinstance(community, int):
                params['community_id'] = community
            elif str(community).isdigit():
                params['community_id'] = int(community)
            else:
                params['community_name'] = str(community)

        return self._pager(
            '/comment/list', 'comments', params, page_size, max_items,
            lambda item: Comment(self, item))

    def get_comment(self, comment_id):
        comment_id = self._comment_id(comment_id)
        data = self._http.get('/comment', params={'id': comment_id})
        return Comment(self, data.get('comment_view') or {})

    # ------------------------------------------------------------------
    # Communities and people
    # ------------------------------------------------------------------

    def list_communities(self, *, type_=None, sort=None, show_nsfw=None,
                         page_size=50, max_items=None):
        self._check_page_size(page_size)
        params = {
            'type_': type_,
            'sort': sort,
            'show_nsfw': show_nsfw,
        }
        return self._pager(
            '/community/list', 'communities', params, page_size, max_items,
            lambda item: Community(self, item))

    def get_community(self, community):
        params = {}
        if isinstance(community, Community):
            params['id'] = community.id
        elif isinstance(community, int):
            params['id'] = community
        elif str(community).isdigit():
            params['id'] = int(community)
        else:
            params['name'] = str(community)
        data = self._http.get('/community', params=params)
        return Community(
            self, data.get('community_view') or {}, details=data)

    def get_user(self, user, *, sort=None, page_size=50, include_content=True):
        self._check_page_size(page_size)
        params = {'sort': sort, 'limit': page_size}
        params.update(self._person_params(user))
        data = self._http.get('/user', params=params)
        view = data.get('person_view') or {}
        posts = [Post(self, item) for item in data.get('posts') or []]
        comments = [Comment(self, item)
                    for item in data.get('comments') or []]
        moderates = data.get('moderates') or []
        if not include_content:
            posts, comments, moderates = [], [], []
        return User(self, view, posts=posts, comments=comments,
                    moderates=moderates)

    def list_user_posts(self, user, *, sort=None, page_size=50,
                        max_items=None):
        return self._user_content_pager(
            user, 'posts', sort, page_size, max_items,
            lambda item: Post(self, item))

    def list_user_comments(self, user, *, sort=None, page_size=50,
                           max_items=None):
        return self._user_content_pager(
            user, 'comments', sort, page_size, max_items,
            lambda item: Comment(self, item))

    def list_user_content(self, user, *, sort=None, page_size=50,
                          max_items=None):
        """Iterate over a user's posts and comments.

        The v3 ``/user`` endpoint returns both lists for each page, so the
        combined pager yields posts followed by comments.  The UI only needs
        one item at a time, and this keeps paging correct without losing either
        kind of content.
        """
        self._check_page_size(page_size)
        person_params = self._person_params(user)

        def fetch(page):
            params = {'sort': sort, 'page': page, 'limit': page_size}
            params.update(person_params)
            data = self._http.get('/user', params=params)
            posts = data.get('posts') or []
            comments = data.get('comments') or []
            items = [Post(self, item) for item in posts]
            items.extend(Comment(self, item) for item in comments)
            return items, bool(posts or comments)

        return Pager(fetch, max_items=max_items)

    def list_saved(self, *, type_=None, page_size=50, max_items=None):
        """Iterate over saved posts and comments through the v4 API."""
        return self._cursor_pager(
            '/account/saved', {'type_': type_}, page_size, max_items,
            self._combined_item)

    def list_liked(self, *, like_type='liked_only', type_='all',
                   page_size=50, max_items=None):
        """Iterate over upvoted or downvoted posts and comments (v4)."""
        if like_type not in ('liked_only', 'disliked_only'):
            raise ValueError(
                'like_type must be liked_only or disliked_only')
        if type_ not in ('all', 'comments', 'posts'):
            raise ValueError('type_ must be all, comments or posts')
        return self._cursor_pager(
            '/account/liked', {'like_type': like_type, 'type_': type_},
            page_size, max_items, self._combined_item)

    def list_hidden(self, *, page_size=50, max_items=None):
        """Iterate over hidden posts through the v4 API."""
        return self._cursor_pager(
            '/account/hidden', {}, page_size, max_items,
            lambda item: Post(self, item))

    def _combined_item(self, item):
        if item.get('type_') == 'comment':
            return Comment(self, item)
        return Post(self, item)

    def _user_content_pager(self, user, key, sort, page_size, max_items,
                            factory):
        self._check_page_size(page_size)
        person_params = self._person_params(user)

        def fetch(page):
            params = {'sort': sort, 'page': page, 'limit': page_size}
            params.update(person_params)
            data = self._http.get('/user', params=params)
            posts = data.get('posts') or []
            comments = data.get('comments') or []
            raw_items = posts if key == 'posts' else comments
            # The endpoint returns both lists.  An empty page for one kind
            # does not mean there are no older items of that kind, so keep
            # paging while either list has data.
            return [factory(item) for item in raw_items], bool(posts or comments)

        return Pager(fetch, max_items=max_items)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query, *, type_=None, sort=None, listing_type=None,
               community=None, creator=None, page=1, limit=50):
        if not query:
            raise ValueError('A search query is required')
        self._check_page_size(limit)
        params = {
            'q': query,
            'type_': type_,
            'sort': sort,
            'listing_type': listing_type,
            'page': page,
            'limit': limit,
        }
        if community is not None:
            if isinstance(community, Community):
                params['community_id'] = community.id
            elif isinstance(community, int):
                params['community_id'] = community
            elif str(community).isdigit():
                params['community_id'] = int(community)
            else:
                params['community_name'] = str(community)
        if creator is not None:
            params['creator_id'] = self._person_id(creator)
        return SearchResults(self, self._http.get('/search', params=params))

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------

    def list_notifications(self, *, type_=None, unread_only=None,
                           creator=None, page_size=50, max_items=None):
        """Iterate over the combined v4 notification stream."""
        self._check_page_size(page_size)
        params = {'type_': type_, 'unread_only': unread_only}
        if creator is not None:
            params['creator_id'] = self._person_id(creator)
        return self._cursor_pager(
            '/account/notification/list', params, page_size, max_items,
            lambda item: Notification(self, item))

    def list_replies(self, *, unread_only=None, sort=None, page_size=50,
                     max_items=None):
        if self.supports_v4():
            return self.list_notifications(
                type_='reply', unread_only=unread_only,
                page_size=page_size, max_items=max_items)
        params = {'unread_only': unread_only, 'sort': sort}
        return self._pager(
            '/user/replies', 'replies', params, page_size, max_items,
            lambda item: Reply(self, item))

    def list_mentions(self, *, unread_only=None, sort=None, page_size=50,
                      max_items=None):
        if self.supports_v4():
            return self.list_notifications(
                type_='mention', unread_only=unread_only,
                page_size=page_size, max_items=max_items)
        params = {'unread_only': unread_only, 'sort': sort}
        return self._pager(
            '/user/mention', 'mentions', params, page_size, max_items,
            lambda item: Mention(self, item))

    def list_messages(self, *, unread_only=None, creator=None, page_size=50,
                      max_items=None):
        if self.supports_v4():
            return self.list_notifications(
                type_='private_message', unread_only=unread_only,
                creator=creator, page_size=page_size, max_items=max_items)
        params = {'unread_only': unread_only}
        if creator is not None:
            params['creator_id'] = self._person_id(creator)
        return self._pager(
            '/private_message/list', 'private_messages', params, page_size,
            max_items, lambda item: PrivateMessage(self, item))

    def unread_count(self):
        if self.supports_v4():
            data = self._http.get(
                '/account/unread_counts', api_version=4)
            return UnreadCount(
                notifications=data.get('notification_count'))
        data = self._http.get('/user/unread_count')
        return UnreadCount(
            replies=data.get('replies'),
            mentions=data.get('mentions'),
            private_messages=data.get('private_messages'))

    def mark_reply_read(self, reply_id, read=True):
        data = self._http.post('/comment/mark_as_read', {
            'comment_reply_id': reply_id,
            'read': bool(read),
        })
        return Reply(self, data.get('comment_reply_view') or {})

    def mark_mention_read(self, mention_id, read=True):
        data = self._http.post('/user/mention/mark_as_read', {
            'person_mention_id': mention_id,
            'read': bool(read),
        })
        return Mention(self, data.get('person_mention_view') or {})

    def mark_message_read(self, message_id, read=True):
        data = self._http.post('/private_message/mark_as_read', {
            'private_message_id': message_id,
            'read': bool(read),
        })
        return PrivateMessage(self, data.get('private_message_view') or {})

    def mark_notification_read(self, notification_id, read=True):
        return self._http.post(
            '/account/notification/mark_as_read', {
                'notification_id': notification_id,
                'read': bool(read),
            }, api_version=4)

    def mark_all_read(self):
        if self.supports_v4():
            return self._http.post(
                '/account/notification/mark_as_read/all', {},
                api_version=4)
        return self._http.post('/user/mark_all_as_read', {})

    def send_message(self, recipient, content):
        data = self._http.post('/private_message', {
            'content': content,
            'recipient_id': self._person_id(recipient),
        })
        return PrivateMessage(self, data.get('private_message_view') or {})

    def edit_message(self, message_id, content):
        data = self._http.put('/private_message', {
            'private_message_id': message_id,
            'content': content,
        })
        return PrivateMessage(self, data.get('private_message_view') or {})

    def delete_message(self, message_id, deleted=True):
        data = self._http.post('/private_message/delete', {
            'private_message_id': message_id,
            'deleted': bool(deleted),
        })
        return PrivateMessage(self, data.get('private_message_view') or {})

    # ------------------------------------------------------------------
    # Votes, saves and read state
    # ------------------------------------------------------------------

    def vote_post(self, post_id, score):
        self._check_score(score)
        data = self._http.post('/post/like', {
            'post_id': self._post_id(post_id),
            'score': score,
        })
        return Post(self, data.get('post_view') or {})

    def vote_comment(self, comment_id, score):
        self._check_score(score)
        data = self._http.post('/comment/like', {
            'comment_id': self._comment_id(comment_id),
            'score': score,
        })
        return Comment(self, data.get('comment_view') or {})

    def save_post(self, post_id, save=True):
        data = self._http.put('/post/save', {
            'post_id': self._post_id(post_id),
            'save': bool(save),
        })
        return Post(self, data.get('post_view') or {})

    def save_comment(self, comment_id, save=True):
        data = self._http.put('/comment/save', {
            'comment_id': self._comment_id(comment_id),
            'save': bool(save),
        })
        return Comment(self, data.get('comment_view') or {})

    def hide_post(self, post_id, hide=True):
        data = self._http.post('/post/hide', {
            'post_id': self._post_id(post_id),
            'hide': bool(hide),
        }, api_version=4)
        return Post(self, data.get('post_view') or {})

    def mark_post_read(self, post_id, read=True):
        if self.supports_v4():
            data = self._http.post('/post/mark_as_read', {
                'post_id': self._post_id(post_id),
                'read': bool(read),
            }, api_version=4)
            return Post(self, data.get('post_view') or {})
        # The v3 endpoint returns an empty response.
        return self._http.post('/post/mark_as_read', {
            'post_id': self._post_id(post_id),
            'read': bool(read),
        })

    def mark_posts_read(self, post_ids, read=True):
        if self.supports_v4():
            return self._http.post('/post/mark_as_read/many', {
                'post_ids': [self._post_id(item) for item in post_ids],
                'read': bool(read),
            }, api_version=4)
        return self._http.post('/post/mark_as_read', {
            'post_ids': [self._post_id(item) for item in post_ids],
            'read': bool(read),
        })

    # ------------------------------------------------------------------
    # Creating and editing content
    # ------------------------------------------------------------------

    def create_post(self, community, name, *, url=None, body=None, nsfw=False,
                    language_id=None):
        if not name:
            raise ValueError('A post title is required')
        data = {
            'name': name,
            'community_id': self._community_id(community),
            'nsfw': bool(nsfw),
        }
        if url is not None:
            data['url'] = url
        if body is not None:
            data['body'] = body
        language_id = self._language_id(language_id)
        if language_id is not None:
            data['language_id'] = language_id
        response = self._http.post('/post', data)
        return Post(self, response.get('post_view') or {})

    def edit_post(self, post_id, **fields):
        allowed = ('name', 'url', 'body', 'nsfw', 'language_id')
        data = {'post_id': self._post_id(post_id)}
        for key, value in fields.items():
            if key not in allowed:
                raise TypeError('Unknown post field: {}'.format(key))
            data[key] = value
        if len(data) == 1:
            raise ValueError('No post fields to edit')
        response = self._http.post('/post', data)
        return Post(self, response.get('post_view') or {})

    def delete_post(self, post_id, deleted=True):
        data = self._http.post('/post/delete', {
            'post_id': self._post_id(post_id),
            'deleted': bool(deleted),
        })
        return Post(self, data.get('post_view') or {})

    def create_comment(self, post_id, content, *, parent_id=None,
                       language_id=None):
        if not content:
            raise ValueError('Comment content is required')
        data = {
            'post_id': self._post_id(post_id),
            'content': content,
        }
        if parent_id is not None:
            data['parent_id'] = self._comment_id(parent_id)
        language_id = self._language_id(language_id)
        if language_id is not None:
            data['language_id'] = language_id
        response = self._http.post('/comment', data)
        return Comment(self, response.get('comment_view') or {})

    def edit_comment(self, comment_id, content, *, language_id=None):
        if not content:
            raise ValueError('Comment content is required')
        data = {
            'comment_id': self._comment_id(comment_id),
            'content': content,
        }
        language_id = self._language_id(language_id)
        if language_id is not None:
            data['language_id'] = language_id
        response = self._http.put('/comment', data)
        return Comment(self, response.get('comment_view') or {})

    def delete_comment(self, comment_id, deleted=True):
        data = self._http.post('/comment/delete', {
            'comment_id': self._comment_id(comment_id),
            'deleted': bool(deleted),
        })
        return Comment(self, data.get('comment_view') or {})

    def follow_community(self, community, follow=True):
        data = self._http.post('/community/follow', {
            'community_id': self._community_id(community),
            'follow': bool(follow),
        })
        return Community(
            self, data.get('community_view') or {}, details=data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pager(self, path, key, params, page_size, max_items, factory):
        self._check_page_size(page_size)

        def fetch(page):
            query = dict(params)
            query.update({'page': page, 'limit': page_size})
            data = self._http.get(path, params=query)
            raw_items = data.get(key) or []
            return ([factory(item) for item in raw_items],
                    len(raw_items) >= page_size)

        return Pager(fetch, max_items=max_items)

    def _cursor_pager(self, path, params, page_size, max_items, factory):
        """Pager for v4 endpoints which use opaque ``page_cursor`` tokens."""
        self._check_page_size(page_size)
        cursors = {}

        def fetch(page):
            if page > 1 and not cursors.get(page):
                return [], False
            query = dict(params)
            query['limit'] = page_size
            if page > 1:
                query['page_cursor'] = cursors[page]
            data = self._http.get(path, params=query, api_version=4)
            raw_items = data.get('items') or []
            next_page = data.get('next_page')
            if next_page:
                cursors[page + 1] = next_page
            return ([factory(item) for item in raw_items],
                    bool(next_page) and bool(raw_items))

        return Pager(fetch, max_items=max_items)

    @staticmethod
    def _check_page_size(page_size):
        if not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(
                'page_size must be between 1 and {}'.format(MAX_PAGE_SIZE))

    @staticmethod
    def _check_score(score):
        if score not in (-1, 0, 1):
            raise ValueError('score must be -1, 0 or 1')

    def _language_id(self, language_id):
        if language_id is not None:
            return language_id
        return self.site().default_language_id

    def _community_id(self, community):
        if isinstance(community, Community):
            return community.id
        if isinstance(community, int):
            return community
        if str(community).isdigit():
            return int(community)
        return self.get_community(str(community)).id

    def _person_id(self, person):
        if isinstance(person, User):
            return person.id
        if isinstance(person, int):
            return person
        if str(person).isdigit():
            return int(person)
        return self.get_user(str(person), include_content=False).id

    def _person_params(self, person):
        if isinstance(person, User):
            return {'person_id': person.id}
        if isinstance(person, int):
            return {'person_id': person}
        if str(person).isdigit():
            return {'person_id': int(person)}
        return {'username': str(person)}

    @staticmethod
    def _post_id(post):
        if isinstance(post, Post):
            return post.id
        return int(post)

    @staticmethod
    def _comment_id(comment):
        if isinstance(comment, Comment):
            return comment.id
        return int(comment)

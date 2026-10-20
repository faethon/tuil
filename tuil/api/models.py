# -*- coding: utf-8 -*-
"""Thin model wrappers around Lemmy API responses.

The wrappers accept both v3 and v4 field layouts and deliberately keep the
original response dict available as ``.raw``.  The UI can therefore switch to
new fields without waiting for this module to grow, while common fields and
actions have a stable interface.
"""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from .errors import UnsupportedFeatureError

UNSET = object()


def to_epoch(value):
    """Convert a Lemmy ISO timestamp to a Unix timestamp, or return None."""
    if not value:
        return None
    value = str(value).strip()
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def image_proxy_target(url):
    """Return the original URL from a Lemmy ``/image_proxy?url=`` link."""
    if not url:
        return url
    parts = urlsplit(url)
    if parts.path.rstrip('/').endswith(('/image_proxy', '/image/proxy')):
        values = parse_qs(parts.query).get('url')
        if values:
            return values[0]
    return url


def qualified_community_name(data):
    """Return ``name@instance`` for a community actor, when available."""
    data = data or {}
    name = data.get('name')
    actor = data.get('actor_id') or data.get('ap_id')
    if name and actor:
        host = urlsplit(actor).netloc
        if host:
            return '{}@{}'.format(name, host)
    return name


class Model(object):
    """Base class for API objects."""

    def __init__(self, client, data):
        self._client = client
        self._data = data or {}

    @property
    def raw(self):
        return self._data

    def _replace(self, data):
        if data is not None:
            self._data = data.raw if isinstance(data, Model) else data
        return self

    def __repr__(self):
        identifier = getattr(self, 'id', None)
        name = getattr(self, 'name', None)
        if name:
            return '<{} {} {!r}>'.format(
                self.__class__.__name__, identifier, name)
        return '<{} {}>'.format(self.__class__.__name__, identifier)


class Post(Model):
    """A post and the context (creator, community, counts) around it."""

    @property
    def post(self):
        return self._data.get('post') or {}

    @property
    def creator_data(self):
        return self._data.get('creator') or {}

    @property
    def community_data(self):
        return self._data.get('community') or {}

    @property
    def counts(self):
        counts = self._data.get('counts') or {}
        if counts:
            return counts
        # API v4 stores vote counts directly on the post.
        return {
            key: self.post.get(key, 0)
            for key in ('score', 'upvotes', 'downvotes', 'comments')
        }

    @property
    def actions(self):
        return self._data.get('post_actions') or {}

    @property
    def id(self):
        return self.post.get('id')

    @property
    def name(self):
        return self.post.get('name')

    @property
    def title(self):
        return self.name

    @property
    def body(self):
        return self.post.get('body')

    @property
    def url(self):
        return self.post.get('url')

    @property
    def link_url(self):
        return image_proxy_target(self.url)

    @property
    def ap_id(self):
        return self.post.get('ap_id')

    @property
    def permalink(self):
        return '{}/post/{}'.format(self._client.instance, self.id)

    @property
    def author(self):
        return self.creator_data.get('name')

    @property
    def author_display_name(self):
        return self.creator_data.get('display_name') or self.author

    @property
    def creator_id(self):
        return self.post.get('creator_id')

    @property
    def community_id(self):
        return self.post.get('community_id')

    @property
    def community_name(self):
        return self.community_data.get('name')

    @property
    def community_qualified_name(self):
        return qualified_community_name(self.community_data)

    @property
    def community_title(self):
        return self.community_data.get('title')

    @property
    def published(self):
        return self.post.get('published') or self.post.get('published_at')

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def updated(self):
        return self.post.get('updated') or self.post.get('updated_at')

    @property
    def edited(self):
        return to_epoch(self.updated)

    @property
    def is_self(self):
        return not self.url

    @property
    def nsfw(self):
        return bool(self.post.get('nsfw'))

    @property
    def locked(self):
        return bool(self.post.get('locked'))

    @property
    def deleted(self):
        return bool(self.post.get('deleted'))

    @property
    def removed(self):
        return bool(self.post.get('removed'))

    @property
    def stickied(self):
        return bool(self.post.get('featured_community')
                    or self.post.get('featured_local'))

    @property
    def local(self):
        return bool(self.post.get('local'))

    @property
    def language_id(self):
        return self.post.get('language_id')

    @property
    def thumbnail_url(self):
        return self.post.get('thumbnail_url')

    @property
    def url_content_type(self):
        return self.post.get('url_content_type')

    @property
    def score(self):
        return self.counts.get('score', 0)

    @property
    def upvotes(self):
        return self.counts.get('upvotes', 0)

    @property
    def downvotes(self):
        return self.counts.get('downvotes', 0)

    @property
    def comments_count(self):
        return self.counts.get('comments', 0)

    @property
    def unread_comments(self):
        return self._data.get('unread_comments', 0)

    @property
    def my_vote(self):
        if 'my_vote' in self._data:
            return self._data.get('my_vote')
        vote = self.actions.get('vote_is_upvote')
        if vote is None:
            return None
        return 1 if vote else -1

    @property
    def likes(self):
        return self.my_vote

    @property
    def saved(self):
        if 'saved' in self._data:
            return bool(self._data.get('saved'))
        return bool(self.actions.get('saved_at'))

    @property
    def read(self):
        if 'read' in self._data:
            return bool(self._data.get('read'))
        return bool(self.actions.get('read_at'))

    @property
    def hidden(self):
        if 'hidden' in self._data:
            return bool(self._data.get('hidden'))
        return bool(self.actions.get('hidden_at'))

    @property
    def subscribed(self):
        if 'subscribed' in self._data:
            return self._data.get('subscribed')
        state = (self._data.get('community_actions') or {}).get(
            'follow_state')
        if state == 'accepted':
            return 'Subscribed'
        if state in ('pending', 'approval_required'):
            return 'Pending'
        return None

    @property
    def creator_is_admin(self):
        return bool(self._data.get('creator_is_admin'))

    @property
    def creator_is_moderator(self):
        return bool(self._data.get('creator_is_moderator'))

    def refresh(self):
        return self._replace(self._client.get_post(self.id))

    def vote(self, score):
        if score not in (-1, 0, 1):
            raise ValueError('score must be -1, 0 or 1')
        return self._replace(self._client.vote_post(self.id, score))

    def upvote(self):
        return self.vote(1)

    def downvote(self):
        return self.vote(-1)

    def clear_vote(self):
        return self.vote(0)

    def save(self, save=True):
        return self._replace(self._client.save_post(self.id, save))

    def unsave(self):
        return self.save(False)

    def mark_read(self, read=True):
        self._client.mark_post_read(self.id, read)
        self._data['read'] = bool(read)
        return self

    def mark_unread(self):
        return self.mark_read(False)

    def edit(self, name=UNSET, url=UNSET, body=UNSET, nsfw=UNSET,
             language_id=UNSET):
        fields = {}
        if name is not UNSET:
            fields['name'] = name
        if url is not UNSET:
            fields['url'] = url
        if body is not UNSET:
            fields['body'] = body
        if nsfw is not UNSET:
            fields['nsfw'] = nsfw
        if language_id is not UNSET:
            fields['language_id'] = language_id
        return self._replace(self._client.edit_post(self.id, **fields))

    def delete(self):
        return self._replace(self._client.delete_post(self.id, True))

    def reply(self, content, language_id=None):
        return self._client.create_comment(
            self.id, content, language_id=language_id)

    def hide(self):
        if not self._client.supports_v4():
            raise UnsupportedFeatureError(
                'Hiding posts requires Lemmy 1.0 or newer')
        return self._replace(self._client.hide_post(self.id, True))

    def unhide(self):
        if not self._client.supports_v4():
            raise UnsupportedFeatureError(
                'Hiding posts requires Lemmy 1.0 or newer')
        return self._replace(self._client.hide_post(self.id, False))


class Comment(Model):
    """A comment, including its post, creator and community context."""

    @property
    def comment(self):
        return self._data.get('comment') or {}

    @property
    def creator_data(self):
        return self._data.get('creator') or {}

    @property
    def post_data(self):
        return self._data.get('post') or {}

    @property
    def community_data(self):
        return self._data.get('community') or {}

    @property
    def counts(self):
        counts = self._data.get('counts') or {}
        if counts:
            return counts
        # API v4 stores vote counts directly on the comment.
        return {
            key: self.comment.get(key, 0)
            for key in ('score', 'upvotes', 'downvotes', 'child_count')
        }

    @property
    def actions(self):
        return self._data.get('comment_actions') or {}

    @property
    def id(self):
        return self.comment.get('id')

    @property
    def content(self):
        return self.comment.get('content')

    @property
    def body(self):
        return self.content

    @property
    def path(self):
        return self.comment.get('path') or ''

    @property
    def path_ids(self):
        return [int(part) for part in self.path.split('.') if part]

    @property
    def depth(self):
        path_ids = self.path_ids
        return max(0, len(path_ids) - 1)

    @property
    def parent_id(self):
        path_ids = self.path_ids
        # Lemmy paths start with the synthetic root ``0``.  A top-level
        # comment has the path ``0.<id>`` and no parent.
        if len(path_ids) <= 2:
            return None
        return path_ids[-2]

    @property
    def post_id(self):
        return self.comment.get('post_id')

    @property
    def creator_id(self):
        return self.comment.get('creator_id')

    @property
    def author(self):
        return self.creator_data.get('name')

    @property
    def author_display_name(self):
        return self.creator_data.get('display_name') or self.author

    @property
    def community_name(self):
        return self.community_data.get('name')

    @property
    def community_qualified_name(self):
        return qualified_community_name(self.community_data)

    @property
    def published(self):
        return (self.comment.get('published')
                or self.comment.get('published_at'))

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def updated(self):
        return (self.comment.get('updated')
                or self.comment.get('updated_at'))

    @property
    def edited(self):
        return to_epoch(self.updated)

    @property
    def deleted(self):
        return bool(self.comment.get('deleted'))

    @property
    def removed(self):
        return bool(self.comment.get('removed'))

    @property
    def distinguished(self):
        return bool(self.comment.get('distinguished'))

    @property
    def local(self):
        return bool(self.comment.get('local'))

    @property
    def language_id(self):
        return self.comment.get('language_id')

    @property
    def ap_id(self):
        return self.comment.get('ap_id')

    @property
    def permalink(self):
        return '{}/comment/{}'.format(self._client.instance, self.id)

    @property
    def is_op(self):
        return self.creator_id == self.post_data.get('creator_id')

    @property
    def score(self):
        return self.counts.get('score', 0)

    @property
    def upvotes(self):
        return self.counts.get('upvotes', 0)

    @property
    def downvotes(self):
        return self.counts.get('downvotes', 0)

    @property
    def child_count(self):
        return self.counts.get('child_count', 0)

    @property
    def my_vote(self):
        if 'my_vote' in self._data:
            return self._data.get('my_vote')
        vote = self.actions.get('vote_is_upvote')
        if vote is None:
            return None
        return 1 if vote else -1

    @property
    def likes(self):
        return self.my_vote

    @property
    def saved(self):
        if 'saved' in self._data:
            return bool(self._data.get('saved'))
        return bool(self.actions.get('saved_at'))

    @property
    def creator_is_admin(self):
        return bool(self._data.get('creator_is_admin'))

    @property
    def creator_is_moderator(self):
        return bool(self._data.get('creator_is_moderator'))

    def refresh(self):
        return self._replace(self._client.get_comment(self.id))

    def vote(self, score):
        if score not in (-1, 0, 1):
            raise ValueError('score must be -1, 0 or 1')
        return self._replace(self._client.vote_comment(self.id, score))

    def upvote(self):
        return self.vote(1)

    def downvote(self):
        return self.vote(-1)

    def clear_vote(self):
        return self.vote(0)

    def save(self, save=True):
        return self._replace(self._client.save_comment(self.id, save))

    def unsave(self):
        return self.save(False)

    def edit(self, content, language_id=UNSET):
        if language_id is UNSET:
            language_id = self.language_id
        return self._replace(self._client.edit_comment(
            self.id, content, language_id=language_id))

    def delete(self):
        return self._replace(self._client.delete_comment(self.id, True))

    def reply(self, content, language_id=None):
        return self._client.create_comment(
            self.post_id, content, parent_id=self.id,
            language_id=language_id)


class Community(Model):
    """A community, optionally with details from ``GET /community``."""

    def __init__(self, client, data, details=None):
        data = data or {}
        details = details or {}
        if 'community_view' in data:
            details = data
            data = data.get('community_view') or {}
        super(Community, self).__init__(client, data)
        self._details = details

    @property
    def community(self):
        return self._data.get('community') or {}

    @property
    def counts(self):
        counts = self._data.get('counts') or {}
        if counts:
            return counts
        return {
            key: self.community.get(key, 0)
            for key in ('subscribers', 'posts', 'comments',
                        'users_active_day', 'users_active_week',
                        'users_active_month', 'users_active_half_year')
        }

    @property
    def actions(self):
        return self._data.get('community_actions') or {}

    @property
    def id(self):
        return self.community.get('id')

    @property
    def name(self):
        return self.community.get('name')

    @property
    def title(self):
        return self.community.get('title')

    @property
    def description(self):
        return self.community.get('description')

    @property
    def actor_id(self):
        return self.community.get('actor_id') or self.community.get('ap_id')

    @property
    def permalink(self):
        return '{}/c/{}'.format(self._client.instance, self.name)

    @property
    def local(self):
        return bool(self.community.get('local'))

    @property
    def nsfw(self):
        return bool(self.community.get('nsfw'))

    @property
    def hidden(self):
        return bool(self.community.get('hidden'))

    @property
    def removed(self):
        return bool(self.community.get('removed'))

    @property
    def deleted(self):
        return bool(self.community.get('deleted'))

    @property
    def posting_restricted_to_mods(self):
        return bool(self.community.get('posting_restricted_to_mods'))

    @property
    def published(self):
        return (self.community.get('published')
                or self.community.get('published_at'))

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def updated(self):
        return (self.community.get('updated')
                or self.community.get('updated_at'))

    @property
    def icon(self):
        return self.community.get('icon')

    @property
    def banner(self):
        return self.community.get('banner')

    @property
    def subscribers(self):
        return self.counts.get('subscribers', 0)

    @property
    def posts(self):
        return self.counts.get('posts', 0)

    @property
    def comments(self):
        return self.counts.get('comments', 0)

    @property
    def users_active_day(self):
        return self.counts.get('users_active_day', 0)

    @property
    def users_active_week(self):
        return self.counts.get('users_active_week', 0)

    @property
    def users_active_month(self):
        return self.counts.get('users_active_month', 0)

    @property
    def users_active_half_year(self):
        return self.counts.get('users_active_half_year', 0)

    @property
    def subscription(self):
        if 'subscribed' in self._data:
            return self._data.get('subscribed')
        state = self.actions.get('follow_state')
        if state == 'accepted':
            return 'Subscribed'
        if state in ('pending', 'approval_required'):
            return 'Pending'
        return None

    @property
    def subscribed(self):
        return self.subscription == 'Subscribed'

    @property
    def subscription_pending(self):
        return self.subscription == 'Pending'

    @property
    def blocked(self):
        if 'blocked' in self._data:
            return bool(self._data.get('blocked'))
        return bool(self.actions.get('blocked_at'))

    @property
    def moderators(self):
        return [
            User(self._client, {'person': item.get('moderator') or {}})
            for item in self._details.get('moderators') or []
        ]

    @property
    def discussion_languages(self):
        return self._details.get('discussion_languages') or []

    @property
    def site(self):
        return self._details.get('site')

    def refresh(self):
        updated = self._client.get_community(self.id)
        self._details = updated._details
        return self._replace(updated)

    def follow(self, follow=True):
        return self._replace(self._client.follow_community(
            self.id, follow))

    def subscribe(self):
        return self.follow(True)

    def unsubscribe(self):
        return self.follow(False)


class User(Model):
    """A person and, when available, their recent posts and comments."""

    def __init__(self, client, data, *, posts=None, comments=None,
                 moderates=None):
        data = data or {}
        self._recent_posts = list(posts or [])
        self._recent_comments = list(comments or [])
        self._moderates = list(moderates or [])
        super(User, self).__init__(client, data)

    @property
    def person(self):
        return self._data.get('person') or self._data

    @property
    def counts(self):
        counts = self._data.get('counts') or {}
        if counts:
            return counts
        return {
            key: self.person.get(key, 0)
            for key in ('post_count', 'comment_count')
        }

    @property
    def id(self):
        return self.person.get('id')

    @property
    def name(self):
        return self.person.get('name')

    @property
    def display_name(self):
        return self.person.get('display_name') or self.name

    @property
    def actor_id(self):
        return self.person.get('actor_id') or self.person.get('ap_id')

    @property
    def bio(self):
        return self.person.get('bio')

    @property
    def avatar(self):
        return self.person.get('avatar')

    @property
    def banner(self):
        return self.person.get('banner')

    @property
    def local(self):
        return bool(self.person.get('local'))

    @property
    def bot(self):
        return bool(self.person.get('bot_account'))

    @property
    def deleted(self):
        return bool(self.person.get('deleted'))

    @property
    def banned(self):
        return bool(self.person.get('banned'))

    @property
    def published(self):
        return (self.person.get('published')
                or self.person.get('published_at'))

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def matrix_user_id(self):
        return self.person.get('matrix_user_id')

    @property
    def is_admin(self):
        if 'is_admin' in self._data:
            return bool(self._data.get('is_admin'))
        return bool(self.person.get('admin'))

    @property
    def post_count(self):
        return self.counts.get('post_count', 0)

    @property
    def comment_count(self):
        return self.counts.get('comment_count', 0)

    @property
    def permalink(self):
        return '{}/u/{}'.format(self._client.instance, self.name)

    @property
    def recent_posts(self):
        return self._recent_posts

    @property
    def recent_comments(self):
        return self._recent_comments

    @property
    def moderates(self):
        return self._moderates

    def send_message(self, content):
        return self._client.send_message(self.id, content)


class PrivateMessage(Model):
    """A private message between two people."""

    @property
    def private_message(self):
        return self._data.get('private_message') or {}

    @property
    def creator_data(self):
        return self._data.get('creator') or {}

    @property
    def recipient_data(self):
        return self._data.get('recipient') or {}

    @property
    def id(self):
        return self.private_message.get('id')

    @property
    def content(self):
        return self.private_message.get('content')

    @property
    def body(self):
        return self.content

    @property
    def creator_id(self):
        return self.private_message.get('creator_id')

    @property
    def recipient_id(self):
        return self.private_message.get('recipient_id')

    @property
    def creator(self):
        return User(self._client, {'person': self.creator_data})

    @property
    def recipient(self):
        return User(self._client, {'person': self.recipient_data})

    @property
    def read(self):
        return bool(self.private_message.get('read'))

    @property
    def deleted(self):
        return bool(self.private_message.get('deleted'))

    @property
    def published(self):
        return (self.private_message.get('published')
                or self.private_message.get('published_at'))

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def edited(self):
        return to_epoch(self.private_message.get('updated')
                        or self.private_message.get('updated_at'))

    @property
    def ap_id(self):
        return self.private_message.get('ap_id')

    @property
    def local(self):
        return bool(self.private_message.get('local'))

    @property
    def permalink(self):
        return self.ap_id

    def mark_read(self, read=True):
        return self._replace(self._client.mark_message_read(
            self.id, read))

    def mark_unread(self):
        return self.mark_read(False)

    def reply(self, content):
        my_id = self._client.user_id
        if self.creator_id == my_id:
            recipient_id = self.recipient_id
        else:
            recipient_id = self.creator_id
        return self._client.send_message(recipient_id, content)

    def edit(self, content):
        return self._replace(self._client.edit_message(self.id, content))

    def delete(self):
        return self._replace(self._client.delete_message(self.id, True))


class Notification(Model):
    """A v4 inbox notification.

    The v4 inbox combines replies, mentions and private messages into one
    notification stream.  This wrapper exposes the same fields as the separate
    v3 ``Reply``, ``Mention`` and ``PrivateMessage`` models so the page layer
    does not need two different code paths.
    """

    @property
    def notification(self):
        return self._data.get('notification') or {}

    @property
    def data(self):
        return self._data.get('data') or {}

    @property
    def data_type(self):
        return self.data.get('type_')

    @property
    def kind(self):
        return self.notification.get('kind')

    @property
    def id(self):
        return self.notification.get('id')

    @property
    def read(self):
        return bool(self.notification.get('read'))

    @property
    def published(self):
        return (self.notification.get('published')
                or self.notification.get('published_at'))

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def creator_data(self):
        return self.data.get('creator') or {}

    @property
    def creator_id(self):
        return self.notification.get('creator_id')

    @property
    def recipient_data(self):
        return self.data.get('recipient') or {}

    @property
    def creator(self):
        return User(self._client, {'person': self.creator_data}) \
            if self.creator_data else None

    @property
    def recipient(self):
        return User(self._client, {'person': self.recipient_data}) \
            if self.recipient_data else None

    @property
    def is_private_message(self):
        return self.data_type == 'private_message'

    @property
    def comment(self):
        if self.data_type != 'comment':
            return None
        return Comment(self._client, self.data)

    @property
    def content(self):
        if self.is_private_message:
            message = self.data.get('private_message') or {}
            return message.get('content')
        if self.data_type == 'comment':
            comment = self.data.get('comment') or {}
            return comment.get('content')
        post = self.data.get('post') or {}
        return post.get('body') or post.get('name')

    @property
    def body(self):
        return self.content

    @property
    def post_data(self):
        return self.data.get('post') or {}

    @property
    def post_id(self):
        return self.post_data.get('id')

    @property
    def post_title(self):
        return self.post_data.get('name')

    @property
    def community_data(self):
        return self.data.get('community') or {}

    @property
    def community_name(self):
        return self.community_data.get('name')

    @property
    def counts(self):
        if self.data_type == 'comment':
            return Comment(self._client, self.data).counts
        return {}

    @property
    def saved(self):
        if self.data_type == 'comment':
            return Comment(self._client, self.data).saved
        return False

    @property
    def my_vote(self):
        if self.data_type == 'comment':
            return Comment(self._client, self.data).my_vote
        return None

    @property
    def permalink(self):
        if self.is_private_message:
            message = self.data.get('private_message') or {}
            return message.get('ap_id')
        if self.data_type == 'comment':
            comment_id = (self.data.get('comment') or {}).get('id')
            return '{}/comment/{}'.format(
                self._client.instance, comment_id)
        if self.data_type == 'post':
            return '{}/post/{}'.format(
                self._client.instance, self.post_id)
        return None

    def mark_read(self, read=True):
        self._client.mark_notification_read(self.id, read)
        self.notification['read'] = bool(read)
        return self

    def mark_unread(self):
        return self.mark_read(False)

    def reply(self, content):
        if self.is_private_message:
            message = self.data.get('private_message') or {}
            my_id = self._client.user_id
            recipient_id = (message.get('recipient_id')
                            if message.get('creator_id') == my_id
                            else message.get('creator_id'))
            return self._client.send_message(recipient_id, content)
        if self.data_type == 'comment':
            return self._client.create_comment(
                self.post_id, content,
                parent_id=(self.data.get('comment') or {}).get('id'))
        return self._client.create_comment(self.post_id, content)

    def delete(self):
        if not self.is_private_message:
            raise UnsupportedFeatureError(
                'Only private messages can be deleted from the inbox')
        message = self.data.get('private_message') or {}
        return self._client.delete_message(message.get('id'), True)


class _CommentInboxItem(Model):
    """Shared implementation for comment replies and mentions."""

    _container_key = None

    @property
    def container(self):
        return self._data.get(self._container_key) or {}

    @property
    def id(self):
        return self.container.get('id')

    @property
    def comment_id(self):
        return self.container.get('comment_id')

    @property
    def read(self):
        return bool(self.container.get('read'))

    @property
    def published(self):
        return self.container.get('published')

    @property
    def created_utc(self):
        return to_epoch(self.published)

    @property
    def creator_data(self):
        return self._data.get('creator') or {}

    @property
    def creator(self):
        return User(self._client, {'person': self.creator_data})

    @property
    def recipient_data(self):
        return self._data.get('recipient') or {}

    @property
    def post_data(self):
        return self._data.get('post') or {}

    @property
    def community_data(self):
        return self._data.get('community') or {}

    @property
    def post_title(self):
        return self.post_data.get('name')

    @property
    def post_id(self):
        return self.post_data.get('id')

    @property
    def community_name(self):
        return self.community_data.get('name')

    @property
    def counts(self):
        return self._data.get('counts') or {}

    @property
    def score(self):
        return self.counts.get('score', 0)

    @property
    def saved(self):
        return bool(self._data.get('saved'))

    @property
    def my_vote(self):
        return self._data.get('my_vote')

    @property
    def comment(self):
        view = {
            'comment': self._data.get('comment') or {},
            'creator': self.creator_data,
            'post': self.post_data,
            'community': self.community_data,
            'counts': self.counts,
            'saved': self._data.get('saved', False),
            'my_vote': self._data.get('my_vote'),
            'creator_is_admin': self._data.get('creator_is_admin', False),
            'creator_is_moderator': self._data.get(
                'creator_is_moderator', False),
        }
        return Comment(self._client, view)

    @property
    def permalink(self):
        return '{}/comment/{}'.format(self._client.instance, self.comment_id)

    def _mark_read(self, read=True):
        raise NotImplementedError

    def mark_read(self, read=True):
        self._mark_read(read)
        self.container['read'] = bool(read)
        return self

    def mark_unread(self):
        return self.mark_read(False)

    def reply(self, content):
        return self._client.create_comment(
            self.post_id, content, parent_id=self.comment_id)


class Reply(_CommentInboxItem):
    """A reply to one of the logged-in user's comments."""

    _container_key = 'comment_reply'

    def _mark_read(self, read=True):
        return self._replace(self._client.mark_reply_read(self.id, read))


class Mention(_CommentInboxItem):
    """A mention of the logged-in user."""

    _container_key = 'person_mention'

    def _mark_read(self, read=True):
        return self._replace(self._client.mark_mention_read(self.id, read))


class SearchResults(Model):
    """One page of search results."""

    @property
    def type(self):
        return self._data.get('type_')

    @property
    def posts(self):
        return [Post(self._client, item)
                for item in self._data.get('posts') or []]

    @property
    def comments(self):
        return [Comment(self._client, item)
                for item in self._data.get('comments') or []]

    @property
    def communities(self):
        return [Community(self._client, item)
                for item in self._data.get('communities') or []]

    @property
    def users(self):
        return [User(self._client, item)
                for item in self._data.get('users') or []]

    @property
    def total(self):
        return (len(self._data.get('posts') or [])
                + len(self._data.get('comments') or [])
                + len(self._data.get('communities') or [])
                + len(self._data.get('users') or []))


class Site(Model):
    """Instance metadata from ``GET /site``."""

    @property
    def site_view(self):
        return self._data.get('site_view') or {}

    @property
    def site(self):
        return self.site_view.get('site') or {}

    @property
    def local_site(self):
        return self.site_view.get('local_site') or {}

    @property
    def counts(self):
        return self.site_view.get('counts') or {}

    @property
    def version(self):
        return self._data.get('version')

    @property
    def name(self):
        return self.site.get('name')

    @property
    def description(self):
        return self.site.get('description')

    @property
    def sidebar(self):
        return self.site.get('sidebar')

    @property
    def icon(self):
        return self.site.get('icon')

    @property
    def banner(self):
        return self.site.get('banner')

    @property
    def actor_id(self):
        return self.site.get('actor_id')

    @property
    def my_user_info(self):
        return self._data.get('my_user') or {}

    @property
    def local_user(self):
        return (self.my_user_info.get('local_user_view') or {}).get(
            'local_user') or {}

    @property
    def my_user(self):
        info = self.my_user_info
        view = info.get('local_user_view') or {}
        person = view.get('person')
        if not person:
            return None
        return User(self._client, {
            'person': person,
            'counts': view.get('counts') or {},
            'is_admin': person.get('admin', False),
        })

    @property
    def admins(self):
        return [
            User(self._client, item)
            for item in self._data.get('admins') or []
        ]

    @property
    def discussion_languages(self):
        return self._data.get('discussion_languages') or []

    @property
    def all_languages(self):
        return self._data.get('all_languages') or []

    @property
    def discussion_language_ids(self):
        ids = []
        for language in self.discussion_languages:
            if isinstance(language, dict):
                ids.append(language.get('id'))
            else:
                ids.append(language)
        return [value for value in ids if value is not None]

    @property
    def default_language_id(self):
        ids = self.discussion_language_ids
        if ids:
            return ids[0]
        for language in self.all_languages:
            if language.get('id') is not None:
                return language.get('id')
        return None

    @property
    def enable_downvotes(self):
        return bool(self.local_site.get('enable_downvotes', True))

    @property
    def enable_nsfw(self):
        return bool(self.local_site.get('enable_nsfw', True))

    @property
    def private_instance(self):
        return bool(self.local_site.get('private_instance'))

    @property
    def community_creation_admin_only(self):
        return bool(self.local_site.get('community_creation_admin_only'))

    @property
    def captcha_enabled(self):
        return bool(self.local_site.get('captcha_enabled'))

    @property
    def registration_mode(self):
        return self.local_site.get('registration_mode')

    @property
    def default_post_listing_type(self):
        return self.local_site.get('default_post_listing_type')

    @property
    def federation_enabled(self):
        return bool(self.local_site.get('federation_enabled'))

    @property
    def taglines(self):
        return self._data.get('taglines') or []


class UnreadCount(object):
    """Unread inbox counters returned by the Lemmy API."""

    def __init__(self, replies=0, mentions=0, private_messages=0,
                 notifications=None):
        self.replies = int(replies or 0)
        self.mentions = int(mentions or 0)
        self.private_messages = int(private_messages or 0)
        self.notifications = (None if notifications is None
                              else int(notifications or 0))

    @property
    def total(self):
        if self.notifications is not None:
            return self.notifications
        return self.replies + self.mentions + self.private_messages

    def __repr__(self):
        return ('<UnreadCount replies={} mentions={} private_messages={}>'
                .format(self.replies, self.mentions, self.private_messages))

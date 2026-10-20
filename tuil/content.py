# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re
import time
import logging
from datetime import datetime
from urllib.parse import urlparse

import six
from bs4 import BeautifulSoup
from kitchen.text.display import wrap

from . import exceptions
from .api import (
    Comment,
    Mention,
    Pager,
    PrivateMessage,
    User,
)

_logger = logging.getLogger(__name__)


LISTING_NAMES = ('front', 'all', 'local', 'subscribed')
USER_ROOMS = ('overview', 'submitted', 'comments')
PRIVATE_USER_ROOMS = ('saved', 'upvoted', 'downvoted', 'hidden')

POST_SORT_PERIODS = {
    'hour': 'TopSixHour',
    'day': 'TopDay',
    'week': 'TopWeek',
    'month': 'TopMonth',
    'year': 'TopYear',
    'all': 'TopAll',
}

COMMENT_SORTS = {
    'hot': 'Hot',
    'top': 'Top',
    'new': 'New',
    'old': 'Old',
    'controversial': 'Controversial',
}


def _community_name(value):
    """Return a bare Lemmy community name."""
    value = str(value).strip().strip('/')
    for prefix in ('c/', 'r/'):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value


def _user_name(value):
    value = str(value).strip().strip('/')
    for prefix in ('u/', 'user/', '@', '!'):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value


def _timestamp(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Content(object):

    def get(self, index, n_cols):
        """
        Grab the item at the given index, and format the text to fit a width of
        n columns.
        """
        raise NotImplementedError

    def iterate(self, index, step, n_cols=70):
        """
        Return an iterator that starts and the current index and increments
        by the given step.
        """

        while True:
            if step < 0 and index < 0:
                # Hack to prevent displaying a submission's post if iterating
                # comments in the negative direction
                break
            try:
                yield self.get(index, n_cols=n_cols)
            except IndexError:
                break
            index += step

    @property
    def range(self):
        """
        Return the minimm and maximum valid indicies.
        """
        raise NotImplementedError

    @staticmethod
    def flatten_comments(comments, root_level=0):
        """
        Flatten a Lemmy comment tree while preserving the nested level of each
        comment via the ``nested_level`` attribute.

        Lemmy returns comments as a flat list.  The parent-child relationship
        is encoded in each comment's ``path`` (for example ``0.12.34``).
        """
        comments = list(comments)
        if not comments:
            return []

        by_id = {}
        for comment in comments:
            identifier = getattr(comment, 'id', None)
            if identifier is not None:
                by_id[identifier] = comment

        children = {}
        roots = []
        for comment in comments:
            parent = getattr(comment, 'parent_id', None)
            if parent in by_id and parent != getattr(comment, 'id', None):
                children.setdefault(parent, []).append(comment)
            else:
                roots.append(comment)

        retval = []
        visited = set()

        def visit(comment, level):
            identifier = getattr(comment, 'id', None)
            if identifier in visited:
                return
            visited.add(identifier)
            comment.nested_level = level
            retval.append(comment)
            for child in children.get(identifier, []):
                visit(child, level + 1)

        for comment in roots:
            visit(comment, root_level)

        # A malformed path should not make comments disappear.
        for comment in comments:
            if getattr(comment, 'id', None) not in visited:
                visit(comment, root_level)

        return retval

    @classmethod
    def strip_comment(cls, comment, level=0):
        """
        Parse a Lemmy comment and return a dict ready for the terminal.
        """
        content = comment.content or '[deleted]'
        author = comment.author or '[deleted]'
        edited = comment.edited

        data = {
            'object': comment,
            'type': 'Comment',
            'level': level,
            'body': content,
            'html': content,
            'created': cls.humanize_timestamp(comment.created_utc),
            'score': '{0}'.format(comment.score),
            'author': author,
            'is_author': bool(comment.is_op),
            'flair': '',
            'likes': comment.my_vote,
            'gold': 0,
            'permalink': comment.permalink,
            'stickied': False,
            'distinguished': bool(comment.distinguished),
            'hidden': False,
            'saved': comment.saved,
            'edited': '',
        }
        if edited:
            data['edited'] = '(edit {})'.format(
                cls.humanize_timestamp(edited))
        return data

    @classmethod
    def strip_submission(cls, post):
        """
        Parse a Lemmy post and return a dict ready for the terminal.

        The ``subreddit`` key is kept for compatibility with the page layer;
        it contains the bare community name.
        """
        title = post.title or '[deleted]'
        text = post.body or ''
        author = post.author or '[deleted]'
        permalink = post.permalink
        edited = post.edited

        data = {
            'object': post,
            'type': 'Submission',
            'title': title,
            'text': text,
            'html': text,
            'created': cls.humanize_timestamp(post.created_utc),
            'created_long': cls.humanize_timestamp(
                post.created_utc, verbose=True),
            'created_exact': cls.exact_timestamp(post.created_utc),
            'comments': post.comments_count,
            'score': '{0}'.format(post.score),
            'author': author,
            'permalink': permalink,
            'subreddit': post.community_name or '[unknown]',
            'flair': '',
            'url_full': post.link_url or permalink,
            'likes': post.my_vote,
            'gold': 0,
            'nsfw': post.nsfw,
            'stickied': post.stickied,
            'hidden': post.hidden,
            'xpost_subreddit': None,
            'index': None,
            'saved': post.saved,
            'edited': '',
            'edited_long': '',
            'edited_exact': '',
        }
        if edited:
            data['edited'] = '(edit {})'.format(
                cls.humanize_timestamp(edited))
            data['edited_long'] = '(edit {})'.format(
                cls.humanize_timestamp(edited, verbose=True))
            data['edited_exact'] = '(edit {})'.format(
                cls.exact_timestamp(edited))

        if post.url:
            data['url'] = post.link_url
            data['url_type'] = 'external'
        else:
            data['url'] = 'self.{0}'.format(data['subreddit'])
            data['url_type'] = 'selfpost'
            data['url_full'] = permalink
        return data

    @staticmethod
    def strip_subscription(community):
        """
        Parse a Lemmy community and return a dict ready for the terminal.
        """
        return {
            'object': community,
            'type': 'Subscription',
            'name': '/c/' + community.name,
            'title': community.title or '',
        }

    @classmethod
    def strip_saved_comment(cls, comment):
        """Render a comment that appears in a post listing."""
        body = comment.content or '[deleted]'
        title = '[Comment] {0}'.format(body.replace('\n', ' '))
        return {
            'object': comment,
            'type': 'SavedComment',
            'level': None,
            'title': title,
            'comments': None,
            'url_full': comment.permalink,
            'url': comment.permalink,
            'permalink': comment.permalink,
            'nsfw': False,
            'subreddit': comment.community_name or '[unknown]',
            'url_type': 'selfpost',
            'score': '{0}'.format(comment.score),
            'likes': comment.my_vote,
            'created': cls.humanize_timestamp(comment.created_utc),
            'saved': comment.saved,
            'stickied': bool(comment.distinguished),
            'gold': 0,
            'author': comment.author or '[deleted]',
            'flair': '',
            'hidden': False,
            'edited': '',
        }

    @classmethod
    def strip_message(cls, message, username=None):
        """
        Parse an inbox item (reply, mention or private message).
        """
        author = getattr(message, 'creator', None)
        author_name = getattr(author, 'name', None) or '[deleted]'
        recipient = getattr(message, 'recipient', None)
        recipient_name = getattr(recipient, 'name', None) or username or ''
        created = _timestamp(getattr(message, 'created_utc', None))

        data = {
            'object': message,
            'id': message.id,
            'body': getattr(message, 'content', None) or '[deleted]',
            'html': getattr(message, 'content', None) or '[deleted]',
            'created': cls.humanize_timestamp(created),
            'created_long': cls.humanize_timestamp(created, verbose=True),
            'author': author_name,
            'recipient': recipient_name,
            'distinguished': None,
            'is_new': not bool(getattr(message, 'read', False)),
            'was_comment': False,
        }

        if isinstance(message, PrivateMessage):
            data.update({
                'type': 'Message',
                'level': 0,
                'permalink': None,
                'submission_permalink': None,
                'subreddit_name': None,
                'link_title': None,
                'context': None,
                'subject': 'Private message',
            })
        else:
            comment = message.comment
            body = comment.content or '[deleted]'
            post_url = '{}/post/{}'.format(
                message._client.instance, message.post_id)
            subject = 'mention' if isinstance(message, Mention) else 'reply'
            data.update({
                'type': 'InboxComment',
                'level': 0,
                'body': body,
                'html': body,
                'permalink': message.permalink,
                'submission_permalink': post_url,
                'subreddit_name': message.community_name or '',
                'link_title': message.post_title or '',
                'context': post_url,
                'subject': subject,
                'was_comment': True,
            })
        return data

    @staticmethod
    def humanize_timestamp(utc_timestamp, verbose=False):
        """
        Convert a utc timestamp into a human readable relative-time.
        """
        if utc_timestamp is None:
            return 'unknown'

        seconds = time.time() - utc_timestamp

        if seconds < 60:
            return 'moments ago' if verbose else '0min'

        minutes = seconds // 60
        if minutes < 60:
            if verbose and minutes == 1:
                return '1 minute ago'
            elif verbose:
                return '%d minutes ago' % minutes
            else:
                return '%dmin' % minutes

        hours = minutes // 60
        if hours < 24:
            if verbose and hours == 1:
                return '1 hour ago'
            elif verbose:
                return '%d hours ago' % hours
            else:
                return '%dhr' % hours

        days = hours // 24
        if days < 30:
            if verbose and days == 1:
                return '1 day ago'
            elif verbose:
                return '%d days ago' % days
            else:
                return '%dday' % days

        months = days // 31
        if months < 12:
            if verbose and months == 1:
                return '1 month ago'
            elif verbose:
                return '%d months ago' % months
            else:
                return '%dmonth' % months

        years = months // 12
        if verbose and years == 1:
            return '1 year ago'
        elif verbose:
            return '%d years ago' % years
        else:
            return '%dyr' % years

    @staticmethod
    def exact_timestamp(utc_timestamp):
        if utc_timestamp is None:
            return 'unknown'
        dt = datetime.fromtimestamp(utc_timestamp)

        # https://stackoverflow.com/a/765990
        yearsago = ((datetime.now() - dt).days / 365.2425)

        if yearsago > 0:
            return six.u(dt.strftime("%Y-%m-%d"))
        else:
            return six.u(dt.strftime("%m-%d %H:%M"))

    @staticmethod
    def wrap_text(text, width):
        """
        Wrap text paragraphs to the given character width while preserving
        newlines.
        """
        out = []
        for paragraph in (text or '').splitlines():
            # Wrap returns an empty list when paragraph is a newline. In order
            # to preserve newlines we substitute a list containing an empty
            # string.
            lines = wrap(paragraph, width=width) or ['']
            out.extend(lines)
        return out

    @staticmethod
    def extract_links(html, base_url=None):
        """
        Extract a list of hyperlinks from Markdown or HTML.
        """
        links = []
        seen = set()

        def add(text, href):
            if not href:
                return
            if href.startswith('/') and base_url:
                href = base_url.rstrip('/') + href
            key = (text, href)
            if key not in seen:
                seen.add(key)
                links.append({'text': text, 'href': href})

        if not html:
            return links

        # Markdown links: [text](https://example.com)
        for match in re.finditer(
                r'\[([^\]]*)\]\((https?://[^)\s]+)\)', html):
            add(match.group(1), match.group(2))

        # Raw HTML anchors, which sometimes appear in Lemmy markdown.
        soup = BeautifulSoup(html, 'html.parser')
        for link in soup.findAll('a'):
            add(link.text, link.get('href'))
        return links


class SubmissionContent(Content):
    """
    Grab a post and its comments from the Lemmy API.
    """

    def __init__(self, client, submission, loader, indent_size=2,
                 max_indent_level=8, order=None, max_comment_cols=120,
                 max_comments=500):

        submission_data = self.strip_submission(submission)
        comments = self._load_comments(client, submission, order, max_comments)
        comments = self.flatten_comments(comments)

        self.indent_size = indent_size
        self.max_indent_level = max_indent_level
        self.name = submission_data['permalink']
        self.order = order
        self.query = None
        self._loader = loader
        self._client = client
        self._submission = submission
        self._submission_data = submission_data
        self._comment_data = [
            self.strip_comment(c, level=getattr(c, 'nested_level', 0))
            for c in comments]
        self._max_comment_cols = max_comment_cols

    @staticmethod
    def _load_comments(client, submission, order, max_comments):
        sort = COMMENT_SORTS.get((order or 'hot').split('-')[0], 'Hot')
        return list(client.list_comments(
            post=submission, sort=sort, max_depth=8, page_size=50,
            max_items=max_comments))

    @classmethod
    def from_url(cls, client, url, loader, indent_size=2,
                 max_indent_level=8, order=None, max_comment_cols=120,
                 max_comments=500):
        post_id, comment_id = cls._parse_url(client, url)
        if comment_id is not None:
            comment = client.get_comment(comment_id)
            submission = client.get_post(comment.post_id)
        else:
            submission = client.get_post(post_id)
        return cls(client, submission, loader, indent_size, max_indent_level,
                   order, max_comment_cols, max_comments)

    @staticmethod
    def _parse_url(client, url):
        value = str(url or '').strip()
        if not value:
            raise exceptions.SubmissionError('A post URL is required')
        if value.isdigit():
            return int(value), None
        if value.startswith('/'):
            value = client.instance.rstrip('/') + value

        path = urlparse(value).path
        match = re.search(r'/(?:post|p)/(\d+)', path)
        if match:
            return int(match.group(1)), None

        match = re.search(r'/comment/(\d+)', path)
        if match:
            return None, int(match.group(1))

        match = re.search(r'/(\d+)(?:/|$)', path)
        if match:
            return int(match.group(1)), None
        raise exceptions.SubmissionError(
            'Could not find a post ID in {!r}'.format(url))

    @property
    def range(self):
        return -1, len(self._comment_data) - 1

    def get(self, index, n_cols=70):
        """
        Grab the `i`th submission, with the title field formatted to fit inside
        of a window of width `n`
        """

        if index < -1:
            raise IndexError

        elif index == -1:
            data = self._submission_data
            data['split_title'] = self.wrap_text(data['title'], width=n_cols-2)
            data['split_text'] = self.wrap_text(data['text'], width=n_cols-2)
            data['n_rows'] = len(data['split_title'] + data['split_text']) + 5
            data['h_offset'] = 0

        else:
            data = self._comment_data[index]
            indent_level = min(data['level'], self.max_indent_level)
            data['h_offset'] = indent_level * self.indent_size

            if data['type'] == 'Comment':
                width = min(n_cols - data['h_offset'], self._max_comment_cols)
                data['split_body'] = self.wrap_text(data['body'], width=width)
                data['n_rows'] = len(data['split_body']) + 1
            else:
                data['n_rows'] = 1

        return data

    def toggle(self, index, n_cols=70):
        """
        Toggle the state of the object at the given index.

        If it is a comment, pack it into a hidden comment.
        If it is a hidden comment, unpack it.
        """
        data = self.get(index)

        if data['type'] == 'Submission':
            # Can't hide the submission!
            pass

        elif data['type'] == 'Comment':
            cache = [data]
            count = 1
            for d in self.iterate(index + 1, 1, n_cols):
                if d['level'] <= data['level']:
                    break

                count += d.get('count', 1)
                cache.append(d)

            comment = {
                'type': 'HiddenComment',
                'cache': cache,
                'count': count,
                'level': data['level'],
                'body': 'Hidden',
                'hidden': True}

            self._comment_data[index:index + len(cache)] = [comment]

        elif data['type'] == 'HiddenComment':
            self._comment_data[index:index + 1] = data['cache']

        else:
            raise ValueError('%s type not recognized' % data['type'])


class SubredditContent(Content):
    """
    Grab posts from a Lemmy listing or community and store them lazily.
    """

    def __init__(self, config, name, submissions, loader, order=None,
                 query=None, filter_nsfw=False, client=None):

        self.config = config
        self.name = name
        self.order = order
        self.query = query
        self.filter_nsfw = filter_nsfw
        self._loader = loader
        self._submissions = submissions
        self._submission_data = []
        self._client = client

        if self.config['look_and_feel'] == 'default':
            self.max_title_rows = 4
        else:
            self.max_title_rows = 1

        # Verify that content exists for the given submission generator.
        try:
            self.get(0)
        except IndexError:
            full_name = self.name
            if self.order:
                full_name += '/' + self.order
            raise exceptions.NoSubmissionsError(full_name)

    @classmethod
    def from_name(cls, client, config, name, loader, order=None, query=None):
        """
        Params:
            client (LemmyClient): Instance of the Lemmy API client.
            name (text): The name of the desired community, user or listing.
            loader (terminal.loader): Handler for the load screen.
            order (text): Optional sort order.
            query (text): Optional search query.
        """
        parsed = cls._parse_name(name, order=order, query=query)
        kind = parsed['kind']
        resource = parsed['resource']
        room = parsed['room']
        parsed_order = parsed['order']
        display_order = parsed['order_full']
        period = parsed['period']
        display_name = parsed['display_name']

        if query:
            submissions = cls._search_submissions(
                client, query, parsed, period)
        elif kind == 'listing':
            if resource == 'subscribed' and not client.is_logged_in:
                raise exceptions.AccountError('Not logged in')
            listing_type = {
                'front': 'Subscribed' if client.is_logged_in else 'Local',
                'all': 'All',
                'local': 'Local',
                'subscribed': 'Subscribed',
            }[resource]
            submissions = client.list_posts(
                type_=listing_type,
                sort=cls._post_sort(parsed_order, period),
                page_size=50)
        elif kind == 'community':
            submissions = client.list_posts(
                community=resource,
                sort=cls._post_sort(parsed_order, period),
                page_size=50)
        else:
            submissions = cls._user_submissions(
                client, resource, room, parsed_order, period)
            if resource == 'me':
                display_name = display_name.replace(
                    '/u/me', '/u/' + client.me().name)

        filter_nsfw = False
        return cls(config, display_name, submissions, loader,
                   order=display_order, query=query,
                   filter_nsfw=filter_nsfw, client=client)

    @classmethod
    def _search_submissions(cls, client, query, parsed, period):
        sort = cls._search_sort(parsed['order'], period)
        kwargs = {}
        if parsed['kind'] == 'community':
            kwargs['community'] = parsed['resource']
        elif parsed['kind'] == 'user':
            user = parsed['resource']
            if user == 'me':
                if not client.is_logged_in:
                    raise exceptions.AccountError('Not logged in')
                user = client.me().name
            kwargs['creator'] = user
        else:
            listing = parsed['resource']
            if listing == 'front':
                kwargs['listing_type'] = (
                    'Subscribed' if client.is_logged_in else 'Local')
            elif listing in ('all', 'local', 'subscribed'):
                if listing == 'subscribed' and not client.is_logged_in:
                    raise exceptions.AccountError('Not logged in')
                kwargs['listing_type'] = {
                    'all': 'All',
                    'local': 'Local',
                    'subscribed': 'Subscribed',
                }[listing]

        def fetch(page):
            results = client.search(
                query, type_='Posts', sort=sort, page=page, limit=50,
                **kwargs)
            posts = results.posts
            return posts, len(posts) >= 50

        return Pager(fetch)

    @classmethod
    def _user_submissions(cls, client, resource, room, order, period):
        if resource == 'me':
            if not client.is_logged_in:
                raise exceptions.AccountError('Not logged in')
            username = client.me().name
            own = True
        else:
            username = _user_name(resource)
            own = False

        sort = cls._post_sort(order or 'new', period)
        if room in PRIVATE_USER_ROOMS:
            if not own:
                raise exceptions.SubredditError(
                    'Unavailable resource: {0}'.format(resource))
            if room == 'hidden':
                raise exceptions.SubredditError(
                    'Hidden posts are not available in Lemmy API v3')
            if room == 'saved':
                return client.list_posts(
                    saved_only=True, sort=sort, page_size=50)
            if room == 'upvoted':
                return client.list_posts(
                    liked_only=True, sort=sort, page_size=50)
            if room == 'downvoted':
                return client.list_posts(
                    disliked_only=True, sort=sort, page_size=50)

        if room == 'comments':
            return client.list_user_comments(
                username, sort=sort, page_size=50)
        if room == 'submitted':
            return client.list_user_posts(
                username, sort=sort, page_size=50)
        return client.list_user_content(
            username, sort=sort, page_size=50)

    @staticmethod
    def _post_sort(order, period=None):
        if not order or order == 'hot':
            return 'Hot'
        if order == 'top':
            return POST_SORT_PERIODS.get(period or 'day', 'TopDay')
        return {
            'new': 'New',
            'rising': 'Active',
            'active': 'Active',
            'old': 'Old',
            'controversial': 'Controversial',
            'gilded': 'TopAll',
            'relevance': 'TopAll',
            'comments': 'MostComments',
        }.get(order, 'Hot')

    @staticmethod
    def _search_sort(order, period=None):
        if not order or order == 'relevance':
            return 'TopAll'
        if order == 'top':
            return POST_SORT_PERIODS.get(period or 'day', 'TopDay')
        return {
            'new': 'New',
            'comments': 'MostComments',
            'hot': 'Hot',
        }.get(order, 'TopAll')

    @classmethod
    def _parse_name(cls, name, order=None, query=None):
        raw = (name or '').strip()
        if not raw:
            raise exceptions.SubredditError('Community cannot be empty')
        if '://' in raw:
            raw = urlparse(raw).path

        parts = [seg for seg in raw.replace('\\', '/').strip(' /').split('/')
                 if seg]
        if not parts:
            raise exceptions.SubredditError('Community cannot be empty')

        if 'domain' in parts:
            raise exceptions.SubredditError(
                'Domain listings are not available in Lemmy')
        if 'm' in parts or parts[0].endswith('/m'):
            raise exceptions.SubredditError(
                'Multireddits are not available in Lemmy')

        # A bare listing name, e.g. "front" or "all/top-day".
        if parts[0] in LISTING_NAMES:
            if len(parts) > 2:
                raise exceptions.SubredditError(
                    '`{}` is an invalid format'.format(name))
            resource = parts[0]
            resource_order = parts[1] if len(parts) == 2 else None
            parsed = cls._make_parsed(
                'listing', resource, None, resource_order, order, query)
            parsed['display_name'] = '/r/' + resource
            return parsed

        root = 'c'
        if parts[0] in ('r', 'c', 'u', 'user', 'community'):
            root = parts.pop(0)
            if root == 'user':
                root = 'u'
            elif root == 'community':
                root = 'c'

        if not parts:
            raise exceptions.SubredditError('Community cannot be empty')

        if root in ('r', 'c'):
            resource = parts[0]
            if len(parts) > 2:
                raise exceptions.SubredditError(
                    '`{}` is an invalid format'.format(name))
            resource_order = parts[1] if len(parts) == 2 else None
            if resource in LISTING_NAMES:
                parsed = cls._make_parsed(
                    'listing', resource, None, resource_order, order, query)
                parsed['display_name'] = '/r/' + resource
                return parsed
            if '+' in resource:
                raise exceptions.SubredditError(
                    'Multi-community pages are not available in Lemmy')
            parsed = cls._make_parsed(
                'community', resource, None, resource_order, order, query)
            parsed['display_name'] = '/r/' + resource
            return parsed

        # User page.
        resource = parts[0]
        room = 'overview'
        resource_order = None
        if len(parts) >= 2:
            if parts[1] in USER_ROOMS + PRIVATE_USER_ROOMS:
                room = parts[1]
                if len(parts) == 3:
                    resource_order = parts[2]
                elif len(parts) > 3:
                    raise exceptions.SubredditError(
                        '`{}` is an invalid format'.format(name))
            elif len(parts) == 2:
                resource_order = parts[1]
            else:
                raise exceptions.SubredditError(
                    '`{}` is an invalid format'.format(name))

        parsed = cls._make_parsed(
            'user', resource, room, resource_order, order, query)
        display_name = '/u/' + resource
        if room != 'overview':
            display_name += '/' + room
        parsed['display_name'] = display_name
        return parsed

    @staticmethod
    def _make_parsed(kind, resource, room, resource_order, order, query):
        order = order or resource_order
        period = None
        if order and '-' in order:
            order, period = order.split('-', 1)
        if kind == 'user' and not order:
            order = 'new'
        order_full = None
        if order:
            order_full = order + ('-' + period if period else '')

        if query:
            allowed = ['relevance', 'top', 'comments', 'new', None]
            period_allowed = ['top', 'comments']
        else:
            allowed = ['hot', 'top', 'rising', 'new', 'controversial',
                       'active', 'old', 'gilded', None]
            period_allowed = ['top', 'controversial']

        if order == 'gilded' and not query:
            raise exceptions.SubredditError(
                'Gilded listings are not available in Lemmy')
        if order not in allowed:
            raise exceptions.SubredditError('Invalid order `%s`' % order)
        if period not in ['all', 'day', 'hour', 'month', 'week', 'year', None]:
            raise exceptions.SubredditError('Invalid period `%s`' % period)
        if period and order not in period_allowed:
            raise exceptions.SubredditError(
                '`%s` order does not allow sorting by period' % order)

        return {
            'kind': kind,
            'resource': resource,
            'room': room,
            'order': order,
            'order_full': order_full,
            'period': period,
            'display_name': None,
        }

    @property
    def range(self):
        # Note that for listings, the submissions are generated lazily and
        # there is no actual "end" index. Instead, we return the bottom index
        # that we have loaded so far.
        return 0, len(self._submission_data) - 1

    def get(self, index, n_cols=70):
        """
        Grab the `i`th submission, with the title field formatted to fit inside
        of a window of width `n_cols`
        """

        if index < 0:
            raise IndexError

        nsfw_count = 0
        while index >= len(self._submission_data):
            try:
                with self._loader('Loading more submissions'):
                    item = next(self._submissions)
                if self._loader.exception:
                    raise IndexError
            except StopIteration:
                raise IndexError
            else:
                # Lemmy does not expose a per-user NSFW preference in the
                # signed-in user object on all versions.  Filtering can be
                # enabled once the setting is available.
                if self.filter_nsfw and getattr(item, 'nsfw', False):
                    nsfw_count += 1
                    if not self._submission_data and nsfw_count >= 20:
                        raise exceptions.SubredditError(
                            'You must be over 18+ to view this community')
                    continue
                else:
                    nsfw_count = 0

                if isinstance(item, Comment):
                    data = self.strip_saved_comment(item)
                elif isinstance(item, User):
                    data = {
                        'object': item,
                        'type': 'User',
                        'title': item.display_name,
                        'text': item.bio or '',
                        'html': item.bio or '',
                        'url_full': item.permalink,
                        'url': item.permalink,
                        'url_type': 'external',
                        'subreddit': '',
                        'comments': None,
                        'score': '0',
                        'likes': None,
                        'saved': False,
                        'hidden': False,
                        'stickied': False,
                        'gold': 0,
                        'nsfw': False,
                        'author': item.name,
                        'flair': '',
                        'created': self.humanize_timestamp(item.created_utc),
                        'edited': '',
                    }
                else:
                    data = self.strip_submission(item)

                data['index'] = len(self._submission_data) + 1

                # Add the post number to the beginning of the title if needed
                if self.config['look_and_feel'] == 'default':
                    data['title'] = '{0}. {1}'.format(
                        data['index'], data['title'])

                self._submission_data.append(data)

        # Modifies the original dict, faster than copying
        data = self._submission_data[index]

        if self.config['look_and_feel'] == 'compact':
            data['n_rows'] = 2
        elif self.config['subreddit_format']:
            data['n_rows'] = self.config['subreddit_format'].count('\n') + 1
        else:
            data['split_title'] = self.wrap_text(data['title'], width=n_cols)
            data['n_rows'] = len(data['split_title']) + 3

        data['h_offset'] = 0

        return data


class SubscriptionContent(Content):

    def __init__(self, name, subscriptions, loader):

        self.name = name
        self.order = None
        self.query = None
        self._loader = loader
        self._subscriptions = subscriptions
        self._subscription_data = []

        try:
            self.get(0)
        except IndexError:
            raise exceptions.SubscriptionError('No content')

        # Load a large number of subscriptions up front so that the user can
        # jump to the end of the page with `G`.
        if name not in ('Popular Communities', 'Popular Subreddits'):
            try:
                self.get(1023)
            except IndexError:
                pass

    @classmethod
    def from_user(cls, client, loader, content_type='subreddit'):
        if content_type == 'subreddit':
            if not client.is_logged_in:
                raise exceptions.AccountError('Not logged in')
            name = 'My Communities'
            items = list(client.list_communities(
                type_='Subscribed', sort='TopAll', page_size=50,
                max_items=1000))
            items.sort(key=lambda c: (c.name or '').lower())
        elif content_type == 'popular':
            name = 'Popular Communities'
            items = list(client.list_communities(
                type_='All', sort='TopAll', page_size=50, max_items=1000))
        else:
            raise exceptions.SubscriptionError(
                'Invalid type %s' % content_type)

        return cls(name, iter(items), loader)

    @property
    def range(self):
        return 0, len(self._subscription_data) - 1

    def get(self, index, n_cols=70):
        """
        Grab the `i`th object, with the title field formatted to fit
        inside of a window of width `n_cols`
        """

        if index < 0:
            raise IndexError

        while index >= len(self._subscription_data):
            try:
                with self._loader('Loading content'):
                    subscription = next(self._subscriptions)
                if self._loader.exception:
                    raise IndexError
            except StopIteration:
                raise IndexError
            else:
                data = self.strip_subscription(subscription)
                self._subscription_data.append(data)

        data = self._subscription_data[index]
        data['split_title'] = self.wrap_text(data['title'], width=n_cols)
        data['n_rows'] = len(data['split_title']) + 1
        data['h_offset'] = 0

        return data


class InboxContent(Content):

    def __init__(self, order, content_generator, loader, username=None,
                 indent_size=2, max_indent_level=8):

        self.name = 'My Inbox'
        self.order = order
        self.query = None
        self.indent_size = indent_size
        self.max_indent_level = max_indent_level
        self._loader = loader
        self._content_generator = content_generator
        self._content_data = []
        self._username = username

        try:
            self.get(0)
        except IndexError:
            if order == 'all':
                raise exceptions.InboxError('Empty Inbox')
            else:
                raise exceptions.InboxError('Empty Inbox [%s]' % order)

    @classmethod
    def from_user(cls, client, loader, order='all'):
        if not client.is_logged_in:
            raise exceptions.AccountError('Not logged in')
        username = getattr(client.me(), 'name', None)

        if order == 'all':
            items = cls._all_items(client, unread_only=False)
        elif order == 'unread':
            items = cls._all_items(client, unread_only=True)
        elif order == 'messages':
            items = list(client.list_messages(
                page_size=50, max_items=200))
        elif order in ('comments', 'posts'):
            items = list(client.list_replies(
                page_size=50, max_items=200))
        elif order == 'mentions':
            items = list(client.list_mentions(
                page_size=50, max_items=200))
        elif order == 'sent':
            items = list(client.list_messages(
                creator=client.me().id, page_size=50, max_items=200))
        else:
            raise exceptions.InboxError('Invalid order %s' % order)

        return cls(order, iter(items), loader, username=username)

    @staticmethod
    def _all_items(client, unread_only=False):
        items = []
        items.extend(client.list_replies(
            unread_only=unread_only, page_size=50, max_items=200))
        items.extend(client.list_mentions(
            unread_only=unread_only, page_size=50, max_items=200))
        items.extend(client.list_messages(
            unread_only=unread_only, page_size=50, max_items=200))
        items.sort(
            key=lambda item: getattr(item, 'created_utc', 0) or 0,
            reverse=True)
        return items

    @property
    def range(self):
        return 0, len(self._content_data) - 1

    def get(self, index, n_cols=70):
        """
        Grab the `i`th object, with the title field formatted to fit
        inside of a window of width `n_cols`
        """

        if index < 0:
            raise IndexError

        while index >= len(self._content_data):
            try:
                with self._loader('Loading content'):
                    item = next(self._content_generator)
                if self._loader.exception:
                    raise IndexError
            except StopIteration:
                raise IndexError
            else:
                data = self.strip_message(item, username=self._username)
                self._content_data.append(data)

        data = self._content_data[index]
        indent_level = min(data['level'], self.max_indent_level)
        data['h_offset'] = indent_level * self.indent_size
        width = n_cols - data['h_offset']
        data['split_body'] = self.wrap_text(data['body'], width=width)
        data['n_rows'] = len(data['split_body']) + 2

        return data


class EmptyContent(Content):

    def __init__(self, loader,
                 indent_size=2, max_indent_level=8):

        self.name = 'Empty Page'
        self.order = None
        self.query = None
        self.indent_size = indent_size
        self.max_indent_level = max_indent_level
        self._loader = loader
        self._content_data = []

    @property
    def range(self):
        return 0, len(self._content_data) - 1

    def get(self, index, n_cols=70):
        data = {}
        data['n_rows'] = 1
        data['h_offset'] = 0
        return data

#!/usr/bin/env python3
"""Run opt-in read-only checks against a live Lemmy instance.

The default checks are anonymous.  The ``--auth`` checks log in with the
credentials in ``TUIL_TEST_USERNAME`` and ``TUIL_TEST_PASSWORD`` (or prompt
for them) and read account data.  This script never votes, posts, edits,
deletes or sends messages.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# pylint: disable=wrong-import-position
from tuil.api import LemmyClient


def require_items(items, label):
    items = list(items)
    if not items:
        raise RuntimeError('{0} returned no items'.format(label))
    return items


def build_parser():
    parser = argparse.ArgumentParser(
        description='Read-only live checks for tuil.')
    parser.add_argument(
        '--instance', default=os.getenv('TUIL_TEST_INSTANCE', 'lemmy.ml'),
        help='Lemmy instance to test')
    parser.add_argument(
        '--community', default=os.getenv('TUIL_TEST_COMMUNITY', 'linux'),
        help='Community used for listing and lookup checks')
    parser.add_argument(
        '--user-name', default=os.getenv('TUIL_TEST_USER', 'dessalines'),
        help='User used for profile and content checks')
    parser.add_argument(
        '--page-size', type=int, default=5,
        help='Number of items fetched by each listing check')
    parser.add_argument(
        '--timeout', type=float, default=20.0,
        help='HTTP timeout in seconds')
    parser.add_argument(
        '--auth', action='store_true',
        help='Also log in and check account read endpoints')
    return parser


def main():
    args = build_parser().parse_args()
    if args.page_size < 1:
        raise SystemExit('--page-size must be positive')

    client = LemmyClient(args.instance, timeout=args.timeout)
    failures = []

    def check(label, callback):
        try:
            value = callback()
        except Exception as exc:  # pylint: disable=broad-except
            failures.append((label, exc))
            print('FAIL {0}: {1}'.format(label, exc))
            return None
        print('PASS {0}'.format(label))
        return value

    try:
        site = check('site metadata', client.site)
        if site is not None:
            print('     version: {0}'.format(site.version))
            print('     API: {0}'.format(
                'v4' if client.supports_v4() else 'v3'))

        posts = check(
            'anonymous post listing',
            lambda: require_items(
                client.list_posts(
                    type_='All', sort='Hot',
                    page_size=args.page_size,
                    max_items=args.page_size).take(args.page_size),
                'post listing'))
        if posts:
            post = check(
                'post details',
                lambda: client.get_post(posts[0].id))
            if post is not None:
                comments = check(
                    'comment listing',
                    lambda: client.list_comments(
                        post=post.id, page_size=args.page_size,
                        max_items=args.page_size).take(args.page_size))
                print('     comments: {0}'.format(
                    len(comments) if comments else 0))

        community = check(
            'community lookup: {0}'.format(args.community),
            lambda: client.get_community(args.community))
        if community is not None:
            print('     community: {0}'.format(community.name))
            check(
                'community post listing',
                lambda: require_items(
                    client.list_posts(
                        community=community, sort='Hot',
                        page_size=args.page_size,
                        max_items=args.page_size).take(args.page_size),
                    'community post listing'))

        user = check(
            'user lookup: {0}'.format(args.user_name),
            lambda: client.get_user(args.user_name, include_content=False))
        if user is not None:
            print('     user: {0}'.format(user.name))
            items = check(
                'user content listing',
                lambda: client.list_user_content(
                    args.user_name, page_size=args.page_size,
                    max_items=args.page_size).take(args.page_size))
            if items is not None:
                print('     items: {0}'.format(len(items)))

        check(
            'community listing',
            lambda: require_items(
                client.list_communities(
                    type_='All', sort='TopAll',
                    page_size=args.page_size,
                    max_items=args.page_size).take(args.page_size),
                'community listing'))
        check(
            'search',
            lambda: require_items(
                client.search(
                    args.community, type_='Posts', sort='TopDay',
                    limit=args.page_size).posts,
                'search'))

        if args.auth:
            run_auth_checks(client, args, check, failures)
    finally:
        client.close()

    if failures:
        print('\n{0} check(s) failed'.format(len(failures)))
        return 1
    print('\nAll checks passed')
    return 0


def run_auth_checks(client, args, check, failures):
    username = os.getenv('TUIL_TEST_USERNAME')
    password = os.getenv('TUIL_TEST_PASSWORD')
    totp = os.getenv('TUIL_TEST_TOTP')
    if not username:
        username = input('Lemmy username or email: ')
    if password is None:
        password = getpass.getpass('Lemmy password: ')

    user = check(
        'login',
        lambda: client.login(username, password, totp_2fa_token=totp))
    if user is None:
        return
    print('     logged in as: {0}'.format(user.name))

    count = check('unread counts', client.unread_count)
    if count is not None:
        print('     unread total: {0}'.format(count.total))

    for label, callback in (
            ('inbox replies', client.list_replies),
            ('inbox mentions', client.list_mentions),
            ('inbox messages', client.list_messages)):
        items = check(
            label,
            lambda callback=callback: callback(
                page_size=args.page_size,
                max_items=args.page_size).take(args.page_size))
        if items is not None:
            print('     items: {0}'.format(len(items)))

    if client.supports_v4():
        for label, callback in (
                ('inbox notifications', client.list_notifications),
                ('saved content', client.list_saved),
                ('upvoted content',
                 lambda: client.list_liked(like_type='liked_only')),
                ('downvoted content',
                 lambda: client.list_liked(like_type='disliked_only')),
                ('hidden content', client.list_hidden)):
            items = check(
                label,
                lambda callback=callback: callback(
                    page_size=args.page_size,
                    max_items=args.page_size).take(args.page_size))
            if items is not None:
                print('     items: {0}'.format(len(items)))
    else:
        for label, kwargs in (
                ('saved posts', {'saved_only': True}),
                ('upvoted posts', {'liked_only': True}),
                ('downvoted posts', {'disliked_only': True})):
            items = check(
                label,
                lambda kwargs=kwargs: client.list_posts(
                    page_size=args.page_size, max_items=args.page_size,
                    **kwargs).take(args.page_size))
            if items is not None:
                print('     items: {0}'.format(len(items)))

    def logout():
        client.logout()
        if client.is_logged_in:
            raise RuntimeError('logout left a token in memory')

    check('logout', logout)


if __name__ == '__main__':
    sys.exit(main())

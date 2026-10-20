# -*- coding: utf-8 -*-
"""Lazy pagination helper used by the Lemmy API client."""

from collections import deque


class Pager(object):
    """Iterate over pages of remote objects without loading everything at once.

    ``fetch_page(page_number)`` must return either a list of items or a
    ``(items, has_more)`` tuple.  When only a list is returned, a full page is
    assumed to have more items.
    """

    def __init__(self, fetch_page, max_items=None):
        if max_items is not None and max_items < 0:
            raise ValueError('max_items must be zero or greater')
        self._fetch_page = fetch_page
        self._max_items = max_items
        self._page = 1
        self._buffer = deque()
        self._done = False
        self._count = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._max_items is not None and self._count >= self._max_items:
            raise StopIteration

        while not self._buffer:
            if self._done:
                raise StopIteration

            result = self._fetch_page(self._page)
            self._page += 1

            if isinstance(result, tuple):
                items, has_more = result
            else:
                items = result
                has_more = bool(items)

            items = list(items or [])
            if not items and not has_more:
                self._done = True
                raise StopIteration

            self._buffer.extend(items)
            if not has_more:
                self._done = True

            # An empty page with has_more=True is valid.  Loop and ask for
            # the next page instead of stopping the iterator.

        item = self._buffer.popleft()
        self._count += 1
        return item

    next = __next__

    @property
    def page(self):
        """The page number that will be requested next."""
        return self._page

    @property
    def count(self):
        """Number of items yielded so far."""
        return self._count

    def first(self, default=None):
        """Return the first item, leaving the rest of the pager untouched."""
        try:
            return next(self)
        except StopIteration:
            return default

    def take(self, count):
        """Return up to ``count`` items as a list."""
        if count <= 0:
            return []
        items = []
        for item in self:
            items.append(item)
            if len(items) >= count:
                break
        return items

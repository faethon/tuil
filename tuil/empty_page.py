# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import docs
from .content import EmptyContent
from .page import Page, PageController, logged_in
from .objects import Navigator


class EmptyController(PageController):
    character_map = {}


class EmptyPage(Page):
    BANNER = docs.BANNER_EMPTY
    footer = docs.FOOTER_EMPTY

    name = 'empty'

    def __init__(self, reddit, term, config, oauth):
        super(EmptyPage, self).__init__(reddit, term, config, oauth)

        self.controller = EmptyController(self, keymap=config.keymap)
        self.content = EmptyContent(term.loader)
        self.nav = Navigator(self.content.get)

    def handle_selected_page(self):
        self.active = False

    @logged_in
    def refresh_content(self, order=None, name=None):
        pass

    def _draw_item(self, win, data, inverted):
        pass

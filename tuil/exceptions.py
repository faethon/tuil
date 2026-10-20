# -*- coding: utf-8 -*-
from __future__ import unicode_literals


class EscapeInterrupt(Exception):
    "Signal that the ESC key has been pressed"


class ConfigError(Exception):
    "There was a problem with the configuration"


class TUILError(Exception):
    "Base TUIL error class"


class AccountError(TUILError):
    "Could not access user account"


class SubmissionError(TUILError):
    "Post could not be loaded"


class SubredditError(TUILError):
    "Community could not be loaded"


class NoSubmissionsError(TUILError):
    "No posts for the given page"

    def __init__(self, name):
        self.name = name
        message = '`{0}` has no posts'.format(name)
        super(NoSubmissionsError, self).__init__(message)


class SubscriptionError(TUILError):
    "Content could not be fetched"


class InboxError(TUILError):
    "Content could not be fetched"


class ProgramError(TUILError):
    "Problem executing an external program"


class BrowserError(TUILError):
    "Could not open a web browser tab"


class TemporaryFileError(TUILError):
    "Indicates that an error has occurred and the file should not be deleted"


class MailcapEntryNotFound(TUILError):
    "A valid mailcap entry could not be coerced from the given url"


class InvalidRefreshToken(TUILError):
    "The refresh token is corrupt and cannot be used to login"

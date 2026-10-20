# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position

from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import locale
import logging
import warnings

import six

# Need to check for curses compatibility before performing the tuil imports
try:
    import curses
except ImportError:
    if sys.platform == 'win32':
        sys.exit('Fatal Error: This program is not compatible with Windows '
                 'Operating Systems.')
    else:
        sys.exit('Fatal Error: Your python distribution appears to be missing '
                 '_curses.so.\nWas it compiled without support for curses?')

# If we want to override the $BROWSER variable that the python webbrowser
# references, it needs to be done before the webbrowser module is imported
# for the first time.
webbrowser_import_warning = ('webbrowser' in sys.modules)
TUIL_BROWSER, BROWSER = os.environ.get('TUIL_BROWSER'), os.environ.get('BROWSER')
if TUIL_BROWSER:
    os.environ['BROWSER'] = TUIL_BROWSER

from . import docs
from .api import LemmyClient, normalize_instance
from .auth import AuthHelper
from .config import Config, copy_default_config, copy_default_mailcap
from .theme import Theme
from .terminal import Terminal
from .objects import curses_session, patch_webbrowser
from .subreddit_page import SubredditPage
from .submission_page import SubmissionPage
from .exceptions import ConfigError
from .__version__ import __version__

_logger = logging.getLogger(__name__)


# Pycharm debugging note:
# You can use pycharm to debug a curses application by launching tuil in a
# console window (python -m tuil) and using pycharm to attach to the remote
# process. On Ubuntu, you may need to allow ptrace permissions by setting
# ptrace_scope to 0 in /etc/sysctl.d/10-ptrace.conf.
# http://blog.mellenthin.de/archives/2010/10/18/gdb-attach-fails


def main():
    """Main entry point"""

    # Squelch SSL warnings
    logging.captureWarnings(True)
    if six.PY3:
        # These ones get triggered even when capturing warnings is turned on
        warnings.simplefilter('ignore', ResourceWarning)  # pylint:disable=E0602

    # Set the terminal title
    if os.getenv('DISPLAY'):
        title = 'tuil {0}'.format(__version__)
        sys.stdout.write('\x1b]2;{0}\x07'.format(title))
        sys.stdout.flush()

    args = Config.get_args()
    fargs, bindings = Config.get_file(args.get('config'))

    # Apply the file config first, then overwrite with any command line args
    if args.get('user'):
        #simple multi-account support
        user = args.get('user')
        token_file = os.path.join(Config.TUIL_DATA_HOME, user + '.token')
        history_file = os.path.join(Config.TUIL_DATA_HOME, user + '.history.log')
        config = Config(history_file, token_file)
    else:
        #single-account
        config = Config()
    config.update(**fargs)
    config.update(**args)

    # If key bindings are supplied in the config file, overwrite the defaults
    if bindings:
        config.keymap.set_bindings(bindings)

    if config['copy_config']:
        return copy_default_config()
    if config['copy_mailcap']:
        return copy_default_mailcap()
    if config['list_themes']:
        return Theme.print_themes()

    # Load the browsing history from previous sessions
    config.load_history()

    # Load any previously saved auth session token
    config.load_refresh_token()
    if config['clear_auth']:
        config.delete_refresh_token()

    if config['log']:
        # Log request headers to the file (print hack only works on python 3.x)
        # from http import client
        # _http_logger = logging.getLogger('http.client')
        # client.HTTPConnection.debuglevel = 2
        # def print_to_file(*args, **_):
        #     if args[0] != "header:":
        #         _http_logger.info(' '.join(args))
        # client.print = print_to_file
        logging.basicConfig(
            level=logging.DEBUG,
            filename=config['log'],
            format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
    else:
        # Add an empty handler so the logger doesn't complain
        logging.root.addHandler(logging.NullHandler())

    if config['post_format']:
        # If the user has explicitly set a post format, we don't want to
        # try to do something else with the format so we fall out of the if now
        pass
    elif not config['look_and_feel'] or config['look_and_feel'] == 'default':
        # FIXME - default needs its own post_format but can't because
        # no wrapped-title specifier exists
        pass
    elif config['look_and_feel'] == 'compact':
        config['post_format'] = config.COMPACT_FORMAT

    # Make sure the locale is UTF-8 for unicode support
    default_locale = locale.setlocale(locale.LC_ALL, '')
    try:
        encoding = locale.getlocale()[1] or locale.getdefaultlocale()[1]
    except ValueError:
        # http://stackoverflow.com/a/19961403
        # OS X on some terminals will set the LC_CTYPE to "UTF-8"
        # (as opposed to something like "en_US.UTF-8") and python
        # doesn't know how to handle it.
        _logger.warning('Error parsing system locale: `%s`,'
                        ' falling back to utf-8', default_locale)
        encoding = 'UTF-8'

    if not encoding or encoding.lower() != 'utf-8':
        text = ('System encoding was detected as (%s) instead of UTF-8'
                ', falling back to ascii only mode' % encoding)
        warnings.warn(text)
        config['ascii'] = True

    # Update the webbrowser module's default behavior
    patch_webbrowser()
    if webbrowser_import_warning:
        _logger.warning('webbrowser module was unexpectedly imported before'
                        '$BROWSER could be overwritten')

    # Construct the Lemmy user agent
    user_agent = docs.AGENT.format(version=__version__)

    debug_info = [
        'tuil version: tuil {}'.format(__version__),
        'tuil module path: {}'.format(os.path.abspath(__file__)),
        'python version: {}'.format(sys.version.replace('\n', ' ')),
        'python executable: {}'.format(sys.executable),
        'Lemmy instance: {}'.format(config['instance'] or 'lemmy.ml'),
        'Lemmy API: v3',
        'locale, encoding: {}, {}'.format(default_locale, encoding),
        'Environment Variables']
    for name, value in [
        ('BROWSER', BROWSER),
        ('DISPLAY', os.getenv('DISPLAY')),
        ('EDITOR', os.getenv('EDITOR')),
        ('LANG', os.getenv('LANG')),
        ('PAGER', os.getenv('PAGER')),
        ('TUIL_BROWSER', TUIL_BROWSER),
        ('TUIL_EDITOR', os.getenv('TUIL_EDITOR')),
        ('TUIL_PAGER', os.getenv('TUIL_PAGER')),
        ('TUIL_URLVIEWER', os.getenv('TUIL_URLVIEWER')),
        ('TERM', os.getenv('TERM')),
        ('VISUAL', os.getenv('VISUAL')),
        ('XDG_CONFIG_HOME', os.getenv('XDG_CONFIG_HOME')),
        ('XDG_DATA_HOME', os.getenv('XDG_DATA_HOME')),
    ]:
        debug_info.append('  {:<16}: {}'.format(name, value or ''))
    debug_info.append('')
    debug_text = '\n'.join(debug_info)

    _logger.info(debug_text)
    if config['debug_info']:
        print(debug_text)
        return

    try:
        with curses_session() as stdscr:

            term = Terminal(stdscr, config)

            if config['monochrome'] or config['theme'] == 'monochrome':
                _logger.info('Using monochrome theme')
                theme = Theme(use_color=False)
            elif config['theme'] and config['theme'] != 'default':
                _logger.info('Loading theme: %s', config['theme'])
                theme = Theme.from_name(config['theme'])
            else:
                # Set to None to let the terminal figure out which theme
                # to use depending on if colors are supported or not
                theme = None
            term.set_theme(theme)

            instance = normalize_instance(config['instance'] or 'lemmy.ml')
            config['instance'] = instance
            client = None
            try:
                with term.loader('Connecting to {0}'.format(instance),
                                 catch_exception=False):
                    client = LemmyClient(
                        instance, user_agent=user_agent, timeout=10,
                        cache_ttl=300)
                    client.site()
            except Exception as e:
                raise ConfigError(
                    'Unable to connect to {0}: {1}'.format(instance, e))

            # Restore a saved session if possible.  A rejected token is
            # discarded quietly and the client stays anonymous.
            oauth = AuthHelper(client, term, config)
            if config['autologin'] and config.refresh_token:
                oauth.restore()

            # Open the supplied post link before opening the community.
            if config['link']:
                page = None
                with term.loader('Loading post'):
                    try:
                        page = SubmissionPage(
                            client, term, config, oauth, config['link'])
                    except Exception as e:
                        _logger.exception(e)
                        term.show_notification(
                            'Unable to load {0}'.format(config['link']),
                            style='Error')
                while page:
                    page = page.loop()

            page = None
            name = config['community'] or 'front'
            with term.loader('Loading {0}'.format(name)):
                try:
                    page = SubredditPage(client, term, config, oauth, name)
                except Exception as e:
                    # If the requested page cannot be loaded, fall back to
                    # the instance-wide listing so the application starts.
                    _logger.exception(e)
                    term.show_notification(
                        'Unable to load {0}'.format(name), style='Error')
                    page = SubredditPage(
                        client, term, config, oauth, 'all')

            # Launch the community page
            while page:
                page = page.loop()

    except ConfigError as e:
        _logger.exception(e)
        print(e)
    except Exception as e:
        _logger.exception(e)
        import traceback
        exit_message = '\n'.join([
            debug_text,
            traceback.format_exc(),
            'tuil has crashed. Please report this traceback at:',
            'https://github.com/faethon/tuil/issues\n'])
        sys.stderr.write(exit_message)
        return 1  # General error exception code
    except KeyboardInterrupt:
        pass
    finally:
        # Try to save the browsing history
        config.save_history()
        # Ensure sockets are closed to prevent a ResourceWarning
        if 'client' in locals() and client is not None:
            client.close()


sys.exit(main())

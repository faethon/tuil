<h1 align="center">TUIL</h1>

<p align="center">
A terminal interface (TUI) for browsing and interacting with <a href="https://join-lemmy.org/">Lemmy</a>.<br>
</p>

TUIL is based on [tuir](https://gitlab.com/Chocimier/tuir), the terminal client
for Reddit. The layout, key bindings and configuration format are intentionally
kept close to tuir. The Reddit/PRAW backend has been replaced with a native
Lemmy API client.

## Status

TUIL is in early development and supports:

- Anonymous browsing of communities, posts, comments and users
- Logging in with a username and password
- Voting, saving, posting, replying, editing and deleting
- Joining and leaving communities
- Community search and user profiles
- Inbox, private messages and unread counts
- Status bar themes, custom key bindings and mailcap media handling

Most functionality works with Lemmy 0.19.x and Lemmy 1.0. The client uses the
older v3 API on 0.19 instances and switches to v4 for community, post and user
listings, the inbox, mentions, private messages, read state, and saved, liked
and hidden content on 1.0.

Multireddits, domain listings and Reddit gold are not part of Lemmy. Post
hiding is available on Lemmy 1.0; on 0.19 the key binding shows an error.
User-page sorting is unavailable on Lemmy 1.0 because the v4 API returns a
fixed order.

## Installation

### From PyPI

Install the `tuir-lemmy` distribution with uv. The installed command is still
`tuil`.

```bash
$ uv tool install tuir-lemmy
$ tuil
```

The same distribution can be installed with pip or pipx:

```bash
$ pip install tuir-lemmy
$ pipx install tuir-lemmy
```

### From source

Python 3.10 or newer is required.

```bash
$ git clone https://github.com/faethon/tuil.git
$ cd tuil
$ python3 -m venv .venv
$ . .venv/bin/activate
$ pip install -e .
```

Run it with:

```bash
$ tuil
```

or directly from the source tree:

```bash
$ python3 -m tuil
```

## Usage

Connect to any Lemmy instance with `--instance` and optionally open a community
or listing on startup:

```bash
$ tuil --instance lemmy.ml
$ tuil --instance lemmy.world --community linux
$ tuil --instance lemmy.ml --community all
$ tuil https://lemmy.ml/post/12345
```

The default instance is `lemmy.ml`. Community and listing pages use Lemmy's
paths: `/c/linux` for a community, `/c/all` for the local instance's federated
timeline, and `/c/front` for the front page. The `/` prompt also accepts bare
community names such as `/linux`, post URLs, and user pages.

### Logging in

Press <kbd>u</kbd> to log in. TUIL asks for your Lemmy username and password and
stores only the returned session token, in `$XDG_DATA_HOME/tuil/token`. The token
is bound to the instance that issued it; switching instances will not reuse a
token from another instance. Credentials are not stored.

Useful options:

- `--non-persistent` forget the session token when the program exits
- `--no-autologin` do not restore a saved session on startup
- `--clear-auth` delete the saved token on startup
- `--user NAME` keep a separate token and history file per account

## Controls

Move the cursor with the arrow keys or Vim-style movement. Press <kbd>?</kbd> for
the in-app help, or see [CONTROLS.md](CONTROLS.md) for the full key map.

- <kbd>j</kbd>/<kbd>k</kbd> - move the cursor
- <kbd>l</kbd>/<kbd>h</kbd> - open an item or return to the previous page
- <kbd>1</kbd>-<kbd>5</kbd> - change the post/comment sort order
- <kbd>l</kbd> in a community - open the selected post and its comments
- <kbd>/</kbd> - open the navigation prompt
- <kbd>a</kbd>/<kbd>z</kbd> - upvote/downvote
- <kbd>c</kbd> - create a post or reply
- <kbd>w</kbd> - save/unsave
- <kbd>F</kbd> - search for communities
- <kbd>s</kbd> - view subscribed communities
- <kbd>i</kbd> - view the inbox
- <kbd>u</kbd> - log in or out
- <kbd>?</kbd> - open help
- <kbd>q</kbd> - quit

## Settings

Configuration is stored in `$XDG_CONFIG_HOME/tuil/tuil.cfg` (normally
`~/.config/tuil/tuil.cfg`). Run `tuil --copy-config` to create a default file.
The full list of options, including custom post formats and key bindings, is
documented in [tuil.cfg](tuil/templates/tuil.cfg).

The main startup settings are:

```ini
[tuil]
instance = lemmy.ml
community = front
persistent = True
autologin = True
```

Older tuir config files are accepted as a fallback when no tuil config exists.
The `[tuir]` section, the `subreddit` and `subreddit_format` options, and the old
`~/.config/tuir/tuir.cfg` path keep working. The new names are `[tuil]`,
`community` and `post_format`.

### Viewing media links

TUIL can use [mailcap](https://en.wikipedia.org/wiki/Media_type#Mailcap) to open
images and videos in external programs. Copy the example file with:

```bash
$ tuil --copy-mailcap
```

Then enable the feature with `--enable-media` or by setting `enable_media = True`
in `tuil.cfg`.

An existing `~/.config/tuir/mailcap` or `~/.mailcap` is also read, so a tuir
mailcap can be reused without copying it. To point to a file elsewhere, set
the `MAILCAPS` environment variable to its path.

### Environment variables

- `TUIL_EDITOR` - editor used for posts, comments and messages
- `TUIL_BROWSER` - browser used to open links
- `TUIL_URLVIEWER` - urlview/urlscan-compatible link extractor

If unset, TUIL falls back to `VISUAL`/`EDITOR`, `BROWSER`, and the system default
programs. The clipboard command is configured with `clipboard_cmd` in
`tuil.cfg`.

## Themes

List the installed themes with `tuil --list-themes`, select one with
`tuil --theme NAME`, or cycle through them in the app with <kbd>F2</kbd> and
<kbd>F3</kbd>. Themes in `~/.config/tuil/themes` and the old
`~/.config/tuir/themes` are both loaded. Theme files use the same attribute
names as tuir; see [THEMES.md](THEMES.md).

## Development

Development was made with the support of AI, including reimplementing the
Reddit API calls for Lemmy.

```bash
$ .venv/bin/python -m pytest -q
```

The Lemmy API client lives in [tuil/api](tuil/api). Verified response shapes and
known endpoint differences are documented in
[docs/lemmy-api-notes.md](docs/lemmy-api-notes.md).

Optional read-only checks against a live instance:

```bash
$ .venv/bin/python scripts/live_check.py --instance lemmy.ml
```

See [docs/live-testing.md](docs/live-testing.md) for authenticated and manual
write checks.

## License

TUIL is distributed under the GNU General Public License, version 3 only. It is
derived from tuir and retains the upstream copyright notices and attribution.
See [COPYING](COPYING) and [AUTHORS.rst](AUTHORS.rst).

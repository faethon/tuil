# Live testing

The automated test suite uses mocked API responses.  These checks exercise the
real client against a live instance.

## Read-only checks

Run the anonymous checks against a Lemmy 0.19 instance:

```bash
.venv/bin/python scripts/live_check.py \
    --instance lemmy.ml \
    --community linux \
    --user-name dessalines
```

Run them against a Lemmy 1.0 instance:

```bash
.venv/bin/python scripts/live_check.py \
    --instance voyager.lemmy.ml \
    --community gnulinuxitalia \
    --user-name enzoesco
```

The script checks site metadata, post and comment listings, community and user
name resolution, user content, community listings and search.  It does not
modify anything.

To check the authenticated read paths, provide credentials through environment
variables or let the script prompt for them:

```bash
.venv/bin/python scripts/live_check.py \
    --instance lemmy.world \
    --community linux \
    --user-name dessalines \
    --auth
```

The password prompt does not echo.  The script logs in, reads unread counts,
inbox collections, saved/liked/hidden content, and then logs out.  It does not
store the token or perform write operations.

For a non-interactive run, pass the credentials in environment variables:

```bash
export TUIL_TEST_USERNAME='testaccount'
read -sr TUIL_TEST_PASSWORD
export TUIL_TEST_PASSWORD
.venv/bin/python scripts/live_check.py --instance lemmy.world --auth
unset TUIL_TEST_PASSWORD
```

If the account uses two-factor authentication, set `TUIL_TEST_TOTP` as well.

## Manual write checks

Use a disposable account and a test community.  Run the TUI with isolated
configuration and token directories:

```bash
mkdir -p /tmp/tuil-auth/config /tmp/tuil-auth/data

XDG_CONFIG_HOME=/tmp/tuil-auth/config \
XDG_DATA_HOME=/tmp/tuil-auth/data \
.venv/bin/tuil --instance lemmy.world --user testaccount
```

Log in with <kbd>u</kbd>, then verify:

- [ ] Token file exists with mode `0600`
- [ ] Restart restores the session
- [ ] Logout deletes the token
- [ ] `--non-persistent` deletes the token on exit
- [ ] Post and comment votes can be set and removed
- [ ] Posts and comments can be saved and unsaved
- [ ] A community can be joined and left
- [ ] A post can be created, edited and deleted
- [ ] A comment can be created, edited and deleted
- [ ] All inbox tabs load
- [ ] Sent PM copies do not appear in received views
- [ ] Inbox items can be marked read
- [ ] A private message can be sent, edited and deleted
- [ ] `/u/me/saved`, `/u/me/upvoted` and `/u/me/downvoted` load
- [ ] `/u/me/hidden` loads and <kbd>Space</kbd> hides/unhides a post on 1.0

Delete any test posts, comments and messages when finished.

# Lemmy API client

`tuil.api` is the in-house Lemmy client used by the UI.  It has no UI
imports, so it can also be used from a REPL or a script.

```python
from tuil.api import LemmyClient

with LemmyClient('lemmy.ml') as client:
    site = client.site()
    print(site.name, site.version)

    for post in client.list_posts(type_='Local', sort='Hot').take(5):
        print(post.score, post.title, post.community_name)

    for comment in client.list_comments(post=post.id, sort='Top').take(20):
        print('  ' * comment.depth, comment.author, comment.body)
```

Lists return a lazy `Pager`.  It requests the next page only when iteration
reaches the end of the current one, and `max_items` lets the caller stop
early:

```python
posts = client.list_posts(page_size=25, max_items=100)
first_page = posts.take(25)
```

## Login

```python
client = LemmyClient('lemmy.ml')
user = client.login('username', 'password')
print(user.name)
client.logout()
```

The JWT is held in memory.  The application layer is responsible for storing
it between runs.  `AuthenticationError` is raised for a rejected login;
`BadRequestError` is what older Lemmy versions use for wrong credentials.

## Objects and actions

Objects are thin wrappers around the raw response.  ``.raw`` always contains
the original dict.

```python
post = client.get_post(123)
post.upvote()
post.save()
post.mark_read()

comment = post.reply('Thanks!')
comment.edit('Thanks again!')

community = client.get_community('linux')
community.subscribe()
```

The common actions update the local object from the server response (or
optimistically, for the endpoints that return no body).  A successful write
also clears the client cache.

## Inbox

```python
count = client.unread_count()
for reply in client.list_replies(unread_only=True):
    reply.mark_read()
for mention in client.list_mentions(unread_only=True):
    mention.mark_read()
for message in client.list_messages(unread_only=True):
    message.mark_read()
```

The client detects the instance version and uses API v3 on Lemmy 0.19 or API
v4 on Lemmy 1.0 for the inbox.  The page layer sees the same object interface
on both versions:

```python
for notification in client.list_notifications(unread_only=True):
    print(notification.kind, notification.content)
    notification.mark_read()

for item in client.list_saved():
    print(item.__class__.__name__, item.id)

for item in client.list_liked(like_type='liked_only'):
    print(item.__class__.__name__, item.id)

for post in client.list_hidden():
    post.unhide()
```

## Errors

All client errors derive from `LemmyError`:

- `NetworkError` — connection failure or timeout
- `AuthenticationError` — 401, login required
- `PermissionDeniedError` — 403
- `NotFoundError` — 404
- `RateLimitError` — 429, with `.retry_after`
- `ServerError` — 5xx
- `InvalidResponseError` — the response was not valid JSON
- `UnsupportedFeatureError` — not available in the selected API version

GET requests are retried twice on timeouts, connection failures, 429 and
5xx.  POST/PUT requests are not retried because they are not idempotent.

# Lemmy API notes

Working notes for the Lemmy client. Recorded 2026-10-20 against live instances.

## Test instances

| Instance | Version | API v3 | API v4 |
|---|---|---|---|
| lemmy.ml | 0.19.20 | full | no |
| lemmy.world | 0.19.19 | full | no |
| lemmy.dbzer0.com | 0.19.20 | full | no |
| voyager.lemmy.ml | 1.0.0-nightly | partial | yes |

Most public instances still run 0.19.x, so v3 is the first target.

## API v3 on Lemmy 1.0

The backwards-compatible v3 API on 1.0 covers login, voting, saving, posting,
commenting and searching, but not the inbox and read-state endpoints.  Listing
endpoints have two additional traps:

- v3 list endpoints still accept old query parameters, but several now require
  lowercase enum values.  For example `type_=All` works on
  `/api/v3/post/list`, while `/api/v3/community/list` returns 400.
- Federated names must be fully qualified.  `/api/v3/post/list?community_name=test`
  and `/api/v3/community?name=test` fail or return an empty list for a remote
  community, while `community_name=test@lemmy.ml` and `community_id=892` work.
  The same applies to remote people.  tuil resolves bare names through
  `/api/v3/search` and then uses the returned id.

| Endpoint | 0.19.20 | 1.0 nightly |
|---|---|---|
| `GET /api/v3/post/list` | 200 | 200 |
| `GET /api/v3/comment/list` | 200 | 200 |
| `GET /api/v3/community/list` | 200 | 200 |
| `GET /api/v3/search` | 200 | 200 |
| `POST /api/v3/user/login` | 400 on empty body | 400 on empty body |
| `POST /api/v3/post/like`, `comment/like` | 401 anonymous | 401 anonymous |
| `PUT /api/v3/post/save`, `comment/save` | 401 anonymous | 401 anonymous |
| `POST /api/v3/post`, `PUT /api/v3/post` | 401 anonymous | 401 anonymous |
| `POST /api/v3/comment`, `PUT /api/v3/comment` | 401 anonymous | 401 anonymous |
| `POST /api/v3/post/delete`, `comment/delete` | 401 anonymous | 401 anonymous |
| `POST /api/v3/community/follow` | 401 anonymous | 401 anonymous |
| `GET /api/v3/user/replies` | 401 anonymous | 404 |
| `GET /api/v3/user/mention` | 401 anonymous | 404 |
| `GET /api/v3/private_message/list` | 401 anonymous | 404 |
| `POST /api/v3/private_message` | 401 anonymous | 404 |
| `GET /api/v3/user/unread_count` | 401 anonymous | 401 anonymous |
| `POST /api/v3/post/mark_as_read` | 401 anonymous | 404 |
| `POST /api/v3/comment/mark_as_read` | 401 anonymous | 404 |
| `POST /api/v3/private_message/mark_as_read` | 401 anonymous | 404 |

This is why tuil uses v4 for community, post and user listings on 1.0, and for
inbox, mentions, private messages, unread counters, saved content and read
state.  v3 remains sufficient for 0.19.  The client checks the site version and
switches only the affected endpoints.

## API v4

Lemmy 1.0 groups the inbox into a single notification stream and replaces
page numbers with cursors.  The endpoints used by tuil are:

| Purpose | Endpoint |
|---|---|
| Post listing | `GET /api/v4/post/list` |
| Community listing | `GET /api/v4/community/list` |
| Community lookup | `GET /api/v4/community` |
| User details | `GET /api/v4/person` |
| Person content | `GET /api/v4/person/content` |
| Name resolution | `GET /api/v4/search` |
| Inbox | `GET /api/v4/account/notification/list` |
| Unread count | `GET /api/v4/account/unread_counts` |
| Mark one notification | `POST /api/v4/account/notification/mark_as_read` |
| Mark all notifications | `POST /api/v4/account/notification/mark_as_read/all` |
| Saved posts and comments | `GET /api/v4/account/saved` |
| Upvoted/downvoted content | `GET /api/v4/account/liked` |
| Hidden posts | `GET /api/v4/account/hidden` |
| Hide or unhide a post | `POST /api/v4/post/hide` |
| Send/edit/delete a private message | `POST`/`PUT`/`DELETE /api/v4/private_message` |

The notification list accepts `type_` (`reply`, `mention`, `subscribed`,
`private_message`, `mod_action`, `all`), `unread_only`, `creator_id`, `limit`
and `page_cursor`.  Each item contains a `notification` record and a `data`
object.  The `data.type_` field identifies the payload (`comment`, `post`,
`private_message` or `mod_action`).

Private messages are special: filtering by `type_=private_message` returns both
received and sent messages.  Adding `creator_id` returns both sides of a
conversation with that person.  The UI removes sender copies from the received
views and keeps them for the "sent" view.

All v4 enum values are lowercase.  Post sorts use `top` together with
`time_range_seconds` instead of values such as `TopDay`; top of all time is
`time_range_seconds=0`.  Unqualified names for federated communities and people
fail, so tuil resolves them through the version-appropriate `/search`, then
requests the canonical object by id.  Communities and people seen in listings
are cached by name and id for later navigation.

`/api/v4/person/content` has no sort parameter and the v3 user endpoint is
unavailable on 1.0, so user-page sort controls cannot change the order there.
Community, post and search listings do support sorting.

Response fields also changed in v4.  Vote, save and read state now live in
`post_actions`, `comment_actions`, `community_actions` and `person_actions`;
counts live directly on posts, comments and communities.  Timestamps use
`published_at` and `updated_at`.  The model wrappers accept both shapes.

The first page of a cursor-paginated endpoint carries a `next_page` token.
Pass it unchanged as `page_cursor` to get the next page.  Do not parse it.

`account/liked` accepts `like_type=liked_only|disliked_only` and
`type_=all|comments|posts`; `account/saved` accepts the same `type_` filter.
Both return the combined post/comment view with a `type_` discriminator.
`post/hide` takes `{"post_id": 1, "hide": true}` and returns a `post_view`.

## Authentication

```
POST /api/v3/user/login
{"username_or_email": "...", "password": "...", "totp_2fa_token": null}
-> {"jwt": "...", "registration_created": false, "verify_email_sent": false}
```

Send the token on subsequent requests:

```
Authorization: Bearer <jwt>
```

Anonymous browsing works for all list/get endpoints. Write endpoints return
`401 {"error": "incorrect_login"}`.

## Pagination

v3 uses page numbers:

```
?limit=50&page=1
```

Stop when a page returns fewer than `limit` items or an empty list.
v4 uses cursors (`page_cursor`), so the client exposes a pager abstraction
instead of leaking page numbers into the UI.

## Core response shapes

### Post list

`GET /api/v3/post/list?type_=Local&sort=Hot&limit=20`

```json
{"posts": [{
  "post": {"id": 1, "name": "...", "url": "...", "body": "...",
           "published": "...", "updated": null, "nsfw": false,
           "locked": false, "deleted": false, "removed": false,
           "featured_community": false},
  "creator": {"id": 2, "name": "user", "display_name": "...",
              "actor_id": "https://..."},
  "community": {"id": 3, "name": "linux", "title": "...",
                "actor_id": "https://..."},
  "counts": {"comments": 3, "score": 12, "upvotes": 14, "downvotes": 2},
  "my_vote": 1,
  "saved": false,
  "read": false,
  "hidden": false
}]}
```

- `my_vote` is `1`, `-1` or `null`; this maps to tuir's `likes`.
- `counts.score` replaces Reddit's upvote/downvote display.
- There is no `score_hidden`; show the score.
- Self posts have `post.url` unset or pointing at the post itself.

### Comments

`GET /api/v3/comment/list?post_id=1&sort=Top&max_depth=8&limit=50&page=1`

Comments are returned as a flat list, in tree order:

```json
{"comments": [{
  "comment": {"id": 10, "creator_id": 2, "post_id": 1,
              "content": "markdown", "path": "0.10",
              "published": "...", "updated": null,
              "deleted": false, "removed": false,
              "distinguished": false},
  "creator": {"id": 2, "name": "user"},
  "post": {"id": 1, "name": "..."},
  "community": {"id": 3, "name": "linux"},
  "counts": {"score": 3, "upvotes": 4, "downvotes": 1, "child_count": 0},
  "my_vote": null,
  "saved": false
}]}
```

- `comment.path` is `"0.<id>.<id>..."`; depth is `len(path.split('.')) - 1`.
  Reconstruct the tree from this instead of relying on a "more comments"
  object.
- `content` is Markdown. The UI needs a Markdown-to-text conversion.
- `max_depth` and `limit` both need to be handled; request enough depth and
  paginate if the thread is long.

### Community list

`GET /api/v3/community/list?type_=All&sort=TopAll&limit=50&page=1`

```json
{"communities": [{
  "community": {"id": 3, "name": "linux", "title": "Linux",
                "actor_id": "https://lemmy.ml/c/linux", "nsfw": false},
  "counts": {"subscribers": 1000, "posts": 42, "comments": 500},
  "subscribed": "Subscribed",
  "blocked": false
}]}
```

`type_` is `All`, `Local` or `Subscribed`; sort is a `SortType`.

### Search

`GET /api/v3/search?q=linux&type_=Posts&sort=Top&listing_type=Local&limit=20`

`type_` is `All`, `Comments`, `Posts`, `Communities`, `Users` or `Url`.
Community-scoped search additionally accepts `community_id`.

## Endpoints needed by tuil

### Read

- `GET /api/v3/site`
- `GET /api/v3/post/list` (`type_`, `sort`, `page`, `limit`, `community_id`,
  `community_name`, `creator_id`, `creator_username`, `saved_only`,
  `liked_only`)
- `GET /api/v3/post?id=`
- `GET /api/v3/comment/list`
- `GET /api/v3/community/list`
- `GET /api/v3/community?name=`
- `GET /api/v3/user?username=`
- `GET /api/v3/search`
- `GET /api/v3/user/replies`
- `GET /api/v3/user/mention` (singular in v3)
- `GET /api/v3/private_message/list`
- `GET /api/v3/user/unread_count`

### Write

- `POST /api/v3/user/login`
- `POST /api/v3/post/like` `{"post_id": 1, "score": 1|-1|0}`
- `POST /api/v3/comment/like` `{"comment_id": 1, "score": 1|-1|0}`
- `PUT /api/v3/post/save` `{"post_id": 1, "save": true}`
- `PUT /api/v3/comment/save` `{"comment_id": 1, "save": true}`
- `POST /api/v3/post` (create)
- `PUT /api/v3/post` (edit)
- `POST /api/v3/post/delete` `{"post_id": 1, "deleted": true}`
- `POST /api/v3/comment` (create)
- `PUT /api/v3/comment` (edit)
- `POST /api/v3/comment/delete` `{"comment_id": 1, "deleted": true}`
- `POST /api/v3/post/mark_as_read` `{"post_id": 1, "read": true}`
- `POST /api/v3/comment/mark_as_read` (comment reply, `comment_reply_id`)
- `POST /api/v3/user/mention/mark_as_read` (`person_mention_id`)
- `POST /api/v3/community/follow` `{"community_id": 1, "follow": true}`
- `POST /api/v3/private_message` `{"content": "...", "recipient_id": 1}`
- `POST /api/v3/private_message/mark_as_read`

Notes:

- `post/hide` does not exist in v3; hiding posts must be handled client-side
  or deferred to the v4 backend.
- `/user/mention` is singular in v3, unlike the other inbox endpoints.
- `/comment/mark_as_read` marks a **comment reply in the inbox** and takes
  `comment_reply_id`.  There is no server-side read flag on a comment itself.
- `/user/mention/mark_as_read` takes `person_mention_id`.
- `/private_message/mark_as_read` takes `private_message_id`.
- `/post/mark_as_read` accepts `post_id` or `post_ids`.
- `GET /site` returns `discussion_languages` as a list of language **ids**,
  while `all_languages` is a list of objects.
- Private messages have no subject field. tuir's compose flow needs to drop
  the subject prompt for Lemmy.
- Creating posts requires `language_id`; use the site's default or expose a
  config option.  For comments, omit `language_id` unless the user explicitly
  chooses one.  Lemmy inherits the post or parent comment language, and sending
  the site default can fail with `language_not_allowed` when the community
  restricts languages.

## Sort mapping

v3 accepts all of these on 0.19.20: `Active`, `Hot`, `New`, `Old`,
`TopDay`, `TopWeek`, `TopMonth`, `TopYear`, `TopAll`, `MostComments`,
`NewComments`, `Controversial`, `Scaled`.  There is no plain `Top`: always
send a period-qualified value such as `TopDay` or `TopAll`.

Proposed tuir mapping:

| tuir | Lemmy |
|---|---|
| hot | Hot |
| new | New |
| rising | Active |
| controversial | Controversial |
| top | TopDay / TopWeek / TopMonth / TopYear / TopAll |
| gilded | unsupported |

## Error format

```
{"error": "incorrect_login", "message": "..."}
```

Map `401` to login-required, `403` to forbidden, `404` to not found,
`429` to rate-limited and everything else to a generic API error.

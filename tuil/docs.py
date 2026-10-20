# -*- coding: utf-8 -*-
from __future__ import unicode_literals

AGENT = """\
desktop:https://github.com/faethon/tuil:{version}\
"""

SUMMARY = """
TUIL (Terminal UI for Lemmy) is a terminal interface to view and interact with Lemmy.
"""

USAGE = """\
tuil [URL] [-i INSTANCE] [-s COMMUNITY]

  $ tuil https://lemmy.ml/post/123
  $ tuil -i lemmy.ml -s linux
"""

CONTROLS = """
Move the cursor using the arrow keys or vim style movement.
Press `?` to open the help screen.
"""

HELP = """\
====================================
Terminal UI for Lemmy

https://github.com/faethon/tuil
====================================

[Basic Commands]
  j     : Move the cursor down
  k     : Move the cursor up
  l     : View the currently selected item
  h     : Return to the previous view
  m     : Move the cursor up one page
  n     : Move the cursor down one page
  gg    : Jump to the top of the page
  G     : Jump to the bottom of the page
  1-5   : Sort posts by category
  r     : Refresh the content on the current page
  u     : Log in to your Lemmy account
  q     : Quit
  Q     : Force quit
  y     : Copy post permalink to clipboard
  Y     : Copy post link to clipboard
  F2    : Cycle to the previous color theme
  F3    : Cycle to the next color theme
  ?     : Show the help screen
  /     : Open a prompt to select a community

[Authenticated Commands]
  a     : Upvote
  z     : Downvote
  c     : Compose a new post or comment
  C     : Compose a new private message
  e     : Edit the selected post or comment
  d     : Delete the selected post or comment
  i     : View your inbox (see Inbox Mode)
  s     : View your subscribed communities (see Community List Mode)
  u     : Log out of your Lemmy account
  w     : Save the selected post or comment

[Community Mode]
  l     : View the comments for the selected post (see Post Mode)
  o     : Open the selected post link using your web browser
  p     : Toggle between the current community and /c/front
  f     : Open a prompt to search the current community for a text string
  t     : Join this community
  T     : Leave this community
  v     : Open the community for the selected post
  V     : Open the author's user page for the selected post

[Post Mode]
  h     : Close the post and return to the previous page
  l     : View the selected comment using the system's pager
  o     : Open a link in the comment using your web browser
  SPACE : Fold or expand the selected comment and its children
  b     : Send the comment text to the system's urlviewer application
  J     : Move the cursor down to the next comment at the same indentation
  K     : Move the cursor up to the parent comment
  V     : Open the author's user page for the selected comment

[Community List Mode]
  h     : Close your communities and return to the previous page
  l     : Open the selected community

[Inbox Mode]
  h     : Close your inbox and return to the previous page
  l     : View the context of the selected comment
  o     : Open the post of the selected comment
  c     : Reply to the selected comment or message
  w     : Mark the selected comment or message as read

[Prompt]
  The / key opens a text prompt at the bottom of the screen. You can use this
  to type in the name of the community that you want to open. The following
  text formats are recognized:

  /linux                       - Open a community, shorthand
  /c/linux                     - Open a community
  /c/linux/new                 - Open a community, sorted by category
  /c/linux/top-week            - Open a community, sorted by category and time
  /c/front                     - Open your subscribed communities
  /c/all                       - Open all communities on the instance
  /c/local                     - Open the local communities listing
  /c/subscribed                - Open your subscribed communities
  /post/123                    - Open a post
  /comment/123                 - Open a post containing a comment
  /u/me                        - View your posts and comments
  /u/me/saved                  - View your saved content
  /u/me/upvoted                - View your upvoted content
  /u/me/downvoted              - View your downvoted content
  /u/alice                     - View a user's posts and comments
  /u/alice/submitted           - View a user's posts
  /u/alice/comments            - View a user's comments
"""

BANNER_SUBREDDIT = """
[1]hot [2]top [3]active [4]new [5]controversial
"""

BANNER_SUBMISSION = """
[1]hot [2]top [3]old [4]new [5]controversial
"""

BANNER_SEARCH = """
[1]relevance [2]top [3]comments [4]new
"""

BANNER_INBOX = """
[1]all [2]unread [3]messages [4]comments [5]posts [6]mentions [7]sent
"""

BANNER_EMPTY = """
[?]Help [q]Quit [/]Prompt [i]Inbox [u]Login
"""

FOOTER_SUBREDDIT = """
[?]Help [q]Quit [l]Comments [/]Prompt [u]Login [o]Open [c]Post [a/z]Vote [r]Refresh
"""

FOOTER_SUBREDDIT_LOGGED_IN = """
[?]Help [q]Quit [l]Comments [/]Prompt [u]Logout [o]Open [c]Post [a/z]Vote [r]Refresh
"""

FOOTER_SUBMISSION = """
[?]Help [q]Quit [h]Return [space]Fold/Expand [o]Open [c]Comment [a/z]Vote [r]Refresh
"""

FOOTER_SUBSCRIPTION = """
[?]Help [q]Quit [h]Return [l]Select Community [r]Refresh
"""

FOOTER_INBOX = """
[?]Help [l]View Context [o]Open Post [c]Reply [w]Mark Read [r]Refresh
"""

FOOTER_EMPTY = BANNER_EMPTY

TOKEN = "INSTRUCTIONS"

FORMATTING_HELP = """Formatting help:
Text formatting:
_italic_ / *italic*
__bold__ / **bold**
___bold-italic___ / ***bold-italic***
~~strikethrough~~

Special formatting:
`code` (or indent each line with four spaces)
> Quote someone else
[link text](link url)"""

REPLY_FILE = """<!--{token}
Replying to {{author}}'s {{type}}:
{{content}}

Enter your reply below this instruction block, an empty message will abort
the reply.

{formatting_help}
{token}-->
""".format(token=TOKEN, formatting_help=FORMATTING_HELP)

COMMENT_EDIT_FILE = """<!--{token}
Editing comment #{{id}}.
The comment is shown below, update it and save the file.

{formatting_help}
{token}-->

{{content}}
""".format(token=TOKEN, formatting_help=FORMATTING_HELP)

SUBMISSION_FILE = """<!--{token}
Creating a post in {{name}}.

Enter your post below this instruction block:
- The first line will be interpreted as the title
- The following lines will be interpreted as the body
- An empty message will abort the post

{formatting_help}
{token}-->
""".format(token=TOKEN, formatting_help=FORMATTING_HELP)

SUBMISSION_EDIT_FILE = """<!--{token}
Editing post #{{id}}.
The post is shown below, update it and save the file.

{formatting_help}
{token}-->

{{content}}
""".format(token=TOKEN, formatting_help=FORMATTING_HELP)

MESSAGE_FILE = """<!--{token}
Compose a new private message

Enter your message below this instruction block:
- The first line should contain the recipient's Lemmy username
- Subsequent lines will be interpreted as the message body

{formatting_help}
{token}-->
""".format(token=TOKEN, formatting_help=FORMATTING_HELP)

TIME_ORDER_MENU = """
Posts from:
  [1] Past hour
  [2] Past 24 hours
  [3] Past week
  [4] Past month
  [5] Past year
  [6] All time
"""

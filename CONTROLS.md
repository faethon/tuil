# Controls

## Basic Commands

- <kbd>j</kbd> or <kbd>▼</kbd> - Move the cursor down
- <kbd>k</kbd> or <kbd>▲</kbd> - Move the cursor up
- <kbd>l</kbd> or <kbd>►</kbd> - View the currently selected item
- <kbd>h</kbd> or <kbd>◄</kbd> - Return to the previous view
- <kbd>m</kbd> or <kbd>PgUp</kbd> - Move the cursor up one page
- <kbd>n</kbd> or <kbd>PgDn</kbd> - Move the cursor down one page
- <kbd>gg</kbd> - Jump to the top of the page
- <kbd>G</kbd> - Jump to the bottom of the page
- <kbd>1</kbd> to <kbd>5</kbd> - Sort posts or comments by category
- <kbd>r</kbd> or <kbd>F5</kbd> - Refresh the content on the current page
- <kbd>u</kbd> - Log in to your Lemmy account
- <kbd>q</kbd> - Quit
- <kbd>Q</kbd> - Force quit
- <kbd>y</kbd> - Copy post permalink to clipboard
- <kbd>Y</kbd> - Copy post link to clipboard
- <kbd>F2</kbd> - Cycle to the previous color theme
- <kbd>F3</kbd> - Cycle to the next color theme
- <kbd>?</kbd> - Show the help screen
- <kbd>/</kbd> - Open a prompt to select a community

The <kbd>/</kbd> key opens a text prompt at the bottom of the screen. You can use
this to type in the name of the community that you want to open. The following
text formats are recognized:

- ``/linux`` - Open a community, shorthand
- ``/c/linux`` - Open a community
- ``/c/linux/new`` - Open a community, sorted by category
- ``/c/linux/top-week`` - Open a community, sorted by category and time
- ``/c/front`` - Open your front page (subscribed communities, or local when logged out)
- ``/c/all`` - Open all communities known to the instance
- ``/c/local`` - Open the instance's local communities
- ``/c/subscribed`` - Open your subscribed communities
- ``/post/12345`` - Open a post
- ``/comment/12345`` - Open the post containing a comment
- ``/u/me`` - View your posts and comments
- ``/u/me/saved`` - View your saved content
- ``/u/me/upvoted`` - View your upvoted content
- ``/u/me/downvoted`` - View your downvoted content
- ``/u/alice`` - View a user's posts and comments
- ``/u/alice/submitted`` - View a user's posts
- ``/u/alice/comments`` - View a user's comments

## Authenticated Commands

Some actions require that you be logged in to your Lemmy account. You can log in
by pressing the <kbd>u</kbd> key. Once you are logged in, your username will
appear in the top-right corner of the screen.

- <kbd>a</kbd> - Upvote
- <kbd>z</kbd> - Downvote
- <kbd>c</kbd> - Compose a new post or comment
- <kbd>C</kbd> - Compose a new private message
- <kbd>e</kbd> - Edit the selected post or comment
- <kbd>d</kbd> - Delete the selected post or comment
- <kbd>i</kbd> - View your inbox (see [inbox mode](#inbox-mode))
- <kbd>s</kbd> - View your subscribed communities (see [community list mode](#community-list-mode))
- <kbd>u</kbd> - Log out of your Lemmy account
- <kbd>w</kbd> - Save the selected post or comment

## Community Mode

The following actions can be performed when viewing a community:

- <kbd>l</kbd> or <kbd>►</kbd> - View the comments for the selected post (see [post mode](#post-mode))
- <kbd>o</kbd> or <kbd>ENTER</kbd> - Open the selected post link using your web browser or ``.mailcap`` config
- <kbd>p</kbd> - Toggle between the currently viewed community and ``/c/front``
- <kbd>f</kbd> - Open a prompt to search the current community for a text string
- <kbd>t</kbd> - Join this community
- <kbd>T</kbd> - Leave this community
- <kbd>v</kbd> - Open the community for the selected post
- <kbd>V</kbd> - Open the author's user page for the selected post

## Post Mode

The following actions can be performed when viewing a post:

- <kbd>h</kbd> or <kbd>◄</kbd> - Close the post and return to the previous page
- <kbd>l</kbd> or <kbd>►</kbd> - View the selected comment using the system's pager
- <kbd>o</kbd> or <kbd>ENTER</kbd> - Open a link in the comment using your web browser or ``.mailcap`` config
- <kbd>SPACE</kbd> - Fold or expand the selected comment and its children
- <kbd>b</kbd> - Send the comment text to the system's urlviewer application
- <kbd>J</kbd> - Move the cursor down to the next comment at the same indentation
- <kbd>K</kbd> - Move the cursor up to the parent comment

## Community List Mode

The following actions can be performed when viewing your subscribed communities:

- <kbd>h</kbd> or <kbd>◄</kbd> - Close the community list and return to the previous page
- <kbd>l</kbd> or <kbd>►</kbd> - Open the selected community

## Inbox Mode

The following actions can be performed when viewing your inbox:

- <kbd>h</kbd> or <kbd>◄</kbd> - Close your inbox and return to the previous page
- <kbd>l</kbd> or <kbd>►</kbd> - View the context of the selected comment
- <kbd>o</kbd> or <kbd>Enter</kbd> - Open the post of the selected comment
- <kbd>c</kbd> - Reply to the selected comment or message
- <kbd>w</kbd> - Mark the selected comment or message as read

## Unavailable Reddit Features

Multireddits, domain listings and gilded posts are specific to Reddit and are
not available in Lemmy. Their legacy key bindings show an error or do nothing.
Hiding a post with <kbd>Space</kbd> requires Lemmy 1.0 or newer; on 0.19 the
key shows an error.

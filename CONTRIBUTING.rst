----------------------
Contributor Guidelines
----------------------

Before you start
================

- Post an issue on the `tracker <https://github.com/faethon/tuil/issues>`_
  describing the bug or feature you would like to add
- If an issue already exists, leave a comment to let others know that you
  intend to work on it

Considerations
==============

- One of the project's goals is to maintain compatibility with as many
  terminal emulators as possible. Please be mindful of this when designing a
  new feature.

  - Is it compatible with both Linux and OS X?
  - Is it compatible with Python 3.10 and newer?
  - Will it work over ssh (without X11)?
  - What about terminals that don't support color, or that support only 8 or
    256 colors?
  - Will it work in tmux/screen?
  - Will it fail gracefully if unicode is not supported?

- If you're adding a new feature, try to include a few test cases. See the
  section below on setting up your test environment.
- If you tried but can't get the tests running in your environment, it's ok.
- If you are unsure about anything, ask!

Submitting a pull request
=========================

- Reference the issue number that the pull request is related to.
- Make sure you have merged in the latest changes from the ``master`` branch.
- Make sure the test suite passes locally.
- Be prepared to have your code reviewed. For non-trivial additions, it's
  normal for this process to take a few iterations.
- Keep commit messages short and descriptive.

Style guide
===========

- All code should follow `PEP 8 <https://www.python.org/dev/peps/pep-0008/>`_.
- Try to keep lines under 80 characters, but don't sacrifice readability to do
  it!

  **Ugly**

  .. code-block:: python

              text = ''.join(
                  line for line in fp2 if not line.startswith('#'))

  **Better**

  .. code-block:: python

            text = ''.join(line for line in fp2 if not line.startswith('#'))

- Use the existing codebase as a reference when writing docstrings (adopted
  from the `Google Style Guide
  <https://google.github.io/styleguide/pyguide.html#Comments>`_).
- Add an encoding header ``# -*- coding: utf-8 -*-`` to all new files.
- **Please don't submit pull requests for style-only code changes.**

Running the tests
=================

The test suite uses `pytest <http://pytest.org/>`_ and `responses
<https://github.com/getsentry/responses>`_ for mocked HTTP requests. It does
not require a Lemmy account or network access.

1. Create a virtual environment and install the test dependencies:

   .. code-block:: bash

      $ python3 -m venv .venv
      $ . .venv/bin/activate
      $ pip install -e '.[test]'

2. Run the tests from the repository root:

   .. code-block:: bash

      $ python -m pytest -q

3. When changing the Lemmy API layer, update or add mocked tests in
   ``tests/api/``. If you discover a new endpoint quirk, document it in
   ``docs/lemmy-api-notes.md``.

Live tests against a real instance are optional. They need network access and
should not be part of the default test run.

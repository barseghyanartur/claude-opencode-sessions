=======================
claude-copilot-sessions
=======================
.. External references

.. _Copilot CLI: https://github.com/github/copilot-cli
.. _Claude Code: https://code.claude.com
.. _uv: https://docs.astral.sh/uv/

.. Internal references

.. _claude-copilot-sessions: https://github.com/barseghyanartur/claude-sessions-importer/tree/main/plugins/copilot-sessions/
.. _docs/design.md: https://github.com/barseghyanartur/claude-sessions-importer/blob/main/plugins/copilot-sessions/docs/design.md

Bring your `Copilot CLI`_ sessions into `Claude Code`_.

.. image:: https://github.com/barseghyanartur/claude-sessions-importer/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/barseghyanartur/claude-sessions-importer/actions
   :alt: Build Status

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://github.com/barseghyanartur/claude-sessions-importer/#License
   :alt: MIT

`claude-copilot-sessions`_ is a Claude Code plugin (and a command-line
tool) that imports your GitHub Copilot CLI sessions for the current
repository into Claude Code. Run ``/copilot-sessions:import``, then use
``/resume`` (or ``claude --resume``) to browse the imported
``[copilot] …`` conversations and press Enter to continue one.

Features
========
- **No model call, no tokens.** The import runs in a Claude Code hook and
  prints its report directly. Tokens are only spent once you resume a session
  and start typing, just like any other conversation.
- **No duplicates, ever.** A session whose content hasn't changed since its
  last import is skipped. A session that changed gets a new copy with the
  next suffix: ``Title``, ``Title (1)``, ``Title (2)``…. Existing files are
  never overwritten.
- **Only this repository.** Scoping works like ``/resume``: the current git
  worktree by default, or ``--worktrees`` for all worktrees of the repo.
- Reads Copilot CLI's own session files directly, **read-only**. No
  database, no CLI call, no network access.

Prerequisites
=============
Python 3.10+

Installation
============
As a Claude Code plugin
-----------------------
.. code-block:: sh

    claude plugin marketplace add barseghyanartur/claude-sessions-importer
    claude plugin install copilot-sessions@barseghyanartur

Or inside a Claude Code session:

.. code-block:: text

    /plugin marketplace add barseghyanartur/claude-sessions-importer
    /plugin install copilot-sessions@barseghyanartur

Update later with ``claude plugin update copilot-sessions@barseghyanartur``,
or turn on auto-update for the marketplace under **Marketplaces** in
``/plugin``.

The plugin runs the code bundled in the plugin itself, so it does not need
the PyPI package. It needs a Python >= 3.10 on ``PATH`` (``python3``,
``python3.1x``) or `uv`_. Note that
``/usr/bin/python3`` on macOS is 3.9. ``brew install python`` or
``uv python install 3.12`` fixes that, or set ``CCS_PYTHON=/path/to/python``.

As a command-line tool
----------------------
.. code-block:: sh

    uv tool install claude-copilot-sessions      # or: pipx install claude-copilot-sessions
    uvx claude-copilot-sessions list              # one-off run without installing

Usage in Claude Code
====================
.. code-block:: text

    /copilot-sessions:import                      # sessions of the current worktree
    /copilot-sessions:import --worktrees          # every worktree of the repository
    /copilot-sessions:import --dry-run            # show what would happen
    /copilot-sessions:import --with-tool-output   # include (truncated) tool output
    /resume                                       # pick a "[copilot] …" session

Example report:

.. code-block:: text

    Copilot CLI → Claude Code import · git worktree /Users/me/repos/brrn
    into ~/.claude/projects/-Users-me-repos-brrn

      imported     [copilot] Clarify Project Objectives

    1 imported
    Open them with /resume — titles start with "[copilot]".

What an imported conversation contains
--------------------------------------
- One transcript per Copilot CLI session, in Claude Code's own session
  folder for this project (``~/.claude/projects/<project>/<uuid>.jsonl``).
- User messages and assistant replies as text. Each tool call becomes one
  line (``→ view: `path/to/file.py```), and its output is left out unless
  you pass ``--with-tool-output``. Reasoning content is left out, same as
  Claude Code's own thinking blocks.
- A first line saying which Copilot CLI session it came from. Claude reads
  this when you resume, so it knows the context.
- The title Copilot CLI itself gave the session, or the first line of your
  first message when it didn't.

How duplicates are prevented
----------------------------
The Claude session id is ``uuid5(Copilot session id + hash of the converted
content)``. Importing unchanged content maps to a file that already exists,
so it is skipped. The first line of each imported file records the Copilot
session id, content hash and suffix, so changed content gets the next free
suffix (the highest existing one + 1). New files are written under a
temporary name and hard-linked into place, which can't overwrite an existing
file. Continuing an imported conversation in Claude doesn't count as a
change: only the Copilot CLI side is compared.

Claude Code's transcript format is internal and may change between Claude
Code versions. The importer writes only a minimal, stable subset of it.

Command line
============
The same package works in the terminal:

.. code-block:: sh

    claude-copilot-sessions import --dry-run           # same as /copilot-sessions:import
    claude-copilot-sessions import --worktrees
    claude-copilot-sessions list                       # sessions in scope, newest first
    claude-copilot-sessions list --all --format json
    claude-copilot-sessions doctor                      # environment + sessions report

Scoping
-------
.. list-table::
   :header-rows: 1
   :widths: 12 20 50 18

   * - Mode
     - Flag
     - Sessions whose directory is…
     - ``/resume`` equivalent
   * - worktree
     - *(default)*
     - inside the current git worktree (its top-level directory or below).
       Outside git: the current directory or below
     - default view
   * - repo
     - ``--worktrees``
     - inside any worktree of the repository
     - ``Ctrl+W``
   * - all
     - ``--all`` (``list`` only)
     - anywhere
     - ``Ctrl+A``

Configuration
-------------
.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Purpose
   * - ``COPILOT_HOME``
     - Copilot CLI's own config/data directory. Default: ``~/.copilot``.
       Sessions are read from
       ``$COPILOT_HOME/session-state/<uuid>/{workspace.yaml,events.jsonl}``
   * - ``CCS_PYTHON``
     - Interpreter for the plugin launcher (``scripts/copilot-sessions``)

Every command also accepts ``--copilot-home PATH``.

How it works
============
Copilot CLI keeps one directory per session under
``$COPILOT_HOME/session-state/<uuid>/``: a ``workspace.yaml`` with the
session's directory, title and timestamps, and an ``events.jsonl`` with the
conversation itself. There's also a ``session-store.db`` SQLite index, but
everything this importer needs is already in the two per-session files, so
the database is never opened. See `docs/design.md`_ for the full format
notes.

Development
===========
.. code-block:: sh

    make install     # uv sync (creates .venv with dev tools)
    make test        # pytest (tests live in src/claude_copilot_sessions/tests)
    make check       # ruff + mypy --strict + pytest + manifest validation
    make run ARGS="list --all"
    make dev         # claude --plugin-dir . (live plugin; /reload-plugins after edits)
    make install-local / make uninstall-local

Troubleshooting
===============
If ``/copilot-sessions:import`` makes Claude answer instead of printing a
report, the hook didn't run. Check the Python requirement above and run
``claude-copilot-sessions doctor``, or
``sh ~/.claude/plugins/…/scripts/copilot-sessions doctor``. It shows the
Python in use, the Copilot home in use, the session count and the scope
roots for the current directory.

License
=======
MIT

Support
=======
For security issues contact me at the e-mail given in the `Author`_ section.

For overall issues, go to
`GitHub <https://github.com/barseghyanartur/claude-sessions-importer/issues>`_.

Author
======
Artur Barseghyan <artur.barseghyan@gmail.com>

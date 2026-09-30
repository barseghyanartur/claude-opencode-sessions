========================
claude-opencode-sessions
========================
.. External references

.. _opencode: https://opencode.ai
.. _Claude Code: https://code.claude.com
.. _uv: https://docs.astral.sh/uv/

.. Internal references

.. _claude-opencode-sessions: https://github.com/barseghyanartur/claude-sessions-importer/tree/main/plugins/opencode-sessions/
.. _docs/design.md: https://github.com/barseghyanartur/claude-sessions-importer/blob/main/plugins/opencode-sessions/docs/design.md
.. _docs/schema-notes.md: https://github.com/barseghyanartur/claude-sessions-importer/blob/main/plugins/opencode-sessions/docs/schema-notes.md

Bring your `opencode`_ sessions into `Claude Code`_.

.. image:: https://img.shields.io/pypi/v/claude-opencode-sessions.svg
   :target: https://pypi.python.org/pypi/claude-opencode-sessions
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/claude-opencode-sessions.svg
    :target: https://pypi.python.org/pypi/claude-opencode-sessions/
    :alt: Supported Python versions

.. image:: https://github.com/barseghyanartur/claude-sessions-importer/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/barseghyanartur/claude-sessions-importer/actions
   :alt: Build Status

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://github.com/barseghyanartur/claude-sessions-importer/#License
   :alt: MIT

`claude-opencode-sessions`_ is a Claude Code plugin (and a command-line
tool) that imports your opencode sessions for the current repository into
Claude Code. Run ``/opencode-sessions:import``, then use ``/resume`` (or
``claude --resume``) to browse the imported ``[opencode] …`` conversations
and press Enter to continue one.

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
- Reads opencode's SQLite database **read-only**: opencode 1.2+ (1.x and 2.x
  layouts), with ``opencode export`` as a fallback.
- No dependencies, no network access.

Prerequisites
=============
Python 3.10+

Installation
============
As a Claude Code plugin
-----------------------
.. code-block:: sh

    claude plugin marketplace add barseghyanartur/claude-sessions-importer
    claude plugin install opencode-sessions@barseghyanartur

Or inside a Claude Code session:

.. code-block:: text

    /plugin marketplace add barseghyanartur/claude-sessions-importer
    /plugin install opencode-sessions@barseghyanartur

Update later with ``claude plugin update opencode-sessions@barseghyanartur``,
or turn on auto-update for the marketplace under **Marketplaces** in
``/plugin``.

The plugin runs the code bundled in the plugin itself, so it does not need
the PyPI package. It needs a Python >= 3.10 on ``PATH`` (``python3``,
``python3.1x``) or `uv`_. Note that
``/usr/bin/python3`` on macOS is 3.9. ``brew install python`` or
``uv python install 3.12`` fixes that, or set ``OCS_PYTHON=/path/to/python``.

As a command-line tool
----------------------
.. code-block:: sh

    uv tool install claude-opencode-sessions      # or: pipx install claude-opencode-sessions
    uvx claude-opencode-sessions list             # one-off run without installing

Usage in Claude Code
====================
.. code-block:: text

    /opencode-sessions:import                      # sessions of the current worktree
    /opencode-sessions:import --worktrees          # every worktree of the repository
    /opencode-sessions:import --dry-run            # show what would happen
    /opencode-sessions:import --with-tool-output   # include (truncated) tool output
    /resume                                        # pick an "[opencode] …" session

Example report:

.. code-block:: text

    opencode → Claude Code import · git worktree /Users/me/repos/brrn
    into ~/.claude/projects/-Users-me-repos-brrn

      imported     [opencode] Fixing stalled make armdict-fetch-hy build (1)
      unchanged    [opencode] HTTP Request/Response Log Analysis for brrn.ru …

    1 imported, 1 unchanged · skipped: 1 sub-agent
    Open them with /resume — titles start with "[opencode]".

What an imported conversation contains
--------------------------------------
- One transcript per opencode session, in Claude Code's own session folder
  for this project (``~/.claude/projects/<project>/<uuid>.jsonl``).
- User messages and assistant replies as text. Each tool call becomes one
  line (``→ bash: `pytest -x```), and its output is left out unless you pass
  ``--with-tool-output``. Reasoning, synthetic and sub-agent content are left
  out.
- A first line saying which opencode session it came from. Claude reads this
  when you resume, so it knows the context.

How duplicates are prevented
----------------------------
The Claude session id is ``uuid5(opencode session id + hash of the converted
content)``. Importing unchanged content maps to a file that already exists,
so it is skipped. The first line of each imported file records the opencode
session id, content hash and suffix, so changed content gets the next free
suffix (the highest existing one + 1). New files are written under a
temporary name and hard-linked into place, which can't overwrite an existing
file. Continuing an imported conversation in Claude doesn't count as a
change: only the opencode side is compared.

Claude Code's transcript format is internal and may change between Claude
Code versions. The importer writes only a minimal, stable subset of it.

Command line
============
The same package works in the terminal:

.. code-block:: sh

    claude-opencode-sessions import --dry-run           # same as /opencode-sessions:import
    claude-opencode-sessions import --worktrees
    claude-opencode-sessions list                       # sessions in scope, newest first
    claude-opencode-sessions list --all --format json
    claude-opencode-sessions doctor                     # environment + database report

Hidden by default: archived sessions (``--include-archived``) and sub-agent
sessions (``--include-subagents``).

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
     - inside any worktree of the repository, plus sessions of the same
       opencode project whose worktree was deleted
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
   * - ``OPENCODE_SESSIONS_DB``
     - Path to ``opencode.db``. Default:
       ``$XDG_DATA_HOME/opencode/opencode.db``, then
       ``~/.local/share/opencode/opencode.db``, then ``opencode db path``
   * - ``OCS_PYTHON``
     - Interpreter for the plugin launcher (``scripts/opencode-sessions``)

Every command also accepts ``--db PATH`` and ``--backend auto|sqlite|cli``.

How it works
============
- **sqlite** (default): opens ``opencode.db`` with ``mode=ro``. On 2.x it
  reads ``session_v2`` + ``session_message``. On 1.x it reads ``session`` +
  ``message`` + ``part``. When both exist in the same file, sessions are
  merged by id (2.x wins), and messages fall back to the 1.x tables per
  session.
- **cli** (fallback): used when the database is missing, locked or not
  recognised, or when more than 20% of a session's messages can't be parsed.
  It runs ``opencode session list --format json`` and
  ``opencode export <id>``.

See `docs/design.md`_ for the design and `docs/schema-notes.md`_ for the
tables and fields that are read.

Development
===========
.. code-block:: sh

    make install     # uv sync (creates .venv with dev tools)
    make test        # pytest (tests live in src/claude_opencode_sessions/tests)
    make check       # ruff + mypy --strict + pytest + manifest validation
    make run ARGS="list --all"
    make dev         # claude --plugin-dir . (live plugin; /reload-plugins after edits)
    make install-local / make uninstall-local

Troubleshooting
===============
If ``/opencode-sessions:import`` makes Claude answer instead of printing a
report, the hook didn't run. Check the Python requirement above and run
``claude-opencode-sessions doctor``, or
``sh ~/.claude/plugins/…/scripts/opencode-sessions doctor``. It shows the
Python in use, the database path, the detected layout, row counts and the
scope roots for the current directory.

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

=====================
claude-codex-sessions
=====================
.. External references

.. _Codex CLI: https://developers.openai.com/codex
.. _Claude Code: https://code.claude.com
.. _uv: https://docs.astral.sh/uv/

.. Internal references

.. _claude-codex-sessions: https://github.com/barseghyanartur/claude-sessions-importer/tree/main/plugins/codex-sessions/
.. _docs/design.md: https://github.com/barseghyanartur/claude-sessions-importer/blob/main/plugins/codex-sessions/docs/design.md

Bring your `Codex CLI`_ sessions into `Claude Code`_.

.. image:: https://img.shields.io/pypi/v/claude-codex-sessions.svg
   :target: https://pypi.python.org/pypi/claude-codex-sessions
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/claude-codex-sessions.svg
    :target: https://pypi.python.org/pypi/claude-codex-sessions/
    :alt: Supported Python versions

.. image:: https://github.com/barseghyanartur/claude-sessions-importer/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/barseghyanartur/claude-sessions-importer/actions
   :alt: Build Status

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://github.com/barseghyanartur/claude-sessions-importer/#License
   :alt: MIT

`claude-codex-sessions`_ is a Claude Code plugin (and a command-line tool)
that imports your Codex CLI sessions for the current repository into Claude
Code. Run ``/codex-sessions:import``, then use ``/resume`` (or
``claude --resume``) to browse the imported ``[codex] …`` conversations and
press Enter to continue one.

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
- Reads Codex's own rollout JSONL files directly, **read-only**. No
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
    claude plugin install codex-sessions@barseghyanartur

Or inside a Claude Code session:

.. code-block:: text

    /plugin marketplace add barseghyanartur/claude-sessions-importer
    /plugin install codex-sessions@barseghyanartur

Update later with ``claude plugin update codex-sessions@barseghyanartur``,
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

    uv tool install claude-codex-sessions      # or: pipx install claude-codex-sessions
    uvx claude-codex-sessions list             # one-off run without installing

Usage in Claude Code
====================
.. code-block:: text

    /codex-sessions:import                      # sessions of the current worktree
    /codex-sessions:import --worktrees          # every worktree of the repository
    /codex-sessions:import --dry-run            # show what would happen
    /codex-sessions:import --with-tool-output   # include (truncated) tool output
    /resume                                     # pick a "[codex] …" session

Example report:

.. code-block:: text

    Codex → Claude Code import · git worktree /Users/me/repos/brrn
    into ~/.claude/projects/-Users-me-repos-brrn

      imported     [codex] I want to create a local version of English <-> Armenian dictionary

    1 imported
    Open them with /resume — titles start with "[codex]".

What an imported conversation contains
--------------------------------------
- One transcript per Codex session, in Claude Code's own session folder
  for this project (``~/.claude/projects/<project>/<uuid>.jsonl``).
- User messages and assistant replies as text. Each tool call becomes one
  line (``→ exec_command: `pytest -x```), and its output is left out unless
  you pass ``--with-tool-output``. Reasoning content is left out, same as
  Claude Code's own thinking blocks.
- A first line saying which Codex session it came from. Claude reads this
  when you resume, so it knows the context.
- A title, taken from Codex's own session index when it has one, otherwise
  the first line of your first message.

Known gap: Codex injects some context into the conversation as plain,
untagged text (an ``AGENTS.md`` instructions header, IDE "Active file"
context, "Files mentioned by the user" lists). Only content Codex wraps in
a recognised ``<tag>…</tag>`` block is filtered out as synthetic; the rest
is imported verbatim, same as a real message. Sessions and tool calls that
Codex tracks only in its own internal SQLite state (archived status, for
one) aren't visible here — only what's in the rollout files.

How duplicates are prevented
----------------------------
The Claude session id is ``uuid5(Codex session id + hash of the converted
content)``. Importing unchanged content maps to a file that already exists,
so it is skipped. The first line of each imported file records the Codex
session id, content hash and suffix, so changed content gets the next free
suffix (the highest existing one + 1). New files are written under a
temporary name and hard-linked into place, which can't overwrite an existing
file. Continuing an imported conversation in Claude doesn't count as a
change: only the Codex side is compared.

Claude Code's transcript format is internal and may change between Claude
Code versions. The importer writes only a minimal, stable subset of it.

Command line
============
The same package works in the terminal:

.. code-block:: sh

    claude-codex-sessions import --dry-run           # same as /codex-sessions:import
    claude-codex-sessions import --worktrees
    claude-codex-sessions list                       # sessions in scope, newest first
    claude-codex-sessions list --all --format json
    claude-codex-sessions doctor                      # environment + sessions report

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
   * - ``CODEX_HOME``
     - Codex's own config/data directory. Default: ``~/.codex``. Sessions
       are read from ``$CODEX_HOME/sessions/**/rollout-*.jsonl``
   * - ``CCS_PYTHON``
     - Interpreter for the plugin launcher (``scripts/codex-sessions``)

Every command also accepts ``--codex-home PATH``.

How it works
============
Codex keeps one JSONL "rollout" file per session under
``$CODEX_HOME/sessions/<year>/<month>/<day>/rollout-<timestamp>-<id>.jsonl``,
plus a best-effort ``session_index.jsonl`` with titles for some of them.
There is no database to open and no CLI export to fall back on — the
rollout files are read directly, read-only. See `docs/design.md`_ for the
full format notes.

Development
===========
.. code-block:: sh

    make install     # uv sync (creates .venv with dev tools)
    make test        # pytest (tests live in src/claude_codex_sessions/tests)
    make check       # ruff + mypy --strict + pytest + manifest validation
    make run ARGS="list --all"
    make dev         # claude --plugin-dir . (live plugin; /reload-plugins after edits)
    make install-local / make uninstall-local

Troubleshooting
===============
If ``/codex-sessions:import`` makes Claude answer instead of printing a
report, the hook didn't run. Check the Python requirement above and run
``claude-codex-sessions doctor``, or
``sh ~/.claude/plugins/…/scripts/codex-sessions doctor``. It shows the
Python in use, the Codex home in use, the rollout file count and the scope
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

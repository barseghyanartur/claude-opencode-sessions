=======================
claude-sessions-importer
=======================
.. External references

.. _Claude Code: https://code.claude.com
.. _opencode: https://opencode.ai
.. _Codex CLI: https://developers.openai.com/codex
.. _Copilot CLI: https://github.com/github/copilot-cli

.. image:: https://github.com/barseghyanartur/claude-sessions-importer/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/barseghyanartur/claude-sessions-importer/actions
   :alt: Build Status

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://github.com/barseghyanartur/claude-sessions-importer/#License
   :alt: MIT

Bring sessions from other coding agents into `Claude Code`_, so you can
continue them with ``/resume``. This repository hosts three independent
Claude Code plugins, one per source. Each is its own PyPI package with its
own version, changelog and command — see its README for details.

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Plugin
     - Command
     - Source
   * - `opencode-sessions <plugins/opencode-sessions/README.rst>`_
     - ``/opencode-sessions:import``
     - `opencode`_ sessions (``opencode.db``)
   * - `codex-sessions <plugins/codex-sessions/README.rst>`_
     - ``/codex-sessions:import``
     - `Codex CLI`_ sessions (rollout JSONL files)
   * - `copilot-sessions <plugins/copilot-sessions/README.rst>`_
     - ``/copilot-sessions:import``
     - `Copilot CLI`_ sessions (``session-state/`` directories)

All three plugins share the same shape: no model call (the import runs in
a Claude Code hook and prints its own report), no duplicate imports ever,
and scoping that mirrors Claude Code's own ``/resume`` (current git
worktree by default, ``--worktrees`` for the whole repository).

Installation
============
.. code-block:: sh

    claude plugin marketplace add barseghyanartur/claude-sessions-importer
    claude plugin install opencode-sessions@barseghyanartur
    claude plugin install codex-sessions@barseghyanartur
    claude plugin install copilot-sessions@barseghyanartur

Or inside a Claude Code session:

.. code-block:: text

    /plugin marketplace add barseghyanartur/claude-sessions-importer
    /plugin install opencode-sessions@barseghyanartur
    /plugin install codex-sessions@barseghyanartur
    /plugin install copilot-sessions@barseghyanartur

Development
===========
.. code-block:: sh

    make install     # uv sync --all-packages (one shared .venv for every plugin)
    make test        # every plugin's test suite
    make check       # ruff + mypy --strict + pytest + validate, for every plugin
    make dev         # claude --plugin-dir . (every plugin live; /reload-plugins after edits)

Each plugin also has its own Makefile with plugin-specific targets
(``bump``, ``release``, ``tag``, …) — see ``plugins/<name>/Makefile`` or
that plugin's own README.

License
=======
MIT

Author
======
Artur Barseghyan <artur.barseghyan@gmail.com>

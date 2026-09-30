=========
Changelog
=========
All notable changes to this project are documented here. Versions apply to
both the PyPI package ``claude-opencode-sessions`` and the Claude Code plugin
``opencode-sessions``.

0.1.0
=====
2026-09-30

- First release.
- ``import``, ``list`` and ``doctor`` commands (``claude-opencode-sessions``).
- Reads opencode's SQLite database directly, read-only: opencode 1.x
  (>= 1.2, ``session``/``message``/``part``) and 2.x
  (``session_v2``/``session_message``), with ``opencode session list`` /
  ``opencode export`` as a fallback.
- Scoping mirrors Claude Code's ``/resume``: current worktree by default,
  ``--worktrees``, ``--all``.
- Claude Code plugin ``opencode-sessions`` with ``/opencode-sessions:import``.
  It imports the repository's opencode sessions as Claude Code conversations,
  so they open with ``/resume``. It runs in a ``UserPromptExpansion`` hook
  without a model call, and never creates duplicates (content-addressed
  session ids, plus ``(1)``, ``(2)``… suffixes for changed sessions).

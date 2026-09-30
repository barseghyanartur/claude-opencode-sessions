=========
Changelog
=========
All notable changes to this project are documented here. Versions apply to
both the PyPI package ``claude-copilot-sessions`` and the Claude Code
plugin ``copilot-sessions``.

0.1.0
=====
Unreleased

- First release.
- ``import``, ``list`` and ``doctor`` commands (``claude-copilot-sessions``).
- Reads GitHub Copilot CLI's session files directly, read-only: one
  directory per session under
  ``$COPILOT_HOME/session-state/<uuid>/{workspace.yaml,events.jsonl}``. No
  database, no CLI fallback, no network access.
- Scoping mirrors Claude Code's ``/resume``: current worktree by default,
  ``--worktrees``, ``--all``.
- Claude Code plugin ``copilot-sessions`` with ``/copilot-sessions:import``.
  It imports the repository's Copilot CLI sessions as Claude Code
  conversations, so they open with ``/resume``. It runs in a
  ``UserPromptExpansion`` hook without a model call, and never creates
  duplicates (content-addressed session ids, plus ``(1)``, ``(2)``…
  suffixes for changed sessions).

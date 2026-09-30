=========
Changelog
=========
All notable changes to this project are documented here. Versions apply to
both the PyPI package ``claude-codex-sessions`` and the Claude Code plugin
``codex-sessions``.

0.1.0
=====
Unreleased

- First release.
- ``import``, ``list`` and ``doctor`` commands (``claude-codex-sessions``).
- Reads Codex CLI's rollout JSONL files directly, read-only: one file per
  session under ``$CODEX_HOME/sessions/**/rollout-*.jsonl``, with
  ``session_index.jsonl`` used best-effort for titles. No database, no CLI
  fallback, no network access.
- Scoping mirrors Claude Code's ``/resume``: current worktree by default,
  ``--worktrees``, ``--all``.
- Claude Code plugin ``codex-sessions`` with ``/codex-sessions:import``. It
  imports the repository's Codex sessions as Claude Code conversations, so
  they open with ``/resume``. It runs in a ``UserPromptExpansion`` hook
  without a model call, and never creates duplicates (content-addressed
  session ids, plus ``(1)``, ``(2)``… suffixes for changed sessions).

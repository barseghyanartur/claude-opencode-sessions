---
description: Import this repository's Codex CLI sessions into Claude Code so you can open them with /resume. Unchanged sessions are never imported twice; changed ones get a (1), (2)… suffix. Runs in a hook, without calling the model.
argument-hint: "[--worktrees] [--dry-run] [--with-tool-output]"
disable-model-invocation: true
---

The codex-sessions import hook did not handle this command. Normally it runs before this text reaches you, at no token cost.

Reply with exactly one short sentence telling the user that the import hook didn't run. Suggest they run `claude-codex-sessions import` in a terminal, or `sh ${CLAUDE_PLUGIN_ROOT}/scripts/codex-sessions doctor` to diagnose it. Do not run any tools.

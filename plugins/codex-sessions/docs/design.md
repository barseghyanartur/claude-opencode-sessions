# Design

## Goal

Continue work started in Codex CLI inside Claude Code, without spending
tokens on browsing. `/codex-sessions:import` turns this repository's Codex
sessions into Claude Code conversations. After that, Claude Code's own
`/resume` picker is the browsable list, and Enter loads a session.

This is the Codex counterpart of `opencode-sessions`
(../opencode-sessions/, the sibling plugin in this same monorepo), which does
the same for opencode. The two packages don't share code (different source
formats — a SQLite database there, JSONL rollout files here) but follow the
same shape: `models.py` / `scope.py` / `importer.py` / `import_command.py`
/ `render.py` / `cli.py`.

## Codex's on-disk format (reverse-engineered, not a published schema)

Verified against real Codex CLI and Codex Desktop rollout files,
`cli_version` 0.118–0.159.

- **Location:** `$CODEX_HOME/sessions/<year>/<month>/<day>/rollout-<ts>-<id>.jsonl`.
  `$CODEX_HOME` defaults to `~/.codex` (Codex's own env var; see `codex --help`).
- **Shape:** one JSON object per line: `{"timestamp", "ordinal", "type", "payload"}`.
  - `session_meta` (once, first line): `session_id`, `cwd`, `cli_version`,
    `source` (`cli`/`vscode`/…), `timestamp` (session start).
  - `turn_context` (once per turn): `model` — a plain string, unlike
    opencode's `{providerID, id}` pair.
  - `event_msg` / `task_started`: `collaboration_mode_kind` (`default` /
    `plan`), read as `Session.agent`.
  - `response_item`: the conversation itself —
    - `message` (`role`: `user` / `assistant` / `developer`). `developer`
      carries Codex's own system prompt and tool/skill/plugin instructions;
      dropped entirely.
    - `reasoning`: a `summary` list of text blocks. Dropped from the
      imported conversation, like Claude Code's own thinking blocks.
    - `function_call` + `function_call_output` (also `local_shell_call` /
      `local_shell_call_output`, `tool_search_call` / `tool_search_output`):
      paired by `call_id` (or `id`) into one tool part, same shape as
      opencode's `{tool, input, output}`.
  - `world_state`: opaque; not read.
- **Titles:** `$CODEX_HOME/session_index.jsonl` has `{"id", "thread_name",
  "updated_at"}` for sessions Codex's own `resume` picker has shown — not
  guaranteed to cover every session. Used when present; otherwise the title
  is the first line of the first user message.
- **Synthetic user content:** Codex wraps some injected context in tags —
  `<environment_context>`, `<recommended_plugins>`, `<skill>`,
  `<turn_aborted>`, `<user_instructions>`, `<app-context>`, and a few more
  (`parse.py`, `_SYNTHETIC_USER_TAGS`) — which are filtered out. Other
  injected context is plain, untagged text (an `AGENTS.md` instructions
  header, IDE "Active file" context, "Files mentioned by the user" lists)
  and is **not** filtered; there's no structural way to tell it apart from
  what the user actually typed. Documented as a known gap in the README.
- **Not read:** archived status (`codex archive`/`unarchive`) and anything
  else Codex keeps only in its internal SQLite state
  (`state_*.sqlite`, `thread_history_*.sqlite`) rather than in the rollout
  file itself. Those schemas are undocumented and were not reverse
  engineered for this project; a session that's archived in Codex still
  shows up here.

## Import rules

Same as opencode's, since `importer.py` is only lightly adapted:

- **Target directory:** in the hook, the directory of the running session's
  `transcript_path`. From the terminal, derived as
  `~/.claude/projects/<path with non-alphanumerics → "-">` (respects
  `CLAUDE_CONFIG_DIR`), or set with `--claude-project-dir`.
- **Content:** user text, assistant text, and each tool call as a
  `→ tool: `args`` line (output only with `--with-tool-output`).
  Consecutive assistant steps are merged, so turns alternate. A header
  naming the Codex session is prepended to the first user turn.
- **Transcript entries:** a `custom-title` entry (`[codex] Title`, with a
  `codexImport` marker holding the Codex id, content hash and suffix), then
  a `parentUuid` chain of `user` / `assistant` entries. Assistant messages
  use model `<synthetic>`, so resuming doesn't switch your model.
- **No duplicates:** the Claude session id is `uuid5(namespace, "<codex
  id>:<sha256 of the turns>")`. Unchanged content maps to an existing file
  and is skipped; changed content gets the next free `(N)` suffix. Files
  are written to a temp name and hard-linked into place, which fails
  instead of overwriting.
- **Skipped:** sessions with no conversation text (aborted before any
  message, or entirely `developer`/synthetic content).

## Decisions

- **Python ≥ 3.10, standard library only.** `uv` and hatchling for
  development; tests live in `src/claude_codex_sessions/tests`.
- **Naming:** PyPI package `claude-codex-sessions`; plugin `codex-sessions`
  in marketplace `barseghyanartur`, hence `/codex-sessions:import`.
- **No model-driven skills.** Same reasoning as opencode's sister project —
  they'd cost tokens on every use.
- **No `--include-archived` / `--include-subagents` flags.** opencode has
  both; Codex's rollout files don't expose either concept (see "Not read"
  above), so the flags would be permanently inert. Left out rather than
  shipped as dead options.

## Risks

- **Codex's rollout format is undocumented.** This was reverse-engineered
  from five real transcripts (CLI, VS Code extension and Desktop
  originators) across `cli_version` 0.118–0.159. A future Codex release
  could change field names or add new `response_item` types; unrecognised
  types are skipped rather than raising, but their content would be
  silently dropped until this package is updated.
- **Claude Code's transcript format is internal.** Same risk as the
  opencode importer; the tests pin the written shape.

## References

- Codex CLI: https://developers.openai.com/codex
- Claude Code hooks (`UserPromptExpansion`): https://code.claude.com/docs/en/hooks
- Claude Code sessions and `/resume`: https://code.claude.com/docs/en/sessions
- Plugins: https://code.claude.com/docs/en/plugins-reference,
  https://code.claude.com/docs/en/plugins/publish

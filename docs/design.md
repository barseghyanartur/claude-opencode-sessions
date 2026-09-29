# Design

## Goal

Continue work started in opencode inside Claude Code, without spending tokens
on browsing. `/opencode-sessions:import` turns this repository's opencode
sessions into Claude Code conversations. After that, Claude Code's own `/resume`
picker is the browsable list, and Enter loads a session.

## Flow

```
/opencode-sessions:import [--worktrees] [--dry-run] [--with-tool-output]
  │  UserPromptExpansion hook (hooks/hooks.json)
  ▼
scripts/opencode-sessions hook   # POSIX launcher: finds Python ≥ 3.10 or uses uv
  │  python -m claude_opencode_sessions hook  (event JSON on stdin)
  ▼
read opencode.db (read-only) → scope to repo → convert → write transcripts
  │
  ▼
{"decision": "block", "reason": "<report>"}   # prompt never reaches the model
```

Claude Code shows the report as `UserPromptExpansion operation blocked by hook:
… Original prompt: …`. That wrapper is fixed Claude Code text and can't be
changed by a plugin. Blocking is what keeps the model out of the loop.

`skills/import/SKILL.md` exists only so the slash command exists. Its body is
a one-sentence fallback that Claude sees only if the hook didn't run.

## Modules (`src/claude_opencode_sessions`)

| Module | Role |
|---|---|
| `locate.py` | Find `opencode.db` (`$OPENCODE_SESSIONS_DB`, XDG path, `opencode db path`) |
| `sqlite_backend.py` | Read-only access. Detects the 1.x (`session`/`message`/`part`) and 2.x (`session_v2`/`session_message`) layouts, merges both |
| `cli_backend.py` | Fallback via `opencode session list --format json` / `opencode export <id>` |
| `parse.py`, `models.py` | Stored JSON → `Session` / `Message` / `Part`, defensively |
| `service.py` | Picks the backend (sqlite first, cli fallback), lists and filters sessions, loads messages (falls back to export if > 20% of rows can't be parsed) |
| `scope.py` | Which sessions belong to "this repo", mirroring `/resume`: current git worktree (default), all worktrees (`--worktrees`), everything (`--all`, `list` only) |
| `importer.py` | Conversion to Claude Code transcripts and duplicate prevention |
| `import_command.py` | `import` command, hook entry point, report |
| `render.py`, `cli.py` | `list`, `doctor`, argument parsing |

## Import rules

- **Target directory:** in the hook, the directory of the running session's
  `transcript_path`. That is exactly where Claude Code keeps this project's
  sessions, whatever its settings. From the terminal, the directory is derived
  as `~/.claude/projects/<path with non-alphanumerics → "-">` (respects
  `CLAUDE_CONFIG_DIR`), or set with `--claude-project-dir`.
- **Content:** user text (not synthetic parts), assistant text, and each tool
  call as a `→ tool: args` line (output only with `--with-tool-output`).
  Consecutive assistant steps are merged, so turns alternate. A header naming
  the opencode session is prepended to the first user turn. The conversation
  is padded so it starts with a user turn and ends with an assistant turn.
- **Transcript entries:** a `custom-title` entry (`[opencode] Title`, with an
  `opencodeImport` marker holding the opencode id, content hash and suffix),
  then a `parentUuid` chain of `user` / `assistant` entries. Assistant
  messages use model `<synthetic>`, so resuming doesn't switch your model.
- **No duplicates:**
  - The Claude session id is `uuid5(namespace, "<opencode id>:<sha256 of the
    turns>")`. Unchanged content maps to an existing file, so it is skipped.
  - Changed content gets a new file titled with the next suffix: the highest
    existing suffix + 1, found by reading the marker lines.
  - Files are written to a temp name and hard-linked into place, which fails
    instead of overwriting.
  - Continuing an imported conversation in Claude appends to its file but
    doesn't change the marker, so it doesn't trigger a re-import.
- **Skipped:** sub-agent and archived sessions (unless the `--include-*`
  flags are given), and sessions with no conversation text.

## Decisions

- **opencode ≥ 1.2** (both SQLite layouts). The JSON storage used before 1.2
  isn't supported. 1.x is verified against a real 1.18.32 database; 2.x is
  built from public reports (see `schema-notes.md`).
- **Python ≥ 3.10, standard library only.** `uv` and hatchling for
  development; tests live in `src/claude_opencode_sessions/tests`.
- **Naming:** PyPI package `claude-opencode-sessions`; plugin
  `opencode-sessions` in marketplace `barseghyanartur`. Claude Code puts the
  plugin name in front of every plugin command, hence `/opencode-sessions:import`.
- **No model-driven skills.** An earlier version had `list`/`show`/`search`
  skills that ran through Claude; they were removed because they cost tokens.

## Verified

With Claude Code 2.1.285 and 2.1.277: the import ran with 0 model turns and
cost $0; re-running reported "unchanged"; a changed session came in as
`(1)`; resuming an imported session let Claude answer questions about its
content.

## Risks

- **Claude Code's transcript format is internal.** A future version could
  change it. The importer writes a minimal subset, and the tests pin its shape.
- **opencode 2.x schema.** Defensive parsing, `opencode export` fallback, and
  `doctor` for diagnosis.

## References

- opencode CLI: https://opencode.ai/docs/cli/
- opencode 2.x tables: https://github.com/Dicklesworthstone/coding_agent_session_search/issues/504,
  https://github.com/wakatime/wakatime-cli/issues/1599
- Claude Code hooks (`UserPromptExpansion`): https://code.claude.com/docs/en/hooks
- Claude Code sessions and `/resume`: https://code.claude.com/docs/en/sessions
- Plugins: https://code.claude.com/docs/en/plugins-reference,
  https://code.claude.com/docs/en/plugins/publish

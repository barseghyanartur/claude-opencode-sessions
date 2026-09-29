# opencode storage: what this package reads

Phase 0 findings, from a real database written by opencode **1.18.32**
(macOS, September 2026: 155 sessions, 12k messages, 50k parts). The schema
is copied into `src/claude_opencode_sessions/tests/fixtures/schema_1x.sql`.
No data was copied.

## Location

`~/.local/share/opencode/opencode.db` (+ `-wal`, `-shm`), i.e.
`$XDG_DATA_HOME/opencode/opencode.db`. `opencode db path` prints it.
The directory also holds `auth.json` and `account.json`, and the database
has `account`/`credential` tables. **This package never reads those.**

## 1.x layout (>= 1.2, current stable)

The 1.18 database already contains the 2.x `session_message` table, but it
is **empty**. Everything lives in the 1.x tables:

- `session`: `id, project_id, parent_id, slug, directory, title, version,
  time_created, time_updated, time_archived, agent, model (JSON {id,
  providerID}), cost, tokens_input, tokens_output, …`
  - `parent_id` set → sub-agent (task) session.
  - `version` = the opencode version that last wrote the session.
- `message`: `id, session_id, time_created, time_updated, data (JSON)`
  - user: `{role, time{created}, agent, model{providerID, modelID}, summary}`
  - assistant: `{role, parentID, mode, agent, path{cwd, root}, cost,
    tokens{total, input, output, reasoning, cache{read, write}}, modelID,
    providerID, time{created, completed}, finish, error?{name, data{message}}}`
- `part`: `id, message_id, session_id, time_created, time_updated, data (JSON)`
  - observed `type`s: `text` (`synthetic` flag on injected user text),
    `reasoning`, `tool` (`tool`, `callID`, `state{status, input, output,
    metadata, title, time}`), `step-start`, `step-finish`, `patch` (`files`),
    `file` (`filename, mime, url`), `compaction`.
  - opencode stores **each assistant step as its own message**. The
    importer merges consecutive assistant messages into one Claude turn.
- `project`: `id` (git root commit hash, or `global`), `worktree`, `vcs`, …
  One project spans all worktrees and clones of a repo. Non-git directories
  all share `global`.

## 2.x layout (beta, >= ~2.0.18)

Not verified against a real database. The following comes from public
reports (see the references in `docs/design.md`):

- `session_v2`: `id, project_id, parent_id, directory, title, agent, model,
  time_created, time_updated, time_archived, …`. Early 2.0.x builds kept the
  name `session`.
- `session_message`: `id, session_id, type, seq, time_created,
  time_updated, data (JSON)`.
  - `type`: `user | assistant | system | synthetic | idle | agent-switched | …`
  - user `data`: `{"text": …}`. Assistant `data` nests
    `model{id, providerID}`, `tokens` and `cost`.
- The frozen 1.x tables stay in the file. Migrated sessions keep their ids.

The 2.x parser is deliberately permissive: `text`, `content` or `parts`
payloads and tool-ish items. If more than 20% of a session's rows can't be
parsed, the session is loaded via `opencode export` instead. **Once a real 2.x
database is available, re-run this check and tighten
`parse.parse_v2_row` plus the 2.x fixtures.**

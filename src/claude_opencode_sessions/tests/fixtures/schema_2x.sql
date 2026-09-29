-- opencode 2.x layout (>= ~2.0.18): sessions in `session_v2`, conversation
-- events in `session_message`. Reconstructed from the 1.18 tables plus
-- public reports (no real 2.x database was available); columns this package
-- does not read are omitted. The frozen 1.x tables may coexist in the file.

CREATE TABLE `project` (
	`id` text PRIMARY KEY,
	`worktree` text NOT NULL,
	`vcs` text,
	`name` text,
	`time_created` integer NOT NULL,
	`time_updated` integer NOT NULL
);

CREATE TABLE `session_v2` (
	`id` text PRIMARY KEY,
	`project_id` text NOT NULL,
	`parent_id` text,
	`directory` text NOT NULL,
	`title` text NOT NULL,
	`agent` text,
	`model` text,
	`time_created` integer NOT NULL,
	`time_updated` integer NOT NULL,
	`time_archived` integer
);

CREATE TABLE `session_message` (
	`id` text PRIMARY KEY,
	`session_id` text NOT NULL,
	`type` text NOT NULL,
	`time_created` integer NOT NULL,
	`time_updated` integer NOT NULL,
	`data` text NOT NULL,
	`seq` integer NOT NULL
);
CREATE UNIQUE INDEX `session_message_session_seq_idx` ON `session_message` (`session_id`,`seq`);

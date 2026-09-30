# claude-sessions-importer — monorepo of independent Claude Code plugins.
# Each plugin under plugins/<name>/ has its own Makefile, pyproject.toml,
# version and release cadence; these targets just fan out to all of them.
# See plugins/<name>/Makefile for that plugin's own targets (bump, release, tag, …).

.DEFAULT_GOAL := help
SHELL := /bin/bash
UV    ?= uv

PLUGINS := opencode-sessions codex-sessions copilot-sessions

.PHONY: help install test cov lint fmt typecheck validate check dev clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Plugins: $(PLUGINS)"
	@echo "  Per-plugin targets: make -C plugins/<name> <target>"

install: ## uv sync every plugin into one shared .venv (workspace mode)
	$(UV) sync --all-packages

test: ## Run every plugin's test suite
	@for p in $(PLUGINS); do echo "== $$p =="; $(MAKE) -C plugins/$$p test || exit 1; done

cov: ## Run every plugin's tests with coverage
	@for p in $(PLUGINS); do echo "== $$p =="; $(MAKE) -C plugins/$$p cov || exit 1; done

lint: ## Lint every plugin (ruff)
	@for p in $(PLUGINS); do echo "== $$p =="; $(MAKE) -C plugins/$$p lint || exit 1; done

fmt: ## Auto-fix + format every plugin (ruff)
	@for p in $(PLUGINS); do $(MAKE) -C plugins/$$p fmt; done

typecheck: ## Type-check every plugin (mypy --strict)
	@for p in $(PLUGINS); do echo "== $$p =="; $(MAKE) -C plugins/$$p typecheck || exit 1; done

validate: ## Validate the marketplace manifest and every plugin
	@if command -v claude >/dev/null 2>&1; then \
	    claude plugin validate --strict . ; \
	else \
	    echo "claude CLI not found - skipping 'claude plugin validate'"; \
	fi

check: lint typecheck test validate ## Everything CI runs, for every plugin

dev: ## Start Claude Code with both plugins loaded from this checkout
	claude --plugin-dir "$(CURDIR)"

clean: ## Remove build artefacts from every plugin, plus the shared .venv
	rm -rf .venv dist  # dist/ here only if `uv build` was ever run from the root by mistake
	@for p in $(PLUGINS); do $(MAKE) -C plugins/$$p clean; done

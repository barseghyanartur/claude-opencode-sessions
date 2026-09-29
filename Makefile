# claude-opencode-sessions / opencode-sessions — development & release tasks.
# Requires: uv (https://docs.astral.sh/uv/), git; `claude` for plugin tasks;
# a PyPI trusted publisher (or UV_PUBLISH_TOKEN) for publishing.
# Compatible with the GNU make 3.81 that ships with macOS.

.DEFAULT_GOAL := help
SHELL := /bin/bash

PACKAGE     := claude-opencode-sessions
PLUGIN      := opencode-sessions
MARKETPLACE := barseghyanartur
GITHUB_REPO := barseghyanartur/claude-plugin-opencode-sessions
UV          ?= uv
VERSION     := $(shell $(UV) version --short 2>/dev/null)
TAG         := v$(VERSION)

.PHONY: help install test cov lint fmt typecheck validate check run dev \
	    install-local uninstall-local version bump build plugin-zip \
	    publish-test publish release-check release submit clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- development ------------------------------------------------------------

install: ## Create .venv with the dev dependencies (uv sync)
	$(UV) sync

test: ## Run the test suite
	$(UV) run pytest

cov: ## Run tests with coverage (terminal + htmlcov/)
	$(UV) run pytest --cov --cov-report=term --cov-report=html

lint: ## Lint and check formatting (ruff)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Auto-fix lint issues and format (ruff)
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## Type-check the package (mypy --strict)
	$(UV) run mypy

version-check: ## Fail unless plugin.json has the pyproject.toml version
	@grep -q '"version": "$(VERSION)"' .claude-plugin/plugin.json || \
		{ echo "plugin.json version != $(VERSION) (run: make bump VERSION=$(VERSION))"; exit 1; }

validate: version-check ## Validate plugin + marketplace manifests
	@if command -v claude >/dev/null 2>&1; then \
	    claude plugin validate --strict . ; \
	else \
	    echo "claude CLI not found - skipping 'claude plugin validate'"; \
	fi

check: lint typecheck test validate ## Everything CI runs

run: ## Run the CLI from source, e.g. make run ARGS="list --all"
	@sh scripts/opencode-sessions $(ARGS)

# --- Claude Code plugin -----------------------------------------------------

dev: ## Start Claude Code with the plugin loaded from this checkout
	claude --plugin-dir "$(CURDIR)"

install-local: ## Install the plugin from this checkout through a local marketplace
	claude plugin marketplace add "$(CURDIR)"
	claude plugin install $(PLUGIN)@$(MARKETPLACE)

uninstall-local: ## Remove the local marketplace and the plugin
	-claude plugin uninstall $(PLUGIN)@$(MARKETPLACE)
	-claude plugin marketplace remove $(MARKETPLACE)

# --- releasing --------------------------------------------------------------

version: ## Print the current version
	@echo $(VERSION)

bump: ## Set the version: make bump BUMP=patch|minor|major, or VERSION=x.y.z
	$(UV) version $(if $(BUMP),--bump $(BUMP),$(VERSION))
	sed -i.bak 's/"version": "[^"]*"/"version": "'"$$($(UV) version --short)"'"/' .claude-plugin/plugin.json
	rm -f .claude-plugin/plugin.json.bak
	@echo "Now add a $$($(UV) version --short) section to CHANGELOG.rst"

build: clean ## Build sdist + wheel (uv build) and the plugin zip into dist/
	$(UV) build
	$(MAKE) plugin-zip

plugin-zip: ## Zip the committed plugin files (for `claude --plugin-url`)
	@mkdir -p dist
	git archive --format=zip --prefix=$(PLUGIN)/ -o dist/$(PLUGIN)-$(VERSION).zip HEAD \
	    .claude-plugin hooks skills scripts src/claude_opencode_sessions README.rst LICENSE CHANGELOG.rst
	@echo "dist/$(PLUGIN)-$(VERSION).zip"

publish-test: build ## Upload to TestPyPI (needs UV_PUBLISH_TOKEN for test.pypi.org)
	$(UV) publish --publish-url https://test.pypi.org/legacy/ dist/*.whl dist/*.tar.gz

publish: build ## Upload to PyPI by hand (normally `make release` does it via CI)
	$(UV) publish dist/*.whl dist/*.tar.gz

release: check ## Tag vX.Y.Z and push; CI publishes to PyPI + GitHub release
	@test -z "$$(git status --porcelain)" || { echo "commit your changes first"; exit 1; }
	git tag -a v$(VERSION) -m "v$(VERSION)"
	git push origin HEAD v$(VERSION)

submit: ## Print what Anthropic's community-marketplace form asks for
	@echo "Form (individuals): https://platform.claude.com/plugins/submit"
	@echo "Form (Team/Enterprise org): https://claude.ai/admin-settings/directory/submissions/plugins/new"
	@echo "Plugin name:  $(PLUGIN)"
	@echo "Version:      $(VERSION)"
	@echo "Repository:   https://github.com/$(GITHUB_REPO)"
	@echo "Commit SHA:   $$(git rev-parse HEAD)"
	@echo "Tag:          $$(git describe --tags --exact-match 2>/dev/null || echo '(HEAD is not tagged)')"

clean: ## Remove build artefacts
	rm -rf dist build *.egg-info htmlcov .coverage

# claude-codex-sessions / codex-sessions — development & release tasks.
# Requires: uv (https://docs.astral.sh/uv/), git; `claude` for plugin tasks.
# Publishing uses twine with the credentials in ~/.pypirc (pypi + testpypi).
# Compatible with the GNU make 3.81 that ships with macOS.

.DEFAULT_GOAL := help
SHELL := /bin/bash

PACKAGE     := claude-codex-sessions
PLUGIN      := codex-sessions
MARKETPLACE := barseghyanartur
GITHUB_REPO := barseghyanartur/claude-sessions-importer
UV          ?= uv
VERSION     := $(shell $(UV) version --short 2>/dev/null)

.PHONY: help install test cov lint fmt typecheck validate check run dev \
	    install-local uninstall-local version version-check bump build \
	    check-build test-release release tag submit clean

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
	@sh scripts/codex-sessions $(ARGS)

# --- Claude Code plugin -----------------------------------------------------

dev: ## Start Claude Code with the plugin loaded from this checkout
	claude --plugin-dir "$(CURDIR)"

install-local: ## Install the plugin from this checkout through a local marketplace
	claude plugin marketplace add "$(CURDIR)/../.."  # marketplace.json lives at the monorepo root
	claude plugin install $(PLUGIN)@$(MARKETPLACE)

uninstall-local: ## Remove the local marketplace and the plugin
	-claude plugin uninstall $(PLUGIN)@$(MARKETPLACE)
	-claude plugin marketplace remove $(MARKETPLACE)

# --- releasing --------------------------------------------------------------
#
# Release checklist:
#
#   make bump BUMP=minor     # or BUMP=patch|major, or VERSION=0.2.0
#   $EDITOR CHANGELOG.rst    # add the release notes
#   git commit -am "Release $(uv version --short)"
#   make test-release        # check, build, twine check, upload to TestPyPI
#   make release             # the same, upload to PyPI
#   make tag                 # tag <plugin>-vX.Y.Z and push (plugin users get the update)
#
# Uploads use twine with the API tokens in ~/.pypirc ([pypi] and [testpypi],
# username __token__), so no credentials are typed.
#
# Optional: list the plugin in Anthropic's community marketplace with the
# details `make submit` prints.

version: ## Print the current version
	@echo $(VERSION)

bump: ## Set the version: make bump BUMP=patch|minor|major, or VERSION=x.y.z
	$(UV) version $(if $(BUMP),--bump $(BUMP),$(VERSION))
	sed -i.bak 's/"version": "[^"]*"/"version": "'"$$($(UV) version --short)"'"/' .claude-plugin/plugin.json
	rm -f .claude-plugin/plugin.json.bak
	@echo "Now add a $$($(UV) version --short) section to CHANGELOG.rst"

build: clean ## Build sdist + wheel into dist/
	$(UV) build

check-build: ## Check dist/ (twine check)
	$(UV) run twine check --strict dist/*

test-release: check build check-build ## Upload to TestPyPI (credentials from ~/.pypirc)
	$(UV) run twine upload --repository testpypi dist/*

release: check build check-build ## Upload to PyPI (credentials from ~/.pypirc)
	$(UV) run twine upload dist/* --verbose

tag: ## Tag <plugin>-vX.Y.Z and push (publishes the plugin version to marketplace users)
	@test -z "$$(git status --porcelain)" || { echo "commit your changes first"; exit 1; }
	git tag -a $(PLUGIN)-v$(VERSION) -m "$(PLUGIN) v$(VERSION)"
	git push origin HEAD $(PLUGIN)-v$(VERSION)

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

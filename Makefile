# Makefile for lftools-uv development with uv
.PHONY: help install install-dev sync update test lint format clean build docs serve-docs check pre-commit all

# Default target
help:
	@echo "Available targets:"
	@echo "  install       Install project dependencies"
	@echo "  install-dev   Install project with all development dependencies"
	@echo "  sync          Sync dependencies from lock file"
	@echo "  update        Update dependencies and regenerate lock file"
	@echo "  test          Run tests with pytest"
	@echo "  lint          Run linting with ruff"
	@echo "  format        Format code with black and ruff"
	@echo "  clean         Clean build artifacts and cache"
	@echo "  build         Build package with hatchling"
	@echo "  docs          Build documentation"
	@echo "  serve-docs    Serve documentation locally"
	@echo "  check         Run all checks (lint, test, etc.)"
	@echo "  pre-commit    Run pre-commit hooks"
	@echo "  all           Install, format, lint, test, and build"

# Install project dependencies
install:
	uv sync

# Install project with all development dependencies
install-dev:
	uv sync --extra dev --extra test --extra docs --extra ldap --extra openstack

# Sync dependencies from lock file (fast install)
sync:
	uv sync --frozen

# Update dependencies and regenerate lock file
update:
	uv sync --upgrade

# Run tests
test:
	uv run pytest

# Run tests with coverage
test-cov:
	uv run pytest --cov=lftools_uv --cov-report=html --cov-report=term

# Run linting
lint:
	uv run ruff check .
	uv run mypy lftools_uv

# Format code
format:
	uv run ruff format .
	uv run ruff check --fix .

# Clean build artifacts and cache
clean:
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .coverage htmlcov/
	rm -rf docs/_build/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

# Build package
build: clean
	uv build

# Build documentation
docs:
	uv run --extra docs sphinx-build -b html -n -d docs/_build/doctrees ./docs/ docs/_build/html

# Serve documentation locally
serve-docs: docs
	cd docs/_build/html && python -m http.server 8000

# Run all checks
check: lint test

# Run pre-commit hooks
pre-commit:
	uv run --extra dev pre-commit run --all-files

# Development setup - install everything and run initial checks
dev-setup: install-dev format lint test
	@echo "Development environment ready!"

# Full pipeline - everything
all: install-dev format lint test build
	@echo "All tasks completed successfully!"

# Run tox tests
tox:
	uv run --extra dev tox

# Install the package in editable mode
install-editable:
	uv pip install -e .

# Generate requirements.txt for compatibility
requirements:
	uv export --format requirements-txt --output-file requirements.txt
	uv export --format requirements-txt --extra dev --extra test --extra docs --extra ldap --extra openstack --output-file requirements-dev.txt

# Version bump (requires bumpver or similar)
version-patch:
	uv run bumpver update --patch

version-minor:
	uv run bumpver update --minor

version-major:
	uv run bumpver update --major

# Security audit
audit:
	uv run --extra dev pip-audit

# Shell with all dependencies available
shell:
	uv run --extra dev --extra test --extra docs --extra ldap --extra openstack python

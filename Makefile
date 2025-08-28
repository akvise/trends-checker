SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PY ?= python3
VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: help venv install run run-related clean reset

help:
	@echo "Available targets:"; \
	awk -F':.*## ' '/^[a-zA-Z0-9_.-]+:.*## /{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create Python virtualenv at .venv
	$(PY) -m venv $(VENV)

install: venv ## Install dependencies into .venv from pyproject
	@source $(VENV)/bin/activate && \
	  python -m pip install --upgrade pip setuptools wheel && \
	  python -m pip install -e .

run: ## Run CLI with defaults
	$(PYTHON) -m trends_checker.cli

run-related: ## Run CLI with related queries enabled
	$(PYTHON) -m trends_checker.cli --related

clean: ## Remove caches and build artifacts
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@rm -rf .pytest_cache build dist

reset: ## Remove venv and caches
	@rm -rf $(VENV)
	@$(MAKE) clean


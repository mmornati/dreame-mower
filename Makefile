---
# Makefile for Dreame Mower Custom Component Development

.PHONY: help test test-unit test-integration start stop restart logs clean format lint install-dev package status

help:
	@echo "Dreame Mower Development Commands"
	@echo "================================"
	@echo ""
	@echo "Development:"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make format           Format code with black and isort"
	@echo "  make lint             Run linters"
	@echo "  make package          Build a distributable zip for manual testing"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-unit        Run unit tests only"
	@echo ""
	@echo "Integration Testing:"
	@echo "  make start            Start Home Assistant for testing"
	@echo "  make stop             Stop Home Assistant"
	@echo "  make restart          Restart Home Assistant"
	@echo "  make logs             Show Home Assistant logs (follow mode)"
	@echo "  make status           Show status"
	@echo "  make clean            Clean all test data"
	@echo ""

install-dev:
	@echo "Creating virtual environment (.venv) if needed..."
	python3 -m venv .venv
	@echo "Installing development dependencies inside .venv..."
	. .venv/bin/activate && pip install --upgrade pip
	. .venv/bin/activate && pip install -r requirements-dev.txt
	@echo "Environment ready. Activate it with: source .venv/bin/activate"

format:
	@echo "Formatting code..."
	.venv/bin/black custom_components/dreame_mower/
	.venv/bin/isort custom_components/dreame_mower/

lint:
	@echo "Running linters..."
	.venv/bin/pylint custom_components/dreame_mower/ || true

test: test-unit
	@echo "All tests completed!"

test-unit:
	@echo "Running unit tests..."
	.venv/bin/pytest tests/ -v

start:
	./scripts/integration-test.sh start

stop:
	./scripts/integration-test.sh stop

restart:
	./scripts/integration-test.sh restart

logs:
	./scripts/integration-test.sh logs

status:
	./scripts/integration-test.sh status

clean:
	./scripts/integration-test.sh clean
	@echo "Cleaning Python cache..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaning coverage reports..."
	rm -rf htmlcov/ .coverage 2>/dev/null || true

package:
	@echo "Creating development zip package..."
	mkdir -p dist
	rm -f dist/hass-custom-dreame-mower.zip
	cd custom_components && \
	zip -r ../dist/hass-custom-dreame-mower.zip dreame_mower \
		-x "*.git*" \
		-x "*__pycache__*" \
		-x "*.pyc" \
		-x "*.pyo" \
		-x "*.DS_Store" \
		-x "*.pytest_cache*"
	@echo "Package created at dist/hass-custom-dreame-mower.zip"
.PHONY: help build test test-watch lint lint-fix format clean

help:
	@echo "HASS Dashboard - Development Commands"
	@echo "======================================"
	@echo "make build       - Build the tools container"
	@echo "make test        - Run pytest tests"
	@echo "make test-watch  - Run pytest in watch mode"
	@echo "make lint        - Run ruff linter"
	@echo "make lint-fix    - Auto-fix linting issues"
	@echo "make format      - Format code with ruff"
	@echo "make clean       - Remove test outputs and cache"

build:
	docker compose build tools

test:
	docker compose run --rm tools pytest tests/ -v

test-watch:
	docker compose run --rm tools pytest tests/ -v --tb=short -s

test-cov:
	docker compose run --rm tools pytest tests/ --cov=src --cov-report=html

lint:
	docker compose run --rm --entrypoint ruff tools check src/ tests/

lint-fix:
	docker compose run --rm --entrypoint ruff tools check src/ tests/ --fix

format:
	docker compose run --rm --entrypoint ruff tools format src/ tests/

clean:
	rm -f test_*.bmp test_output.bmp
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

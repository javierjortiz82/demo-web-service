.PHONY: help install test lint format type-check security-check build run clean docs fix-perms

help:
	@echo "Demo Agent Service - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install          Install dependencies"
	@echo "  make run              Run development server"
	@echo "  make test             Run tests"
	@echo "  make test-cov         Run tests with coverage"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run linters (ruff, black, isort)"
	@echo "  make format           Format code with black and isort"
	@echo "  make type-check       Run mypy type checker"
	@echo "  make security-check   Run bandit security scanner"
	@echo "  make quality          Run all quality checks"
	@echo ""
	@echo "Docker:"
	@echo "  make build            Build Docker image"
	@echo "  make docker-up        Start Docker containers"
	@echo "  make docker-down      Stop Docker containers"
	@echo "  make docker-logs      Show Docker logs"
	@echo "  make docker-restart   Restart Docker containers"
	@echo "  make fix-perms        Fix file permissions for Docker volumes"
	@echo ""
	@echo "Cleaning:"
	@echo "  make clean            Clean temporary files"
	@echo "  make clean-docker     Remove Docker containers and volumes"

install:
	pip install -r requirements.txt
	pre-commit install 2>/dev/null || true

run:
	PYTHONPATH=.:$$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 9090 --reload

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=app --cov-report=html --cov-report=term-missing

lint:
	ruff check .
	black --check .
	isort --check-only .

format:
	black .
	isort .
	ruff check . --fix

type-check:
	mypy app

security-check:
	bandit -r app -lll

quality: lint type-check security-check
	@echo "All quality checks passed!"

build:
	docker build -t demo-agent:latest .

# Fix permissions for Docker volume mounts (development)
fix-perms:
	@echo "Fixing file permissions for Docker..."
	find app -name "*.py" -exec chmod 644 {} \;
	find prompts -name "*.j2" -exec chmod 644 {} \; 2>/dev/null || true
	find . -maxdepth 1 -name "*.py" -exec chmod 644 {} \;
	@echo "Permissions fixed!"

docker-up: fix-perms
	DOCKER_UID=$$(id -u) DOCKER_GID=$$(id -g) docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f demo-agent

docker-restart: fix-perms
	DOCKER_UID=$$(id -u) DOCKER_GID=$$(id -g) docker compose up -d demo-agent

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache dist build *.egg-info
	rm -rf logs/*.log

clean-docker:
	docker compose down -v
	docker image rm demo-agent:latest 2>/dev/null || true

.DEFAULT_GOAL := help
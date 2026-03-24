.PHONY: help install dev run test lint format build docker-build docker-up docker-down clean

PYTHON   := python3.11
PIP      := pip
APP      := app.main:app
PORT     := 8000

help:          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "\033[36m%-20s\033[0m %s\n",$$1,$$2}'

install:       ## Install production dependencies
	$(PIP) install -r requirements.txt

dev:           ## Install development dependencies
	$(PIP) install -r requirements-dev.txt
	pre-commit install

run:           ## Run the service locally (hot-reload)
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --reload

run-prod:      ## Run in production mode
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --workers 4

test:          ## Run all tests with coverage
	pytest tests/ -v --tb=short

test-unit:     ## Run unit tests only
	pytest tests/unit/ -v

test-int:      ## Run integration tests only
	pytest tests/integration/ -v

lint:          ## Lint with ruff
	ruff check app/ tests/

format:        ## Auto-format with ruff
	ruff format app/ tests/

type-check:    ## Run mypy type checks
	mypy app/ --ignore-missing-imports

build:         ## Build source distribution + wheel
	$(PYTHON) setup.py sdist
	$(PYTHON) -m build

docker-build:  ## Build Docker image
	docker build -t microservice-boilerplate:latest .

docker-up:     ## Start full stack (app + postgres + rabbitmq)
	docker compose up --build -d

docker-down:   ## Stop and remove containers
	docker compose down

docker-logs:   ## Tail application logs
	docker compose logs -f app

clean:         ## Remove build artefacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .coverage coverage.xml __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete

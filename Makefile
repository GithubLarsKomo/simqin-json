# SIMQIN JSON Platform — Makefile

.PHONY: test up down lint help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Run all Python tests
	cd services/worker && python -m pytest tests/ -v

up: ## Start all services via Docker Compose
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Show logs from all services
	docker compose logs -f

lint: ## Check Python files for syntax errors
	python -m py_compile services/api/app/main.py
	python -m py_compile services/worker/app/parser.py
	python -m py_compile services/worker/app/mapper.py
	python -m py_compile services/worker/app/main.py
	@echo "All Python files compile OK."

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-build: ## Build frontend for production
	cd frontend && npm run build

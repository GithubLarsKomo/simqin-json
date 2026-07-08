# SIMQIN JSON Platform — Makefile

PYTHON = python
WORKER_DIR = services/worker
API_DIR = services/api
FRONTEND_DIR = frontend

.PHONY: test up down logs lint frontend-build help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Run all Python tests from repo root
	cd $(WORKER_DIR) && $(PYTHON) -m pytest tests/ -v

up: ## Start all services via Docker Compose
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Show logs from all services
	docker compose logs -f

lint: ## Check Python files for syntax errors
	$(PYTHON) -m py_compile $(API_DIR)/app/main.py
	$(PYTHON) -m py_compile $(WORKER_DIR)/app/parser.py
	$(PYTHON) -m py_compile $(WORKER_DIR)/app/mapper.py
	$(PYTHON) -m py_compile $(WORKER_DIR)/app/main.py
	@echo "All Python files compile OK."

frontend-install: ## Install frontend dependencies
	cd $(FRONTEND_DIR) && npm install

frontend-build: ## Build frontend for production
	cd $(FRONTEND_DIR) && npm run build

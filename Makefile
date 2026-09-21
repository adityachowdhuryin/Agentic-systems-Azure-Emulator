.PHONY: install init seed dev test reset-demo backend frontend

ROOT := $(shell pwd)
VENV := $(ROOT)/backend/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install: backend-install frontend-install

backend-install:
	cd backend && python3 -m venv .venv && $(PIP) install -r requirements.txt

frontend-install:
	cd frontend && npm install

init:
	mkdir -p data
	cd backend && PYTHONPATH=. $(PYTHON) scripts/init_db.py

seed: init

reset-demo:
	curl -s -X POST http://localhost:8000/api/v1/demo/reset

dev:
	@echo "Starting backend on :8000 and frontend on :5173"
	@make -j2 backend frontend

backend:
	cd backend && PYTHONPATH=. $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && PYTHONPATH=. $(PYTHON) -m pytest tests/ -v

test-frontend:
	cd frontend && npm run test

docker-up:
	docker compose up --build

docker-down:
	docker compose down

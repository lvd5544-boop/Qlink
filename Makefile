.PHONY: up dev down stop logs ps migrate test test-backend test-frontend backup config

up:
	docker compose up -d --build

dev: up

down:
	docker compose down

stop: down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

migrate:
	docker compose run --rm migration

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && npm test && npm run lint && npm run build

backup:
	./scripts/backup.sh

config:
	docker compose config --quiet

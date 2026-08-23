.PHONY: up dev down stop logs ps migrate test test-backend test-frontend evaluate-ranking evaluate-hypotheses ranking-label-template compare-ranking-labels backup config production-preflight production-go-live-preflight production-config production-up production-ps production-logs production-smoke

PRODUCTION_ENV_FILE ?= .env.production
PRODUCTION_COMPOSE = docker compose --env-file $(PRODUCTION_ENV_FILE) -f docker-compose.yml -f docker-compose.production.yml

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

evaluate-ranking:
	backend/.venv/bin/python backend/scripts/run_ranking_evaluation.py

evaluate-hypotheses:
	backend/.venv/bin/python backend/scripts/run_hypothesis_evaluation.py

ranking-label-template:
	@test -n "$(REVIEWER_ALIAS)" || (echo "REVIEWER_ALIAS is required" >&2; exit 2)
	@test -n "$(SEED)" || (echo "SEED is required" >&2; exit 2)
	@backend/.venv/bin/python backend/scripts/ranking_annotations.py template --reviewer-alias "$(REVIEWER_ALIAS)" --seed "$(SEED)"

compare-ranking-labels:
	@test -n "$(REVIEWER_A)" || (echo "REVIEWER_A is required" >&2; exit 2)
	@test -n "$(REVIEWER_B)" || (echo "REVIEWER_B is required" >&2; exit 2)
	@backend/.venv/bin/python backend/scripts/ranking_annotations.py compare --reviewer-a "$(REVIEWER_A)" --reviewer-b "$(REVIEWER_B)"

backup:
	./scripts/backup.sh

config:
	docker compose config --quiet

production-preflight:
	python3 scripts/production_preflight.py --env-file $(PRODUCTION_ENV_FILE)
	$(PRODUCTION_COMPOSE) config --quiet

production-go-live-preflight:
	python3 scripts/production_preflight.py --env-file $(PRODUCTION_ENV_FILE) --go-live
	$(PRODUCTION_COMPOSE) config --quiet

production-config: production-preflight
	$(PRODUCTION_COMPOSE) config --services

production-up: production-preflight
	$(PRODUCTION_COMPOSE) up -d --build

production-ps:
	$(PRODUCTION_COMPOSE) ps

production-logs:
	$(PRODUCTION_COMPOSE) logs -f --tail=200

production-smoke:
	@test -n "$(PUBLIC_ORIGIN)" || (echo "PUBLIC_ORIGIN=https://your-domain is required" >&2; exit 2)
	python3 scripts/production_smoke.py --origin $(PUBLIC_ORIGIN)

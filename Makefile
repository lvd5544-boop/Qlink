.PHONY: up dev down stop logs ps migrate test test-backend test-frontend evaluate-ranking evaluate-hypotheses ranking-label-template compare-ranking-labels backup config

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

# QLink repository guide for coding agents

## Scope

This repository contains a FastAPI backend, a React frontend, browser E2E tests, and Docker Compose deployment assets. Preserve the evidence-grounded product contract: model output is not a candidate fact until the candidate confirms it.

## Required checks

Run the narrowest relevant tests while editing. Before handing off a repository-wide change, run:

```bash
make test
```

For changes to deployed routes, migrations, or full user journeys, also run the relevant smoke or Playwright flow documented in `MANUAL_ACCEPTANCE_GUIDE.md`.

## Safety and product invariants

- Never commit secrets, `.env` files, real resumes, user uploads, or production exports.
- Preserve user and employer ownership checks on every private resource.
- Do not convert inferred skills, interview observations, or generated text into confirmed facts without an explicit state transition.
- External submission, messaging, rejection, or other high-impact actions require a user-visible preview and explicit approval.
- Do not introduce school or employer prestige scoring, protected-attribute proxies, or hiring-probability claims.
- Keep writes idempotent where clients or workers may retry them.

## Repository conventions

- Backend application code: `backend/app/`
- Backend tests: `backend/tests/`
- Frontend product code: `frontend/src/`
- Browser E2E: `frontend/e2e/`
- Operational scripts: `scripts/` and `backend/scripts/`
- Public documentation: `docs/` and the selected root-level plans and acceptance reports

Follow `CONTRIBUTING.md` for branch and commit naming. Local Cursor/AI planning history is intentionally ignored; do not force-add it.

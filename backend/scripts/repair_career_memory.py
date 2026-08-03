"""Repair legacy resume summaries and project resumes into career memory.

Dry-run by default:
    python scripts/repair_career_memory.py
Apply:
    python scripts/repair_career_memory.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.claim_passport import sync_resume_claims  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models_db import Resume  # noqa: E402
from app.resume_parser import enrich_resume_from_text  # noqa: E402


async def run(*, apply: bool) -> dict[str, int]:
    result = {"resumes": 0, "summaries_cleared": 0, "claims_linked": 0}
    async with AsyncSessionLocal() as db:
        resumes = (await db.execute(select(Resume))).scalars().all()
        for resume in resumes:
            result["resumes"] += 1
            parsed = dict(resume.parsed_json or {})
            repaired = enrich_resume_from_text(parsed, resume.raw_text or "").model_dump()
            if parsed.get("summary") and not repaired.get("summary"):
                result["summaries_cleared"] += 1
                if apply:
                    resume.parsed_json = repaired
            if apply and resume.user_id:
                claims = await sync_resume_claims(
                    db,
                    resume,
                    actor_id=str(resume.user_id),
                    reason="legacy_career_memory_repair",
                )
                result["claims_linked"] += len(claims)
        if apply:
            await db.commit()
        else:
            await db.rollback()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()

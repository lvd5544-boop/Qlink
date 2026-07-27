"""Deterministic, provenance-aware target-role profiles for PR9.

This module deliberately does *not* treat a general taxonomy as a company's
recruiting truth.  The employer's submitted JD remains the only requirement
source; the local crosswalk only gives stable canonical labels for matching and
for a replayable simulation snapshot.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .company_registry import normalize_skill_name

PROFILE_VERSION = "target-role-profile-v1"
CROSSWALK_VERSION = "local-occupation-crosswalk-v1"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _skill_name(value: Any) -> str:
    return normalize_skill_name(value.get("name", "") if isinstance(value, dict) else str(value))


def build_target_role_profile(job: dict[str, Any], job_title: str) -> dict[str, Any]:
    """Return a stable profile without inventing requirements from a taxonomy.

    ``source_kind`` is intentionally explicit: a locally entered employer JD
    is employer-provided, not an "official ESCO/O*NET requirement".  Consumers
    can therefore distinguish requirement provenance from normalization aid.
    """
    skills = job.get("required_skills") or job.get("skills") or []
    canonical_skills = sorted({_skill_name(item) for item in skills} - {""})
    raw_text = str(job.get("_raw_text") or job.get("raw_text") or "")
    parsed_snapshot = {key: value for key, value in job.items() if not key.startswith("_")}
    jd_snapshot_sha256 = _fingerprint({"raw_text": raw_text, "parsed": parsed_snapshot})
    requirements = [
        {
            "requirement_id": f"jd:{jd_snapshot_sha256[:12]}:skill:{index}",
            "kind": "skill",
            "text": skill,
            "canonical_skill": skill,
            "normalization": {
                "source": "local_crosswalk",
                "version": CROSSWALK_VERSION,
                "crosswalk_key": f"skill:{skill}",
            },
        }
        for index, skill in enumerate(canonical_skills)
    ]
    years = job.get("experience_years")
    if years not in (None, "", 0, 0.0):
        requirements.append(
            {
                "requirement_id": f"jd:{jd_snapshot_sha256[:12]}:experience_years",
                "kind": "experience_years",
                "text": str(years),
                "value": years,
                "normalization": None,
            }
        )
    return {
        "profile_version": PROFILE_VERSION,
        "taxonomy_version": CROSSWALK_VERSION,
        "source": {
            "source_kind": "employer_provided_job_description",
            "is_company_requirement": True,
            "raw_text_sha256": _fingerprint(raw_text),
            "parsed_snapshot_sha256": _fingerprint(parsed_snapshot),
            "jd_snapshot_sha256": jd_snapshot_sha256,
        },
        "title": job_title or str(job.get("title") or ""),
        "requirements": requirements,
        "normalization_notice": "本地 crosswalk 仅用于标准化，不新增或证明公司录用要求。",
    }

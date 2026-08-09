"""Task profiles for the AI gateway."""

from __future__ import annotations

from dataclasses import dataclass

from .config import resolve_model_for_task


@dataclass(frozen=True)
class TaskProfile:
    task: str
    temperature: float
    max_tokens: int
    prompt_version: str
    schema_version: str
    allow_thinking: bool = False


PROFILES: dict[str, TaskProfile] = {
    "resume_parse": TaskProfile("resume_parse", 0.1, 4000, "resume_parse_v1", "resume_info_v1"),
    "jd_parse": TaskProfile("jd_parse", 0.1, 2000, "jd_parse_v1", "job_info_v1"),
    "faithful_rewrite": TaskProfile(
        "faithful_rewrite", 0.2, 4000, "faithful_rewrite_v1", "rewrite_v1"
    ),
    "interview_question_render": TaskProfile(
        "interview_question_render", 0.4, 1500, "interview_v1", "interview_turn_v1"
    ),
    "generic_chat": TaskProfile("generic_chat", 0.2, 2000, "generic_chat_v1", "chat_v1"),
    "advisor_answer": TaskProfile("advisor_answer", 0.2, 2000, "advisor_v1", "advisor_v1"),
    "screening_evidence_summary": TaskProfile(
        "screening_evidence_summary", 0.1, 2000, "screening_v1", "screening_v1"
    ),
    "claim_extract": TaskProfile("claim_extract", 0.1, 2000, "claim_extract_v1", "claim_v1"),
    "claim_evidence_assess": TaskProfile(
        "claim_evidence_assess", 0.1, 2000, "claim_evidence_v1", "claim_v1"
    ),
    "interview_observation_extract": TaskProfile(
        "interview_observation_extract", 0.1, 2000, "interview_obs_v1", "obs_v1"
    ),
    "consistency_alternative_explanations": TaskProfile(
        "consistency_alternative_explanations",
        0.1,
        2000,
        "consistency_v1",
        "consistency_v1",
    ),
}


def get_profile(task: str) -> TaskProfile:
    return PROFILES.get(task, PROFILES["generic_chat"])


def model_for(task: str) -> str:
    return resolve_model_for_task(task)

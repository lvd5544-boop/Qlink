"""AI runtime configuration. Business modules must not read provider keys."""

from __future__ import annotations

import os


def ai_enabled() -> bool:
    raw = os.getenv("AI_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def primary_api_key() -> str:
    return (os.getenv("AI_PRIMARY_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()


def primary_base_url() -> str:
    return (
        (os.getenv("AI_PRIMARY_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "")
        .strip()
        .rstrip("/")
    )


def primary_provider_name() -> str:
    return (os.getenv("AI_PRIMARY_PROVIDER") or "openai_compatible").strip()


def data_region() -> str:
    return (os.getenv("AI_DATA_REGION") or "cn-beijing").strip()


def request_timeout_seconds() -> float:
    return float(
        os.getenv("AI_REQUEST_TIMEOUT_SECONDS") or os.getenv("MODEL_LLM_TIMEOUT_SECONDS") or "60"
    )


def max_retries() -> int:
    return max(0, int(os.getenv("AI_MAX_RETRIES", "1")))


def audit_content_logging() -> bool:
    return os.getenv("AI_AUDIT_CONTENT_LOGGING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


# Task → env alias. Empty means "must be configured explicitly when AI is used".
_TASK_MODEL_ENV = {
    "resume_parse": "AI_MODEL_RESUME_PARSE",
    "jd_parse": "AI_MODEL_RESUME_PARSE",
    "claim_extract": "AI_MODEL_REASONING",
    "claim_evidence_assess": "AI_MODEL_REASONING",
    "interview_question_render": "AI_MODEL_INTERVIEW",
    "interview_observation_extract": "AI_MODEL_INTERVIEW",
    "faithful_rewrite": "AI_MODEL_REWRITE",
    "advisor_answer": "AI_MODEL_REASONING",
    "screening_evidence_summary": "AI_MODEL_REASONING",
    "consistency_alternative_explanations": "AI_MODEL_REASONING",
    "generic_chat": "AI_MODEL_REWRITE",
}


def resolve_model_for_task(task: str) -> str:
    """Resolve model ID for a task. Never defaults to offline deepseek-chat."""
    env_name = _TASK_MODEL_ENV.get(task, "AI_MODEL_REWRITE")
    configured = (os.getenv(env_name) or "").strip()
    if configured:
        return configured
    # Transitional mapping: allow DEEPSEEK_MODEL only when explicitly set (non-empty).
    legacy = (os.getenv("DEEPSEEK_MODEL") or "").strip()
    if legacy:
        return legacy
    # Final fallback alias for local rules_only / tests — not a live DeepSeek ID.
    return (os.getenv("AI_MODEL_DEFAULT") or "qwen-plus").strip()


def provider_configured() -> bool:
    return bool(primary_api_key()) and ai_enabled()

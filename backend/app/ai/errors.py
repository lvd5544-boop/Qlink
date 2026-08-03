"""AI gateway errors."""

from __future__ import annotations


class AIUnavailableError(RuntimeError):
    """Raised when AI is disabled or no provider credentials are configured."""

    code = "ai_unavailable"

    def __init__(self, message: str = "AI 暂不可用，规则与人工功能仍可使用"):
        super().__init__(message)


class SchemaValidationError(ValueError):
    """Raised when model output fails schema or ID authorization checks."""

    code = "ai_schema_invalid"

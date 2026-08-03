import logging
import re

from .ai.errors import AIUnavailableError, SchemaValidationError
from .ai.gateway import InvocationContext, gateway_run
from .models import JobInfo, SkillRequirement

logger = logging.getLogger(__name__)


def parse_job_rules_only(text: str) -> JobInfo:
    """Deterministic fallback when no model key is configured."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]

    def labelled_values(labels: tuple[str, ...]) -> list[str]:
        values: list[str] = []
        for line in lines:
            match = re.match(
                rf"^(?:{'|'.join(re.escape(label) for label in labels)})\s*[：:]\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if match and match.group(1).strip():
                values.append(match.group(1).strip())
        return values

    title = "未命名岗位"
    for line in lines[:5]:
        for prefix in ("岗位：", "职位：", "title:", "Title:"):
            if prefix in line:
                title = line.split(prefix, 1)[1].strip() or title
                break
        else:
            if "工程师" in line or "经理" in line or "开发" in line:
                title = line
                break
    location = None
    for line in lines:
        if "地点" in line or "location" in line.lower():
            location = re.split(r"[：:]", line, maxsplit=1)[-1].strip()
            break
    skills = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,24}", text or ""):
        if token.lower() not in {s.name.lower() for s in skills}:
            skills.append(SkillRequirement(name=token))
        if len(skills) >= 12:
            break
    responsibilities = labelled_values(("职责", "岗位职责", "工作职责", "responsibilities"))[:8]
    requirements = labelled_values(
        ("要求", "任职要求", "必须要求", "任职资格", "资格要求", "requirements")
    )
    experience_years = None
    experience_values = labelled_values(("经验", "工作经验", "经验要求", "experience"))
    if experience_values:
        year_match = re.search(r"(\d+)\s*年", experience_values[0])
        if year_match:
            experience_years = int(year_match.group(1))
    return JobInfo(
        title=title,
        location=location,
        required_skills=skills,
        responsibilities=responsibilities or lines[1:6],
        requirements="；".join(requirements) or None,
        experience_years=experience_years,
        other_notes="parsed_by=rules_only",
    )


async def parse_job_with_llm(
    text: str,
    *,
    user_id: str | None = None,
    org_id: str | None = None,
) -> JobInfo:
    """Parse a JD through the task gateway, with a deterministic safe fallback."""
    prompt = (
        "从以下岗位描述提取结构化岗位信息。缺失字段使用 null 或空数组。"
        "不得把职业常识、公司公开材料或市场趋势补成企业岗位要求。\n\n"
        f"岗位描述：\n{text}"
    )
    try:
        result = await gateway_run(
            task="jd_parse",
            payload={
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            schema=JobInfo,
            context=InvocationContext(user_id=user_id, org_id=org_id),
        )
        return result.parsed
    except (AIUnavailableError, SchemaValidationError, TimeoutError):
        return parse_job_rules_only(text)
    except Exception:
        logger.exception("JD gateway parse failed; using deterministic parser")
        return parse_job_rules_only(text)

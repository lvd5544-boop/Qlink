import os
import json
import re
from openai import OpenAI

from .llm_client import model_api_key
from .models import JobInfo, SkillRequirement


def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def parse_job_rules_only(text: str) -> JobInfo:
    """Deterministic fallback when no model key is configured."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
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
    responsibilities = [line for line in lines if "职责" in line or line.startswith("-")][:8]
    return JobInfo(
        title=title,
        location=location,
        required_skills=skills,
        responsibilities=responsibilities or lines[1:6],
        other_notes="parsed_by=rules_only",
    )


def parse_job_with_llm(text: str) -> JobInfo:
    if not model_api_key():
        return parse_job_rules_only(text)

    client = get_openai_client()
    model = get_model()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_job",
                "description": "提取岗位详细信息",
                "parameters": JobInfo.model_json_schema(),
            },
        }
    ]

    prompt = f"""你是专业的HR信息提取专家。请从以下岗位描述中提取信息，严格按照 JSON Schema 返回。
缺失字段用 null 或空数组。
请额外识别：soft_skills（沟通协作等软实力）、leadership_signals（带团队/项目管理等）、
communication_signals、education_requirement、school_tier_keywords（如985/211/硕士等）。

岗位描述：
{text}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个精准的岗位解析器，输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "extract_job"}},
            temperature=0.1,
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            args = json.loads(msg.tool_calls[0].function.arguments)
            return JobInfo(**args)
        raise ValueError("无法解析岗位信息")
    except Exception:
        return parse_job_rules_only(text)

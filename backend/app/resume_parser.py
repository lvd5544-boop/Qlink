import os
import json
import re
import fitz
from docx import Document
from openai import OpenAI
from .llm_client import model_api_key
from .models import ResumeInfo, Skill, WorkExperience

# 中文字段 → 英文模型的映射，用于回退解析
CN_KEY_MAP = {
    "姓名": "name",
    "手机": "phone",
    "邮箱": "email",
    "期望职位": "expected_job_title",
    "个人简介": "summary",
    "技能": "skills",
    "工作经历": "work_experience",
    "项目经历": "projects",
    "教育背景": "education",  # 回退时可能需要特殊处理，这里简单映射
    "语言": "languages",
    "兴趣爱好": "hobbies",
    "期望薪资": "expected_salary",  # 回退时为字符串，后续需转换
    "期望工作地点": "location_preference",
}


def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    return "\n".join(page.get_text() for page in doc)


def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    return "\n".join(para.text for para in doc.paragraphs)


def parse_resume_rules_only(text: str) -> ResumeInfo:
    """Deterministic fallback for rules_only / CI without model keys."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    data = {
        "name": None,
        "email": None,
        "expected_job_title": None,
        "summary": None,
        "skills": [],
        "work_experience": [],
    }
    for line in lines:
        if line.startswith("姓名：") or line.startswith("姓名:"):
            data["name"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith("邮箱：") or line.startswith("邮箱:") or "@" in line:
            email_match = re.search(r"[\w.+-]+@[\w.-]+", line)
            if email_match:
                data["email"] = email_match.group(0)
        elif line.startswith("期望职位：") or line.startswith("期望职位:"):
            data["expected_job_title"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith("技能：") or line.startswith("技能:"):
            raw = line.split("：", 1)[-1].split(":", 1)[-1]
            data["skills"] = [
                Skill(name=part.strip()) for part in re.split(r"[,，、/|]", raw) if part.strip()
            ]
        elif line.startswith("工作经历：") or "工程师" in line:
            data["work_experience"].append(
                WorkExperience(
                    company="未命名公司",
                    position=data.get("expected_job_title") or "工程师",
                    duration_years=1.0,
                    description=line,
                )
            )
    if not data["summary"]:
        data["summary"] = "\n".join(lines[:8])
    return ResumeInfo(**data)


def parse_with_llm(text: str) -> ResumeInfo:
    if not model_api_key():
        return parse_resume_rules_only(text)

    client = get_openai_client()
    model = get_model()

    # 使用 tools + tool_choice 确保 function calling 生效
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_resume",
                "description": "提取简历的结构化信息，字段名必须为英文",
                "parameters": ResumeInfo.model_json_schema(),
            },
        }
    ]

    prompt = f"""请提取以下简历的结构化信息，严格按照要求的JSON Schema输出。
注意：所有字段名必须使用英文，缺失信息用null或空数组表示。
若简历有「项目经历」板块，请填入 projects 数组（每项含 name/role/duration/description），不要混入 work_experience。

简历内容：
{text}
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个专业的简历解析器，只输出符合Schema的JSON。"},
            {"role": "user", "content": prompt},
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_resume"}},
        temperature=0.1,
    )

    msg = response.choices[0].message

    # 方式1：正确触发了 tool_calls
    if msg.tool_calls:
        args_str = msg.tool_calls[0].function.arguments
        data = json.loads(args_str)
        return ResumeInfo(**data)

    # 方式2：未触发工具调用，但 content 中有 JSON（回退）
    if msg.content:
        # 尝试从 content 中提取 JSON
        json_match = re.search(r"\{.*\}", msg.content, re.DOTALL)
        if json_match:
            raw_json = json_match.group(0)
            try:
                data = json.loads(raw_json)
                # 将中文键转为英文
                converted = {}
                for k, v in data.items():
                    eng_key = CN_KEY_MAP.get(k, k)
                    converted[eng_key] = v
                # 对嵌套字段做简单适配
                if "work_experience" in converted and isinstance(
                    converted["work_experience"], list
                ):
                    new_work = []
                    for exp in converted["work_experience"]:
                        if isinstance(exp, dict):
                            # 中文工作经历键映射
                            exp_mapped = {}
                            for ek, ev in exp.items():
                                if ek == "公司":
                                    exp_mapped["company"] = ev
                                elif ek == "职位":
                                    exp_mapped["position"] = ev
                                elif ek == "时间段":
                                    exp_mapped["duration"] = ev  # 需要额外处理
                                elif ek == "工作内容":
                                    exp_mapped["description"] = (
                                        "\n".join(ev) if isinstance(ev, list) else ev
                                    )
                            new_work.append(exp_mapped)
                    converted["work_experience"] = new_work
                if "education" in converted and isinstance(converted["education"], list):
                    # 只取第一个学历作为字符串 summary
                    if converted["education"]:
                        edu = converted["education"][0]
                        if isinstance(edu, dict):
                            parts = [edu.get("学校", ""), edu.get("专业", ""), edu.get("学历", "")]
                            converted["education"] = " ".join(parts)
                        else:
                            converted["education"] = str(edu)
                if "skills" in converted and isinstance(converted["skills"], list):
                    # 转换为 {name, level} 列表
                    converted["skills"] = [
                        {"name": s, "level": "intermediate"} for s in converted["skills"]
                    ]
                return ResumeInfo(**converted)
            except Exception:
                pass  # 回退失败抛出原始错误

    raise ValueError("DeepSeek 未返回有效的 tool_calls 或 content JSON，原始响应：" + str(response))

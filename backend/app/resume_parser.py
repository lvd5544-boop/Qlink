import os
import json
import logging
import re
from typing import Any
import fitz
from docx import Document
from .llm_client import default_model_name, model_api_key, sync_chat_completion
from .models import ResumeInfo, Skill

logger = logging.getLogger(__name__)

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


def get_model():
    return default_model_name("resume_parse")


def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    return "\n".join(page.get_text() for page in doc)


def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    return "\n".join(para.text for para in doc.paragraphs)


_SECTION_PATTERNS = (
    (
        "projects",
        re.compile(
            r"^(?:selected |key |academic |personal )?"
            r"(?:projects?|project experience|项目经历|项目经验|代表项目)$",
            re.I,
        ),
    ),
    (
        "education",
        re.compile(
            r"^(?:education|education background|educational background|"
            r"academic background|academic qualifications|教育背景|教育经历|学历)$",
            re.I,
        ),
    ),
    (
        "skills",
        re.compile(
            r"^(?:(?:technical|core|key|professional) )?"
            r"(?:skills(?: and competencies)?|competencies|technologies|tech stack|"
            r"技能|专业技能|技术栈)$",
            re.I,
        ),
    ),
    (
        "work_experience",
        re.compile(
            r"^(?:work experience|professional experience|employment history|"
            r"career history|experience|employment|工作经历|工作经验|职业经历)$",
            re.I,
        ),
    ),
    (
        "summary",
        re.compile(
            r"^(?:professional summary|summary|profile|career objective|objective|"
            r"个人简介|个人总结|求职目标)$",
            re.I,
        ),
    ),
    (
        "other",
        re.compile(
            r"^(?:research|publications?|awards?|certifications?|activities|"
            r"leadership|languages?|interests?|references|研究经历|论文|发表|"
            r"获奖|证书|活动|语言|兴趣)$",
            re.I,
        ),
    ),
)

_DEGREE_PATTERN = re.compile(
    r"\b(?:ph\.?d|doctor(?:ate)?|master(?:'s)?|m\.?s\.?|mba|"
    r"bachelor(?:'s)?|b\.?s\.?|b\.?a\.?|associate(?:'s)?)\b|"
    r"博士|硕士|本科|学士|专科",
    re.I,
)
_SCHOOL_PATTERN = re.compile(
    r"\b(?:university|college|institute|academy|school)\b|大学|学院|院校",
    re.I,
)
_DATE_PATTERN = re.compile(
    r"(?:19|20)\d{2}(?:[./]\d{1,2}|-\d{1,2}(?!\d))?"
    r"(?:\s*(?:-|–|—|to|至)\s*(?:(?:19|20)\d{2}(?:[./]\d{1,2}|-\d{1,2}(?!\d))?|present|至今))?",
    re.I,
)
_CONTACT_HEADER_PATTERN = re.compile(
    r"(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"(?:mobile|phone|tel|电话|手机)\s*[:：+]?\s*[\d\s()+-]{7,}|"
    r"\b\d{1,6}\s+[A-Za-z][A-Za-z .'-]+\s+(?:Dr|Drive|St|Street|Rd|Road|Ave|Avenue)\b|"
    r"(?:educational background|education|教育背景))",
    re.I,
)


def _clean_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().strip(":：|")).lower()


def _has_explicit_summary_heading(text: str) -> bool:
    for raw_line in text.splitlines():
        heading = _clean_heading(raw_line)
        if any(
            key == "summary" and pattern.fullmatch(heading) for key, pattern in _SECTION_PATTERNS
        ):
            return True
    return False


def _looks_like_contact_header(summary: str | None, source_text: str) -> bool:
    """Reject identity/contact blocks accidentally returned as a profile.

    A provider may copy the first few resume lines into ``summary``.  We only
    clear it when there is no explicit summary section and the value contains
    several strong header signals, so an actual profile mentioning one date or
    location is preserved.
    """
    value = re.sub(r"\s+", " ", str(summary or "")).strip()
    if not value or _has_explicit_summary_heading(source_text):
        return False
    signals = len(_CONTACT_HEADER_PATTERN.findall(value))
    dates = len(_DATE_PATTERN.findall(value))
    header_terms = len(
        re.findall(
            r"\b(?:email|mobile|education(?:al background)?|address)\b|"
            r"邮箱|手机|电话|地址|教育背景",
            value,
            re.I,
        )
    )
    sentence_markers = len(re.findall(r"[。！？.!?](?:\s|$)", value))
    return (signals >= 2 and (dates >= 2 or header_terms >= 2)) or (
        signals >= 3 and sentence_markers <= 1
    )


def _is_numbered_marker(line: str) -> bool:
    return bool(re.fullmatch(r"[\[(（【]?\d{1,3}[\])）】.]?", line.strip()))


def _looks_like_generic_heading(line: str) -> bool:
    """Recognize compact standalone headings without learning resume-specific labels."""
    value = line.strip().strip(":：|")
    return bool(
        4 <= len(value) <= 30
        and len(value.split()) == 1
        and value.isalpha()
        and (value.istitle() or value.isupper())
    )


def _section_name(line: str) -> str | None:
    cleaned = _clean_heading(line)
    if len(cleaned) > 70 or len(cleaned.split()) > 8:
        return None
    if re.search(r"\b(?:skills?|competenc(?:y|ies)|technologies)\b", cleaned) and not re.search(
        r"[.;]", cleaned
    ):
        return "skills"
    for name, pattern in _SECTION_PATTERNS:
        if pattern.fullmatch(cleaned):
            return name
    return None


def _split_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    numbered_project_markers = 0
    previous_was_marker = False
    for line in lines:
        section = _section_name(line)
        inline_match = re.match(
            r"^\s*(工作经历|工作经验|work experience|experience|项目经历|项目经验|projects?)\s*[:：]\s*(.+?)\s*$",
            line,
            re.I,
        )
        inline_content = None
        if inline_match:
            label = inline_match.group(1).lower()
            section = (
                "projects"
                if ("项目" in label or label.startswith("project"))
                else "work_experience"
            )
            inline_content = inline_match.group(2).strip()
        marker = _is_numbered_marker(line)
        if (
            not section
            and current == "projects"
            and numbered_project_markers >= 2
            and not previous_was_marker
            and _looks_like_generic_heading(line)
        ):
            # Some PDF generators title-case section labels rather than using
            # conventional all-caps headings. Once multiple numbered projects
            # have been observed, a new standalone heading closes the section.
            section = "other"
        if section:
            current = section
            sections.setdefault(section, [])
            if inline_content:
                sections[section].append(inline_content)
        elif current:
            sections[current].append(line)
            if current == "projects" and marker:
                numbered_project_markers += 1
        else:
            preamble.append(line)
        previous_was_marker = marker
    return preamble, sections


def _explicit_value(line: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.match(rf"^\s*{re.escape(label)}\s*[:：]\s*(.+?)\s*$", line, re.I)
        if match:
            return match.group(1).strip()
    return None


def _looks_like_name(line: str) -> bool:
    value = line.strip()
    if not value or len(value) > 60 or re.search(r"[@\d]|https?://|www\.", value, re.I):
        return False
    if _section_name(value) or re.search(
        r"\b(?:email|phone|mobile|address|engineer|developer|manager|student|resume|cv)\b",
        value,
        re.I,
    ):
        return False
    if re.fullmatch(r"[\u4e00-\u9fff·]{2,8}", value):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", value)
    return 2 <= len(words) <= 5 and all(word[:1].isupper() for word in words)


def _project_groups(lines: list[str]) -> list[list[str]]:
    meaningful = [line.strip() for line in lines if len(line.strip()) > 1]
    if not meaningful:
        return []
    groups: list[list[str]] = []
    current: list[str] = []
    for line in meaningful:
        if _is_numbered_marker(line):
            if current:
                groups.append(current)
            current = []
            continue
        current.append(line)
    if current:
        groups.append(current)
    return groups or [meaningful]


def _project_from_lines(lines: list[str], index: int) -> dict[str, Any] | None:
    if not lines:
        return None
    first = lines[0].strip()
    name = first.split(":", 1)[0].strip()
    if len(name) > 100:
        name = " ".join(name.split()[:10]).strip(" ,.;:-")
    if not name:
        name = f"项目 {index + 1}"
    duration_match = next(
        (_DATE_PATTERN.search(line) for line in lines if _DATE_PATTERN.search(line)), None
    )
    return {
        "name": name,
        "duration": duration_match.group(0) if duration_match else None,
        "description": "\n".join(lines).strip(),
    }


def _work_from_lines(lines: list[str]) -> dict[str, Any] | None:
    if not lines:
        return None
    header = lines[0].strip()
    duration_match = _DATE_PATTERN.search(header)
    header_without_date = _DATE_PATTERN.sub("", header).strip(" ,.;，；|-")
    parts = header_without_date.split()
    company = parts[0] if parts else "未命名组织"
    position = " ".join(parts[1:]).strip() if len(parts) > 1 else "未填写职位"
    duration_years = 0.0
    if duration_match:
        years = [int(value) for value in re.findall(r"(?:19|20)\d{2}", duration_match.group(0))]
        if len(years) >= 2:
            duration_years = float(max(0, years[-1] - years[0]))
    description = "\n".join(lines[1:]).strip() or None
    return {
        "company": company,
        "position": position,
        "duration_years": duration_years,
        "description": description,
    }


def parse_resume_rules_only(text: str) -> ResumeInfo:
    """Deterministic fallback for rules_only / CI without model keys."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    preamble, sections = _split_sections(lines)
    data = {
        "name": None,
        "email": None,
        "phone": None,
        "expected_job_title": None,
        "summary": None,
        "skills": [],
        "work_experience": [],
        "projects": [],
        "education": None,
        "school": None,
        "degree": None,
    }
    for line in lines:
        explicit_name = _explicit_value(line, ("姓名", "name"))
        if explicit_name:
            data["name"] = explicit_name
        if not data["email"] and ("@" in line or _explicit_value(line, ("邮箱", "email"))):
            email_match = re.search(r"[\w.+-]+@[\w.-]+", line)
            if email_match:
                data["email"] = email_match.group(0)
        if not data["phone"]:
            phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", line)
            phone_digits = re.sub(r"\D", "", phone_match.group(0)) if phone_match else ""
            date_range = bool(
                phone_match
                and re.fullmatch(
                    r"\s*(?:19|20)\d{2}\s*[-–—至]\s*(?:(?:19|20)\d{2}|至今|present)\s*",
                    phone_match.group(0),
                    re.I,
                )
            )
            if phone_match and not date_range and 8 <= len(phone_digits) <= 15 and "@" not in line:
                data["phone"] = phone_match.group(0).strip()
        expected_title = _explicit_value(line, ("期望职位", "目标职位", "target role"))
        if expected_title:
            data["expected_job_title"] = expected_title
        raw_skills = _explicit_value(line, ("技能", "skills"))
        if raw_skills:
            data["skills"] = [
                Skill(name=part.strip())
                for part in re.split(r"[,，、/|]", raw_skills)
                if part.strip()
            ]

    if not data["name"]:
        data["name"] = next((line for line in preamble[:10] if _looks_like_name(line)), None)

    education_lines = [line for line in sections.get("education", []) if len(line.strip()) > 1]
    school_line = next((line for line in education_lines if _SCHOOL_PATTERN.search(line)), None)
    degree_line = next((line for line in education_lines if _DEGREE_PATTERN.search(line)), None)
    if school_line:
        data["school"] = school_line
    if degree_line:
        data["degree"] = degree_line
    education_parts = list(dict.fromkeys(part for part in (school_line, degree_line) if part))
    if not education_parts and education_lines:
        education_parts = education_lines[:3]
    if education_parts:
        data["education"] = " · ".join(education_parts)

    project_groups = _project_groups(sections.get("projects", []))
    data["projects"] = [
        project
        for index, group in enumerate(project_groups)
        if (project := _project_from_lines(group, index))
    ]

    work_groups = _project_groups(sections.get("work_experience", []))
    data["work_experience"] = [work for group in work_groups if (work := _work_from_lines(group))]

    if not data["skills"] and sections.get("skills"):
        candidates: list[str] = []
        for line in sections["skills"][:12]:
            candidates.extend(re.split(r"[,，、|;/•·]+", line))
        data["skills"] = [
            Skill(name=item.strip())
            for item in candidates
            if 1 < len(item.strip()) <= 60 and not _is_numbered_marker(item)
        ][:30]

    # A summary is semantic content, not the otherwise-unclassified resume
    # header.  Never manufacture it from name/contact/education preamble.
    summary_lines = sections.get("summary") or []
    data["summary"] = "\n".join(summary_lines[:8]).strip() or None
    return ResumeInfo(**data)


def enrich_resume_from_text(parsed: ResumeInfo | dict[str, Any], text: str) -> ResumeInfo:
    """Fill parser omissions from source text without overwriting extracted facts."""
    current = parsed if isinstance(parsed, ResumeInfo) else ResumeInfo.model_validate(parsed or {})
    fallback = parse_resume_rules_only(text)
    merged = current.model_dump()
    fallback_data = fallback.model_dump()
    for key in (
        "name",
        "email",
        "phone",
        "expected_job_title",
        "summary",
        "education",
        "school",
        "degree",
    ):
        if not merged.get(key) and fallback_data.get(key):
            merged[key] = fallback_data[key]
    for key in ("skills", "work_experience", "projects"):
        if not merged.get(key) and fallback_data.get(key):
            merged[key] = fallback_data[key]
    if _looks_like_contact_header(merged.get("summary"), text):
        logger.info("Discarded resume header mistakenly extracted as summary")
        merged["summary"] = None
    return ResumeInfo.model_validate(merged)


def _parse_with_provider(text: str) -> ResumeInfo:
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
summary 只能来自明确的 Professional Summary/Profile/个人简介段落；姓名、联系方式、地址、
教育背景和日期属于基本信息，不得拼接成 summary。没有简介段落时 summary 必须为 null。
若简历有「项目经历」板块，请填入 projects 数组（每项含 name/role/duration/description），不要混入 work_experience。
姓名必须填入 name；院校必须填入 school；学位填入 degree；education 仅作为教育背景摘要。
英文简历中的 EDUCATION、PROJECTS、EXPERIENCE、SKILLS 等栏目同样必须完整提取。

简历内容：
{text}
"""
    response = sync_chat_completion(
        messages=[
            {"role": "system", "content": "你是一个专业的简历解析器，只输出符合Schema的JSON。"},
            {"role": "user", "content": prompt},
        ],
        model=model,
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_resume"}},
        temperature=0.1,
        task="resume_parse",
    )

    msg = response.choices[0].message

    # 方式1：正确触发了 tool_calls
    if msg.tool_calls:
        args_str = msg.tool_calls[0].function.arguments
        data = json.loads(args_str)
        return enrich_resume_from_text(ResumeInfo(**data), text)

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
                return enrich_resume_from_text(ResumeInfo(**converted), text)
            except Exception:
                pass  # 回退失败抛出原始错误

    raise ValueError("DeepSeek 未返回有效的 tool_calls 或 content JSON，原始响应：" + str(response))


def parse_with_llm(text: str) -> ResumeInfo:
    """Parse with the provider, falling back to rules when AI is optional."""
    if not model_api_key():
        return parse_resume_rules_only(text)
    try:
        return enrich_resume_from_text(_parse_with_provider(text), text)
    except Exception as exc:
        model_required = os.getenv("MODEL_REQUIRED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if model_required:
            raise
        logger.warning(
            "Resume provider parsing failed; using rules-only fallback: %s",
            type(exc).__name__,
        )
        return parse_resume_rules_only(text)

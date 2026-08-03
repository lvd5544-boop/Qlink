from __future__ import annotations

import pytest

from app import resume_parser


ENGLISH_SECTIONED_RESUME = """
Jordan Example
+86 138 0000 0000 | Shanghai
jordan@example.com

EDUCATION BACKGROUND
2019 - 2023
Example University
Bachelor of Science in Computer Science

PROJECTS
（1）
AI Job Platform: 2025.01 - 2025.07
Built a FastAPI service and PostgreSQL data model.
Added deterministic resume parsing and regression tests.
（2）
Search Quality Lab: 2024.03 - 2024.08
Implemented evaluation datasets and ranking diagnostics.

RESEARCH
（1）
This publication section must not be merged into project descriptions.

TECHNICAL SKILLS AND COMPETENCIES
Python, FastAPI, PostgreSQL, React
"""

GENERIC_BOUNDARY_RESUME = """
Taylor Example

PROJECTS
(1)
First Project
Built the first project.
(2)
Second Project
Built the second project.

Teaching
(1)
This numbered teaching item is not a project.

Core Skill Development
(1)
Python, SQL

Awards
Example award
"""


def test_rules_parser_extracts_english_identity_education_projects_and_skills():
    parsed = resume_parser.parse_resume_rules_only(ENGLISH_SECTIONED_RESUME)

    assert parsed.name == "Jordan Example"
    assert "Example University" in (parsed.school or "")
    assert "Bachelor" in (parsed.degree or "")
    assert len(parsed.projects) == 2
    assert parsed.projects[0].name == "AI Job Platform"
    assert "FastAPI" in (parsed.projects[0].description or "")
    assert "publication section" not in (parsed.projects[-1].description or "")
    assert {skill.name for skill in parsed.skills} >= {
        "Python",
        "FastAPI",
        "PostgreSQL",
        "React",
    }


def test_enrichment_preserves_existing_parser_values_and_fills_omissions():
    enriched = resume_parser.enrich_resume_from_text(
        {
            "name": "Provider Name",
            "email": "provider@example.com",
            "projects": [],
            "skills": [],
        },
        ENGLISH_SECTIONED_RESUME,
    )

    assert enriched.name == "Provider Name"
    assert enriched.email == "provider@example.com"
    assert len(enriched.projects) == 2
    assert "Example University" in (enriched.school or "")


def test_numbered_projects_stop_at_generic_heading_and_skill_markers_are_ignored():
    parsed = resume_parser.parse_resume_rules_only(GENERIC_BOUNDARY_RESUME)

    assert [project.name for project in parsed.projects] == [
        "First Project",
        "Second Project",
    ]
    assert {skill.name for skill in parsed.skills} == {"Python", "SQL"}


def test_resume_parser_uses_rules_when_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr(resume_parser, "model_api_key", lambda: "configured-key")
    monkeypatch.setattr(
        resume_parser,
        "_parse_with_provider",
        lambda _text: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    monkeypatch.delenv("MODEL_REQUIRED", raising=False)

    parsed = resume_parser.parse_with_llm(
        "姓名：验收用户\n邮箱：acceptance@example.com\n期望职位：后端工程师"
    )

    assert parsed.name == "验收用户"
    assert parsed.email == "acceptance@example.com"
    assert parsed.expected_job_title == "后端工程师"


def test_resume_parser_surfaces_provider_failure_when_model_is_required(monkeypatch):
    monkeypatch.setattr(resume_parser, "model_api_key", lambda: "configured-key")
    monkeypatch.setattr(
        resume_parser,
        "_parse_with_provider",
        lambda _text: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    monkeypatch.setenv("MODEL_REQUIRED", "true")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        resume_parser.parse_with_llm("resume")


def test_inline_work_heading_is_parsed_and_date_range_is_not_a_phone():
    parsed = resume_parser.parse_resume_rules_only(
        "\n".join(
            [
                "姓名：E2E候选人",
                "邮箱：candidate@example.com",
                "期望职位：后端工程师",
                "技能：Python, FastAPI, PostgreSQL",
                "工作经历：某科技 后端工程师 2022-2025",
                "负责招聘平台 API 与匹配服务，日请求 10 万+",
            ]
        )
    )

    assert parsed.phone is None
    assert len(parsed.work_experience) == 1
    assert parsed.work_experience[0].company == "某科技"
    assert parsed.work_experience[0].position == "后端工程师"
    assert "日请求 10 万" in (parsed.work_experience[0].description or "")


def test_contact_and_education_header_is_not_used_as_personal_summary():
    source = """
Lin Deng
3119 Nittany Dr, Rm 417, Altoona, PA 16601
Email lvd5544@psu.edu Mobile +1 814 329 8517
Educational Background
Aug 2025 - Now
Sep 2022 - Jun 2025

PROJECTS
Air Quality Forecasting
Compared forecasting models using R² and MSE.
"""
    parsed = resume_parser.parse_resume_rules_only(source)

    assert parsed.name == "Lin Deng"
    assert parsed.email == "lvd5544@psu.edu"
    assert parsed.summary is None


def test_provider_contact_header_summary_is_sanitized():
    source = """
Lin Deng
3119 Nittany Dr, Altoona, PA 16601
Email lvd5544@psu.edu Mobile +1 814 329 8517
Educational Background
Aug 2025 - Now
Sep 2022 - Jun 2025
"""
    enriched = resume_parser.enrich_resume_from_text(
        {
            "name": "Lin Deng",
            "summary": (
                "Lin Deng 3119 Nittany Dr, Altoona, PA 16601 "
                "Email lvd5544@psu.edu Mobile +1 814 329 8517 "
                "Educational Background Aug 2025 - Now Sep 2022 - Jun 2025"
            ),
        },
        source,
    )

    assert enriched.summary is None


def test_explicit_professional_summary_is_retained():
    source = """
Lin Deng
lin@example.com

PROFESSIONAL SUMMARY
Data scientist who builds forecasting systems and explains model trade-offs.

SKILLS
Python, SQL
"""
    parsed = resume_parser.parse_resume_rules_only(source)

    assert parsed.summary == (
        "Data scientist who builds forecasting systems and explains model trade-offs."
    )

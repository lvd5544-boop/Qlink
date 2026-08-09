from app.personalized_guidance import (
    build_interview_action_plan,
    build_job_guidance,
)


def test_interview_plan_is_anchored_to_candidate_project_and_target_skill():
    resume = {
        "name": "Lin",
        "skills": ["Python", "SQL"],
        "projects": [
            {
                "name": "PM2.5 Forecasting",
                "description": "Built random forest models for air-quality forecasting.",
            }
        ],
    }
    job = {"title": "Data Scientist", "required_skills": ["Python", "Statistics"]}

    result = build_interview_action_plan(
        gap_types=["result", "metric", "reflection"],
        resume_json=resume,
        job_json=job,
        job_title="Data Scientist",
        answer_corpus="I built and tuned several models.",
        recurring_gap_types=["metric"],
    )

    assert result["personalization_basis"]["anchor_experience"] == "PM2.5 Forecasting"
    assert result["personalization_basis"]["target_skill"] == "Python"
    assert "PM2.5 Forecasting" in result["north_star"]
    assert any("连续面试" in item["why"] for item in result["actions"])
    assert all(item["steps"] and item["success_criteria"] for item in result["actions"])


def test_job_guidance_prioritizes_real_anchor_instead_of_generic_rewrite():
    result = build_job_guidance(
        resume_json={
            "projects": [{"name": "Monopoly", "description": "Python and Pygame project"}],
        },
        job_json={"title": "Software Engineer", "required_skills": ["Python"]},
        job_title="Software Engineer",
        issues=[
            {
                "diagnosis": "岗位相关性较弱",
                "claim_ids": ["claim-1"],
                "strategies": [
                    {
                        "title": "突出已有 Python 任务",
                        "recommended": True,
                        "next_action": "preview_rewrite",
                    }
                ],
            }
        ],
    )

    assert result["anchor_experience"] == "Monopoly"
    assert result["actions"][0]["start_from"] == "Monopoly"
    assert "未经用户提供的事实" in result["actions"][0]["success_criteria"][1]


def test_job_guidance_uses_distinct_reason_steps_and_success_criteria():
    result = build_job_guidance(
        resume_json={
            "projects": [{"name": "Monopoly", "description": "Python game project"}],
        },
        job_json={"title": "Product Analyst", "required_skills": ["Experimentation"]},
        job_title="Product Analyst",
        issues=[
            {
                "diagnosis": "影响力证据不足",
                "target_requirement_id": "impact",
                "strategies": [
                    {
                        "strategy": "method_and_tradeoff",
                        "title": "补充方法与权衡",
                        "recommended": True,
                    }
                ],
            },
            {
                "diagnosis": "相关性较弱",
                "target_requirement_id": "experimentation",
                "strategies": [
                    {
                        "strategy": "relevance_alignment",
                        "title": "突出相关任务",
                        "recommended": True,
                    }
                ],
            },
            {
                "diagnosis": "转向叙事不足",
                "target_requirement_id": "career_transition",
                "strategies": [
                    {"strategy": "career_narrative", "title": "说明转向路径", "recommended": True}
                ],
            },
        ],
    )

    actions = result["actions"]
    assert len({item["why_for_you"] for item in actions}) == 3
    assert len({item["first_step"] for item in actions}) == 3
    assert len({tuple(item["success_criteria"]) for item in actions}) == 3


def test_interview_answer_anchor_wins_over_unrelated_long_resume_project():
    result = build_interview_action_plan(
        gap_types=["result"],
        resume_json={
            "projects": [
                {
                    "name": "Monopoly",
                    "description": "A very long unrelated game project description " * 8,
                }
            ],
        },
        job_json={"required_skills": ["research"]},
        job_title="Data Labeling Specialist",
        answer_corpus="我在SJTU的志远学院实习帮助学姐完成项目，具体负责跑实验和调参数。",
    )

    assert result["personalization_basis"]["anchor_experience"] == "SJTU的志远学院实习"
    assert "Monopoly" not in result["north_star"]

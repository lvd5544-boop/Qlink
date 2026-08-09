from app.resume_coach import build_rule_based_rewrite_suggestions


def test_rule_fallback_returns_faithful_before_after_examples():
    resume = {
        "summary": "后端工程师",
        "work_experience": [{"company": "示例公司", "description": "负责订单系统开发与性能优化"}],
    }

    suggestions = build_rule_based_rewrite_suggestions(resume)

    assert len(suggestions) == 2
    assert suggestions[0]["example_before"] == "后端工程师"
    assert suggestions[0]["example_after"] == "主要工作包括：后端工程师。"
    assert suggestions[1]["example_before"] == "负责订单系统开发与性能优化"
    assert suggestions[1]["example_after"] == "负责订单系统开发与性能优化。"
    rendered = str(suggestions)
    assert "Kubernetes" not in rendered
    assert not any(
        char.isdigit() for suggestion in suggestions for char in suggestion["example_after"]
    )


def test_rule_fallback_does_not_invent_content_for_empty_resume():
    assert build_rule_based_rewrite_suggestions({}) == []

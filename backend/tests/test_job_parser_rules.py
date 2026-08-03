from app.job_parser import parse_job_rules_only


def test_rules_parser_keeps_explicit_hard_requirement_and_experience():
    parsed = parse_job_rules_only(
        """岗位：数据平台工程师
职责：建设实时数据平台 API
必须要求：具备合法工作许可
技能：Python、SQL、PostgreSQL
经验：3 年数据平台经验
地点：上海
"""
    )

    assert parsed.title == "数据平台工程师"
    assert parsed.responsibilities == ["建设实时数据平台 API"]
    assert parsed.requirements == "具备合法工作许可"
    assert parsed.experience_years == 3
    assert parsed.location == "上海"

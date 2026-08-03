import pytest

from app.market_analytics import build_role_market_fallback


@pytest.mark.asyncio
async def test_role_market_fallback_aggregates_cross_company_open_jds(
    db_session,
    job_a,
    job_b,
):
    fallback = await build_role_market_fallback(db_session, "engineering")

    assert fallback is not None
    assert fallback["scope"] == "role_market_open_jd"
    assert fallback["jd_sample_size"] == 2
    assert fallback["skill_freq"]["python"] == 2
    assert "不代表所选公司的招聘偏好" in fallback["caveat"]

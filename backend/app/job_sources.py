"""岗位数据来源标签与筛选"""

EMPLOYER_FOREIGN = "foreign"
EMPLOYER_GUOQI = "guoqi"
EMPLOYER_SYSTEM_LEGACY = "system"


def job_source_label(employer_id: str, parsed: dict | None = None) -> str:
    parsed = parsed or {}
    if employer_id == EMPLOYER_GUOQI:
        return "国企"
    if employer_id in (EMPLOYER_FOREIGN, EMPLOYER_SYSTEM_LEGACY):
        return "外企"
    if parsed.get("company_type") == "soe":
        return "国企"
    if parsed.get("company_type") == "foreign":
        return "外企"
    return "企业发布"


def job_source_type(employer_id: str, parsed: dict | None = None) -> str:
    """soe | foreign | employer"""
    label = job_source_label(employer_id, parsed)
    if label == "国企":
        return "soe"
    if label == "外企":
        return "foreign"
    return "employer"

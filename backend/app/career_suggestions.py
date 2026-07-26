"""
岗位定向职业建议 — 根据目标岗位 gap 生成可执行的经历/项目建议。

设计原则：
  - 由评分系统「诊断并生成」建议（career_suggestions）
  - 由简历工作台「展示并采纳」建议（resume_coach / MyResumes）
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from .company_registry import infer_role_family, normalize_skill_name

# 岗位类型 → 经历建议模板
EXPERIENCE_TEMPLATES: Dict[str, List[dict]] = {
    "quant": [
        {
            "type": "internship",
            "title": "量化研究/开发实习",
            "company_examples": ["头部券商量化部", "私募/对冲基金", "Prop Trading 公司"],
            "position_examples": ["Quant Research Intern", "Quant Developer Intern"],
            "why": "量化岗看重实盘或回测经验，实习是最快补齐行业信号的方式",
            "estimated_score_gain": 1.2,
        },
        {
            "type": "role",
            "title": "量化策略研究助理",
            "company_examples": ["金融工程实验室", "校内量化社团合作企业"],
            "position_examples": ["Research Assistant", "策略研究助理"],
            "why": "体现因子研究、策略验证能力",
            "estimated_score_gain": 0.8,
        },
    ],
    "engineering": [
        {
            "type": "internship",
            "title": "后端/全栈开发实习",
            "company_examples": ["互联网大厂", "B 轮以上 SaaS 公司"],
            "position_examples": ["Backend Intern", "Software Engineer Intern"],
            "why": "补充工程化与线上系统经验",
            "estimated_score_gain": 1.0,
        },
    ],
    "data": [
        {
            "type": "internship",
            "title": "数据分析/数据工程实习",
            "company_examples": ["电商", "金融科技", "咨询公司"],
            "position_examples": ["Data Analyst Intern", "Analytics Intern"],
            "why": "数据分析岗需要业务场景下的 SQL/指标体系实践",
            "estimated_score_gain": 1.0,
        },
    ],
    "ai": [
        {
            "type": "internship",
            "title": "机器学习/AI 应用实习",
            "company_examples": ["AI 应用公司", "大厂 AI Lab"],
            "position_examples": ["ML Engineer Intern", "Applied Scientist Intern"],
            "why": "LLM/算法岗需要真实模型落地案例",
            "estimated_score_gain": 1.2,
        },
    ],
}

# 岗位类型 → 项目建议模板
PROJECT_TEMPLATES: Dict[str, List[dict]] = {
    "quant": [
        {
            "type": "project",
            "title": "量化回测与交易系统",
            "description": "设计并实现一个完整的量化策略回测框架：数据清洗 → 因子计算 → 信号生成 → 回测 → 绩效分析（Sharpe、最大回撤）",
            "skills_gained": ["python", "pandas", "numpy", "backtest", "统计"],
            "deliverable": "GitHub 仓库 + 回测报告（含至少 3 个因子对比）",
            "why": "Quant 岗最看重「能否把策略想法变成可验证的系统」",
            "estimated_score_gain": 1.5,
        },
        {
            "type": "project",
            "title": "高频/中频行情数据处理管道",
            "description": "搭建 tick 级或分钟级行情 ingestion + 特征工程 pipeline，支持实时与批量模式",
            "skills_gained": ["python", "c++", "kafka", "redis"],
            "deliverable": "可运行的数据管道 + 延迟/吞吐 benchmark",
            "why": "体现工程化能力，区别于纯学术背景",
            "estimated_score_gain": 1.2,
        },
    ],
    "engineering": [
        {
            "type": "project",
            "title": "微服务电商/订单系统",
            "description": "Spring Boot / Go 实现订单-库存-支付拆分，接入 Redis 缓存与 Kafka 消息队列",
            "skills_gained": ["java", "spring", "redis", "kafka", "docker"],
            "deliverable": "可部署 Demo + 架构文档",
            "why": "后端岗需要分布式系统实践",
            "estimated_score_gain": 1.0,
        },
    ],
    "ai": [
        {
            "type": "project",
            "title": "RAG 知识库问答系统",
            "description": "基于 LangChain/LlamaIndex 构建文档 ingestion + 向量检索 + LLM 回答，含评测集",
            "skills_gained": ["python", "llm", "rag", "embedding"],
            "deliverable": "可交互 Demo + 准确率评测报告",
            "why": "AI 应用岗需要端到端 LLM 落地案例",
            "estimated_score_gain": 1.3,
        },
    ],
    "data": [
        {
            "type": "project",
            "title": "业务指标体系与看板",
            "description": "从原始日志构建 DAU/留存/转化漏斗，SQL + dbt + 可视化看板",
            "skills_gained": ["sql", "python", "dbt", "tableau"],
            "deliverable": "SQL 脚本 + 看板截图 + 分析结论",
            "why": "数据岗需要「从数据到业务洞察」的完整链路",
            "estimated_score_gain": 1.0,
        },
    ],
}

# 缺失技能 → 定向小项目
SKILL_PROJECT_MAP: Dict[str, dict] = {
    "redis": {
        "title": "Redis 缓存优化实战",
        "description": "在现有项目中引入 Redis 缓存热点数据，对比优化前后 QPS 与 P99 延迟",
        "estimated_score_gain": 0.5,
    },
    "docker": {
        "title": "Docker 容器化部署",
        "description": "将项目 Docker 化并编写 docker-compose，实现一键本地/云部署",
        "estimated_score_gain": 0.4,
    },
    "kubernetes": {
        "title": "K8s 集群部署练习",
        "description": "在 minikube/k3s 上部署微服务，配置 HPA 与 Service",
        "estimated_score_gain": 0.6,
    },
    "aws": {
        "title": "AWS 云原生小项目",
        "description": "使用 S3 + Lambda + RDS 搭建 serverless 数据处理流水线",
        "estimated_score_gain": 0.5,
    },
}


def _detect_role_key(job_title: str, job_json: dict) -> str:
    blob = f"{job_title} {job_json.get('title') or ''}".lower()
    if any(k in blob for k in ("quant", "量化", "trading", "交易员")):
        return "quant"
    if any(k in blob for k in ("ai", "llm", "nlp", "机器学习", "算法工程师")):
        return "ai"
    if any(k in blob for k in ("数据", "data analyst", "分析师")):
        return "data"
    family = infer_role_family(job_title or job_json.get("title") or "")
    if family == "data":
        return "data"
    return "engineering"


def _resume_skill_set(resume_json: dict) -> Set[str]:
    skills: Set[str] = set()
    for s in resume_json.get("skills") or []:
        if isinstance(s, dict):
            skills.add(normalize_skill_name(s.get("name", "")))
        else:
            skills.add(normalize_skill_name(str(s)))
    return {s for s in skills if s}


def generate_career_suggestions(
    resume_json: dict,
    job_json: dict,
    job_title: str = "",
    missing_skills: Optional[List[str]] = None,
    impact_weak: bool = False,
    industry_mismatch: bool = False,
    max_items: int = 6,
) -> dict:
    """
    生成岗位定向提升建议。

    Returns:
        {
          "role_key": "quant",
          "experience_suggestions": [...],
          "project_suggestions": [...],
          "skill_projects": [...],
          "summary": "..."
        }
    """
    role_key = _detect_role_key(job_title, job_json)
    missing = missing_skills or []
    known = _resume_skill_set(resume_json)

    experience: List[dict] = list(
        EXPERIENCE_TEMPLATES.get(role_key, EXPERIENCE_TEMPLATES["engineering"])
    )
    projects: List[dict] = list(PROJECT_TEMPLATES.get(role_key, PROJECT_TEMPLATES["engineering"]))

    # 行业不匹配时优先建议相关行业实习
    if industry_mismatch and role_key == "quant":
        experience.insert(
            0,
            {
                "type": "internship",
                "title": "金融机构科技/量化实习",
                "company_examples": ["券商 IT 部", "银行金融科技中心", "合规量化团队"],
                "position_examples": ["FinTech Intern"],
                "why": "从游戏/互联网转向 Quant 需要金融行业经历背书",
                "estimated_score_gain": 1.5,
                "priority": "high",
            },
        )

    # 影响力弱 → 建议量化现有项目
    if impact_weak:
        projects.insert(
            0,
            {
                "type": "project",
                "title": "量化改造现有项目描述",
                "description": "为已有项目补充 metrics：性能提升 %、用户量、成本节省、错误率下降等",
                "skills_gained": ["impact storytelling"],
                "deliverable": "改写后的 bullet points（每条含数字）",
                "why": "大厂招聘非常看重可量化的项目影响力",
                "estimated_score_gain": 0.8,
                "priority": "high",
            },
        )

    # 按缺失技能补充小项目
    skill_projects: List[dict] = []
    for sk in missing[:4]:
        tmpl = SKILL_PROJECT_MAP.get(sk)
        if tmpl and sk not in known:
            skill_projects.append({"skill": sk, **tmpl})

    # 截断
    experience = experience[:3]
    projects = projects[:3]
    skill_projects = skill_projects[:3]

    total_gain = sum(
        s.get("estimated_score_gain", 0) for s in experience + projects + skill_projects
    )

    role_labels = {
        "quant": "量化",
        "ai": "AI/算法",
        "data": "数据分析",
        "engineering": "工程开发",
    }
    summary = (
        f"针对【{role_labels.get(role_key, role_key)}】岗位，"
        f"建议补充 {len(experience)} 项经历方向、{len(projects)} 个代表性项目"
    )
    if missing:
        summary += f"，优先补齐：{', '.join(missing[:3])}"
    summary += f"。预计可提升约 {round(total_gain, 1)} 分（规则估算）。"

    return {
        "role_key": role_key,
        "experience_suggestions": experience,
        "project_suggestions": projects,
        "skill_projects": skill_projects,
        "estimated_total_gain": round(total_gain, 1),
        "summary": summary,
    }

"""商业化初稿：状态机、忠实改写与 claim 线程单测。"""

from __future__ import annotations

import os
import sys

import pytest

# 保证可从 backend 根目录导入 app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _FakeApp:
    def __init__(self, status="needs_clarification", pipeline_meta=None):
        self.status = status
        self.pipeline_meta = pipeline_meta or {}


def test_append_quantification_rejects_template_injection():
    from app.resume_suggestions import _append_quantification_text, apply_suggestion_patch

    with pytest.raises(ValueError, match="真实数据"):
        _append_quantification_text("做过优化", 0, None)

    with pytest.raises(ValueError, match="真实数据"):
        apply_suggestion_patch(
            {"work_experience": [{"company": "A", "description": "做过优化"}]},
            {"action": "append_quantification", "section": "work_experience", "index": 0},
        )

    out = apply_suggestion_patch(
        {"work_experience": [{"company": "A", "description": "做过优化"}]},
        {
            "action": "append_quantification",
            "section": "work_experience",
            "index": 0,
            "value": "将接口 P99 从 200ms 降到 120ms",
        },
    )
    assert "120ms" in out["work_experience"][0]["description"]
    assert "约 30%" not in out["work_experience"][0]["description"]


def test_strict_mode_forces_conservative_rewrite(monkeypatch):
    monkeypatch.setenv("EVIDENCE_FOLLOWUP_STRICT", "true")
    from app.evidence_followup import regenerate_evidence_sentence

    context = {
        "entry_type": "work",
        "section": "work_experience",
        "index": 0,
        "field_path": "work_experience[0].description",
        "name": "示例公司",
        "role": "工程师",
        "description": "负责订单模块",
        "needs_followup": True,
    }
    result = regenerate_evidence_sentence(
        context,
        [{"id": "r1", "question": "结果？", "answer": "QPS 提升到 2千"}],
        rewrite_mode="assertive",
    )
    assert result["rewrite_mode"] == "conservative"
    assert result["strict_mode"] is True
    assert "负责订单模块" in result["example_after"]
    assert "2千" in result["example_after"]


def test_match_saved_records_prefers_claim_id(monkeypatch):
    monkeypatch.setenv("EVIDENCE_FOLLOWUP_STRICT", "true")
    from app.evidence_followup import match_clarification_answers

    resume = {
        "clarification_answers": [
            {
                "claim_id": "work_experience_0_action_0",
                "claim_text": "负责重构",
                "answer": "将核心接口延迟降低 35%",
            },
            {
                "claim_id": "work_experience_1_action_0",
                "claim_text": "别的经历",
                "answer": "不相关答案",
            },
        ]
    }
    context = {
        "section": "work_experience",
        "index": 0,
        "entry_type": "work",
        "name": "公司A",
        "role": "工程师",
        "description": "负责重构",
        "claim_id": "work_experience_0_action_0",
    }
    matched = match_clarification_answers(resume, context)
    assert matched
    assert matched[0]["match_type"] == "claim_id"
    assert "35%" in matched[0]["answer"]


def test_claim_thread_status_machine():
    from app.claim_threads import (
        answer_claim_thread,
        open_claim_thread,
        recompute_clarification_status,
        open_claim_count,
    )

    app = _FakeApp()
    open_claim_thread(
        app,
        claim_id="c1",
        claim_text="主张1",
        request_message_id="m1",
        questions=["问1"],
    )
    open_claim_thread(
        app,
        claim_id="c2",
        claim_text="主张2",
        request_message_id="m2",
        questions=["问2"],
    )
    assert open_claim_count(app) == 2
    assert recompute_clarification_status(app) == "needs_clarification"

    answer_claim_thread(
        app,
        claim_id="c1",
        claim_text="主张1",
        response_message_id="r1",
        request_message_id="m1",
    )
    assert open_claim_count(app) == 1
    assert recompute_clarification_status(app) == "needs_clarification"

    answer_claim_thread(
        app,
        claim_id="c2",
        claim_text="主张2",
        response_message_id="r2",
        request_message_id="m2",
    )
    assert open_claim_count(app) == 0
    assert recompute_clarification_status(app) == "clarified"


def test_fidelity_detects_fabricated_segment():
    from app.evidence_followup import _fidelity_violated

    source = "负责订单模块重构 用户补充了缓存优化"
    generated = "负责订单模块重构；引入量子计算将成本降低八成并开辟海外市场"
    assert _fidelity_violated(source, generated) is True

    faithful = "负责订单模块重构；用户补充了缓存优化"
    assert _fidelity_violated(source, faithful) is False


def test_actionable_suggestions_require_evidence():
    from app.resume_suggestions import build_actionable_suggestions

    parsed = {
        "work_experience": [
            {"company": "Acme", "description": "负责开发"},
        ]
    }
    health = {
        "completeness": {"missing": []},
        "quantification": {
            "unquantified_entries": [
                {"id": "work_0", "entry_type": "work", "index": 0},
            ],
            "details": [{"id": "work_0", "company": "Acme", "entry_type": "work", "index": 0}],
        },
    }
    actions = build_actionable_suggestions(parsed, health)
    quant = [a for a in actions if a.get("requires_evidence")]
    assert quant
    assert quant[0]["needs_followup"] is True
    assert quant[0]["patch"].get("value") is None

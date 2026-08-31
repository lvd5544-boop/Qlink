"""Evidence-constrained resume writing style tests."""

from __future__ import annotations

from app.evidence_followup import assess_fidelity, regenerate_evidence_sentence
from app.resume_writing_style import compose_evidence_forward, serialize_style


def _not_empty(value: str) -> bool:
    return not value.strip()


def test_evidence_forward_orders_action_task_context_result_without_invention():
    context = {"description": "订单系统相关工作"}
    answers = [
        {"id": "result", "question": "结果是什么？", "answer": "接口 P99 降低 35%"},
        {"id": "scope", "question": "工作规模？", "answer": "服务日均 5 万订单"},
        {"id": "action", "question": "采取了什么动作？", "answer": "使用 Redis 重构缓存逻辑"},
    ]

    actual = compose_evidence_forward(context, answers, is_empty_answer=_not_empty)

    assert actual == (
        "使用 Redis 重构缓存逻辑；订单系统相关工作；"
        "服务日均 5 万订单；接口 P99 降低 35%"
    )
    source = "订单系统相关工作\n使用 Redis 重构缓存逻辑\n服务日均 5 万订单\n接口 P99 降低 35%"
    assert assess_fidelity(source, actual)["violated"] is False


def test_evidence_forward_keeps_existing_action_led_source_first():
    actual = compose_evidence_forward(
        {"description": "开发订单查询接口"},
        [{"id": "result", "question": "结果？", "answer": "响应时间降低 20%"}],
        is_empty_answer=_not_empty,
    )

    assert actual == "开发订单查询接口；响应时间降低 20%"


def test_strict_regeneration_returns_versioned_style_and_exact_sources(monkeypatch):
    monkeypatch.setenv("EVIDENCE_FOLLOWUP_STRICT", "true")
    context = {
        "entry_type": "work",
        "section": "work_experience",
        "index": 0,
        "field_path": "work_experience[0].description",
        "name": "示例公司",
        "role": "工程师",
        "description": "订单系统相关工作",
    }
    answers = [
        {"id": "action", "question": "采取了什么动作？", "answer": "协助重构缓存逻辑"},
        {"id": "result", "question": "结果是什么？", "answer": "接口 P99 降低 35%"},
    ]

    result = regenerate_evidence_sentence(
        context,
        answers,
        rewrite_mode="assertive",
        style_template="unknown-style",
    )

    assert result["rewrite_mode"] == "conservative"
    assert result["style_template"] == "evidence_forward"
    assert result["style_version"] == "evidence_forward_v1"
    assert result["example_after"] == "协助重构缓存逻辑；订单系统相关工作；接口 P99 降低 35%"
    assert "主导" not in result["example_after"]
    assert result["fidelity_result"]["violated"] is False


def test_style_metadata_describes_evidence_boundary():
    style = serialize_style("evidence_forward")

    assert style["style_label"] == "证据优先·招聘方易读"
    assert "仅使用已有证据" in style["sentence_pattern"]

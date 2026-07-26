"""申请维度的 claim 级澄清线程状态机。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_pipeline_meta(application) -> dict:
    meta = getattr(application, "pipeline_meta", None) or {}
    if not isinstance(meta, dict):
        return {}
    return dict(meta)


def set_pipeline_meta(application, meta: dict) -> None:
    application.pipeline_meta = meta


def get_claim_threads(application) -> Dict[str, dict]:
    meta = get_pipeline_meta(application)
    threads = meta.get("claim_threads") or {}
    return dict(threads) if isinstance(threads, dict) else {}


def _thread_key(claim_id: Optional[str], claim_text: Optional[str] = None) -> str:
    if claim_id and str(claim_id).strip():
        return str(claim_id).strip()
    text = (claim_text or "").strip()
    if text:
        return f"text:{text[:80]}"
    return f"anon:{_now()}"


def open_claim_thread(
    application,
    *,
    claim_id: Optional[str],
    claim_text: str,
    request_message_id: str,
    questions: Optional[List[str]] = None,
) -> dict:
    """打开或刷新一条 claim 澄清线程。"""
    meta = get_pipeline_meta(application)
    threads = dict(meta.get("claim_threads") or {})
    base_key = _thread_key(claim_id, claim_text)
    key = base_key
    if key in threads:
        round_number = 2
        while f"{base_key}#r{round_number}" in threads:
            round_number += 1
        key = f"{base_key}#r{round_number}"
    threads[key] = {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "status": "open",
        "request_message_id": request_message_id,
        "response_message_id": None,
        "questions": [q for q in (questions or []) if q],
        "opened_at": _now(),
        "answered_at": None,
        "reviewed_at": None,
        "round": 1 if key == base_key else int(key.rsplit("#r", 1)[1]),
    }
    meta["claim_threads"] = threads
    meta["last_employer_activity_at"] = _now()
    set_pipeline_meta(application, meta)
    return threads[key]


def answer_claim_thread(
    application,
    *,
    claim_id: Optional[str],
    claim_text: Optional[str],
    response_message_id: str,
    request_message_id: Optional[str] = None,
    allow_single_open_fallback: bool = True,
) -> Optional[dict]:
    """
    标记对应 claim 线程为已回答；返回被更新的线程。

    多条 open 线程时必须提供可解析的 claim_id（或精确匹配的 request_message_id），
    不得默认关闭「最新一条」。仅当恰好一条 open 且允许兼容时，才自动绑定。
    """
    meta = get_pipeline_meta(application)
    threads = dict(meta.get("claim_threads") or {})
    open_items = [(k, t) for k, t in threads.items() if t.get("status") == "open"]

    key = None
    if claim_id and claim_id in threads and threads[claim_id].get("status") == "open":
        key = claim_id
    elif claim_id:
        for k, t in reversed(list(threads.items())):
            if t.get("claim_id") == claim_id and t.get("status") == "open":
                key = k
                break
        if key is None:
            maybe = _thread_key(claim_id, claim_text)
            if maybe in threads:
                key = maybe

    if key is None and request_message_id:
        for k, t in threads.items():
            if t.get("request_message_id") == request_message_id:
                key = k
                break

    if key is None and claim_text:
        for k, t in open_items:
            if t.get("claim_text") == claim_text:
                key = k
                break

    if key is None:
        if allow_single_open_fallback and len(open_items) == 1:
            key = open_items[0][0]
        elif len(open_items) > 1:
            raise ValueError("存在多条待澄清 Claim，必须指定 claim_id，不能默认绑定其中一条。")
        elif not open_items and not claim_id and not claim_text:
            raise ValueError("没有可回复的开放 Claim，且未提供 claim_id。")

    if key is None or key not in threads:
        if not claim_id and not claim_text:
            raise ValueError("无法定位 Claim 线程")
        # 无既有线程时补建（兼容旧数据）
        key = _thread_key(claim_id, claim_text)
        threads[key] = {
            "claim_id": claim_id,
            "claim_text": claim_text,
            "status": "answered",
            "request_message_id": request_message_id,
            "response_message_id": response_message_id,
            "questions": [],
            "opened_at": _now(),
            "answered_at": _now(),
            "reviewed_at": None,
        }
    else:
        thread = dict(threads[key])
        if thread.get("status") != "open":
            raise ValueError("该 Claim 不处于待回复状态")
        thread["status"] = "answered"
        thread["response_message_id"] = response_message_id
        thread["answered_at"] = _now()
        if claim_id:
            thread["claim_id"] = claim_id
        if claim_text:
            thread["claim_text"] = claim_text
        threads[key] = thread

    meta["claim_threads"] = threads
    meta["last_candidate_activity_at"] = _now()
    set_pipeline_meta(application, meta)
    return threads.get(key)


def mark_claim_reviewed(application, claim_id: str) -> Optional[dict]:
    meta = get_pipeline_meta(application)
    threads = dict(meta.get("claim_threads") or {})
    key = claim_id if claim_id in threads else None
    if key is None:
        for k, t in threads.items():
            if t.get("claim_id") == claim_id:
                key = k
                break
    if key is None:
        return None
    thread = dict(threads[key])
    if thread.get("status") != "answered":
        raise ValueError("只有候选人已回答的 Claim 才能标记为 reviewed")
    thread["status"] = "reviewed"
    thread["reviewed_at"] = _now()
    threads[key] = thread
    meta["claim_threads"] = threads
    meta["employer_reviewed_ids"] = list(
        set(list(meta.get("employer_reviewed_ids") or []) + [str(application.id)])
    )
    meta["last_employer_activity_at"] = _now()
    set_pipeline_meta(application, meta)
    return thread


def mark_application_reviewed(application) -> dict:
    """招聘方标记整单已复核（持久化，替代前端 reviewedIds）。"""
    meta = get_pipeline_meta(application)
    meta["employer_reviewed_at"] = _now()
    meta["last_employer_activity_at"] = _now()
    # 将所有 answered 线程标为 reviewed
    threads = dict(meta.get("claim_threads") or {})
    for k, t in threads.items():
        if t.get("status") == "answered":
            nt = dict(t)
            nt["status"] = "reviewed"
            nt["reviewed_at"] = _now()
            threads[k] = nt
    meta["claim_threads"] = threads
    set_pipeline_meta(application, meta)
    return meta


def open_claim_count(application) -> int:
    return sum(1 for t in get_claim_threads(application).values() if t.get("status") == "open")


def answered_unreviewed_count(application) -> int:
    return sum(1 for t in get_claim_threads(application).values() if t.get("status") == "answered")


def close_open_claims_by_employer(
    application,
    *,
    employer_id: str,
    reason: Optional[str] = None,
) -> List[dict]:
    """
    招聘方显式「人工关闭澄清」：把所有 open 线程标为 closed，
    记录关闭人/原因/时间；不伪装成候选人已回复。返回被关闭的线程。
    """
    meta = get_pipeline_meta(application)
    threads = dict(meta.get("claim_threads") or {})
    closed: List[dict] = []
    ts = _now()
    for k, t in threads.items():
        if t.get("status") == "open":
            nt = dict(t)
            nt["original_status"] = t.get("status")
            nt["status"] = "closed"
            nt["closed_by_employer"] = True
            nt["closed_by"] = str(employer_id)
            nt["close_reason"] = reason
            nt["closed_at"] = ts
            threads[k] = nt
            closed.append(nt)
    meta["claim_threads"] = threads
    meta["last_employer_activity_at"] = ts
    set_pipeline_meta(application, meta)
    return closed


def recompute_clarification_status(application) -> str:
    """
    根据 claim 线程重算申请状态：
    - 仍有 open → needs_clarification
    - 无 open 且存在招聘方关闭未回答 → clarification_closed
    - 无 open 且至少存在候选人回答/复核 → clarified
    - 否则保持原状
    """
    threads = get_claim_threads(application)
    if not threads:
        return application.status
    if any(t.get("status") == "open" for t in threads.values()):
        return "needs_clarification"
    if any(t.get("status") == "closed" for t in threads.values()):
        return "clarification_closed"
    if any(t.get("status") in {"answered", "reviewed"} for t in threads.values()):
        return "clarified"
    return application.status


def claim_threads_summary(application) -> dict:
    threads = get_claim_threads(application)
    items = []
    for key, t in threads.items():
        items.append(
            {
                "thread_key": key,
                **t,
            }
        )
    items.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
    return {
        "claim_threads": items,
        "open_claim_count": open_claim_count(application),
        "answered_unreviewed_count": answered_unreviewed_count(application),
        "employer_reviewed_at": get_pipeline_meta(application).get("employer_reviewed_at"),
    }


def parse_claim_entry_hint(claim_id: Optional[str]) -> dict:
    """从 claim_id 解析 section/index，便于写入 clarification_answers。"""
    if not claim_id:
        return {}
    parts = claim_id.split("_")
    # work_experience_0_action_0 / projects_1_metric_0
    if len(parts) >= 3 and parts[0] == "work" and parts[1] == "experience":
        try:
            return {
                "section": "work_experience",
                "entry_type": "work",
                "entry_index": int(parts[2]),
            }
        except ValueError:
            return {}
    if len(parts) >= 2 and parts[0] == "projects":
        try:
            return {"section": "projects", "entry_type": "project", "entry_index": int(parts[1])}
        except ValueError:
            return {}
    return {}

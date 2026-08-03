import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from zoneinfo import ZoneInfo
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import ProfileFragment
from .models_db import Resume, JobApplication, InterviewResult
from .claim_reasoning import generate_claim_followup_questions
from .interview_fair_use import (
    InterviewFairUse,
    consume_interview_turn,
    send_fair_use_error,
)
from .llm_client import async_chat_completion, default_model_name, model_api_key
from .provider_costs import extract_provider_usage, record_provider_cost_event

logger = logging.getLogger(__name__)

# Redis 连接由 main.py 注入（可选，用于断线重连；非硬依赖）
redis_client = None
_local_provider_calls: dict[str, int] = {}
_local_provider_lock = asyncio.Lock()


class ProviderCapacityExceeded(RuntimeError):
    """Platform-wide provider protection; this is not user quota."""


def _provider_day_and_ttl() -> tuple[str, int]:
    local_timezone = ZoneInfo(os.getenv("BILLING_TIMEZONE", "Asia/Shanghai"))
    now = datetime.now(timezone.utc).astimezone(local_timezone)
    next_midnight = datetime.combine(
        (now + timedelta(days=1)).date(),
        datetime.min.time(),
        tzinfo=local_timezone,
    )
    return (
        now.strftime("%Y-%m-%d"),
        max(60, int((next_midnight - now).total_seconds())),
    )


async def _reserve_provider_capacity() -> None:
    limit = int(os.getenv("INTERVIEW_GLOBAL_PROVIDER_CALLS_PER_DAY", "5000"))
    if limit < 1:
        raise ProviderCapacityExceeded("AI 面试服务当前暂停")
    day, ttl_seconds = _provider_day_and_ttl()
    key = f"ai-job-platform:interview-provider-calls:{day}"
    if redis_client is not None:
        try:
            used = int(await redis_client.incr(key))
            if used == 1:
                await redis_client.expire(key, ttl_seconds)
        except Exception as exc:
            if os.getenv("ENV", "development").strip().lower() == "production":
                raise ProviderCapacityExceeded("AI 面试容量保护暂时不可用") from exc
            logger.warning(
                "Redis 容量计数失败，使用进程内计数: %s",
                type(exc).__name__,
            )
        else:
            if used > limit:
                raise ProviderCapacityExceeded("AI 面试今日平台容量已用完")
            return
    async with _local_provider_lock:
        used = _local_provider_calls.get(day, 0) + 1
        _local_provider_calls.clear()
        _local_provider_calls[day] = used
    if used > limit:
        raise ProviderCapacityExceeded("AI 面试今日平台容量已用完")


async def _call_interview_provider(**kwargs):
    await _reserve_provider_capacity()
    return await async_chat_completion(task="interview_question_render", **kwargs)


async def _ensure_accepted(websocket: WebSocket) -> None:
    if websocket.client_state == WebSocketState.CONNECTING:
        await websocket.accept()


def get_model():
    return default_model_name("interview_question_render")


SYSTEM_PROMPT = """
你是一个专业且友善的AI面试官，正在与求职者进行一场轻松的对话。
你需要按顺序了解以下信息，每次只问1-2个问题，根据求职者的回答自然地深入，避免审问式提问。

需要收集的维度：
1. 期望的职位（如 Java开发、产品经理）
2. 期望薪资范围（如 15k-25k）
3. 技能（编程语言、工具等，尽量具体）
4. 主要工作经历（公司、职位、年限）
5. 学历背景
6. 业余爱好
7. 期望工作地点（如上海、远程）

当你认为已经收集到足够的信息（至少包含了期望职位、技能、工作经历），请给出一段友好的总结，概括你了解到的求职者画像，然后在回复的最后单独一行加上：[INTERVIEW_END]
"""


def build_messages(history: list) -> list:
    """拼接完整的消息列表"""
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


# ---------- 画像提取 ----------
async def _record_interview_cost(
    db: AsyncSession,
    *,
    user_id: str,
    response=None,
    model: str,
    prompt_version: str,
    provider_status: str,
) -> None:
    usage = (
        extract_provider_usage(
            response,
            provider="deepseek",
            requested_model=model,
        )
        if response is not None
        else None
    )
    await record_provider_cost_event(
        db,
        reservation_id=None,
        user_id=user_id,
        organization_id=None,
        feature="interview_turn",
        prompt_version=prompt_version,
        provider_status=provider_status,
        usage=usage,
        requested_model=model,
    )
    await db.commit()


async def _create_interview_result(
    db: AsyncSession,
    *,
    fair_use: InterviewFairUse,
    user_id: str,
    mode: str,
    transcript: list[dict],
    extracted: dict,
    resume_id: Optional[str] = None,
    application_id: Optional[str] = None,
    requested_uses: Optional[dict] = None,
) -> InterviewResult:
    existing = (
        await db.execute(
            select(InterviewResult).where(
                InterviewResult.fair_use_session_id == fair_use.session_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = InterviewResult(
        fair_use_session_id=fair_use.session_id,
        user_id=user_id,
        resume_id=resume_id,
        application_id=application_id,
        mode=mode,
        status="pending_confirmation",
        transcript=transcript,
        extracted_json=extracted,
        source_references=[
            {
                "message_index": index,
                "role": item.get("role"),
            }
            for index, item in enumerate(transcript)
            if item.get("role") == "user"
        ],
        requested_uses=requested_uses
        or {
            "resume_write": False,
            "job_recommendation": False,
            "employer_share": False,
            "model_improvement": False,
        },
        allowed_uses={
            "resume_write": False,
            "job_recommendation": False,
            "employer_share": False,
            "model_improvement": False,
        },
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _send_interview_result(
    websocket: WebSocket,
    row: InterviewResult,
) -> None:
    await websocket.send_text(
        json.dumps(
            {
                "type": "interview_result",
                "id": str(row.id),
                "mode": row.mode,
                "status": row.status,
                "resume_id": str(row.resume_id) if row.resume_id else None,
                "application_id": (str(row.application_id) if row.application_id else None),
                "extracted": row.extracted_json or {},
                "message": (
                    "面试结果已保存为待确认草稿。"
                    "在你逐项授权前，不会写入简历、用于推荐或分享给招聘方。"
                ),
            },
            ensure_ascii=False,
        )
    )


async def extract_fragment(
    messages: list,
    model,
    *,
    db: AsyncSession,
    user_id: str,
) -> Optional[ProfileFragment]:
    """调用大模型尝试从最新对话中提取画像片段"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_profile_fragment",
                "description": "提取求职者画像的增量信息，未提及的字段留空",
                "parameters": ProfileFragment.model_json_schema(),
            },
        }
    ]
    try:
        response = await _call_interview_provider(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "extract_profile_fragment"}},
            temperature=0.1,
        )
        await _record_interview_cost(
            db,
            user_id=user_id,
            response=response,
            model=model,
            prompt_version="interview-profile-extract-v1",
            provider_status="succeeded",
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            args_str = msg.tool_calls[0].function.arguments
            data = json.loads(args_str)
            return ProfileFragment(**data)
        return None
    except ProviderCapacityExceeded:
        raise
    except Exception as e:
        logger.error("画像提取失败: %s", type(e).__name__)
        await _record_interview_cost(
            db,
            user_id=user_id,
            model=model,
            prompt_version="interview-profile-extract-v1",
            provider_status="failed",
        )
        return None


# ---------- 主面试逻辑 ----------
async def interview_handler(
    websocket: WebSocket,
    user_id: str,
    db: AsyncSession,
    fair_use: InterviewFairUse,
    application_id: Optional[str] = None,
):
    await _ensure_accepted(websocket)

    if not model_api_key():
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "error": "ai_unavailable",
                    "message": "AI 暂不可用，规则与人工功能仍可使用",
                },
                ensure_ascii=False,
            )
        )
        await websocket.close(code=1013, reason="ai_unavailable")
        return
    model = get_model()
    # Redis 可选：有则清空旧会话；无则纯内存
    redis_key = f"chat_history:{user_id}"
    if redis_client is not None:
        try:
            await redis_client.delete(redis_key)
        except Exception as e:
            logger.warning("Redis 清理失败，继续使用内存会话: %s", type(e).__name__)

    history = []

    welcome = (
        "你好！我是你的专属面试官。我们轻松聊聊你的职业期望吧～ 可以先告诉我你想找什么样的工作吗？"
    )
    await websocket.send_text(welcome)
    history.append({"role": "assistant", "content": welcome})

    try:
        while True:
            data = await websocket.receive_text()
            if data.strip().lower() in ["结束", "quit", "exit"]:
                await websocket.send_text("感谢你的时间，面试结束。再见！")
                break
            try:
                await consume_interview_turn(db, fair_use)
            except HTTPException as exc:
                await send_fair_use_error(websocket, exc)
                await websocket.close(code=1008, reason="fair_use_exceeded")
                break

            history.append({"role": "user", "content": data})
            messages = build_messages(history)

            try:
                response = await _call_interview_provider(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=300,
                )
                await _record_interview_cost(
                    db,
                    user_id=user_id,
                    response=response,
                    model=model,
                    prompt_version="interview-profile-turn-v1",
                    provider_status="succeeded",
                )
                reply = response.choices[0].message.content
            except ProviderCapacityExceeded as exc:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error": "provider_capacity_exceeded",
                            "message": str(exc),
                        },
                        ensure_ascii=False,
                    )
                )
                await websocket.close(
                    code=1013,
                    reason="provider_capacity_exceeded",
                )
                break
            except Exception as e:
                logger.error("LLM 调用失败: %s", type(e).__name__)
                await _record_interview_cost(
                    db,
                    user_id=user_id,
                    model=model,
                    prompt_version="interview-profile-turn-v1",
                    provider_status="failed",
                )
                await websocket.send_text("抱歉，我暂时无法回应，请稍后再试。")
                continue

            if "[INTERVIEW_END]" in reply:
                clean = reply.replace("[INTERVIEW_END]", "").strip()
                await websocket.send_text(clean)
                await websocket.send_text("[系统] 面试已完成，感谢你的参与！")
                history.append({"role": "assistant", "content": reply})
                try:
                    fragment = await extract_fragment(messages, model,
                        db=db,
                        user_id=user_id,
                    )
                except ProviderCapacityExceeded:
                    fragment = None
                extracted = fragment.model_dump() if fragment else {}
                extracted["summary"] = clean
                result = await _create_interview_result(
                    db,
                    fair_use=fair_use,
                    user_id=user_id,
                    mode="profile",
                    transcript=history,
                    extracted=extracted,
                    application_id=application_id,
                    requested_uses=getattr(
                        websocket.state,
                        "interview_requested_uses",
                        None,
                    ),
                )
                await _send_interview_result(websocket, result)
                break

            await websocket.send_text(reply)
            history.append({"role": "assistant", "content": reply})

    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} 断开 WebSocket 连接")
    except Exception as e:
        logger.error("面试过程异常: %s", type(e).__name__)
        try:
            await websocket.send_text("系统内部错误，面试提前结束。")
        except Exception:
            pass
    finally:
        if redis_client is not None:
            try:
                await redis_client.delete(redis_key)
            except Exception:
                pass


# ---------- Claim 追问模式 ----------
CLAIM_FOLLOWUP_PROMPT = """
你是友善的 AI 面试官，正在帮助求职者补齐简历 claim 的细节，使经历表达更可信。
禁止审问式提问，禁止暗示候选人在造假。

当前正在追问的 claim：{claim_text}
追问原因：{why_ask}

根据求职者的回答：
1. 若回答充分，简短肯定并自然过渡
2. 若回答模糊，温和追问一个具体细节（基线/周期/个人贡献/技术场景）
3. 每次只问 1 个问题，语气专业友善
4. 当该 claim 已澄清完毕，在回复末尾单独一行加上：[CLAIM_DONE]
"""


async def claim_followup_handler(
    websocket: WebSocket,
    user_id: str,
    resume_id: str,
    db: AsyncSession,
    fair_use: InterviewFairUse,
    application_id: Optional[str] = None,
):
    """简历 Claim 追问模式：只生成用户所有的待确认草稿。"""
    await _ensure_accepted(websocket)

    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != user_id:
        await websocket.send_text("未找到您的简历，请先上传简历。")
        await websocket.close(code=1008)
        return

    # 若绑定申请，校验归属并优先用申请上的简历
    if application_id:
        app = await db.get(JobApplication, application_id)
        if not app or app.candidate_id != user_id:
            await websocket.send_text("无权访问该申请的面试会话。")
            await websocket.close(code=1008)
            return
        if app.resume_id and app.resume_id != resume_id:
            bound = await db.get(Resume, app.resume_id)
            if bound and bound.user_id == user_id:
                resume = bound

    parsed = resume.parsed_json or {}
    questions = generate_claim_followup_questions(parsed)
    if not questions:
        await websocket.send_text(
            "您的简历暂无明显需澄清的 claim。如需优化描述，可使用「AI 语义忠实扩写」功能。"
        )
        await websocket.close()
        return

    if not model_api_key():
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "error": "ai_unavailable",
                    "message": "AI 暂不可用，规则与人工功能仍可使用",
                },
                ensure_ascii=False,
            )
        )
        await websocket.close(code=1013, reason="ai_unavailable")
        return
    model = get_model()
    q_index = 0
    collected_answers: List[dict] = []

    intro = (
        "为了让这段经历表达得更可信，AI 面试官会帮你补齐细节。"
        f"\n\n我们先从这条经历开始：\n「{questions[0].get('claim_text', '')}」"
        f"\n\n{questions[0]['question']}"
    )
    await websocket.send_text(intro)

    current_q = questions[0]
    history = [{"role": "assistant", "content": intro}]

    async def _persist_answers(
        *,
        send: bool = True,
    ) -> Optional[InterviewResult]:
        if not collected_answers:
            return None
        result = await _create_interview_result(
            db,
            fair_use=fair_use,
            user_id=user_id,
            mode="claim_followup",
            transcript=history,
            extracted={"answers": collected_answers},
            resume_id=str(resume.id),
            application_id=application_id,
            requested_uses=getattr(
                websocket.state,
                "interview_requested_uses",
                None,
            ),
        )
        if send:
            await _send_interview_result(websocket, result)
        return result

    try:
        while True:
            data = await websocket.receive_text()
            if data.strip().lower() in ["结束", "quit", "exit"]:
                await _persist_answers()
                await websocket.send_text(
                    "感谢你的补充。结果已保存为待确认草稿，授权前不会写入简历或分享。"
                )
                break
            try:
                await consume_interview_turn(db, fair_use)
            except HTTPException as exc:
                await _persist_answers()
                await send_fair_use_error(websocket, exc)
                await websocket.close(code=1008, reason="fair_use_exceeded")
                break

            collected_answers.append(
                {
                    "claim_id": current_q["claim_id"],
                    "question": current_q["question"],
                    "answer": data.strip(),
                    "question_type": current_q.get("question_type"),
                    "claim_text": current_q.get("claim_text"),
                }
            )
            history.append({"role": "user", "content": data})

            system = CLAIM_FOLLOWUP_PROMPT.format(
                claim_text=current_q.get("claim_text", ""),
                why_ask=current_q.get("why_ask", ""),
            )
            messages = [{"role": "system", "content": system}] + history[-6:]

            try:
                response = await _call_interview_provider(
                    model=model,
                    messages=messages,
                    temperature=0.5,
                    max_tokens=300,
                )
                await _record_interview_cost(
                    db,
                    user_id=user_id,
                    response=response,
                    model=model,
                    prompt_version="interview-claim-followup-v1",
                    provider_status="succeeded",
                )
                reply = response.choices[0].message.content or ""
            except ProviderCapacityExceeded as exc:
                await _persist_answers()
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error": "provider_capacity_exceeded",
                            "message": str(exc),
                        },
                        ensure_ascii=False,
                    )
                )
                await websocket.close(
                    code=1013,
                    reason="provider_capacity_exceeded",
                )
                break
            except Exception as e:
                logger.error("Claim followup LLM failed: %s", type(e).__name__)
                await _record_interview_cost(
                    db,
                    user_id=user_id,
                    model=model,
                    prompt_version="interview-claim-followup-v1",
                    provider_status="failed",
                )
                reply = "感谢补充。还有其他想补充的细节吗？"

            if "[CLAIM_DONE]" in reply:
                reply = reply.replace("[CLAIM_DONE]", "").strip()
                await websocket.send_text(reply)
                q_index += 1
                if q_index >= len(questions):
                    await _persist_answers()
                    await websocket.send_text(
                        "[系统] 所有 Claim 追问已完成。请逐项确认用途；授权前不会写入简历或分享。"
                    )
                    break
                current_q = questions[q_index]
                next_msg = (
                    f"\n接下来关于：\n「{current_q.get('claim_text', '')}」\n\n"
                    f"{current_q['question']}"
                )
                await websocket.send_text(next_msg)
                history.append({"role": "assistant", "content": next_msg})
            else:
                await websocket.send_text(reply)
                history.append({"role": "assistant", "content": reply})

    except WebSocketDisconnect:
        logger.info("用户 %s claim followup 断开", user_id)
        try:
            await _persist_answers(send=False)
        except Exception as e:
            logger.warning("断开时保存 claim 追问回答失败: %s", type(e).__name__)
    except Exception as e:
        logger.error("Claim followup 异常: %s", type(e).__name__)
        try:
            await _persist_answers()
        except Exception as save_err:
            logger.warning(
                "异常时保存 claim 追问回答失败: %s",
                type(save_err).__name__,
            )
        try:
            await websocket.send_text("系统内部错误，追问提前结束。")
        except Exception:
            pass

import os
import json
import logging
from typing import Optional
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import OpenAI
from .models import ProfileFragment
from .models_db import Resume

logger = logging.getLogger(__name__)

# Redis 连接由 main.py 注入
redis_client = None

def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )

def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

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
async def extract_fragment(messages: list, client, model) -> Optional[ProfileFragment]:
    """调用大模型尝试从最新对话中提取画像片段"""
    tools = [{
        "type": "function",
        "function": {
            "name": "extract_profile_fragment",
            "description": "提取求职者画像的增量信息，未提及的字段留空",
            "parameters": ProfileFragment.model_json_schema()
        }
    }]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "extract_profile_fragment"}},
            temperature=0.1,
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            args_str = msg.tool_calls[0].function.arguments
            data = json.loads(args_str)
            return ProfileFragment(**data)
        return None
    except Exception as e:
        logger.error(f"画像提取失败: {e}")
        return None


# ---------- 写入数据库 ----------
async def update_profile_in_db(user_id: str, fragment: ProfileFragment, db: AsyncSession):
    """将提取的画像片段合并到用户最新的简历记录中"""
    try:
        # 查找该用户最新一份简历
        stmt = select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc()).limit(1)
        result = await db.execute(stmt)
        resume = result.scalars().first()

        if not resume:
            # 如果没有简历记录，创建一个空的占位记录
            resume = Resume(user_id=user_id, parsed_json={}, raw_text="")
            db.add(resume)
            await db.flush()

        current = resume.parsed_json.copy() if resume.parsed_json else {}

        # 合并增量信息
        if fragment.expected_job_title:
            current["expected_job_title"] = fragment.expected_job_title
        if fragment.expected_salary:
            current["expected_salary"] = fragment.expected_salary
        if fragment.skills:
            existing_skills = current.get("skills", [])
            skill_names = {s.get("name", "") for s in existing_skills if isinstance(s, dict)}
            for skill_name in fragment.skills:
                if skill_name not in skill_names:
                    existing_skills.append({"name": skill_name, "level": "intermediate"})
            current["skills"] = existing_skills
        if fragment.work_summary:
            old_summary = current.get("summary", "")
            current["summary"] = (old_summary + "\n" + fragment.work_summary).strip()
        if fragment.education:
            current["education"] = fragment.education
        if fragment.hobbies:
            current["hobbies"] = fragment.hobbies
        if fragment.location_preference:
            current["location_preference"] = fragment.location_preference

        resume.parsed_json = current
        await db.commit()
        logger.info(f"已更新用户 {user_id} 的画像")
    except Exception as e:
        logger.error(f"更新画像到数据库失败: {e}")
        await db.rollback()


# ---------- 主面试逻辑 ----------
async def interview_handler(websocket: WebSocket, user_id: str, db: AsyncSession):
    await websocket.accept()

    if redis_client is None:
        logger.error("Redis 未连接，无法保存对话历史")
        await websocket.close(code=1011)
        return

    client = get_openai_client()
    model = get_model()
    redis_key = f"chat_history:{user_id}"

    # 每次面试都是全新的（可配置是否保留历史，这里选择清空）
    await redis_client.delete(redis_key)
    history = []

    welcome = "你好！我是你的专属面试官。我们轻松聊聊你的职业期望吧～ 可以先告诉我你想找什么样的工作吗？"
    await websocket.send_text(welcome)
    history.append({"role": "assistant", "content": welcome})

    try:
        while True:
            # 接收用户消息
            data = await websocket.receive_text()
            if data.strip().lower() in ["结束", "quit", "exit"]:
                await websocket.send_text("感谢你的时间，面试结束。再见！")
                break

            history.append({"role": "user", "content": data})
            messages = build_messages(history)

            # 生成面试官回复
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=300,
                )
                reply = response.choices[0].message.content
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                await websocket.send_text("抱歉，我暂时无法回应，请稍后再试。")
                continue

            # 检查是否结束
            if "[INTERVIEW_END]" in reply:
                clean = reply.replace("[INTERVIEW_END]", "").strip()
                await websocket.send_text(clean)
                await websocket.send_text("[系统] 面试已完成，感谢你的参与！")
                history.append({"role": "assistant", "content": reply})
                # 最后再提取一次画像
                fragment = await extract_fragment(messages, client, model)
                if fragment:
                    await update_profile_in_db(user_id, fragment, db)
                break

            # 正常回复
            await websocket.send_text(reply)
            history.append({"role": "assistant", "content": reply})

            # 实时提取画像（每轮对话后尝试）
            fragment = await extract_fragment(messages, client, model)
            if fragment:
                await update_profile_in_db(user_id, fragment, db)

            # 保存对话历史到 Redis（可选，用于断线重连，当前未启用）
            # await redis_client.setex(redis_key, 3600, json.dumps(history, ensure_ascii=False))

    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} 断开 WebSocket 连接")
    except Exception as e:
        logger.error(f"面试过程异常: {e}")
        # 尝试发送错误提示
        try:
            await websocket.send_text("系统内部错误，面试提前结束。")
        except:
            pass
    finally:
        # 清理 Redis 中的历史记录（保证下次是全新的）
        await redis_client.delete(redis_key)
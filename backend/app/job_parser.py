import os
import json
from openai import OpenAI
from .models import JobInfo   # 之后定义

def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )

def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

def parse_job_with_llm(text: str) -> JobInfo:
    client = get_openai_client()
    model = get_model()

    tools = [{
        "type": "function",
        "function": {
            "name": "extract_job",
            "description": "提取岗位详细信息",
            "parameters": JobInfo.model_json_schema()
        }
    }]
    
    prompt = f"""你是专业的HR信息提取专家。请从以下岗位描述中提取信息，严格按照 JSON Schema 返回。
缺失字段用 null 或空数组。
请额外识别：soft_skills（沟通协作等软实力）、leadership_signals（带团队/项目管理等）、
communication_signals、education_requirement、school_tier_keywords（如985/211/硕士等）。

岗位描述：
{text}
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个精准的岗位解析器，输出JSON。"},
            {"role": "user", "content": prompt}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_job"}},
        temperature=0.1,
    )
    msg = response.choices[0].message
    if msg.tool_calls:
        args = json.loads(msg.tool_calls[0].function.arguments)
        return JobInfo(**args)
    else:
        # 简单回退尝试从 content 提取，此处略
        raise ValueError("无法解析岗位信息")
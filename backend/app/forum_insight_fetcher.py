"""
从公开网络社区抓取招聘/录用经验帖（Reddit、V2EX、HN Algolia、本地语料）。

合规：仅访问公开页面/API，不爬登录态内容，不绕过验证码，不采集私人信息。
后续可接入牛客/脉脉/知乎等需单独评估 robots 与授权；当前以 HN + 本地语料为主。
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import List, Dict

import httpx

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).parent / "data" / "forum_insights_corpus.json"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

PLATFORM_WEIGHT = {
    "reddit": 1.0,
    "v2ex": 1.0,
    "hackernews": 0.9,
    "corpus": 0.35,
}


async def _get_json(client: httpx.AsyncClient, url: str, params: dict = None) -> dict:
    resp = await client.get(url, params=params or {}, headers=HTTP_HEADERS, timeout=25.0)
    resp.raise_for_status()
    return resp.json()


def _query_terms(queries: List[str]) -> List[str]:
    terms = set()
    for q in queries:
        for part in re.split(r"[\s+]+", q):
            part = part.strip()
            if len(part) >= 2 and part not in {
                "面试",
                "offer",
                "interview",
                "experience",
                "hiring",
            }:
                terms.add(part.lower())
    return list(terms)[:30]


def _post_matches_terms(post: Dict, terms: List[str]) -> bool:
    if not terms:
        return True
    blob = f"{post.get('title', '')} {post.get('body', '')}".lower()
    return any(t in blob for t in terms)


async def fetch_reddit_posts(client: httpx.AsyncClient, queries: List[str]) -> List[Dict]:
    if os.getenv("DISABLE_REDDIT_FETCH", "").lower() in ("1", "true", "yes"):
        return []
    posts = []
    for q in queries[:12]:
        try:
            url = "https://www.reddit.com/search.json"
            data = await _get_json(
                client,
                url,
                {"q": q, "limit": 15, "sort": "relevance", "t": "year", "raw_json": 1},
            )
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                posts.append(
                    {
                        "platform": "reddit",
                        "source_url": f"https://reddit.com{d.get('permalink', '')}",
                        "title": d.get("title", ""),
                        "body": d.get("selftext", "") or "",
                        "search_query": q,
                    }
                )
        except Exception as e:
            logger.warning("Reddit 抓取失败 q=%s: %s", q, e)
    return posts


async def fetch_v2ex_posts(client: httpx.AsyncClient, queries: List[str]) -> List[Dict]:
    """
    V2EX 已下线 /api/search.json（404）。
    改为拉取近期话题并在本地按关键词过滤。
    """
    posts = []
    terms = _query_terms(queries)
    pages = ["/api/topics/recent.json", "/api/topics/hot.json"]
    try:
        for page in pages:
            data = await _get_json(client, f"https://www.v2ex.com{page}")
            for item in data[:80]:
                post = {
                    "platform": "v2ex",
                    "source_url": f"https://www.v2ex.com/t/{item.get('id', '')}",
                    "title": item.get("title", ""),
                    "body": item.get("content", "") or item.get("title", ""),
                    "search_query": "v2ex_recent",
                }
                if _post_matches_terms(post, terms):
                    posts.append(post)
    except Exception as e:
        logger.warning("V2EX 抓取失败: %s", e)
    return posts


async def fetch_hackernews_posts(client: httpx.AsyncClient, queries: List[str]) -> List[Dict]:
    posts = []
    for q in queries[:6]:
        try:
            url = "https://hn.algolia.com/api/v1/search"
            data = await _get_json(client, url, {"query": q, "tags": "story", "hitsPerPage": 12})
            for hit in data.get("hits", []):
                posts.append(
                    {
                        "platform": "hackernews",
                        "source_url": hit.get("url")
                        or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                        "title": hit.get("title", ""),
                        "body": hit.get("story_text", "") or hit.get("title", ""),
                        "search_query": q,
                    }
                )
        except Exception as e:
            logger.warning("HN 抓取失败 q=%s: %s", q, e)
    return posts


def load_corpus_posts() -> List[Dict]:
    if not CORPUS_PATH.exists():
        return []
    with open(CORPUS_PATH, encoding="utf-8") as f:
        items = json.load(f)
    posts = []
    for item in items:
        posts.append(
            {
                "platform": "corpus",
                "source_url": "",
                "title": item.get("title", ""),
                "body": item.get("body", ""),
                "search_query": "corpus",
                "corpus_companies": item.get("companies", []),
            }
        )
    return posts


def build_search_queries(companies: List) -> List[str]:
    """基于公司库生成中英搜索词"""
    queries = set(
        [
            "offer 录用 面试 经验",
            "校招 上岸 背景",
            "hiring interview experience offer",
            "Apple Google Microsoft interview offer",
        ]
    )
    for c in companies[:40]:
        queries.add(f"{c.name} 面试 offer")
        for alias in (c.name_aliases or [])[:2]:
            if alias and len(alias) >= 2:
                queries.add(f"{alias} interview offer")
    return list(queries)


async def fetch_all_forum_posts(companies: List) -> List[Dict]:
    queries = build_search_queries(companies)
    all_posts = load_corpus_posts()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        hn = await fetch_hackernews_posts(client, queries)
        all_posts.extend(hn)
        v2ex = await fetch_v2ex_posts(client, queries)
        all_posts.extend(v2ex)
        reddit = await fetch_reddit_posts(client, queries)
        all_posts.extend(reddit)
    logger.info(
        "论坛原始帖合计 %s 条（语料=%s HN=%s V2EX=%s Reddit=%s）",
        len(all_posts),
        len(load_corpus_posts()),
        len(hn),
        len(v2ex),
        len(reddit),
    )
    if not reddit:
        logger.info(
            "Reddit 未获取到数据（常见原因：403 限流或网络不可达）。"
            "可依赖本地语料与 HN；或在 .env 设置 DISABLE_REDDIT_FETCH=1 跳过。"
        )
    return all_posts

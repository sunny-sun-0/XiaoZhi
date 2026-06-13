#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智AI推荐图文工具 - MCP图片搜索服务
提供免费搜索引擎获取食物/通用图片，无需注册，开箱即用
作为 MCP stdio 服务运行，供小智主程序调用
"""

import json
import requests
import logging
import random
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mcp = FastMCP("小智图文推荐")

# ========== 图片搜索方案 ==========

# 方案1：Unsplash 免费图片搜索（无需Key，有速率限制但个人使用足够）
UNSPLASH_URL = "https://unsplash.com/napi/search/photos"

# 方案2：Pexels 付费/免费Key（可选）
PEXELS_URL = "https://api.pexels.com/v1/search"

# ========== 搜索引擎实现 ==========

def _search_unsplash(query: str, per_page: int = 5) -> list:
    """Unsplash免费搜索"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(UNSPLASH_URL, headers=headers,
                            params={"query": query, "per_page": per_page, "page": 1},
                            timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            photos = data.get("photos", {}).get("results", [])
            return [{
                "id": p.get("id"),
                "image_url": p.get("urls", {}).get("regular", ""),
                "thumb_url": p.get("urls", {}).get("thumb", ""),
                "description": p.get("description") or p.get("alt_description") or query,
                "photographer": p.get("user", {}).get("name", "")
            } for p in photos]
        return []
    except Exception as e:
        logger.warning(f"Unsplash搜索异常: {e}")
        return []


# ========== MCP 工具 ==========

@mcp.tool()
def recommend_with_image(user_id: str, food_name: str = "", taste_preferences: list = None,
                         dietary_restrictions: list = None) -> dict:
    """
    推荐美食并附带美食图片（多模态输出：文本+图像）

    参数说明:
    - user_id: 用户标识
    - food_name: (可选) 指定菜品名称，为空则自动推荐
    - taste_preferences: (可选) 口味偏好，如 ["辣","麻辣"]
    - dietary_restrictions: (可选) 饮食禁忌，如 ["素食"]
    """
    try:
        # 导入主推荐引擎
        import sys
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from foodRecommendation import FoodRecommendationEngine, MemoryStorage, FOOD_KNOWLEDGE_BASE

        rec_result = FoodRecommendationEngine.recommend(
            user_id,
            {"taste_preferences": taste_preferences, "dietary_restrictions": dietary_restrictions}
            if taste_preferences or dietary_restrictions else None
        )

        if not rec_result.get("success"):
            return rec_result

        recommendation = rec_result.get("recommendation") or {}
        food_name = recommendation.get("food_name", food_name or "美食")

        # 搜索图片
        image_result = search_food_image(food_name)

        return {
            "success": True,
            "message": f"推荐 {food_name}！{recommendation.get('description', '')}",
            "food_name": food_name,
            "recommendation": recommendation,
            "image": image_result,
            "record_id": rec_result.get("record_id", "")
        }
    except Exception as e:
        logger.error(f"推荐失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def search_food_image(prompt: str) -> dict:
    """
    搜索美食图片，根据菜品名称从网上找到对应的真实美食照片

    参数说明:
    - prompt: 菜品名称或美食描述，例如：麻婆豆腐、北京烤鸭、意大利面
    """
    try:
        # 多关键词搜索提高命中率
        queries = [f"food {prompt} dish", prompt, f"{prompt}美食"]
        all_photos = []
        for q in queries:
            photos = _search_unsplash(q, per_page=4)
            all_photos.extend(photos)
            if len(all_photos) >= 5:
                break

        if all_photos:
            selected = random.choice(all_photos[:5])
            logger.info(f"✅ 找到图片: {selected.get('description', prompt)[:50]}...")
            return {
                "success": True,
                "image_url": selected["image_url"],
                "thumb_url": selected["thumb_url"],
                "description": selected.get("description", prompt),
                "source": "Unsplash"
            }

        # 备用：高质量占位图
        return {
            "success": True,
            "image_url": f"https://source.unsplash.com/800x600/?food,{quote(prompt)}",
            "thumb_url": f"https://source.unsplash.com/400x300/?food,{quote(prompt)}",
            "description": f"{prompt} 美食参考",
            "source": "placeholder"
        }

    except Exception as e:
        logger.error(f"搜索美食图片异常: {e}")
        return {
            "success": False,
            "image_url": f"https://source.unsplash.com/800x600/?food,{quote(prompt)}",
            "error": str(e)
        }


@mcp.tool()
def search_general_image(query: str, count: int = 3) -> dict:
    """
    通用图片搜索，搜索任何主题的图片

    参数说明:
    - query: 搜索关键词，如"长城"、"小猫"、"日落"
    - count: 返回图片数量，默认3，最大10
    """
    try:
        count = max(1, min(10, count))
        photos = _search_unsplash(query, per_page=count)

        if photos:
            return {
                "success": True,
                "query": query,
                "total": len(photos),
                "image_url": photos[0]["image_url"],
                "images": photos,
                "source": "Unsplash"
            }

        return {
            "success": True,
            "query": query,
            "image_url": f"https://source.unsplash.com/800x600/?{quote(query)}",
            "images": [{"image_url": f"https://source.unsplash.com/800x600/?{quote(query)}"}],
            "source": "placeholder"
        }

    except Exception as e:
        logger.error(f"通用搜索异常: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_recommendation_image(user_id: str) -> dict:
    """
    为用户的最新一条推荐附带美食图片

    参数说明:
    - user_id: 用户标识
    """
    try:
        from foodRecommendation import MemoryStorage
        records = MemoryStorage.get_user_recommendations(user_id, limit=1)
        if not records:
            return {"success": False, "message": "暂无推荐记录"}

        latest = records[0]
        food_name = latest.get("food_name", "美食")

        # 搜索图片
        image_result = search_food_image(food_name)

        return {
            "success": True,
            "record_id": latest["id"],
            "food_name": food_name,
            "image": image_result
        }

    except Exception as e:
        logger.error(f"获取推荐图片失败: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("=" * 60)
    print("🍽️📸 小智AI推荐图文工具")
    print("� 免费 Unsplash 图片搜索，无需API Key")
    print("🔌 MCP服务已启动 (stdio传输)")
    print("=" * 60)

    mcp.run(transport="stdio")
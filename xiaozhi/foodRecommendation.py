#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智AI美食推荐官 - 主服务模块
功能：记忆对话人偏好、饮食禁忌、过往推荐记录，持续推荐适配美食
支持多模态（文本+图像）API，拥有完整的记忆系统
图片搜索：必应 > 百度 > Unsplash > 占位图，全部国内可访问
对话中提取菜名→返回相关图片
"""

from mcp.server.fastmcp import FastMCP
import json
import os
import random
import logging
import hashlib
import re
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FoodRecommendation")

mcp = FastMCP("小智美食推荐官")

# ========== 数据存储 ==========
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
RECOMMENDATIONS_FILE = os.path.join(DATA_DIR, "recommendations.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")


# ========== 记忆存储引擎 ==========
class MemoryStorage:
    @staticmethod
    def _load_json(filepath: str, default: dict = None) -> dict:
        if default is None: default = {}
        if not os.path.exists(filepath): return default
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default

    @staticmethod
    def _save_json(filepath: str, data: dict) -> None:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def get_user(user_id: str) -> Optional[dict]:
        return MemoryStorage._load_json(USERS_FILE, {}).get(user_id)

    @staticmethod
    def update_user_preferences(user_id: str, prefs: dict) -> dict:
        users = MemoryStorage._load_json(USERS_FILE, {})
        if user_id not in users:
            users[user_id] = {"user_id": user_id, "created_at": datetime.now().isoformat(),
                              "taste_preferences": [], "dietary_restrictions": [],
                              "favorite_cuisines": [], "dislike_foods": [],
                              "allergies": [], "health_goals": "",
                              "preference_notes": "", "updated_at": datetime.now().isoformat()}
        user = users[user_id]
        for key, value in prefs.items():
            if value is not None:
                if key in ["taste_preferences", "dietary_restrictions", "favorite_cuisines", "dislike_foods", "allergies"] and isinstance(value, list):
                    if key not in user: user[key] = []
                    existing = set(str(i) for i in user[key])
                    for item in value:
                        if str(item) not in existing: user[key].append(item); existing.add(str(item))
                else:
                    user[key] = value
        user["updated_at"] = datetime.now().isoformat()
        MemoryStorage._save_json(USERS_FILE, users)
        logger.debug(f"用户数据已保存: {user_id}, 口味: {user.get('taste_preferences')}")
        return user

    @staticmethod
    def add_recommendation(user_id: str, rec: dict) -> dict:
        data = MemoryStorage._load_json(RECOMMENDATIONS_FILE, {"records": []})
        record = {"id": hashlib.md5(f"{user_id}_{datetime.now().isoformat()}_{random.random()}".encode()).hexdigest()[:12],
                  "user_id": user_id, "timestamp": datetime.now().isoformat(),
                  "food_name": rec.get("food_name", ""), "cuisine_type": rec.get("cuisine_type", ""),
                  "description": rec.get("description", ""), "reason": rec.get("reason", ""),
                  "image_url": rec.get("image_url", ""), "status": "pending", "user_feedback": "", "rating": 0}
        data["records"].insert(0, record)
        data["records"] = data["records"][:100]
        MemoryStorage._save_json(RECOMMENDATIONS_FILE, data)
        logger.debug(f"推荐记录已保存: {user_id} -> {rec.get('food_name')}")
        return record

    @staticmethod
    def get_user_recommendations(user_id: str, limit: int = 20) -> list:
        return [r for r in MemoryStorage._load_json(RECOMMENDATIONS_FILE, {"records": []})["records"] if r["user_id"] == user_id][:limit]

    @staticmethod
    def update_recommendation_feedback(record_id: str, feedback: dict) -> bool:
        data = MemoryStorage._load_json(RECOMMENDATIONS_FILE, {"records": []})
        for i, record in enumerate(data["records"]):
            if record["id"] == record_id:
                for k, v in feedback.items(): data["records"][i][k] = v
                data["records"][i]["updated_at"] = datetime.now().isoformat()
                MemoryStorage._save_json(RECOMMENDATIONS_FILE, data)
                return True
        return False

    @staticmethod
    def get_session(session_id: str) -> Optional[dict]:
        return MemoryStorage._load_json(SESSIONS_FILE, {}).get(session_id)

    @staticmethod
    def save_session(session_id: str, data: dict) -> dict:
        sessions = MemoryStorage._load_json(SESSIONS_FILE, {})
        sessions[session_id] = data
        MemoryStorage._save_json(SESSIONS_FILE, sessions)
        return data

    @staticmethod
    def append_dialogue(session_id: str, role: str, content: str, metadata: dict = None) -> dict:
        sessions = MemoryStorage._load_json(SESSIONS_FILE, {})
        if session_id not in sessions:
            sessions[session_id] = {"session_id": session_id, "created_at": datetime.now().isoformat(),
                                    "dialogues": [], "context": {}, "story_choices": [],
                                    "current_stage": "greeting", "task_progress": {}}
        entry = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), "metadata": metadata or {}}
        sessions[session_id]["dialogues"].append(entry)
        sessions[session_id]["updated_at"] = datetime.now().isoformat()
        if len(sessions[session_id]["dialogues"]) > 50: sessions[session_id]["dialogues"] = sessions[session_id]["dialogues"][-50:]
        MemoryStorage._save_json(SESSIONS_FILE, sessions)
        return entry

    @staticmethod
    def update_story_choice(session_id: str, choice: dict) -> dict:
        sessions = MemoryStorage._load_json(SESSIONS_FILE, {})
        if session_id not in sessions:
            sessions[session_id] = {"session_id": session_id, "created_at": datetime.now().isoformat(),
                                    "dialogues": [], "context": {}, "story_choices": [],
                                    "current_stage": "greeting", "task_progress": {}}
        record = {"timestamp": datetime.now().isoformat(), "stage": sessions[session_id].get("current_stage", "unknown"),
                  "choice": choice.get("choice", ""), "options": choice.get("options", []), "selected": choice.get("selected", "")}
        sessions[session_id]["story_choices"].append(record)
        sessions[session_id]["current_stage"] = choice.get("next_stage", sessions[session_id]["current_stage"])
        MemoryStorage._save_json(SESSIONS_FILE, sessions)
        return record

    @staticmethod
    def update_task_progress(session_id: str, task_data: dict) -> dict:
        sessions = MemoryStorage._load_json(SESSIONS_FILE, {})
        if session_id not in sessions:
            sessions[session_id] = {"session_id": session_id, "created_at": datetime.now().isoformat(),
                                    "dialogues": [], "context": {}, "story_choices": [],
                                    "current_stage": "greeting", "task_progress": {}}
        if "task_progress" not in sessions[session_id]: sessions[session_id]["task_progress"] = {}
        for k, v in task_data.items(): sessions[session_id]["task_progress"][k] = v
        sessions[session_id]["updated_at"] = datetime.now().isoformat()
        MemoryStorage._save_json(SESSIONS_FILE, sessions)
        return sessions[session_id]["task_progress"]


# ========== 美食知识库（8大菜系 51+道菜品）==========
FOOD_KNOWLEDGE_BASE = {
    "川菜": {"description": "以麻辣、鲜香著称，善用辣椒、花椒调味", "style": "麻辣",
             "typical_dishes": [
                 {"name": "麻婆豆腐", "taste": "麻辣", "spicy_level": 5, "description": "嫩豆腐配麻辣肉末，麻辣鲜香"},
                 {"name": "宫保鸡丁", "taste": "甜辣", "spicy_level": 4, "description": "鸡丁配花生、干辣椒，甜辣可口"},
                 {"name": "水煮鱼", "taste": "麻辣", "spicy_level": 5, "description": "鲜嫩鱼片配麻辣汤底"},
                 {"name": "回锅肉", "taste": "咸鲜", "spicy_level": 3, "description": "五花肉配豆瓣酱炒制"},
                 {"name": "夫妻肺片", "taste": "麻辣", "spicy_level": 4, "description": "牛杂配麻辣红油"},
                 {"name": "担担面", "taste": "麻辣", "spicy_level": 4, "description": "四川特色面条，麻辣鲜香"},
                 {"name": "辣子鸡", "taste": "麻辣", "spicy_level": 5, "description": "鸡块配大量干辣椒爆炒"},
                 {"name": "酸菜鱼", "taste": "酸辣", "spicy_level": 3, "description": "酸菜配鲜鱼片，酸辣开胃"}]},
    "粤菜": {"description": "注重原汁原味，清淡鲜美，做工精细", "style": "清淡鲜美",
             "typical_dishes": [
                 {"name": "白切鸡", "taste": "清淡", "spicy_level": 0, "description": "原汁原味白嫩鸡肉，蘸姜葱酱"},
                 {"name": "叉烧", "taste": "甜咸", "spicy_level": 0, "description": "蜜汁烤猪肉，外焦里嫩"},
                 {"name": "清蒸鲈鱼", "taste": "鲜美", "spicy_level": 0, "description": "鲜嫩鲈鱼清蒸，保留原味"},
                 {"name": "煲仔饭", "taste": "咸香", "spicy_level": 0, "description": "砂锅煲制，米饭香糯"},
                 {"name": "虾饺", "taste": "鲜美", "spicy_level": 0, "description": "水晶饺皮包鲜虾馅"},
                 {"name": "肠粉", "taste": "清淡", "spicy_level": 0, "description": "米浆蒸制，滑嫩爽口"},
                 {"name": "烧鹅", "taste": "咸香", "spicy_level": 0, "description": "皮脆肉嫩，经典粤式烧味"},
                 {"name": "老火靓汤", "taste": "鲜美", "spicy_level": 0, "description": "慢火煲炖数小时的滋补汤品"}]},
    "鲁菜": {"description": "咸鲜为主，讲究火候，醇厚不腻", "style": "咸鲜醇厚",
             "typical_dishes": [
                 {"name": "糖醋鲤鱼", "taste": "酸甜", "spicy_level": 0, "description": "黄河鲤鱼糖醋烹制"},
                 {"name": "九转大肠", "taste": "咸鲜", "spicy_level": 0, "description": "猪肠经多道工序烹制"},
                 {"name": "葱烧海参", "taste": "咸鲜", "spicy_level": 0, "description": "海参配大葱烧制"},
                 {"name": "德州扒鸡", "taste": "咸香", "spicy_level": 0, "description": "五香脱骨扒鸡"},
                 {"name": "四喜丸子", "taste": "咸鲜", "spicy_level": 0, "description": "四个大肉丸象征福禄寿喜"}]},
    "湘菜": {"description": "香辣浓郁，色泽重，口味重", "style": "香辣",
             "typical_dishes": [
                 {"name": "剁椒鱼头", "taste": "辣", "spicy_level": 4, "description": "大鱼头配剁椒蒸制"},
                 {"name": "小炒肉", "taste": "辣", "spicy_level": 3, "description": "五花肉配青椒爆炒"},
                 {"name": "臭豆腐", "taste": "咸辣", "spicy_level": 3, "description": "闻着臭吃着香的经典小吃"},
                 {"name": "毛氏红烧肉", "taste": "咸鲜", "spicy_level": 2, "description": "不加酱油的红烧肉"},
                 {"name": "口味虾", "taste": "香辣", "spicy_level": 5, "description": "长沙特色麻辣小龙虾"}]},
    "江浙菜": {"description": "精致细腻，清鲜爽口，偏甜", "style": "清甜鲜美",
               "typical_dishes": [
                   {"name": "西湖醋鱼", "taste": "酸甜", "spicy_level": 0, "description": "草鱼糖醋烹制"},
                   {"name": "东坡肉", "taste": "甜咸", "spicy_level": 0, "description": "文火慢炖，肥而不腻"},
                   {"name": "龙井虾仁", "taste": "清鲜", "spicy_level": 0, "description": "虾仁配龙井茶叶"},
                   {"name": "叫花鸡", "taste": "咸香", "spicy_level": 0, "description": "荷叶包裹烤制"},
                   {"name": "小笼包", "taste": "鲜美", "spicy_level": 0, "description": "薄皮多汁的猪肉小笼"},
                   {"name": "松鼠桂鱼", "taste": "酸甜", "spicy_level": 0, "description": "形似松鼠，酸甜酥脆"}]},
    "日料": {"description": "注重食材原味，精致美观，清淡健康", "style": "清淡精致",
             "typical_dishes": [
                 {"name": "三文鱼刺身", "taste": "鲜美", "spicy_level": 0, "description": "新鲜三文鱼切片"},
                 {"name": "寿司拼盘", "taste": "鲜美", "spicy_level": 0, "description": "各式新鲜握寿司"},
                 {"name": "拉面", "taste": "咸鲜", "spicy_level": 1, "description": "浓郁汤底配劲道面条"},
                 {"name": "天妇罗", "taste": "清淡", "spicy_level": 0, "description": "新鲜食材裹薄衣油炸"},
                 {"name": "照烧鸡", "taste": "甜咸", "spicy_level": 0, "description": "鸡肉配照烧酱汁"},
                 {"name": "味噌汤", "taste": "咸鲜", "spicy_level": 0, "description": "日本传统味噌汤品"}]},
    "西餐": {"description": "以欧洲菜系为代表，使用黄油、奶油等", "style": "浓郁多样",
             "typical_dishes": [
                 {"name": "牛排", "taste": "咸香", "spicy_level": 0, "description": "精选牛肉煎制，可配黑椒汁"},
                 {"name": "意大利面", "taste": "酸甜", "spicy_level": 0, "description": "意面配番茄肉酱"},
                 {"name": "法式焗蜗牛", "taste": "咸香", "spicy_level": 0, "description": "蜗牛配蒜香黄油焗制"},
                 {"name": "凯撒沙拉", "taste": "清淡", "spicy_level": 0, "description": "经典鲜蔬沙拉"},
                 {"name": "奶油蘑菇汤", "taste": "奶香", "spicy_level": 0, "description": "浓郁顺滑的经典西式浓汤"},
                 {"name": "披萨", "taste": "咸香", "spicy_level": 0, "description": "意式薄底配多种配料"},
                 {"name": "提拉米苏", "taste": "甜", "spicy_level": 0, "description": "经典意式咖啡甜点"}]},
    "甜品": {"description": "甜美可口，造型精致，治愈系美食", "style": "甜",
             "typical_dishes": [
                 {"name": "芒果班戟", "taste": "甜", "spicy_level": 0, "description": "芒果配奶油班戟皮"},
                 {"name": "双皮奶", "taste": "甜", "spicy_level": 0, "description": "顺德传统奶制甜品"},
                 {"name": "巧克力熔岩蛋糕", "taste": "甜", "spicy_level": 0, "description": "外酥内软的巧克力蛋糕"},
                 {"name": "杨枝甘露", "taste": "甜", "spicy_level": 0, "description": "芒果西柚椰汁甜品"},
                 {"name": "抹茶冰淇淋", "taste": "甜", "spicy_level": 0, "description": "日式抹茶风味冰淇淋"},
                 {"name": "红豆沙", "taste": "甜", "spicy_level": 0, "description": "传统中式甜品，暖胃暖心"}]}
}


# ========== 推荐引擎 ==========
class FoodRecommendationEngine:
    @staticmethod
    def _match_spicy(user_prefs: dict, dish: dict) -> int:
        taste = user_prefs.get("taste_preferences", [])
        tol = 3
        if "辣" in taste: tol = 4
        if "麻辣" in taste: tol = 5
        if "清淡" in taste: tol = 1
        if "微辣" in taste: tol = 2
        diff = abs(tol - dish.get("spicy_level", 0))
        if diff == 0: return 10
        if diff <= 1: return 8
        if diff <= 2: return 5
        return max(1, 10 - diff * 2)

    @staticmethod
    def _check_allergies(dish_name: str, allergies: list) -> bool:
        if not allergies: return True
        kw_map = {"海鲜过敏": ["虾", "蟹", "鱼", "贝", "海参", "三文鱼", "刺身", "龙虾", "寿司"],
                  "花生过敏": ["花生", "宫保鸡丁"],
                  "牛奶过敏": ["奶", "芝士", "奶酪", "奶油", "冰淇淋", "蛋糕", "布丁", "双皮奶"],
                  "鸡蛋过敏": ["蛋", "蛋糕", "布丁", "班戟"],
                  "小麦过敏": ["面", "包", "披萨", "蛋糕"],
                  "坚果过敏": ["花生", "杏仁", "腰果", "核桃", "松仁"],
                  "大豆过敏": ["豆腐", "豆", "酱油", "味噌"],
                  "芒果过敏": ["芒果"],
                  "辣椒过敏": ["辣椒", "椒", "辣"]}
        for a in allergies:
            keywords = kw_map.get(a, [a])
            for kw in keywords:
                if kw in dish_name: return False
        return True

    @staticmethod
    def _is_disliked(dish_name: str, dislike_foods: list) -> bool:
        if not dislike_foods: return False
        for d in dislike_foods:
            if d in dish_name or dish_name in d: return True
        return False

    @staticmethod
    def _check_restrictions(dish_name: str, dish: dict, restrictions: list) -> bool:
        if not restrictions: return True
        checks = {"清真": ["猪肉", "猪", "叉烧", "东坡肉", "回锅肉", "红烧肉", "排骨", "小炒肉", "毛氏红烧肉", "肉丸", "腊肠", "火腿"],
                  "素食": ["肉", "鸡", "鱼", "虾", "蟹", "牛", "羊", "猪", "排骨", "叉烧", "海鲜", "寿司", "刺身"],
                  "纯素": ["肉", "鸡", "鱼", "虾", "蟹", "牛", "羊", "猪", "蛋", "奶", "芝士", "奶油", "蜂蜜", "冰淇淋", "蛋糕", "双皮奶"],
                  "低卡": ["炸", "焗", "肥肉", "五花", "奶油", "芝士", "巧克力", "蛋糕", "冰淇淋"],
                  "低盐": ["咸", "酱油", "酱", "腊", "腌制"],
                  "无麸质": ["面", "面包", "蛋糕", "饼干", "披萨", "拉面", "意面", "担担面", "肠粉", "小笼包", "饺子"]}
        for r in restrictions:
            forbidden = checks.get(r, [])
            for item in forbidden:
                if item in dish_name: return False
                if item in dish.get("description", ""): return False
        return True

    @staticmethod
    def recommend(user_id: str, preferences: dict = None) -> dict:
        user = MemoryStorage.get_user(user_id)
        if preferences:
            user = MemoryStorage.update_user_preferences(user_id, preferences)
        if not user:
            user = {k: (preferences.get(k, []) if preferences else []) for k in
                    ["taste_preferences", "dietary_restrictions", "favorite_cuisines", "dislike_foods", "allergies"]}
            if preferences: user["health_goals"] = preferences.get("health_goals", "")
            else: user["health_goals"] = ""

        past = MemoryStorage.get_user_recommendations(user_id, limit=50)
        past_foods = set()
        accepted_cuisines, rejected_cuisines = set(), set()
        for r in past:
            past_foods.add(r.get("food_name", ""))
            for c, info in FOOD_KNOWLEDGE_BASE.items():
                for d in info["typical_dishes"]:
                    if d["name"] == r.get("food_name", ""):
                        if r.get("status") in ["accepted", "liked"]: accepted_cuisines.add(c)
                        elif r.get("status") == "rejected": rejected_cuisines.add(c)
                        break

        candidates = []
        target = user.get("favorite_cuisines", [])
        if not target:
            taste = user.get("taste_preferences", [])
            if "辣" in taste or "麻辣" in taste: target = ["川菜", "湘菜"]
            elif "清淡" in taste: target = ["粤菜", "日料"]
            elif "甜" in taste: target = ["江浙菜", "甜品", "西餐"]
            else: target = list(FOOD_KNOWLEDGE_BASE.keys())
        if accepted_cuisines: target = list(accepted_cuisines) + [c for c in target if c not in accepted_cuisines]

        for cuisine in target:
            if cuisine not in FOOD_KNOWLEDGE_BASE: continue
            ci = FOOD_KNOWLEDGE_BASE[cuisine]
            for dish in ci["typical_dishes"]:
                name = dish["name"]
                if name in past_foods: continue
                if not FoodRecommendationEngine._check_allergies(name, user.get("allergies", [])): continue
                if not FoodRecommendationEngine._check_restrictions(name, dish, user.get("dietary_restrictions", [])): continue
                if FoodRecommendationEngine._is_disliked(name, user.get("dislike_foods", [])): continue

                spicy = FoodRecommendationEngine._match_spicy(user, dish)
                taste_prefs = user.get("taste_preferences", [])
                taste_score = 5
                if taste_prefs:
                    dt = dish.get("taste", "")
                    for p in taste_prefs:
                        if p in dt or dt in p: taste_score = 10; break
                    else: taste_score = 3
                bonus = 3 if cuisine in user.get("favorite_cuisines", []) else 0
                penalty = -5 if cuisine in rejected_cuisines else 0
                candidates.append({"dish": dish, "cuisine": cuisine, "style": ci["style"], "score": spicy + taste_score + bonus + penalty})

        if not candidates:
            for cuisine, ci in FOOD_KNOWLEDGE_BASE.items():
                for dish in ci["typical_dishes"]:
                    name = dish["name"]
                    if name in past_foods: continue
                    if not FoodRecommendationEngine._check_allergies(name, user.get("allergies", [])): continue
                    if not FoodRecommendationEngine._check_restrictions(name, dish, user.get("dietary_restrictions", [])): continue
                    if FoodRecommendationEngine._is_disliked(name, user.get("dislike_foods", [])): continue
                    candidates.append({"dish": dish, "cuisine": cuisine, "style": ci["style"], "score": 5})

        candidates.sort(key=lambda x: x["score"], reverse=True)
        if not candidates:
            return {"success": True, "message": "所有美食都已经推荐过了！", "food_name": "", "recommendation": None}

        selected = random.choice(candidates[:min(3, len(candidates))])
        dish = selected["dish"]
        rec = {"food_name": dish["name"], "cuisine_type": selected["cuisine"],
               "cuisine_style": selected["style"], "taste": dish.get("taste", ""),
               "spicy_level": dish.get("spicy_level", 0), "description": dish.get("description", ""),
               "reason": f"根据您的口味偏好推荐这道{selected['cuisine']}经典菜品——{dish['name']}。",
               "image_url": ""}
        record = MemoryStorage.add_recommendation(user_id, rec)
        return {"success": True, "message": f"为您推荐一道{selected['cuisine']}美食：{dish['name']}！{dish.get('description', '')}",
                "food_name": dish["name"], "recommendation": rec, "record_id": record["id"]}


# ========== 多级图片搜索引擎 ==========
class FoodImageService:
    """美食图片搜索引擎，四级策略：必应 > 百度 > Unsplash > 占位图"""

    @staticmethod
    def _search_bing(food_name: str) -> Optional[str]:
        """必应图片搜索，返回图片URL或None"""
        try:
            import requests
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(
                "https://www.bing.com/images/search",
                params={"q": f"{food_name} 美食 菜", "count": 10, "first": 1},
                headers=headers, timeout=10
            )
            if resp.status_code == 200:
                all_srcs = re.findall(r'src="([^"]+)"', resp.text)
                valid_urls = [u for u in all_srcs
                              if u.startswith('http') and not u.startswith('data:')
                              and ('.jpg' in u.lower() or '.jpeg' in u.lower() or '.png' in u.lower()
                                   or '.gif' in u.lower() or '.webp' in u.lower()
                                   or '.cn.bing.net' in u.lower() or '/th/' in u.lower())]
                if valid_urls:
                    logger.info(f"✅ 必应找到图片: {food_name}")
                    return random.choice(valid_urls[:8])
        except Exception as e:
            logger.debug(f"必应搜索异常: {e}")
        return None

    @staticmethod
    def _search_baidu(food_name: str) -> Optional[str]:
        """百度图片搜索，返回图片URL或None"""
        try:
            import requests
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                       "Referer": "https://image.baidu.com/"}
            resp = requests.get(
                "https://image.baidu.com/search/acjson",
                params={"tn": "resultjson_com", "word": f"{food_name}美食", "pn": 1, "rn": 10, "ie": "utf-8"},
                headers=headers, timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 1:
                    for item in data["data"][1:6]:
                        thumb_url = item.get("thumbURL", "")
                        if thumb_url:
                            logger.info(f"✅ 百度找到图片: {food_name}")
                            return thumb_url
        except Exception as e:
            logger.debug(f"百度搜索异常: {e}")
        return None

    @staticmethod
    def _search_unsplash(food_name: str) -> Optional[str]:
        """Unsplash免费搜索，返回图片URL或None"""
        try:
            import requests
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(
                "https://unsplash.com/napi/search/photos",
                params={"query": f"food {food_name} dish", "per_page": 3, "page": 1},
                headers=headers, timeout=15
            )
            if resp.status_code == 200:
                photos = resp.json().get("photos", {}).get("results", [])
                if photos:
                    logger.info(f"✅ Unsplash找到图片: {food_name}")
                    return photos[0].get("urls", {}).get("regular", "")
        except Exception as e:
            logger.debug(f"Unsplash搜索异常: {e}")
        return None

    @staticmethod
    def search_food_image(food_name: str) -> dict:
        """
        同步搜索美食图片
        四级策略：必应 > 百度 > Unsplash > 占位图
        全部国内可访问
        """
        url = FoodImageService._search_bing(food_name)
        source = "Bing"
        if not url:
            url = FoodImageService._search_baidu(food_name)
            source = "Baidu"
        if not url:
            url = FoodImageService._search_unsplash(food_name)
            source = "Unsplash"
        if not url:
            from urllib.parse import quote
            url = f"https://source.unsplash.com/800x600/?food,{quote(food_name)}"
            source = "placeholder"
        return {"success": True, "image_url": url, "thumb_url": url,
                "description": f"{food_name} 美食图片", "source": source}


# ========== 中文菜名检测引擎 ==========
class FoodNameDetector:
    """从对话文本中检测提到的菜名"""
    ALL_KNOWN_DISHES = set()
    DISH_TO_CUISINE = {}

    @classmethod
    def _init_knowledge(cls):
        if cls.ALL_KNOWN_DISHES:
            return
        for cuisine, info in FOOD_KNOWLEDGE_BASE.items():
            for dish in info["typical_dishes"]:
                cls.ALL_KNOWN_DISHES.add(dish["name"])
                cls.DISH_TO_CUISINE[dish["name"]] = cuisine
        # 额外常见美食（扩展覆盖）
        EXTRA = ["北京烤鸭", "火锅", "麻辣烫", "烧烤", "饺子", "馄饨", "粽子", "月饼",
                 "汤圆", "豆腐脑", "油条", "豆浆", "煎饼", "凉皮", "肉夹馍", "羊肉泡馍",
                 "酸辣粉", "螺蛳粉", "热干面", "兰州拉面", "炸鸡", "薯条", "汉堡",
                 "寿司", "刺身", "拉面", "咖喱饭", "蛋炒饭", "盖浇饭", "黄焖鸡米饭",
                 "冒菜", "串串香", "钵钵鸡", "烤鱼", "铁板烧", "关东煮"]
        for food in EXTRA:
            cls.ALL_KNOWN_DISHES.add(food)

    @classmethod
    def detect_food_name(cls, text: str) -> Optional[str]:
        """
        从对话文本中检测提到的菜名。
        按名称长度降序匹配，优先匹配完整菜名。
        """
        cls._init_knowledge()
        if not text:
            return None
        sorted_dishes = sorted(cls.ALL_KNOWN_DISHES, key=len, reverse=True)
        for dish in sorted_dishes:
            if dish in text:
                return dish
        return None

    @classmethod
    def get_cuisine_for_dish(cls, dish_name: str) -> str:
        cls._init_knowledge()
        return cls.DISH_TO_CUISINE.get(dish_name, "通用美食")


# ========== MCP 工具 ==========

@mcp.tool()
def register_user(user_id: str, taste_preferences: list = None, dietary_restrictions: list = None,
                  favorite_cuisines: list = None, dislike_foods: list = None,
                  allergies: list = None, health_goals: str = "") -> dict:
    """注册或更新用户档案，记录口味偏好和饮食禁忌。返回profile_summary包含当前记录的所有偏好。"""
    try:
        data = {"taste_preferences": taste_preferences or [], "dietary_restrictions": dietary_restrictions or [],
                "favorite_cuisines": favorite_cuisines or [], "dislike_foods": dislike_foods or [],
                "allergies": allergies or [], "health_goals": health_goals}
        existing = MemoryStorage.get_user(user_id)
        if existing:
            user = MemoryStorage.update_user_preferences(user_id, data)
            msg = f"已更新饮食档案！记录 {len(user.get('taste_preferences', []))} 种口味偏好、{len(user.get('dietary_restrictions', []))} 项饮食禁忌。"
        else:
            user = MemoryStorage.update_user_preferences(user_id, {
                **data, "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "conversation_history": [], "preference_notes": ""
            })
            msg = f"已创建饮食档案！记录 {len(taste_preferences or [])} 种口味偏好、{len(dietary_restrictions or [])} 项饮食禁忌。"
        logger.info(f"注册用户: {user_id}")
        return {"success": True, "message": msg, "user_id": user_id,
                "profile_summary": {"taste_preferences": user.get("taste_preferences", []),
                                    "dietary_restrictions": user.get("dietary_restrictions", []),
                                    "favorite_cuisines": user.get("favorite_cuisines", []),
                                    "allergies": user.get("allergies", [])}}
    except Exception as e:
        logger.error(f"注册失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def recommend_food(user_id: str, taste_preferences: list = None, dietary_restrictions: list = None,
                   favorite_cuisines: list = None, dislike_foods: list = None,
                   allergies: list = None, health_goals: str = "", session_id: str = "") -> dict:
    """
    根据用户的偏好和记忆推荐适配的美食，附带美食图片。
    返回的message字段包含菜品描述，image字段包含图片URL（国内可访问）。
    前端可用image.image_url显示图片。
    """
    try:
        prefs = {}
        if taste_preferences is not None: prefs["taste_preferences"] = taste_preferences
        if dietary_restrictions is not None: prefs["dietary_restrictions"] = dietary_restrictions
        if favorite_cuisines is not None: prefs["favorite_cuisines"] = favorite_cuisines
        if dislike_foods is not None: prefs["dislike_foods"] = dislike_foods
        if allergies is not None: prefs["allergies"] = allergies
        if health_goals: prefs["health_goals"] = health_goals

        result = FoodRecommendationEngine.recommend(user_id, prefs if prefs else None)

        if result.get("success") and result.get("recommendation"):
            food_name = result["recommendation"]["food_name"]
            image = FoodImageService.search_food_image(food_name)
            result["recommendation"]["image_url"] = image.get("image_url", "")
            result["image"] = image
            result["message"] = f"为您推荐一道{result['recommendation']['cuisine_type']}美食：{food_name}！{result['recommendation']['description']} 图片: {image.get('image_url', '')}"

        if result.get("success") and result.get("recommendation") and session_id:
            MemoryStorage.append_dialogue(session_id, "assistant",
                                          f"推荐: {result['recommendation']['food_name']} ({result['recommendation']['cuisine_type']})", {})

        logger.info(f"推荐完成: {result.get('food_name', 'N/A')}")
        return result
    except Exception as e:
        logger.error(f"推荐失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def record_feedback(user_id: str, record_id: str, status: str, rating: int = 0,
                    feedback_text: str = "", session_id: str = "") -> dict:
    """记录用户对推荐的反馈，拒绝时自动重新推荐带图片"""
    try:
        fb = {"status": status, "rating": max(0, min(5, rating)),
              "feedback_text": feedback_text, "feedback_time": datetime.now().isoformat()}
        if not MemoryStorage.update_recommendation_feedback(record_id, fb):
            return {"success": False, "error": f"未找到记录: {record_id}"}

        status_map = {"accepted": "接受了", "rejected": "拒绝了", "liked": "很喜欢", "cooked": "已尝试"}
        logger.info(f"反馈记录: user={user_id}, record={record_id}, status={status}")

        if status == "rejected":
            new_rec = FoodRecommendationEngine.recommend(user_id)
            if new_rec.get("success") and new_rec.get("recommendation"):
                food_name = new_rec["recommendation"]["food_name"]
                image = FoodImageService.search_food_image(food_name)
                new_rec["recommendation"]["image_url"] = image.get("image_url", "")
                new_rec["image"] = image
                new_rec["message"] = f"为您重新推荐一道{new_rec['recommendation']['cuisine_type']}美食：{food_name}！{new_rec['recommendation']['description']} 图片: {image.get('image_url', '')}"
            return {"success": True, "message": f"已记录反馈({status_map.get(status, status)})，为您重新推荐！",
                    "need_re_recommend": True, "user_id": user_id, "new_recommendation": new_rec}

        return {"success": True, "message": f"已记录反馈({status_map.get(status, status)})，下次推荐更精准~"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_user_profile(user_id: str) -> dict:
    """查看用户饮食档案和推荐统计（接受率等）"""
    try:
        user = MemoryStorage.get_user(user_id)
        if not user: return {"success": False, "message": "未找到用户档案", "user_id": user_id}
        records = MemoryStorage.get_user_recommendations(user_id, limit=100)
        total = len(records)
        acc = sum(1 for r in records if r.get("status") in ["accepted", "liked"])
        rej = sum(1 for r in records if r.get("status") == "rejected")
        return {"success": True, "user_id": user_id,
                "profile": {"taste_preferences": user.get("taste_preferences", []),
                            "dietary_restrictions": user.get("dietary_restrictions", []),
                            "favorite_cuisines": user.get("favorite_cuisines", []),
                            "dislike_foods": user.get("dislike_foods", []),
                            "allergies": user.get("allergies", []),
                            "health_goals": user.get("health_goals", "")},
                "recommendation_stats": {"total": total, "accepted": acc, "rejected": rej,
                                         "acceptance_rate": round(acc / total * 100, 1) if total > 0 else 0}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def recommend_with_image(user_id: str, food_name: str = "", session_id: str = "",
                         taste_preferences: list = None, dietary_restrictions: list = None) -> dict:
    """推荐美食并附带美食图片"""
    try:
        rec = None
        record_id = ""
        if food_name:
            found = None
            for c, ci in FOOD_KNOWLEDGE_BASE.items():
                for d in ci["typical_dishes"]:
                    if d["name"] == food_name:
                        rec = {"food_name": d["name"], "cuisine_type": c, "cuisine_style": ci["style"],
                               "taste": d.get("taste", ""), "spicy_level": d.get("spicy_level", 0),
                               "description": d.get("description", ""), "image_url": ""}
                        record = MemoryStorage.add_recommendation(user_id, rec)
                        record_id = record["id"]
                        found = True
                        break
                if found: break
            if not found: return {"success": False, "message": f"未找到菜品「{food_name}」"}
        else:
            prefs = {}
            if taste_preferences is not None: prefs["taste_preferences"] = taste_preferences
            if dietary_restrictions is not None: prefs["dietary_restrictions"] = dietary_restrictions
            r = FoodRecommendationEngine.recommend(user_id, prefs if prefs else None)
            if not r.get("success") or not r.get("recommendation"): return r
            rec = r["recommendation"]
            record_id = r.get("record_id", "")

        fn = rec["food_name"]
        image = FoodImageService.search_food_image(fn)
        rec["image_url"] = image.get("image_url", "")

        if session_id:
            MemoryStorage.append_dialogue(session_id, "assistant", f"推荐: {fn} (含图片)", {"image": image})

        return {"success": True, "message": f"推荐：{fn}！{rec.get('description', '')} 图片: {image.get('image_url', '')}",
                "food_name": fn, "recommendation": rec, "image": image,
                "record_id": record_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ====== 🔥 核心新功能：对话中菜名 → 返回图片 ======

@mcp.tool()
def detect_and_show_food(user_id: str, user_message: str, session_id: str = "") -> dict:
    """
    检测用户对话中提到的菜名，找到后返回该菜品的详细介绍 + 真实美食图片。
    在跟机器人聊天时用户提到菜名，调用此工具获取相关图片显示在设备上。

    参数:
    - user_id: 用户标识
    - user_message: 用户说的对话文本，例如"我想吃麻婆豆腐"
    - session_id: (可选) 会话ID，用于记忆上下文
    """
    try:
        # 检测菜名
        food_name = FoodNameDetector.detect_food_name(user_message)
        if not food_name:
            return {"success": False, "message": "未在对话中检测到已知菜名",
                    "food_name": None, "has_image": False}

        # 查找菜系信息
        cuisine = FoodNameDetector.get_cuisine_for_dish(food_name)
        dish_detail = None
        if cuisine in FOOD_KNOWLEDGE_BASE:
            for d in FOOD_KNOWLEDGE_BASE[cuisine]["typical_dishes"]:
                if d["name"] == food_name:
                    dish_detail = d
                    break

        # 记录推荐
        rec = {"food_name": food_name, "cuisine_type": cuisine,
               "description": dish_detail.get("description", "") if dish_detail else f"美味的{food_name}",
               "image_url": ""}
        record = MemoryStorage.add_recommendation(user_id, rec)

        # 搜索图片
        image = FoodImageService.search_food_image(food_name)

        # 保存到会话记忆
        if session_id:
            MemoryStorage.append_dialogue(session_id, "user", user_message,
                                          {"detected_food": food_name})
            MemoryStorage.append_dialogue(session_id, "assistant",
                                          f"为您展示 {food_name} 的图片", {"image": image})

        # 构建描述
        if dish_detail:
            desc = f"「{food_name}」— {cuisine}经典菜品，{dish_detail.get('taste', '')}口味"
            if dish_detail.get("spicy_level", 0) > 0:
                desc += f"，辣度{dish_detail['spicy_level']}/5"
            desc += f"。{dish_detail.get('description', '')}"
        else:
            desc = f"「{food_name}」— 美味佳肴"

        # 将图片URL嵌入消息，这样云端LLM可以告诉设备展示图片
        result_msg = f"{desc} 图片: {image.get('image_url', '')}"

        return {"success": True, "message": result_msg,
                "food_name": food_name, "cuisine": cuisine,
                "description": desc,
                "image": image, "has_image": True,
                "record_id": record["id"]}

    except Exception as e:
        logger.error(f"检测菜名失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_food_image(user_id: str, food_name: str, session_id: str = "") -> dict:
    """
    根据用户指定的菜名直接返回美食图片。
    当用户明确说"看看XXX的图片"或"XXX长什么样"时调用此工具。

    参数:
    - user_id: 用户标识
    - food_name: 菜品名称，如"麻婆豆腐"、"北京烤鸭"
    - session_id: (可选) 会话ID
    """
    try:
        # 检测菜名
        detected = FoodNameDetector.detect_food_name(food_name)
        target_name = detected if detected else food_name

        # 查找菜系
        cuisine = FoodNameDetector.get_cuisine_for_dish(target_name)
        dish_detail = None
        if cuisine in FOOD_KNOWLEDGE_BASE:
            for d in FOOD_KNOWLEDGE_BASE[cuisine]["typical_dishes"]:
                if d["name"] == target_name:
                    dish_detail = d
                    break

        # 搜索图片
        image = FoodImageService.search_food_image(target_name)

        # 记录
        rec = {"food_name": target_name, "cuisine_type": cuisine,
               "description": dish_detail.get("description", "") if dish_detail else f"美味的{target_name}",
               "image_url": image.get("image_url", "")}
        record = MemoryStorage.add_recommendation(user_id, rec)

        if session_id:
            MemoryStorage.append_dialogue(session_id, "assistant",
                                          f"展示 {target_name} 的图片", {"image": image})

        return {"success": True, "message": f"为您找到 {target_name} 的美食图片！图片: {image.get('image_url', '')}",
                "food_name": target_name, "cuisine": cuisine,
                "image": image, "has_image": True,
                "description": dish_detail.get("description", f"美味的{target_name}") if dish_detail else f"美味的{target_name}",
                "record_id": record["id"]}

    except Exception as e:
        logger.error(f"获取美食图片失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_recommendation_history(user_id: str, limit: int = 10) -> dict:
    """查看用户的推荐历史记录"""
    try:
        records = MemoryStorage.get_user_recommendations(user_id, limit=min(limit, 50))
        if not records: return {"success": True, "message": "暂无推荐记录", "records": []}
        stats = {}
        for r in records: s = r.get("status", "pending"); stats[s] = stats.get(s, 0) + 1
        return {"success": True, "message": f"共 {len(records)} 条记录", "records": records, "statistics": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def manage_session(session_id: str, action: str, user_id: str = "", stage: str = "", choice: str = "",
                   options: list = None, task_key: str = "", task_value: str = "", context_data: str = "") -> dict:
    """管理对话会话记忆（开始/剧情选择/任务进度/上下文）"""
    try:
        if action == "start":
            MemoryStorage.save_session(session_id, {"session_id": session_id, "user_id": user_id,
                "created_at": datetime.now().isoformat(), "dialogues": [], "context": {"user_id": user_id},
                "story_choices": [], "current_stage": stage or "greeting", "task_progress": {}})
            return {"success": True, "message": "会话已创建", "session_id": session_id}
        elif action == "choice":
            MemoryStorage.update_story_choice(session_id, {"choice": choice, "options": options or [],
                "selected": choice, "next_stage": stage or ""})
            return {"success": True, "message": f"已记录选择: {choice}", "current_stage": stage}
        elif action == "progress":
            td = {task_key: task_value} if task_key else {}
            if context_data:
                try: td.update(json.loads(context_data))
                except: pass
            p = MemoryStorage.update_task_progress(session_id, td)
            return {"success": True, "message": "进度已更新", "task_progress": p}
        elif action == "get_state":
            s = MemoryStorage.get_session(session_id)
            if not s: return {"success": False, "message": "会话不存在"}
            return {"success": True, "session_id": session_id, "user_id": s.get("user_id", ""),
                    "current_stage": s.get("current_stage", ""), "dialogues_count": len(s.get("dialogues", [])),
                    "story_choices": s.get("story_choices", []), "task_progress": s.get("task_progress", {}),
                    "context": s.get("context", {})}
        else:
            return {"success": False, "error": f"未知操作: {action}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cuisine_info(cuisine_name: str = "") -> dict:
    """查询菜系信息和经典菜品"""
    try:
        if cuisine_name:
            c = FOOD_KNOWLEDGE_BASE.get(cuisine_name)
            if not c: return {"success": False, "message": f"未找到菜系「{cuisine_name}」"}
            return {"success": True, "cuisine": cuisine_name, "description": c["description"],
                    "style": c["style"], "typical_dishes": c["typical_dishes"]}
        return {"success": True, "cuisines": {
            n: {"description": i["description"], "style": i["style"],
                "dish_count": len(i["typical_dishes"])}
            for n, i in FOOD_KNOWLEDGE_BASE.items()}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def search_food(query: str, max_results: int = 5) -> dict:
    """搜索菜品信息"""
    try:
        results = []
        ql = query.lower()
        for c, ci in FOOD_KNOWLEDGE_BASE.items():
            for d in ci["typical_dishes"]:
                if ql in d["name"].lower() or ql in d.get("description", "").lower() or ql in c.lower() or ql in ci["style"].lower():
                    relevance = (3 if ql in d["name"].lower() else 0) + \
                                (2 if ql in c.lower() else 0) + \
                                (1 if ql in d.get("description", "").lower() else 0)
                    results.append({"food_name": d["name"], "cuisine": c, "cuisine_style": ci["style"],
                                    "taste": d.get("taste", ""), "spicy_level": d.get("spicy_level", 0),
                                    "description": d.get("description", ""), "relevance": relevance})
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return {"success": True, "query": query, "total_results": len(results), "results": results[:max_results]}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("=" * 60)
    print("🍽️  小智AI美食推荐官 v3.0")
    print("📝  记忆型美食推荐系统 (多级图片搜索)")
    print("🔧  偏好记忆 · 饮食禁忌 · 菜名检测 · 图文展示")
    print("=" * 60)
    print(f"📂 数据目录: {DATA_DIR}")
    print(f"🌐 图片源: 必应 > 百度 > Unsplash > 备用")
    print(f"🔍 支持 {len(FoodNameDetector.ALL_KNOWN_DISHES) if FoodNameDetector.ALL_KNOWN_DISHES else '80+'} 种菜品检测")
    mcp.run(transport="stdio")
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Star, register, Context
from astrbot.api import logger
import random
import time
import os
import json

@register("keyword_landmine", "Care", "踩雷王 (词语版)", "1.0.6")
class KeywordLandminePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 读取同目录下的 config.json 文件（AstrBot 网页端会直接修改这个文件）
        self.config = self._load_config()

        # 核心设置
        self.enable = bool(self.config.get("enable", True))
        self.owner_id = str(self.config.get("owner_qq", "3524815759")).strip()
        self.owner_umo = f"llbot:FriendMessage:{self.owner_id}" if self.owner_id.isdigit() else None
        
        # 游戏参数设置
        self.mute_minutes = int(self.config.get("mute_minutes", 5))
        self.apply_groups = self.config.get("apply_groups", [])
        self.keyword_count = int(self.config.get("keyword_count", 5))
        self.min_len = int(self.config.get("min_keyword_len", 2))
        self.max_len = int(self.config.get("max_keyword_len", 4))
        
        # 指令开关设置 (对应网页配置)
        self.enable_today_cmd = bool(self.config.get("enable_today_cmd", True))
        self.enable_blur_cmd = bool(self.config.get("enable_blur_cmd", True))
        self.enable_rank_cmd = bool(self.config.get("enable_rank_cmd", True))
        self.enable_refresh_cmd = bool(self.config.get("enable_refresh_cmd", True))
        
        self.landmines = []
        self.step_records = {}
        self.last_refresh_date = ""
        self.refresh_landmines()

    def _load_config(self):
        """读取插件目录下的 config.json，供网页端和代码使用"""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取配置文件失败: {e}")
        return {}

    def refresh_landmines(self, force=False):
        today = time.strftime("%Y-%m-%d")
        if not force and today == self.last_refresh_date and self.landmines:
            return
        self.landmines = self._generate_landmines()
        self.step_records.clear()
        self.last_refresh_date = today
        logger.info(f"[雷词游戏] 雷词已刷新 → {self.landmines}")

    def _generate_landmines(self):
        chars = "的一是在不了和有大这主中人上为国地到说时大们产以事他为地于政经成以会可分生同老因其所同等部道想作经家国法同"
        return ["".join(random.choice(chars) for _ in range(random.randint(self.min_len, self.max_len))) 
                for _ in range(self.keyword_count)]

    def _blur(self, kw: str):
        if len(kw) <= 2:
            return kw[0] + "*" * (len(kw) - 1)
        return kw[0] + "*" * (len(kw) - 2) + kw[-1]

    @filter.command("今日雷词")
    async def generate_today(self, event: AstrMessageEvent):
        if not self.enable or not self.enable_today_cmd: return
        self.refresh_landmines()
        if not self.owner_umo:
            yield event.plain_result("⚠️ 未配置主人 QQ")
            return
        text = "【今日完整雷词】\n" + "\n".join(self.landmines) + "\n\n请勿泄露！"
        try:
            await self.context.send_message(self.owner_umo, MessageChain().message(text))
            yield event.plain_result("✅ 已私聊发送给主人")
        except Exception as e:
            yield event.plain_result(f"❌ 私聊失败：{str(e)}")

    @filter.command("今日雷点")
    async def show_blur(self, event: AstrMessageEvent):
        if not self.enable or not self.enable_blur_cmd: return
        self.refresh_landmines()
        blurred = [self._blur(k) for k in self.landmines]
        text = "【今日雷点】\n" + "\n".join(blurred) + "\n小心别踩雷哦～"
        yield event.plain_result(text)

    @filter.command("踩雷排行")
    async def show_rank(self, event: AstrMessageEvent):
        if not self.enable or not self.enable_rank_cmd: return
        self.refresh_landmines()
        if not self.step_records:
            yield event.plain_result("今日暂无踩雷记录～")
            return
        sorted_rank = sorted(self.step_records.items(), key=lambda x: x[1]["count"], reverse=True)
        lines = ["【今日踩雷排行榜】"]
        # 默认显示前5名，若需修改也可加入 config
        for i, (uid, data) in enumerate(sorted_rank[:5], 1):
            lines.append(f"{i}. {data['name']}（踩雷 {data['count']} 次）")
        yield event.plain_result("\n".join(lines))

    # 新增：刷新雷词指令
    @filter.command("刷新雷词")
    async def force_refresh_cmd(self, event: AstrMessageEvent):
        if not self.enable or not self.enable_refresh_cmd: return
        
        # 权限校验：只允许配置的主人刷新，防止群员乱刷
        if str(event.get_sender_id()) != self.owner_id:
            yield event.plain_result("⚠️ 权限不足：只有配置的主人可以刷新雷词！")
            return
            
        self.refresh_landmines(force=True)
        blurred = [self._blur(k) for k in self.landmines]
        yield event.plain_result("✅ 雷词已强制刷新！\n【最新雷点】\n" + "\n".join(blurred))

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def check_landmine(self, event: AstrMessageEvent):
        if not self.enable: return
        group_id = event.get_group_id()
        if self.apply_groups and str(group_id) not in [str(g) for g in self.apply_groups]:
            return
        self.refresh_landmines()
        msg = event.message_str.strip()
        if not msg: return
        triggered = [k for k in self.landmines if k in msg]
        if not triggered: return

        user_id = event.get_sender_id()
        user_name = event.get_sender_name() or "群员"
        if str(user_id) == self.owner_id:
            yield event.plain_result("主人踩雷了，本次不处罚～")
            return

        mute_sec = self.mute_minutes * 60
        try:
            await self.context.api.set_group_ban(group_id=group_id, user_id=user_id, duration=mute_sec)
            await self.context.api.set_group_card(group_id=group_id, user_id=user_id, card="踩雷王")
            
            uid = str(user_id)
            if uid not in self.step_records:
                self.step_records[uid] = {"name": user_name, "count": 0}
            self.step_records[uid]["count"] += 1
            self.step_records[uid]["name"] = user_name
            
            yield event.plain_result(f"💥 {user_name} 踩雷成功！已禁言 {self.mute_minutes} 分钟并改名为「踩雷王」")
        except Exception as e:
            yield event.plain_result(f"💥 {user_name} 踩雷！但 Bot 无管理权限，无法禁言和改名。")

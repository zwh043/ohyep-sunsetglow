"""Ohyep SunsetGlow 主程序。

主循环：遍历 地点 × 推送时段，对每个组合询问所有启用的数据源。
任一源 triggered=True 即合并成一条推送（标注各源理由），写入存储，去重。

推送时段（slot）：
- sunrise        朝霞：前一晚 sunrise_notify_hour 检查次日日出，推一次。
- sunset_afternoon 晚霞预告：当天 sunset_afternoon_hour（如15点）推一次。
- sunset_pre     晚霞临场：日落前 sunset_pre_hours_before 小时推一次。
晚霞两个时段独立去重，故同一次晚霞最多推两条（注意 Server酱免费版每天5条额度）。
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from zoneinfo import ZoneInfo

import yaml

from app.geocode import resolve_location
from app.pusher import build_notifier, format_message
from app.sources import build_sources
from app.storage import Storage
from app.web.server import run_web


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Bot:
    def __init__(self, config: dict):
        self.cfg = config
        sch = config.get("schedule", {})
        self.tz = sch.get("timezone", "Asia/Shanghai")
        self.sunrise_hour = sch.get("sunrise_notify_hour", 22)
        self.sunset_afternoon_hour = sch.get("sunset_afternoon_hour", 15)
        self.sunset_pre_lead = sch.get("sunset_pre_hours_before", 1)
        self.interval = sch.get("check_interval_minutes", 15) * 60

        self.sources = build_sources(config.get("sources", {}), os.environ)
        self.notifier = build_notifier(config.get("push", {}), os.environ)
        self.storage = Storage(config.get("storage", {}).get("db_path", "data/ohyep.db"))

        web_cfg = config.get("web", {})
        self.web_port = web_cfg.get("port", 8080)
        # 反馈链接：优先用 feedback_url（如公众号文章），否则回退本地网页
        self.feedback_url = web_cfg.get("feedback_url", "")
        if web_cfg.get("enabled", True):
            run_web(self.storage, web_cfg.get("host", "0.0.0.0"), self.web_port)

        print(f"启用数据源: {[s.label for s in self.sources]}")

    def _now(self) -> dt.datetime:
        return dt.datetime.now(ZoneInfo(self.tz))

    def _slots_to_check(self, now: dt.datetime) -> list:
        """返回当前应检查的 (kind, slot) 列表。窗口判断在 check 内结合 event_time。"""
        slots = []
        # 朝霞：前一晚 notify_hour 之后
        if now.hour >= self.sunrise_hour:
            slots.append(("朝霞", "sunrise"))
        # 晚霞预告：到达 afternoon_hour 之后（当天）
        if now.hour >= self.sunset_afternoon_hour:
            slots.append(("晚霞", "sunset_afternoon"))
        # 晚霞临场：日落前 lead 小时内（在 check 里用 event_time 精确判断）
        slots.append(("晚霞", "sunset_pre"))
        return slots

    def _in_pre_sunset_window(self, event_time: dt.datetime, now: dt.datetime) -> bool:
        lead = dt.timedelta(hours=self.sunset_pre_lead)
        return event_time - lead <= now <= event_time

    def check(self, location: dict, kind: str, slot: str, now: dt.datetime):
        preds = []
        for src in self.sources:
            try:
                preds.append(src.predict(location, kind, self.tz))
            except Exception as e:  # noqa: BLE001
                print(f"[{location['name']}|{kind}|{src.label}] 异常: {e}")

        valid = [p for p in preds if not p.error]
        if not valid:
            return

        event_time = valid[0].event_time
        event_date = event_time.date().isoformat()

        # 晚霞临场时段需在日落前 lead 窗口内
        if slot == "sunset_pre" and not self._in_pre_sunset_window(event_time, now):
            return

        # 去重：同地点同类型同事件日期同时段已推过则跳过
        if self.storage.has_pushed(location["name"], kind, event_date, slot):
            return

        triggered = [p for p in valid if p.triggered]
        if not triggered:
            tips = " | ".join(f"{p.source_label}:{p.score}" for p in valid)
            print(f"[{location['name']}|{kind}|{slot}] 未达标 {tips}")
            return

        # 日出日落时间（取自源①的 detail，若有）
        sun_info = self._sun_info(valid)

        web_url = self.feedback_url or f"http://localhost:{self.web_port}/"
        title, content = format_message(
            location["name"], kind, event_time, triggered, valid, web_url, sun_info, slot
        )
        print(f"[推送] {title}")
        sent = self.notifier.send(title, content)
        if sent or not self.notifier.configured():
            self.storage.record_push(
                location["name"], kind, event_date,
                event_time.strftime("%Y-%m-%d %H:%M"), triggered, slot=slot
            )
            if not sent:
                print("[推送] 未配置推送渠道，仅记录到数据库")
        else:
            print(f"[推送] 发送失败，下轮重试: {location['name']}|{kind}|{slot}")

    @staticmethod
    def _sun_info(preds: list) -> dict:
        """从预测里取日出日落时间（源①own_algo 的 detail 带 sunrise/sunset）。"""
        for p in preds:
            if p.detail.get("sunrise") or p.detail.get("sunset"):
                return {"sunrise": p.detail.get("sunrise", ""),
                        "sunset": p.detail.get("sunset", "")}
        return {}

    def run_once(self):
        now = self._now()
        print(f"\n=== 检查 {now.strftime('%Y-%m-%d %H:%M')} ===")
        slots = self._slots_to_check(now)
        for loc in self.cfg.get("locations", []):
            try:
                resolved = resolve_location(loc)
            except Exception as e:  # noqa: BLE001
                print(f"[{loc.get('name')}] 地理编码失败: {e}")
                continue
            for kind, slot in slots:
                try:
                    self.check(resolved, kind, slot, now)
                except Exception as e:  # noqa: BLE001
                    print(f"[{resolved['name']}|{kind}|{slot}] 检查异常: {e}")

    def run_forever(self):
        print(f"Ohyep SunsetGlow 启动，每 {self.interval//60} 分钟检查一次")
        while True:
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001
                print(f"[主循环] 异常: {e}")
            time.sleep(self.interval)


def main():
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    bot = Bot(load_config(config_path))
    if "--once" in sys.argv:
        bot.run_once()
    else:
        bot.run_forever()


if __name__ == "__main__":
    main()

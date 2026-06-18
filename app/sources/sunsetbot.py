"""源②：sunsetbot.top 抓取 —— 专业火烧云预测网站。

实测接口（2026-06 验证）：
  GET https://sunsetbot.top/
  参数: query_id=随机数, intend=select_city, query_city=中文城市名(必须中文),
        event_date=None, event=set_1(今天日落)|rise_2(明天日出), times=None
  返回 JSON 关键字段:
    tb_quality: "0.36（小烧）" 形式，需正则提取数值 + 保留中文等级
    tb_aod:     "0.486（小污）" 气溶胶
    tb_event_time: "2026-06-16 19:12:39"
    display_city_name: "广东省-广州"
    status: "ok" | "not_found"
"""
from __future__ import annotations

import datetime as dt
import random
import re

import requests

from app.sources.base import Prediction, PredictionSource


class SunsetBotSource(PredictionSource):
    name = "sunsetbot"
    label = "SunsetBot"

    BASE_URL = "https://sunsetbot.top/"

    def __init__(self, threshold: float = 0.30, timeout: int = 25, retries: int = 3):
        self.threshold = threshold       # 0-1
        self.timeout = timeout
        self.retries = retries

    def predict(self, location: dict, kind: str, tz: str) -> Prediction:
        event = "rise_2" if kind == "朝霞" else "set_1"
        # sunsetbot 用城市/区名查询（认识"天河区"等区级名）。
        # 优先用 sunsetbot_city，否则退回 name。经纬度对本源无用。
        query_city = location.get("sunsetbot_city") or location["name"]
        try:
            data = self._fetch(query_city, event)
        except Exception as e:  # noqa: BLE001
            return self._empty(location, kind, str(e))

        if data.get("status") != "ok":
            return self._empty(location, kind, f"未找到城市预报（{query_city}）")

        quality_str = data.get("tb_quality", "") or ""
        quality = self._extract_number(quality_str)
        aod_str = data.get("tb_aod", "") or ""
        event_time = self._parse_time(data.get("tb_event_time", ""), tz)

        triggered = quality is not None and quality >= self.threshold

        # 简洁理由：质量值+等级 + 气溶胶
        reason = f"质量 {quality_str}"
        if aod_str:
            reason += f", 气溶胶 {aod_str}"

        return Prediction(
            source_name=self.name,
            source_label=self.label,
            location=location["name"],
            kind=kind,
            event_time=event_time or dt.datetime.now(),
            triggered=triggered,
            score=round(quality * 100, 1) if quality is not None else None,
            raw_quality=quality_str,
            reason=reason,
            detail={
                "quality": quality,
                "aod": aod_str,
                "display_city": data.get("display_city_name", ""),
                "img_href": data.get("img_href", ""),
            },
        )

    def _fetch(self, city: str, event: str) -> dict:
        params = {
            "query_id": random.randint(1, 10_000_000),
            "intend": "select_city",
            "query_city": city,
            "event_date": "None",
            "event": event,
            "times": "None",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OhyepSunsetBot/1.0)",
            "X-Requested-With": "XMLHttpRequest",
        }
        last_err = None
        for _ in range(self.retries):
            try:
                resp = requests.get(self.BASE_URL, params=params,
                                    headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise RuntimeError(f"sunsetbot 请求失败: {last_err}")

    @staticmethod
    def _extract_number(s: str):
        """从 '0.36（小烧）' 提取 0.36。"""
        m = re.search(r"(\d+\.?\d*)", s)
        return float(m.group(1)) if m else None

    @staticmethod
    def _parse_time(s: str, tz: str):
        from zoneinfo import ZoneInfo
        try:
            return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(tz))
        except Exception:  # noqa: BLE001
            return None

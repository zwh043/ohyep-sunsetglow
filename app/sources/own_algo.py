"""源①：Ohyep算法 —— Open-Meteo 免费天气 API + 火烧云评分。

Open-Meteo 无需 API Key，传经纬度即可查任意地点的分高度云量、能见度、湿度。
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.meteo import get_forecast
from app.scoring import score_glow
from app.sources.base import Prediction, PredictionSource


class OwnAlgoSource(PredictionSource):
    name = "own_algo"
    label = "Ohyep算法"

    def __init__(self, threshold: float = 55, timeout: int = 20, retries: int = 3):
        self.threshold = threshold
        self.timeout = timeout
        self.retries = retries

    def predict(self, location: dict, kind: str, tz: str) -> Prediction:
        try:
            data = get_forecast(location["latitude"], location["longitude"], tz,
                                 timeout=self.timeout, retries=self.retries)
        except Exception as e:  # noqa: BLE001
            return self._empty(location, kind, str(e))

        event_time = self._event_time(data, kind, tz)
        if event_time is None:
            return self._empty(location, kind, "无日出/日落时间")

        samples = self._window(data, event_time, tz)
        if not samples:
            return self._empty(location, kind, "无对应时段云量数据")

        n = len(samples)
        avg = lambda key: sum(s[key] for s in samples) / n  # noqa: E731
        result = score_glow(
            avg_high=avg("high"), avg_mid=avg("mid"), avg_low=avg("low"),
            avg_vis=avg("vis"), avg_hum=avg("hum"),
        )

        # 附上事件当天的日出/日落时间（推送里展示）
        detail = dict(result["detail"])
        sr, ss = self._sun_times_of_day(data, event_time.date(), tz)
        detail["sunrise"] = sr.strftime("%H:%M") if sr else ""
        detail["sunset"] = ss.strftime("%H:%M") if ss else ""

        return Prediction(
            source_name=self.name,
            source_label=self.label,
            location=location["name"],
            kind=kind,
            event_time=event_time,
            triggered=result["value"] >= self.threshold,
            score=float(result["value"]),
            raw_quality=f"{result['value']}（{result['level']}）",
            reason=result["reason"],
            detail=detail,
        )

    def _fetch(self, lat: float, lon: float, tz: str) -> dict:
        # 已改用 app.meteo.get_forecast（带缓存，多源共享），保留此方法仅作兼容。
        return get_forecast(lat, lon, tz, timeout=self.timeout, retries=self.retries)

    @staticmethod
    def _event_time(data: dict, kind: str, tz: str):
        daily = data.get("daily", {})
        days = daily.get("time", [])
        key = "sunrise" if kind == "朝霞" else "sunset"
        arr = daily.get(key, [])
        tzinfo = ZoneInfo(tz)
        now = dt.datetime.now(tzinfo)

        candidates = []
        for i, d in enumerate(days):
            if i < len(arr) and arr[i]:
                t = dt.datetime.fromisoformat(arr[i]).replace(tzinfo=tzinfo)
                candidates.append(t)

        if kind == "朝霞":
            # 取下一个未过的日出（通常是明天早上）
            future = [t for t in candidates if t > now]
            return future[0] if future else (candidates[0] if candidates else None)
        else:
            # 晚霞：取今天的日落（若已过则取下一个）
            today = now.date()
            same_day = [t for t in candidates if t.date() == today]
            if same_day:
                return same_day[0]
            future = [t for t in candidates if t > now]
            return future[0] if future else (candidates[0] if candidates else None)

    @staticmethod
    def _sun_times_of_day(data: dict, day, tz: str):
        """取指定日期的 (日出, 日落) datetime，缺失返回 (None, None)。"""
        daily = data.get("daily", {})
        days = daily.get("time", [])
        sunrises = daily.get("sunrise", [])
        sunsets = daily.get("sunset", [])
        tzinfo = ZoneInfo(tz)
        sr = ss = None
        for i, d in enumerate(days):
            if dt.date.fromisoformat(d) == day:
                if i < len(sunrises) and sunrises[i]:
                    sr = dt.datetime.fromisoformat(sunrises[i]).replace(tzinfo=tzinfo)
                if i < len(sunsets) and sunsets[i]:
                    ss = dt.datetime.fromisoformat(sunsets[i]).replace(tzinfo=tzinfo)
                break
        return sr, ss

    @staticmethod
    def _window(data: dict, event_time: dt.datetime, tz: str) -> list[dict]:
        """取事件前后各 1 小时的逐小时数据。"""
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        tzinfo = ZoneInfo(tz)
        start = (event_time - dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        end = (event_time + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        def num(arr, i):
            if arr is None or i >= len(arr) or arr[i] is None:
                return 0.0
            return float(arr[i])

        out = []
        for i, t in enumerate(times):
            ht = dt.datetime.fromisoformat(t).replace(tzinfo=tzinfo)
            if start <= ht <= end:
                out.append({
                    "high": num(hourly.get("cloud_cover_high"), i),
                    "mid": num(hourly.get("cloud_cover_mid"), i),
                    "low": num(hourly.get("cloud_cover_low"), i),
                    "vis": num(hourly.get("visibility"), i),
                    "hum": num(hourly.get("relative_humidity_2m"), i),
                })
        return out

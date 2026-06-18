"""源③：彩云天气 + Ohyep算法。

彩云天气需免费注册 token：https://platform.caiyunapp.com/
填 config.yaml 的 sources.caiyun.token 或环境变量 CAIYUN_TOKEN。

要点：
- 彩云 hourly 接口只给**总云量** cloudrate（0-1），不分高/中/低层，
  因此用 app.scoring.score_glow_total 评分（总云量"适中最好"）。
- 彩云 daily 的 astro（日出日落）实测为空，故事件时刻（日出/日落）改用
  Open-Meteo 免费 daily 接口获取（无需 Key）。
- 单位换算：cloudrate(0-1)→%(×100)，visibility(km)→m(×1000)，humidity(0-1)→%(×100)。
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import requests

from app.meteo import get_forecast
from app.scoring import score_glow_total
from app.sources.base import Prediction, PredictionSource


class CaiyunSource(PredictionSource):
    name = "caiyun"
    label = "彩云天气"

    BASE_URL = "https://api.caiyunapp.com/v2.6"

    def __init__(self, token: str = "", threshold: float = 55,
                 timeout: int = 20, retries: int = 3):
        self.token = token
        self.threshold = threshold
        self.timeout = timeout
        self.retries = retries

    def predict(self, location: dict, kind: str, tz: str) -> Prediction:
        if not self.token:
            return self._empty(location, kind, "未配置彩云 token（源③未启用）")

        lat, lon = location["latitude"], location["longitude"]
        try:
            event_time = self._event_time(lat, lon, kind, tz)
        except Exception as e:  # noqa: BLE001
            return self._empty(location, kind, f"取日出日落时刻失败: {e}")
        if event_time is None:
            return self._empty(location, kind, "无日出/日落时间")

        try:
            hourly = self._fetch_hourly(lat, lon)
        except Exception as e:  # noqa: BLE001
            return self._empty(location, kind, str(e))

        samples = self._window(hourly, event_time, tz)
        if not samples:
            return self._empty(location, kind, "无对应时段云量数据")

        n = len(samples)
        avg = lambda key: sum(s[key] for s in samples) / n  # noqa: E731
        # 单位换算：彩云 cloudrate/humidity 为 0-1，visibility 为 km
        result = score_glow_total(
            avg_cloud=avg("cloud") * 100,
            avg_vis=avg("vis") * 1000,
            avg_hum=avg("hum") * 100,
        )

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
            detail=result["detail"],
        )

    # ---- 彩云 hourly 取数 ----
    def _fetch_hourly(self, lat: float, lon: float) -> dict:
        url = f"{self.BASE_URL}/{self.token}/{lon},{lat}/hourly"
        params = {"hourlysteps": 48}
        last_err = None
        for _ in range(self.retries):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                j = resp.json()
                if j.get("status") != "ok":
                    raise RuntimeError(f"彩云返回异常: {j.get('status')}")
                return j["result"]["hourly"]
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise RuntimeError(f"彩云请求失败: {last_err}")

    @staticmethod
    def _window(hourly: dict, event_time: dt.datetime, tz: str) -> list[dict]:
        """取事件前后各 1 小时的逐小时数据（cloudrate/visibility/humidity）。"""
        tzinfo = ZoneInfo(tz)
        start = (event_time - dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        end = (event_time + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        cloud = {d["datetime"]: d["value"] for d in hourly.get("cloudrate", [])}
        vis = {d["datetime"]: d["value"] for d in hourly.get("visibility", [])}
        hum = {d["datetime"]: d["value"] for d in hourly.get("humidity", [])}

        out = []
        for ts in cloud:
            ht = dt.datetime.fromisoformat(ts)
            if ht.tzinfo is None:
                ht = ht.replace(tzinfo=tzinfo)
            else:
                ht = ht.astimezone(tzinfo)
            if start <= ht <= end:
                out.append({
                    "cloud": float(cloud.get(ts, 0.0)),
                    "vis": float(vis.get(ts, 0.0)),
                    "hum": float(hum.get(ts, 0.0)),
                })
        return out

    # ---- 日出/日落时刻（彩云 astro 为空，复用 Open-Meteo 共享缓存）----
    def _event_time(self, lat: float, lon: float, kind: str, tz: str):
        data = get_forecast(lat, lon, tz, timeout=self.timeout, retries=self.retries)
        daily = data.get("daily", {})
        days = daily.get("time", [])
        key = "sunrise" if kind == "朝霞" else "sunset"
        arr = daily.get(key, [])
        tzinfo = ZoneInfo(tz)
        now = dt.datetime.now(tzinfo)

        candidates = []
        for i, _d in enumerate(days):
            if i < len(arr) and arr[i]:
                candidates.append(dt.datetime.fromisoformat(arr[i]).replace(tzinfo=tzinfo))

        if kind == "朝霞":
            future = [t for t in candidates if t > now]
            return future[0] if future else (candidates[0] if candidates else None)
        today = now.date()
        same_day = [t for t in candidates if t.date() == today]
        if same_day:
            return same_day[0]
        future = [t for t in candidates if t > now]
        return future[0] if future else (candidates[0] if candidates else None)

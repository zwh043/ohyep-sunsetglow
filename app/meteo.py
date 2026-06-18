"""Open-Meteo 取数客户端（带 TTL 缓存）。

源①Ohyep算法和源③彩云都要用 Open-Meteo 的日出/日落时刻，源①还要逐小时云量。
为避免同一轮检查里对同一地点重复请求（多时段 × 多源），这里统一取数并缓存。
缓存键 = (lat, lon, tz)，默认 10 分钟过期（云量预报短时间内基本不变）。
"""
from __future__ import annotations

import time

import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# (lat, lon, tz) -> (fetched_at, data)
_cache: dict[tuple, tuple[float, dict]] = {}
_TTL = 600  # 秒


def get_forecast(lat: float, lon: float, tz: str,
                 timeout: int = 20, retries: int = 3, ttl: int = _TTL) -> dict:
    """取（并缓存）某地的逐小时云量/能见度/湿度 + 每日日出日落。"""
    key = (round(float(lat), 4), round(float(lon), 4), tz)
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "cloud_cover_high,cloud_cover_mid,cloud_cover_low,visibility,relative_humidity_2m",
        "daily": "sunrise,sunset",
        "timezone": tz,
        "forecast_days": 3,
    }
    last_err = None
    for _ in range(retries):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            _cache[key] = (now, data)
            return data
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Open-Meteo 请求失败: {last_err}")

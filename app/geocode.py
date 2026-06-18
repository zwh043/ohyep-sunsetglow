"""地理编码：中文城市名 → 经纬度。

用 Open-Meteo 免费地理编码 API（无需 Key），结果缓存到内存，
避免每轮循环重复请求。用户在 config 只需填中文城市名。
"""
from __future__ import annotations

import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# 内存缓存：城市名 -> (lat, lon)
_cache: dict[str, tuple[float, float]] = {}


def geocode(city: str, timeout: int = 15, retries: int = 3) -> tuple[float, float]:
    """把中文城市名转成 (纬度, 经度)。失败抛异常。"""
    if city in _cache:
        return _cache[city]

    params = {"name": city, "count": 1, "language": "zh", "format": "json"}
    last_err = None
    for _ in range(retries):
        try:
            resp = requests.get(GEOCODE_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if not results:
                raise ValueError(f"未找到城市：{city}")
            r = results[0]
            coord = (float(r["latitude"]), float(r["longitude"]))
            _cache[city] = coord
            return coord
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"地理编码失败（{city}）: {last_err}")


def resolve_location(loc: dict) -> dict:
    """补全地点的经纬度。

    - 若已填 latitude/longitude，直接用（手填优先，可盯具体拍摄点）。
    - 否则用城市名自动查。
    - sunsetbot_city（若有）原样保留，供 sunsetbot 源用区级名查询。
    返回带 name/latitude/longitude(/sunsetbot_city) 的 dict。
    """
    name = loc["name"]
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if lat is not None and lon is not None:
        out = {"name": name, "latitude": float(lat), "longitude": float(lon)}
    else:
        lat, lon = geocode(name)
        out = {"name": name, "latitude": lat, "longitude": lon}
    if loc.get("sunsetbot_city"):
        out["sunsetbot_city"] = loc["sunsetbot_city"]
    return out

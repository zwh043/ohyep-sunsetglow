"""火烧云评分算法（Ohyep算法核心，被 own_algo 源使用）。

物理原理：
1. 头顶/对面要有"幕布"——中高层云适中（约30-60%）时最易被低角度阳光染色。
   云太少没东西染，太厚则挡光发灰。
2. 地平线（太阳）方向低层云要少，否则光被挡住照不到上方的云。
3. 空气要通透——低能见度、高湿度（雾霾/水汽）会让颜色发灰变淡。
"""
from __future__ import annotations


def _triangular(x: float, low: float, peak: float, high: float) -> float:
    """三角隶属度：适中最好。peak 处=1，<=low 或 >=high 处=0。"""
    if x <= low or x >= high:
        return 0.0
    if x == peak:
        return 1.0
    if x < peak:
        return (x - low) / (peak - low)
    return (high - x) / (high - peak)


def _descending(x: float, good_below: float, bad_above: float) -> float:
    """越低越好。"""
    if x <= good_below:
        return 1.0
    if x >= bad_above:
        return 0.0
    return (bad_above - x) / (bad_above - good_below)


def _ascending(x: float, bad_below: float, good_above: float) -> float:
    """越高越好。"""
    if x >= good_above:
        return 1.0
    if x <= bad_below:
        return 0.0
    return (x - bad_below) / (good_above - bad_below)


def score_glow(avg_high: float, avg_mid: float, avg_low: float,
               avg_vis: float, avg_hum: float) -> dict:
    """输入云量/能见度/湿度的均值，输出评分与可解释理由。

    avg_vis 单位为米。返回 dict: {value, level, reason, detail}
    """
    f_high = _triangular(avg_high, low=5, peak=45, high=95)
    f_mid = _triangular(avg_mid, low=0, peak=35, high=85)
    f_low = _descending(avg_low, good_below=15, bad_above=70)
    f_vis = _ascending(avg_vis, bad_below=8000, good_above=20000)
    f_hum = _descending(avg_hum, good_below=55, bad_above=90)

    canopy = 0.6 * f_high + 0.4 * f_mid       # 幕布充分度
    clarity = 0.6 * f_vis + 0.4 * f_hum       # 空气通透度
    blocking = f_low                          # 低云不挡光程度

    raw = 0.50 * canopy + 0.25 * clarity + 0.25 * blocking

    # 几乎没有中高云 → 没东西可染，大幅降分
    if avg_high < 5 and avg_mid < 5:
        raw *= 0.2

    value = max(0, min(100, int(round(raw * 100))))

    # 简洁但含关键信息的理由：高云/中云/低云 + 评分 + 等级
    level = _level_of(value)
    reason = (f"高云{avg_high:.0f}% 中云{avg_mid:.0f}% 低云{avg_low:.0f}%, "
              f"能见度{avg_vis/1000:.0f}km, 评分{value}（{level}）")

    detail = {
        "avg_high": round(avg_high, 1),
        "avg_mid": round(avg_mid, 1),
        "avg_low": round(avg_low, 1),
        "avg_visibility_km": round(avg_vis / 1000, 1),
        "avg_humidity": round(avg_hum, 1),
    }
    return {"value": value, "level": level, "reason": reason, "detail": detail}


def _level_of(value: int) -> str:
    if value >= 80:
        return "极佳"
    if value >= 70:
        return "很好"
    if value >= 55:
        return "不错"
    if value >= 40:
        return "一般"
    return "较差"


def score_glow_total(avg_cloud: float, avg_vis: float, avg_hum: float) -> dict:
    """彩云专用评分：彩云只给总云量(cloudrate)，不分高/中/低层。

    输入均为百分比/米（调用方需先把彩云的 0-1 和公里换算好）：
      avg_cloud: 总云量 %（0-100）
      avg_vis:   能见度 米
      avg_hum:   相对湿度 %（0-100）

    总云量"适中最好"：约40-70%时最容易出火烧云（有幕布又不至于全遮）。
    因无法区分低云挡光，准确度略逊分层算法，作为多源对照之一。
    """
    f_cloud = _triangular(avg_cloud, low=10, peak=55, high=95)
    f_vis = _ascending(avg_vis, bad_below=8000, good_above=20000)
    f_hum = _descending(avg_hum, good_below=55, bad_above=90)

    clarity = 0.6 * f_vis + 0.4 * f_hum
    raw = 0.6 * f_cloud + 0.4 * clarity

    # 几乎无云 → 没东西可染
    if avg_cloud < 8:
        raw *= 0.2

    value = max(0, min(100, int(round(raw * 100))))
    level = _level_of(value)
    reason = (f"总云量{avg_cloud:.0f}%, 能见度{avg_vis/1000:.0f}km, "
              f"湿度{avg_hum:.0f}%, 评分{value}（{level}）")
    detail = {
        "avg_cloud": round(avg_cloud, 1),
        "avg_visibility_km": round(avg_vis / 1000, 1),
        "avg_humidity": round(avg_hum, 1),
    }
    return {"value": value, "level": level, "reason": reason, "detail": detail}

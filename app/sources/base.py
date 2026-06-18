"""统一预测数据结构与数据源抽象基类。

三个数据源（Ohyep算法 / sunsetbot.top / 彩云）都输出统一的 Prediction，
主循环只看 triggered 字段决定是否推送，不关心各源内部如何计算。
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Prediction:
    """一个数据源对某地某次朝霞/晚霞的预测结果。"""
    source_name: str                 # 源标识，如 "own_algo" / "sunsetbot" / "caiyun"
    source_label: str                # 源中文名，如 "Ohyep算法" / "SunsetBot"
    location: str                    # 地点中文名
    kind: str                        # "朝霞" 或 "晚霞"
    event_time: dt.datetime          # 日出/日落时刻
    triggered: bool                  # 是否达到该源阈值（决定是否推送）
    score: Optional[float] = None    # 归一化评分（Ohyep算法 0-100，sunsetbot 转成 0-100）
    raw_quality: Optional[str] = None  # 原始质量值/标签，如 "0.36（小烧）"
    reason: str = ""                 # 一句话理由
    detail: dict = field(default_factory=dict)  # 调试用分项数据
    error: Optional[str] = None      # 取数失败时的错误信息

    def short_line(self) -> str:
        """推送里这一源的简短描述。"""
        if self.error:
            return f"[{self.source_label}] 取数失败：{self.error}"
        return f"[{self.source_label}] {self.reason}"


class PredictionSource(ABC):
    """数据源抽象接口。每个源实现 predict()，返回该地该事件的 Prediction。"""

    name: str = "base"
    label: str = "基础源"

    @abstractmethod
    def predict(self, location: dict, kind: str, tz: str) -> Prediction:
        """
        location: {"name","latitude","longitude"}
        kind: "朝霞" 或 "晚霞"
        返回 Prediction（即便 triggered=False 也要返回，便于记录和调试）。
        """
        ...

    def _empty(self, location: dict, kind: str, error: str) -> Prediction:
        """构造一个取数失败的占位 Prediction。"""
        return Prediction(
            source_name=self.name,
            source_label=self.label,
            location=location["name"],
            kind=kind,
            event_time=dt.datetime.now(),
            triggered=False,
            error=error,
        )

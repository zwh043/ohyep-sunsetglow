"""数据源工厂：根据配置构建启用的预测源列表。"""
from __future__ import annotations

import os

from app.sources.base import PredictionSource
from app.sources.caiyun import CaiyunSource
from app.sources.own_algo import OwnAlgoSource
from app.sources.sunsetbot import SunsetBotSource


def build_sources(sources_cfg: dict, env=None) -> list[PredictionSource]:
    """根据 config 的 sources 段构建启用的源。环境变量优先。"""
    env = env if env is not None else os.environ
    sources: list[PredictionSource] = []

    own = sources_cfg.get("own_algo", {})
    if own.get("enabled"):
        sources.append(OwnAlgoSource(threshold=own.get("threshold", 55)))

    sb = sources_cfg.get("sunsetbot", {})
    if sb.get("enabled"):
        sources.append(SunsetBotSource(threshold=sb.get("threshold", 0.30)))

    cy = sources_cfg.get("caiyun", {})
    if cy.get("enabled"):
        token = env.get("CAIYUN_TOKEN") or cy.get("token", "")
        sources.append(CaiyunSource(token=token, threshold=cy.get("threshold", 55)))

    return sources

"""推送模块：Server酱·Turbo（已验证 SendKey 形如 SCT...）+ WxPusher 预留。

多源汇总：把所有触发的源合并成一条 Markdown 消息推送。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import requests


class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, content: str) -> bool:
        ...

    def configured(self) -> bool:
        """是否已配置可用凭据（决定主循环失败时是否重试）。"""
        return True


class ServerChanNotifier(Notifier):
    """Server酱·Turbo：POST https://sctapi.ftqq.com/<KEY>.send
    表单字段 title + desp(支持 Markdown)。"""

    def __init__(self, send_key: str, timeout: int = 15):
        self.send_key = send_key
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.send_key)

    def send(self, title: str, content: str) -> bool:
        if not self.send_key:
            print("[ServerChan] 未配置 SendKey，跳过推送")
            return False
        url = f"https://sctapi.ftqq.com/{self.send_key}.send"
        try:
            resp = requests.post(url, data={"title": title, "desp": content},
                                 timeout=self.timeout)
            resp.raise_for_status()
            j = resp.json()
            if j.get("code") == 0:
                return True
            print(f"[ServerChan] 返回异常: {j}")
            return False
        except Exception as e:  # noqa: BLE001
            print(f"[ServerChan] 推送失败: {e}")
            return False


class WxPusherNotifier(Notifier):
    """WxPusher App 推送（预留）。"""

    API = "https://wxpusher.zjiecode.com/api/send/message"

    def __init__(self, app_token: str, uids=None, topic_ids=None, timeout: int = 15):
        self.app_token = app_token
        self.uids = uids or []
        self.topic_ids = topic_ids or []
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.app_token)

    def send(self, title: str, content: str) -> bool:
        if not self.app_token:
            print("[WxPusher] 未配置 app_token，跳过推送")
            return False
        payload = {
            "appToken": self.app_token,
            "content": f"## {title}\n\n{content}",
            "contentType": 3,
            "uids": self.uids,
            "topicIds": self.topic_ids,
        }
        try:
            resp = requests.post(self.API, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            j = resp.json()
            if j.get("code") == 1000:
                return True
            print(f"[WxPusher] 返回异常: {j}")
            return False
        except Exception as e:  # noqa: BLE001
            print(f"[WxPusher] 推送失败: {e}")
            return False


class MultiNotifier(Notifier):
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def configured(self) -> bool:
        """任一渠道已配置即视为可推送。"""
        return any(n.configured() for n in self.notifiers)

    def send(self, title: str, content: str) -> bool:
        ok = False
        for n in self.notifiers:
            if n.send(title, content):
                ok = True
        return ok


def build_notifier(push_cfg: dict, env) -> Notifier:
    notifiers: list[Notifier] = []
    sc = push_cfg.get("serverchan", {})
    if sc.get("enabled"):
        key = env.get("SERVERCHAN_SENDKEY") or sc.get("send_key", "")
        notifiers.append(ServerChanNotifier(key))
    wx = push_cfg.get("wxpusher", {})
    if wx.get("enabled"):
        token = env.get("WXPUSHER_APP_TOKEN") or wx.get("app_token", "")
        notifiers.append(WxPusherNotifier(token, wx.get("uids", []), wx.get("topic_ids", [])))
    return MultiNotifier(notifiers)


def _burn_level(triggered: list) -> str:
    """按触发源里的最高分映射烧级：80+大烧 / 70+中烧 / 其余小烧。

    各源 score 已统一到 0-100（Ohyep算法、彩云本就是；sunsetbot 是 quality×100）。
    无分数时兜底"小烧"。
    """
    scores = [p.score for p in triggered if getattr(p, "score", None) is not None]
    top = max(scores) if scores else 0
    if top >= 80:
        return "大烧"
    if top >= 70:
        return "中烧"
    return "小烧"


def format_message(location: str, kind: str, event_time, triggered: list,
                   all_preds: list, web_url: str = "",
                   sun_info: dict | None = None, slot: str = "") -> tuple[str, str]:
    """把触发的源合并成一条推送。

    triggered: 触发的 Prediction 列表（至少 1 个）
    all_preds: 全部源的 Prediction（用于附上未触发源的参考值）
    sun_info: {"sunrise","sunset"} 当天日出日落时间字符串
    slot: 推送时段标识，用于在标题区分"预告/临场"
    """
    sun_info = sun_info or {}
    emoji = "🌅" if kind == "朝霞" else "🌇"
    et = event_time.strftime("%m-%d %H:%M") if event_time else "未知"

    # 时段标签（细分，放正文保留信息）
    slot_tag = {
        "sunrise": "明早预报",
        "sunset_afternoon": "今日预告",
        "sunset_pre": "临场提醒",
    }.get(slot, "")

    n_trig = len(triggered)
    # 2 个及以上源同时确认 = 强信号
    strong = n_trig >= 2
    strong_tag = "🔥强信号 " if strong else ""
    # 烧级：取触发源里最高分映射成 小烧/中烧/大烧
    burn = _burn_level(triggered)
    # 标题：🌇[🔥强信号 ]Ohyep SunsetGlow·朝霞预告·小烧
    title = f"{emoji}{strong_tag}Ohyep SunsetGlow·{kind}预告·{burn}"

    lines = [
        f"**{location} · {kind} · {et}**",
    ]
    # 当天日出日落时间（另起一行）
    sr, ss = sun_info.get("sunrise", ""), sun_info.get("sunset", "")
    if sr or ss:
        parts = []
        if sr:
            parts.append(f"日出 {sr}")
        if ss:
            parts.append(f"日落 {ss}")
        lines.append("")
        lines.append(f"_当天 {' · '.join(parts)}_")
    if slot_tag:
        lines.append(f"_推送时段：{slot_tag}_")
    if strong:
        lines += [
            "",
            f"🔥 **{n_trig} 个数据源同时看好，强信号，值得出门！**",
            "",
        ]
    else:
        lines += [
            "",
            f"共 **{n_trig}** 个数据源提示值得期待：",
            "",
        ]
    for p in triggered:
        lines.append(f"- ✅ **{p.source_label}**：{p.reason}")

    # 附上未触发的源作参考（多源对照）
    others = [p for p in all_preds if p not in triggered and not p.error]
    if others:
        lines.append("")
        lines.append("其他源参考：")
        for p in others:
            lines.append(f"- ⬜ {p.source_label}：{p.reason}")

    lines.append("")
    lines.append("---")
    lines.append("出现后欢迎反馈烧的程度，帮助优化预测准确率：")
    if web_url:
        lines.append(f"👉 [点此反馈]({web_url})")
    else:
        lines.append("（在反馈网页选择 未出现/小烧/中烧/大烧）")

    return title, "\n".join(lines)

"""本地反馈网页（Flask）。

功能：
- 首页列出历史推送，每条可点选 未出现/小烧/中烧/大烧 反馈
- 展示各数据源准确率统计
仅本地/局域网使用，无需登录。
"""
from __future__ import annotations

import json
import threading

from flask import Flask, redirect, render_template, request, url_for

from app.storage import FEEDBACK_LABELS, Storage


def create_app(storage: Storage) -> Flask:
    app = Flask(__name__)

    @app.template_filter("from_json")
    def from_json(s):  # noqa: ANN001
        try:
            return json.loads(s) if s else []
        except Exception:  # noqa: BLE001
            return []

    @app.route("/")
    def index():
        pushes = storage.list_pushes(limit=200)
        stats = storage.stats_by_source()
        return render_template("index.html", pushes=pushes, stats=stats,
                               labels=FEEDBACK_LABELS)

    @app.route("/feedback/<int:push_id>", methods=["POST"])
    def feedback(push_id: int):
        value = request.form.get("feedback", "")
        if value in FEEDBACK_LABELS:
            storage.set_feedback(push_id, value)
        return redirect(url_for("index"))

    return app


def run_web(storage: Storage, host: str, port: int):
    """在后台线程启动网页服务。"""
    app = create_app(storage)

    def _run():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"[Web] 反馈网页已启动: http://{host}:{port}")
    return t

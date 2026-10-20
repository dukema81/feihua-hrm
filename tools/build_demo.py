# -*- coding: utf-8 -*-
"""飞花HRM · 离线 DEMO 构建：起临时后端抓快照，内嵌前端与内存 mock 为单 HTML。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
PORT = int(os.environ.get("FEIHUA_PORT", "8885"))
OUT = os.path.join(ROOT, "demo", "feihua-hrm-demo.html")

SNAP_PATHS = [
    ("board", "/api/board"),
    ("departments", "/api/departments"),
    ("employees", "/api/employees"),
    ("attReport", "/api/attendance/report"),
    ("attendance", "/api/attendance"),
    ("leaves", "/api/leaves"),
    ("overtimes", "/api/overtimes"),
    ("payroll", "/api/payroll"),
    ("jobs", "/api/jobs"),
    ("candidates", "/api/candidates"),
    ("interviews", "/api/interviews"),
    ("perfCycles", "/api/perf/cycles"),
    ("perfScores", "/api/perf/scores"),
    ("trainings", "/api/trainings"),
    ("contracts", "/api/contracts"),
    ("headcount", "/api/reports/headcount"),
    ("rules", "/api/rules"),
    ("users", "/api/users"),
    ("logs", "/api/logs"),
    ("keys", "/api/keys"),
    ("webhooks", "/api/webhooks"),
    ("deliveries", "/api/webhooks/deliveries"),
    ("sync", "/api/sync/changes?since=2000-01-01"),
]

MODULES = ["app.js", "org.js", "time.js", "pay.js", "hire.js", "sys.js"]


def wait_up(base, timeout=40):
    dl = time.time() + timeout
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < dl:
        try:
            op.open(base + "/api/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def read(front, name):
    with open(os.path.join(ROOT, "frontend", name), encoding="utf-8") as f:
        return f.read()


def main():
    dbp = os.path.join(tempfile.mkdtemp(prefix="fh_demo_"), "demo.db")
    env = dict(os.environ, FEIHUA_DB=dbp, FEIHUA_PORT=str(PORT))
    proc = subprocess.Popen([sys.executable, os.path.join(BACKEND, "server.py")],
                            env=env, cwd=BACKEND,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % PORT
    try:
        assert wait_up(base), "临时后端启动失败"
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(base + "/api/auth/login", data=json.dumps(
                {"username": "admin", "password": "hr@2026"}).encode(),
                timeout=10) as r:
            token = json.loads(r.read())["token"]

        snap = {}
        for key, path in SNAP_PATHS:
            req = urllib.request.Request(base + path)
            req.add_header("Authorization", "Bearer " + token)
            try:
                with op.open(req, timeout=20) as r:
                    snap[key] = json.loads(r.read())
            except Exception as e:                            # noqa: BLE001
                print("快照跳过 %s: %s" % (key, e))
        if "webhooks" in snap and isinstance(snap["webhooks"], dict):
            snap["events"] = snap["webhooks"].get("events", [])
        print("快照完成：%d 项" % len(snap))
    finally:
        proc.terminate()

    app_js = ""
    for name in MODULES:
        app_js += "\n" + read("frontend", name)
    css = read("frontend", "style.css")
    html = read("frontend", "index.html")
    mock_js = open(os.path.join(ROOT, "tools", "demo_mock.js"), encoding="utf-8").read()

    mock_js = "window.__HRM_SNAPSHOT__ = %s;\n%s" % (
        json.dumps(snap, ensure_ascii=False, default=str), mock_js)

    html = html.replace('<link rel="stylesheet" href="style.css">',
                        "<style>" + css + "</style>")
    tags = "".join('<script src="%s"></script>\n' % m for m in MODULES)
    tags = tags.rstrip("\n")
    assert tags in html, "index.html 脚本引用与 MODULES 不一致"
    html = html.replace(tags, "<script>" + mock_js + "</script>\n<script>" + app_js + "</script>")
    html = html.replace("</body>",
        '<div style="position:fixed;right:10px;bottom:10px;z-index:999;background:#1f7a8c;'
        'color:#fff;font-size:11px;padding:3px 10px;border-radius:10px;opacity:.85">'
        "离线 DEMO · 数据存于浏览器内存</div></body>")
    assert "style.css" not in html and 'src="' not in html.split("<body>")[1], "仍有外链"

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("DEMO 输出：%s（%.1f KB）" % (OUT, os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()

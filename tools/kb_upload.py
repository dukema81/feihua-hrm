# -*- coding: utf-8 -*-
"""飞花HRM系统 · 文档批量上传知识库（分类 33 企业管理系统）"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = r"C:/Users/maxl/WorkBuddy/Claw/feihua-hrm"
BASE = "http://42.193.158.63"
CAT = 33
PASSWORD = "YCSpyVwt@J2UByom3#n6gb"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
REPLACE = "--replace" in sys.argv

DOCS = [
    ("docs/feihua-design.md", "飞花HRM系统建设方案",
     "「飞花HRM系统」完整建设方案 V1.0：建设背景与目标、八部门组织蓝图、零依赖总体架构"
     "（标准库 http.server + sqlite3 WAL）、员工全生命周期主线、四套状态机与闸口（员工四态/请假五态/"
     "候选人五态/薪资三态）、核心口径（考勤判定与弹性宽限、年假按工龄折算、加班 1.5/2/3 倍、"
     "个税七档累进、三险一金基数封顶、薪资勾稽公式、绩效四维加权、合同到期预警）、26 表数据模型、"
     "11 权限×8 角色矩阵、12 条业务规则、三通道集成（API Key / Webhook HMAC 签名 / 增量同步）、"
     "85+ REST 路由总览、15 页前端设计、非功能设计、六阶段实施计划与风险应对。",
     "飞花HRM,企业管理系统,HRM,人力资源,薪资核算,考勤,绩效,建设方案"),
    ("docs/feihua_design_v1.docx", "飞花HRM系统建设方案（docx 版）",
     "《飞花HRM系统建设方案》排版版本（Word V1.0，15 页），含封面、目录与全部 11 章内容。",
     "飞花HRM,企业管理系统,建设方案,docx"),
    ("docs/api.md", "飞花HRM系统 REST 接口契约",
     "85+ 路由的完整契约：统一响应包与状态码、多通道鉴权（会话令牌 4 种携带方式 / API Key fhk_）、"
     "Idempotency-Key 幂等、限流 240 次每分钟、认证与看板、组织与员工（建档/转正/离职闸口）、"
     "考勤（打卡/调整/月度汇总）、请假与加班（余额/重叠/36 小时上限闸口）、薪资（批次核算/发放/"
     "工资条勾稽）、招聘（职位/候选人/面试/Offer 闸口）、绩效与培训、合同风险与续签、"
     "报表与 CSV 导出、设置与日志、集成中心（Key/Webhook HMAC-SHA256 签名 14 种事件/增量同步）、"
     "错误示例与对接实施建议。",
     "飞花HRM,API,接口契约,REST,Webhook,增量同步,对接"),
    ("docs/feihua_api_v1.docx", "飞花HRM系统 REST 接口契约（docx 版）",
     "《飞花HRM系统 REST 接口契约》排版版本（Word V1.0，18 页），面向对接方提供。",
     "飞花HRM,API,docx,对接"),
    ("docs/test-report.md", "飞花HRM系统测试报告",
     "三层自动化测试 50 项全部通过（业务内核单元 21 / REST 接口 19 / 端到端 UI 10），"
     "另有业务主线冒烟 39 检查点、UI 巡检 15 页与离线 DEMO 冒烟 21 检查点；质量门禁 PASS。"
     "含分层策略与测试环境、关键验证点（四态闸口、余额与重叠拦截、加班上限、个税七档、"
     "社保基数封顶、工资条勾稽、权限隔离、Key 鉴权、幂等重放）、14 项缺陷台账（现象/根因/修复）、"
     "非功能验证（限流/并发/连接管理/审计）、验收对照与复现命令。",
     "飞花HRM,测试报告,质量门禁,自动化测试,Playwright"),
    ("docs/feihua_test_v1.docx", "飞花HRM系统测试报告（docx 版）",
     "《飞花HRM系统测试报告》排版版本（Word V1.0，9 页），含封面、目录与完整测试结论（50 项 + 39 检查点）。",
     "飞花HRM,测试报告,docx"),
    ("docs/user-guide.md", "飞花HRM系统项目说明与操作手册",
     "面向岗位的操作手册：启动与环境变量、八账号登录、界面骨架、15 个页面逐页操作说明、"
     "四类角色场景演练（HR 专员的一天 / 薪酬专员月末 / 部门经理季度 / 员工自助）、"
     "离线 DEMO 使用、8 条常见问题（转正绩效拦截、请假余额、打卡重复、批次状态、工资条权限、"
     "CSV 乱码、Webhook 失败）、运维指南（备份恢复、重置演示数据、健康检查、生产部署）。",
     "飞花HRM,操作手册,用户指南,HRM,人力资源"),
    ("docs/feihua_manual_v1.docx", "飞花HRM系统项目说明与操作手册（docx 版）",
     "《飞花HRM系统项目说明与操作手册》排版版本（Word V1.0，11 页）。",
     "飞花HRM,操作手册,docx"),
    ("demo/feihua-hrm-demo.zip", "飞花HRM系统离线演示（DEMO）",
     "单文件离线演示：解压后双击 HTML 即可用浏览器打开，无需服务与网络。内置确定性演示数据"
     "（8 部门 / 22 员工 / 30 天考勤 / 招聘漏斗 / 薪资批次），"
     "新建员工、提交请假、打卡、工资批次核算、API Key 生成等写操作都在浏览器内存里"
     "按与后端一致的口径真实计算（个税七档累进、社保基数封顶、年假按工龄折算）。",
     "飞花HRM,DEMO,离线演示,HRM,人力资源"),
]


def req(path, method="GET", data=None, token=None):
    r = urllib.request.Request(BASE + path, method=method)
    if data is not None:
        r.data = json.dumps(data).encode("utf-8")
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with OP.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:                                     # noqa: BLE001
            return e.code, {}


def curl_upload(path, title, desc, tags):
    full = os.path.join(ROOT, path)
    mime = "application/zip" if full.endswith(".zip") else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if full.endswith(".docx") else "text/markdown")
    cmd = ["curl", "-s", "--noproxy", "*",
           "-H", "Authorization: Bearer " + TOKEN,
           "-F", "file=@%s;type=%s" % (full, mime),
           "-F", "title=" + title,
           "-F", "description=" + desc,
           "-F", "categoryId=%d" % CAT,
           "-F", "tags=" + tags,
           BASE + "/api/documents/upload"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8", "ignore"))
    except Exception:                                         # noqa: BLE001
        return {"code": -1, "raw": out.stdout.decode("utf-8", "ignore")[:400],
                "err": out.stderr.decode("utf-8", "ignore")[:200]}


def existing(cat=CAT):
    st, j = req("/api/documents?categoryId=%d&pageNum=1&pageSize=200" % cat, token=TOKEN)
    data = j.get("data") or {}
    if isinstance(data, list):
        return data
    return data.get("records") or data.get("list") or []


def delete_doc(doc_id):
    return req("/api/documents/%s" % doc_id, "DELETE", token=TOKEN)


def build_demo_zip():
    src = os.path.join(ROOT, "demo", "feihua-hrm-demo.html")
    out = os.path.join(ROOT, "demo", "feihua-hrm-demo.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, "飞花HRM系统Demo.html")
        z.writestr("使用说明.txt",
                   "飞花HRM系统 · 离线演示\r\n"
                   "1. 解压后双击「飞花HRM系统Demo.html」，用浏览器打开即可，无需安装、无需联网。\r\n"
                   "2. 内置确定性演示数据：8 部门 / 22 员工 / 30 天考勤 / 招聘漏斗 / 薪资批次。\r\n"
                   "3. 新建员工、提交请假、打卡、工资批次核算、API Key 生成等写操作，都在浏览器内存里\r\n"
                   "   按与后端一致的口径真实计算（个税七档累进、社保基数封顶、年假按工龄折算）。\r\n"
                   "4. 账号：离线版固定以 admin（系统管理员）进入，便于一个人体验完整流程。\r\n"
                   "5. 完整版本（多账号 + 真实权限 + 落地数据）请部署 backend/server.py 后访问 http://127.0.0.1:8025/。\r\n")
    print("DEMO zip 重建：%.1f KB" % (os.path.getsize(out) / 1024.0))


def main():
    global TOKEN
    st, j = req("/api/auth/login", "POST", {"username": "admin", "password": PASSWORD})
    assert j.get("code") == 200, j
    TOKEN = j["data"]["token"]
    st, j = req("/api/users/whoami", token=TOKEN)
    print("whoami:", j.get("code"))

    build_demo_zip()

    if REPLACE:
        want = {t for _, t, _, _ in DOCS}
        for r in existing():
            if r.get("title") in want:
                st, j = delete_doc(r.get("id"))
                print("删除旧文档 %s id=%s -> %s" % (r.get("title"), r.get("id"), st))
                time.sleep(0.4)

    results = []
    for path, title, desc, tags in DOCS:
        j = curl_upload(path, title, desc, tags)
        code = j.get("code")
        doc_id = (j.get("data") or {}).get("id") if isinstance(j.get("data"), dict) else j.get("data")
        size = os.path.getsize(os.path.join(ROOT, path))
        print("%-32s code=%s id=%s %.1fKB" % (os.path.basename(path), code, doc_id, size / 1024.0))
        if code != 200:
            print("   !!", str(j)[:300])
        results.append((path, title, code, doc_id))
        time.sleep(1.2)

    ok = [r for r in results if r[2] == 200]
    print("\n上传成功 %d / %d" % (len(ok), len(results)))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "kb_upload_result.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": r[0], "title": r[1], "code": r[2], "id": r[3]} for r in results],
                  f, ensure_ascii=False, indent=2)
    st, j = req("/api/document-categories", token=TOKEN)
    for c in (j.get("data") or []):
        if isinstance(c, dict) and c.get("id") == CAT:
            print("cat%d docCount:" % CAT, c.get("docCount"))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""飞花HRM · 全链路冒烟：对运行中的服务（默认 8025）执行业务主线检查点"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("FH_BASE", "http://127.0.0.1:8025")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = [None]
N = [0]


def call(method, path, body=None, headers=None, token="keep"):
    h = {"Content-Type": "application/json"}
    if token == "keep" and TOKEN[0]:
        h["Authorization"] = "Bearer " + TOKEN[0]
    elif token:
        h["Authorization"] = "Bearer " + token
    for k, v in (headers or {}).items():
        h[k] = v
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=h)
    try:
        with OP.open(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return e.code, {}


def ck(cond, label):
    N[0] += 1
    print("%s #%02d %s" % ("✓" if cond else "✗", N[0], label))
    if not cond:
        sys.exit(1)


def main():
    st, r = call("GET", "/api/health", token="")
    ck(st == 200 and r["brand"] == "飞花HRM", "健康检查 brand=%s routes=%d" % (r.get("brand"), r.get("routes", 0)))
    st, r = call("POST", "/api/auth/login", {"username": "admin", "password": "hr@2026"}, token="")
    ck(st == 200 and r["token"], "admin 登录")
    TOKEN[0] = r["token"]
    ck(r["role"] == "admin" and len(r["perms"]) == 11, "权限矩阵 11 项")

    st, r = call("GET", "/api/board")
    ck(st == 200 and r["kpi"]["headcount"] >= 20, "驾驶舱 KPI 在职 %s" % r["kpi"]["headcount"])
    ck(len(r["attTrend"]) > 10, "考勤趋势 %d 个工作日" % len(r["attTrend"]))

    # 主数据
    st, r = call("GET", "/api/departments")
    ck(st == 200 and len(r["list"]) == 8, "部门 8 个")
    st, r = call("GET", "/api/employees")
    ck(st == 200 and r["total"] >= 20, "员工 %d 人" % r["total"])
    d = call("GET", "/api/employees/EMP001")[1]
    ck(d["years"] > 5 and d["quota"], "员工详情 工龄=%.1f 额度=%d 项" % (d["years"], len(d["quota"])))

    # 员工全链路
    empno = "SMK%03d" % (int(time.time()) % 800 + 100)
    r = call("POST", "/api/employees", {"no": empno, "name": "冒烟员工", "dept": "D04",
                                        "hireDate": "2026-10-10", "baseSalary": 11000})[1]
    ck(r["status"] == "试用期", "建档默认试用期")
    st, e = call("POST", "/api/employees/%s/stage" % empno, {"target": "已转正", "regularEval": ""})
    ck(st == 400 and "评估" in e["message"], "转正闸口缺评估拦截")
    call("POST", "/api/perf/scores", {"cycle": "2026-Q3", "emp": empno,
                                      "workQty": 85, "workQuality": 85, "cooperation": 80,
                                      "discipline": 90})
    st, _ = call("POST", "/api/employees/%s/stage" % empno, {"target": "已转正", "regularEval": "冒烟转正评估"})
    ck(st == 200, "转正成功")

    # 考勤
    import datetime
    cday = (datetime.date.today() - datetime.timedelta(days=40 + int(time.time()) % 15)).isoformat()
    r = call("POST", "/api/attendance/clock", {"emp": "EMP007", "date": cday, "time": "08:55"})[1]
    ck(r["action"] in ("clockIn", "clockOut"), "打卡 %s %s" % (r["action"], r.get("status")))
    rep = call("GET", "/api/attendance/report?month=" + cday[:7])[1]
    ck(rep["list"] and rep["list"][0]["rate"] > 0.8, "月度出勤汇总 %d 人" % len(rep["list"]))

    # 请假
    st, e = call("POST", "/api/leaves", {"emp": "EMP009", "type": "年假",
                                         "start": "2026-12-01", "end": "2026-12-30", "days": 22})
    ck(st == 400 and "余额" in e["message"], "年假余额不足拦截")
    r = call("POST", "/api/leaves", {"emp": "EMP009", "type": "事假",
                                     "start": "2026-12-01", "end": "2026-12-02"})[1]
    lv = r["no"]
    ck(r["days"] == 2, "请假单 %s %s 天" % (lv, r["days"]))
    st, _ = call("POST", "/api/leaves/%s/stage" % lv, {"target": "已批准"})
    ck(st == 200, "请假批准")
    st, _ = call("POST", "/api/leaves/%s/stage" % lv, {"target": "已销假"})
    ck(st == 200, "销假返还额度")

    # 加班
    r = call("POST", "/api/overtimes", {"emp": "EMP009", "hours": 3, "type": "周末"})[1]
    ot = r["no"]
    st, _ = call("POST", "/api/overtimes/%s/stage" % ot, {"target": "已批准"})
    ck(st == 200, "加班审批 %s" % ot)
    st, e = call("POST", "/api/overtimes", {"emp": "EMP019", "hours": 40, "type": "工作日"})
    ck(st == 400 and "上限" in e["message"], "月加班 36h 上限拦截")

    # 薪资
    existing = [x["month"] for x in call("GET", "/api/payroll")[1]["list"]]
    month = next(("2099-%02d" % m for m in range(1, 13) if "2099-%02d" % m not in existing),
                 "2098-01")
    r = call("POST", "/api/payroll", {"month": month})[1]
    ck(r["status"] == "草稿", "新建批次 %s" % month)
    st, e = call("POST", "/api/payroll/%s/stage" % month, {"target": "已发放"})
    ck(st == 400 and "核算" in e["message"], "未核算不可发放")
    r = call("POST", "/api/payroll/%s/calc" % month, {})[1]
    ck(r["slips"] >= 20, "核算 %d 条 应发 %.0f" % (r["slips"], r["gross"]))
    slips = call("GET", "/api/payroll/%s/payslips" % month)[1]["list"]
    p0 = slips[0]
    ck(abs(p0["net"] - (p0["gross"] - p0["socialIns"] - p0["hf"] - p0["tax"] - p0["absenceDed"])) < 0.01,
       "工资条勾稽 net=%.2f" % p0["net"])
    st, _ = call("POST", "/api/payroll/%s/stage" % month, {"target": "已发放"})
    ck(st == 200, "批次发放")

    # 招聘
    job = call("POST", "/api/jobs", {"title": "冒烟工程师", "dept": "D04", "salary": "12-18K"})[1]["no"]
    cand = call("POST", "/api/candidates", {"name": "冒烟候选", "job": job, "expected": 13000})[1]["no"]
    st, e = call("POST", "/api/candidates/%s/stage" % cand, {"target": "已发Offer",
                                                             "offerSalary": 13000, "feedback": "x"})
    ck(st == 400 and "面试" in e["message"], "Offer 前置面试闸口")
    call("POST", "/api/interviews", {"cand": cand, "interviewer": "王明", "at": "2026-10-26 14:00"})
    iv = call("GET", "/api/interviews?cand=" + cand)[1]["list"][0]
    call("POST", "/api/interviews/%d" % iv["id"], {"result": "通过", "score": 88, "feedback": "冒烟面试通过"})
    st, _ = call("POST", "/api/candidates/%s/stage" % cand, {"target": "已发Offer",
                                                             "offerSalary": 13500, "feedback": "通过"})
    ck(st == 200, "发 Offer")
    st, _ = call("POST", "/api/candidates/%s/stage" % cand, {"target": "已入职", "onboardDeptOk": True})
    ck(st == 200, "确认入职")

    # 绩效 / 培训 / 合同
    cyc = "SMK-Q%03d" % (int(time.time()) % 900)
    r = call("POST", "/api/perf/cycles", {"name": cyc, "period": "冒烟周期"})[1]
    st, e = call("POST", "/api/perf/cycles/%s/publish" % cyc, {})
    ck(st == 400 and "评分" in e["message"], "空周期归档拦截")
    call("POST", "/api/perf/scores", {"cycle": cyc, "emp": "EMP009", "workQty": 88,
                                      "workQuality": 90, "cooperation": 84, "discipline": 92})
    r = call("POST", "/api/perf/cycles/%s/publish" % cyc, {})[1]
    ck(r["scores"] == 1, "绩效归档发布")
    tr = call("GET", "/api/trainings")[1]["list"][0]["no"]
    st, _ = call("POST", "/api/trainings/%s/enroll" % tr, {"emp": "EMP008"})
    ck(st in (200, 400), "培训报名（满员则拦）")
    d = call("GET", "/api/contracts")[1]
    ck("risk" in d and "expiring" in d["risk"], "合同风险 预警=%d" % len(d["risk"]["expiring"]))

    # 幂等
    key = "smoke-" + str(int(time.time() * 1000))
    h = {"Idempotency-Key": key}
    import datetime as _dt
    _d = _dt.date(2028, 1, 1) + _dt.timedelta(days=int(time.time()) % 300)
    b = {"emp": "EMP009", "type": "事假", "start": _d.isoformat(),
         "end": (_d + _dt.timedelta(days=1)).isoformat()}
    r1 = call("POST", "/api/leaves", b, headers=h)[1]
    r2 = call("POST", "/api/leaves", b, headers=h)[1]
    ck(r1["no"] == r2["no"], "幂等重放同单号 %s" % r1["no"])

    # 集成
    r = call("POST", "/api/keys", {"name": "冒烟Key", "scope": "read"})[1]
    ck(r["key"].startswith("fhk_"), "API Key 明文 fhk_ 前缀")
    st, d = call("GET", "/api/employees", headers={"X-Hr-Key": r["key"]}, token="")
    ck(st == 200, "Key 鉴权 GET")
    st, e = call("POST", "/api/employees", {"no": "X", "name": "x", "dept": "D01",
                                            "hireDate": "2026-01-01"},
                 headers={"X-Hr-Key": r["key"]}, token="")
    ck(st == 403, "Key 只读 scope 写拦截")
    call("POST", "/api/webhooks/test", {})
    dv = call("GET", "/api/webhooks/deliveries")[1]["list"]
    ck(dv and dv[0]["event"] == "test.ping", "Webhook test.ping 投递记录")
    sync = call("GET", "/api/sync/changes?since=2026-01-01%2000%3A00%3A00")[1]
    ck(sync["changes"]["employees"], "增量同步 employees=%d" % len(sync["changes"]["employees"]))

    # 报表导出
    import urllib.request as ur
    req = ur.Request(BASE + "/api/reports/attendance.csv",
                     headers={"Authorization": "Bearer " + TOKEN[0]})
    raw = OP.open(req, timeout=20).read()
    ck(raw.decode("utf-8-sig").splitlines()[0].startswith("date"), "考勤 CSV 导出")

    st, r = call("GET", "/api/openapi.json")
    ck(len(r["paths"]) >= 45, "OpenAPI %d paths" % len(r["paths"]))

    print("\n冒烟完成：%d 项检查点全部通过" % N[0])


if __name__ == "__main__":
    main()

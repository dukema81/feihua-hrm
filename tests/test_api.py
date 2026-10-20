# -*- coding: utf-8 -*-
"""飞花HRM · REST 接口测试（角色隔离 / 全链路 / 闸口 / 幂等 / 集成通道）"""
import time


def test_health_and_version(api):
    st, r = api.call("GET", "/api/health")
    assert st == 200 and r["brand"] == "飞花HRM" and r["routes"] > 50
    st, r = api.call("GET", "/api/openapi.json")
    assert st == 200 and len(r["paths"]) > 40


def test_role_isolation(api, tok_maker):
    # 普通员工无薪资权限
    t = tok_maker("sunq")
    st, r = api.call("GET", "/api/payroll", token=t)
    assert st == 403
    st, r = api.call("GET", "/api/payroll/2026-09/payslips", token=t)
    assert st == 403
    # 员工无招聘写权限
    st, r = api.call("POST", "/api/jobs", {"title": "x", "dept": "D01"}, token=t)
    assert st == 403
    # 员工不能改规则
    st, r = api.call("PUT", "/api/rules/grace_min", {"value": "20"}, token=t)
    assert st == 403
    # 审计只读：能看薪资不能写
    t2 = tok_maker("shenj")
    st, r = api.call("GET", "/api/payroll", token=t2)
    assert st == 200
    st, r = api.call("POST", "/api/payroll", {"month": "2099-01"}, token=t2)
    assert st == 403
    # 薪酬专员不能建员工
    t3 = tok_maker("zhangx")
    st, r = api.call("POST", "/api/employees", {"no": "X1", "name": "x", "dept": "D01",
                                                "hireDate": "2026-10-01"}, token=t3)
    assert st == 403


def test_employee_full_chain(api):
    # 新建 → 试用期 → 转正（缺评估被拦 → 补齐后通过）→ 离职中 → 交接后离职
    r = api.ok("POST", "/api/employees", {
        "no": "EMP900", "name": "测试员工", "dept": "D04", "position": "工程师",
        "hireDate": "2026-10-01", "baseSalary": 12000})
    assert r["status"] == "试用期"
    # 转正闸口：缺评估
    st, e = api.call("POST", "/api/employees/EMP900/stage",
                     {"target": "已转正", "regularEval": ""})
    assert st == 400 and "评估" in e["message"]
    # 先给一条 60 分以上绩效（否则转正被绩效闸口拦截）
    api.ok("POST", "/api/perf/scores", {"cycle": "2026-Q3", "emp": "EMP900",
                                        "workQty": 80, "workQuality": 80,
                                        "cooperation": 80, "discipline": 80})
    api.ok("POST", "/api/employees/EMP900/stage",
           {"target": "已转正", "regularEval": "表现良好"})
    d = api.ok("GET", "/api/employees/EMP900")
    assert d["status"] == "已转正" and d["regularDate"]
    api.ok("POST", "/api/employees/EMP900/stage", {"target": "离职中"})
    st, e = api.call("POST", "/api/employees/EMP900/stage",
                     {"target": "已离职", "handoverDone": False})
    assert st == 400 and "交接" in e["message"]
    api.ok("POST", "/api/employees/EMP900/stage",
           {"target": "已离职", "handoverDone": True})
    d = api.ok("GET", "/api/employees/EMP900")
    assert d["status"] == "已离职"


def test_employee_duplicate_rejected(api):
    st, e = api.call("POST", "/api/employees", {
        "no": "EMP001", "name": "重复", "dept": "D01", "hireDate": "2026-10-01"})
    assert st == 400 and "已存在" in e["message"]


def test_attendance_clock_and_adjust(api):
    r = api.ok("POST", "/api/attendance/clock", {"emp": "EMP009", "time": "08:55"})
    assert r["action"] == "clockIn"
    # 重复上班打卡被拦
    st, e = api.call("POST", "/api/attendance/clock", {"emp": "EMP009", "time": "08:56"})
    assert st == 200 and e["action"] == "clockOut"    # 第二次视为下班打卡
    # 手工调整（迟到口径）
    r = api.ok("POST", "/api/attendance", {"emp": "EMP008", "date": "2026-10-20",
                                           "in": "09:40", "out": "18:10"})
    assert r["status"] == "迟到"
    # 报表
    rep = api.ok("GET", "/api/attendance/report")
    assert rep["list"] and rep["list"][0]["workdays"] > 0


def test_leave_chain_with_balance(api):
    # 余额检查：年假大额请假被拦
    st, e = api.call("POST", "/api/leaves", {"emp": "EMP009", "type": "年假",
                                             "start": "2026-12-01", "end": "2026-12-30",
                                             "days": 25})
    assert st == 400 and "余额" in e["message"]
    # 正常提交
    r = api.ok("POST", "/api/leaves", {"emp": "EMP009", "type": "事假",
                                       "start": "2026-12-01", "end": "2026-12-02",
                                       "reason": "家中有事"})
    no = r["no"]
    assert r["days"] == 2
    # 非审批人不能批
    st, e = api.call("POST", "/api/leaves/%s/stage" % no, {"target": "已批准"},
                     token=api.token)  # admin 有 leave.approve → 应通过
    assert st == 200
    # 销假返还
    api.ok("POST", "/api/leaves/%s/stage" % no, {"target": "已销假"})
    d = api.ok("GET", "/api/leaves?status=已销假")
    assert any(x["no"] == no for x in d["list"])


def test_leave_overlap_rejected(api):
    api.ok("POST", "/api/leaves", {"emp": "EMP007", "type": "事假",
                                   "start": "2026-11-01", "end": "2026-11-03"})
    st, e = api.call("POST", "/api/leaves", {"emp": "EMP007", "type": "事假",
                                             "start": "2026-11-02", "end": "2026-11-04"})
    assert st == 400 and "重叠" in e["message"]


def test_overtime_cap(api):
    # EMP019 已批 5h，再造 40h 一次性超过月上限 36h
    st, e = api.call("POST", "/api/overtimes", {"emp": "EMP019", "hours": 40,
                                                "type": "工作日"})
    assert st == 400 and "上限" in e["message"]
    r = api.ok("POST", "/api/overtimes", {"emp": "EMP008", "hours": 2, "type": "周末"})
    no = r["no"]
    st, e = api.call("POST", "/api/overtimes/%s/stage" % no, {"target": "已批准"},
                     token="")  # 未登录
    assert st == 401
    api.ok("POST", "/api/overtimes/%s/stage" % no, {"target": "已批准"})


def test_payroll_full_cycle(api):
    # 新建本月批次 → 核算 → 发放
    month = time.strftime("%Y-%m")
    r = api.ok("POST", "/api/payroll", {"month": month})
    assert r["status"] == "草稿"
    st, e = api.call("POST", "/api/payroll/%s/stage" % month, {"target": "已发放"})
    assert st == 400 and "先完成核算" in e["message"]
    r = api.ok("POST", "/api/payroll/%s/calc" % month, {})
    assert r["slips"] > 15
    api.ok("POST", "/api/payroll/%s/stage" % month, {"target": "已发放"})
    slips = api.ok("GET", "/api/payroll/%s/payslips" % month)
    first = slips["list"][0]
    assert first["net"] == round(first["gross"] - first["socialIns"] - first["hf"]
                                 - first["tax"] - first["absenceDed"], 2)
    # 已发放不能再核算
    st, e = api.call("POST", "/api/payroll/%s/calc" % month, {})
    assert st == 400


def test_hiring_chain(api):
    r = api.ok("POST", "/api/jobs", {"title": "测试工程师", "dept": "D04", "salary": "10-15K"})
    job = r["no"]
    r = api.ok("POST", "/api/candidates", {"name": "测试候选", "job": job, "expected": 12000})
    cand = r["no"]
    # Offer 闸口：未面试直接发 Offer
    st, e = api.call("POST", "/api/candidates/%s/stage" % cand, {"target": "已发Offer",
                                                                 "offerSalary": 12000,
                                                                 "feedback": "ok"})
    assert st == 400 and "面试" in e["message"]
    # 安排面试 → 候选人自动进入面试中
    api.ok("POST", "/api/interviews", {"cand": cand, "interviewer": "王明",
                                       "at": "2026-10-25 14:00"})
    d = api.ok("GET", "/api/candidates?stage=面试中")
    assert any(x["no"] == cand for x in d["list"])
    # 录入通过结果
    ivs = api.ok("GET", "/api/interviews?cand=" + cand)
    api.ok("POST", "/api/interviews/%d" % ivs["list"][0]["id"],
           {"result": "通过", "score": 85, "feedback": "良好"})
    # 发 Offer（有面试通过记录）
    api.ok("POST", "/api/candidates/%s/stage" % cand, {"target": "已发Offer",
                                                       "offerSalary": 12500,
                                                       "feedback": "面试通过"})
    # 入职确认
    api.ok("POST", "/api/candidates/%s/stage" % cand, {"target": "已入职",
                                                       "onboardDeptOk": True})
    d = api.ok("GET", "/api/candidates?stage=已入职")
    assert any(x["no"] == cand for x in d["list"])
    # 关闭职位
    api.ok("POST", "/api/jobs/%s/stage" % job, {"target": "已关闭"})


def test_perf_publish_gate(api):
    r = api.ok("POST", "/api/perf/cycles", {"name": "2099-Q1", "period": "测试周期"})
    # 无评分数据不能归档
    st, e = api.call("POST", "/api/perf/cycles/2099-Q1/publish", {})
    assert st == 400 and "评分" in e["message"]
    api.ok("POST", "/api/perf/scores", {"cycle": "2099-Q1", "emp": "EMP009",
                                        "workQty": 90, "workQuality": 88,
                                        "cooperation": 85, "discipline": 92})
    r = api.ok("POST", "/api/perf/cycles/2099-Q1/publish", {})
    assert r["scores"] == 1
    scores = api.ok("GET", "/api/perf/scores?cycle=2099-Q1")
    assert scores["list"][0]["grade"] in ("S", "A", "B", "C", "D")


def test_training_quota_and_enroll(api):
    r = api.ok("POST", "/api/trainings", {"title": "闸口验证培训", "date": "2026-11-01",
                                          "quota": 1})
    no = r["no"]
    api.ok("POST", "/api/trainings/%s/enroll" % no, {"emp": "EMP009"})
    st, e = api.call("POST", "/api/trainings/%s/enroll" % no, {"emp": "EMP008"})
    assert st == 400 and "满" in e["message"]
    # 同一员工重复报名
    api.ok("POST", "/api/trainings", {"title": "重复报名验证", "date": "2026-11-02",
                                      "quota": 10})
    recs = api.ok("GET", "/api/trainings?").get("list", [])
    # 成绩录入
    api.ok("POST", "/api/trainings/%s/grade" % no, {"emp": "EMP009", "score": 55})
    rec = api.ok("GET", "/api/trainings/%s/records" % no)
    assert rec["list"][0]["status"] == "缺席"


def test_contract_renew_and_risk(api):
    d = api.ok("GET", "/api/contracts")
    assert d["list"] and "risk" in d
    api.ok("POST", "/api/contracts/renew", {"emp": "EMP021", "end": "2029-10-21"})
    d2 = api.ok("GET", "/api/contracts")
    assert len(d2["list"]) == len(d["list"]) + 1


def test_idempotent_login_and_key_headers(api):
    ts = str(int(time.time() * 1000))
    h = {"Idempotency-Key": "hrm-test-" + ts}
    body = {"emp": "EMP009", "type": "事假", "start": "2027-01-05", "end": "2027-01-06"}
    st1, r1 = api.call("POST", "/api/leaves", body, headers=h)
    st2, r2 = api.call("POST", "/api/leaves", body, headers=h)
    assert st1 == 200 and st2 == 200 and r1["no"] == r2["no"]


def test_api_key_auth(api):
    r = api.ok("POST", "/api/keys", {"name": "测试Key", "scope": "read"})
    key = r["key"]
    assert key.startswith("fhk_")
    # Key 只读：GET 可用，POST 被拦
    st, d = api.call("GET", "/api/employees", token="", headers={"X-Hr-Key": key})
    assert st == 200
    st, e = api.call("POST", "/api/employees", {"no": "X", "name": "x", "dept": "D01",
                                                "hireDate": "2026-01-01"},
                     token="", headers={"X-Hr-Key": key})
    assert st == 403
    # 错误 Key 401
    st, e = api.call("GET", "/api/employees", token="", headers={"X-Hr-Key": "fhk_bad"})
    assert st == 401
    # 吊销
    keys = api.ok("GET", "/api/keys")
    kid = keys["list"][0]["id"]
    api.ok("POST", "/api/keys/%d/revoke" % kid, {})
    st, e = api.call("GET", "/api/employees", token="", headers={"X-Hr-Key": key})
    assert st == 401


def test_webhook_and_sync(api):
    wh = api.ok("GET", "/api/webhooks")
    assert len(wh["events"]) >= 12
    r = api.ok("POST", "/api/webhooks", {
        "name": "测试回调", "url": "http://127.0.0.1:9/hook",
        "events": ["test.ping", "employee.created"]})
    assert r["secret"]
    api.ok("POST", "/api/webhooks/test", {})
    dv = api.ok("GET", "/api/webhooks/deliveries")
    assert dv["list"]
    sync = api.ok("GET", "/api/sync/changes?since=2026-01-01 00:00:00")
    assert sync["changes"]["employees"]


def test_csv_exports(api):
    st, headers, raw = api.raw("GET", "/api/reports/attendance.csv")
    assert st == 200 and "attachment" in headers.get("Content-Disposition", "")
    assert raw.decode("utf-8-sig").splitlines()[0].startswith("date")
    st, _, raw2 = api.raw("GET", "/api/reports/leaves.csv")
    assert st == 200
    st, _, raw3 = api.raw("GET", "/api/reports/payslips.csv")
    assert st == 200


def test_multi_channel_token(api, tok_maker):
    t = tok_maker("zhouh")
    st, r = api.call("GET", "/api/auth/me", token=t)
    assert st == 200 and r["role"] == "hr"
    st, r = api.call("GET", "/api/auth/me?token=" + t, token="")
    assert st == 200 and r["role"] == "hr"
    st, r = api.call("GET", "/api/auth/me", token="", headers={"X-Hr-Token": t})
    assert st == 200


def test_wrong_password(api):
    st, r = api.call("POST", "/api/auth/login",
                     {"username": "admin", "password": "wrong"})
    assert st == 401 and "错误" in r["message"]

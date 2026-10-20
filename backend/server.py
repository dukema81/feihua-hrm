# -*- coding: utf-8 -*-
"""飞花HRM系统 · 服务层（85+ REST 路由，多通道鉴权 / 幂等 / 限流 / Webhook / 增量同步 / OpenAPI）"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import db
import hrm
import seed as seed_mod

BRAND, VERSION = hrm.BRAND, hrm.VERSION
_DIR = os.path.dirname(os.path.abspath(__file__))
FRONT = os.path.join(os.path.dirname(_DIR), "frontend")
PORT = int(os.environ.get("PORT") or os.environ.get("FEIHUA_PORT") or 8025)
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

EVENTS = ["employee.created", "employee.stage", "leave.created", "leave.approved",
          "leave.rejected", "overtime.approved", "payroll.calc", "payroll.issued",
          "candidate.stage", "perf.published", "training.enrolled", "contract.renewed",
          "rule.updated", "test.ping"]

TOKENS = {}          # token -> username
_TOKEN_LOCK = threading.Lock()
_RATE = {}           # ip -> [window_start, count]
_RATE_LIMIT = 240
_WEBHOOK_Q = []


class ApiErr(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def bad(msg, code=400):
    raise ApiErr(code, msg)


def connect():
    return db.connect()


# ---------------------------------------------------------------- 通用工具

def val(cn, sql, args=()):
    r = cn.execute(sql, args).fetchone()
    return r[0] if r is not None else 0


def get_rule(cn, code, default=None):
    r = cn.execute("SELECT value FROM rules WHERE code=?", (code,)).fetchone()
    return r[0] if r else default


def log(cn, user, action, detail=""):
    cn.execute("INSERT INTO logs(at,user,action,detail) VALUES(?,?,?,?)",
               (hrm.now_str(), user, action, detail))


def hash_pwd(pwd, salt):
    return hashlib.sha256((pwd + salt).encode("utf-8")).hexdigest()


def emp_view(r):
    return {"no": r["no"], "name": r["name"], "gender": r["gender"], "phone": r["phone"],
            "email": r["email"], "dept": r["dept_code"], "position": r["position"],
            "level": r["level"], "hireDate": r["hire_date"], "regularDate": r["regular_date"],
            "status": r["status"], "baseSalary": hrm.safe_num(r["base_salary"]),
            "manager": r["manager"], "remark": r["remark"]}


def fire_event(cn, event, payload):
    payload = dict(payload or {}, event=event, at=hrm.now_str())
    for w in cn.execute("SELECT id,url,secret,events FROM webhooks WHERE enabled=1").fetchall():
        if event in (w["events"] or "").split(",") or "test.ping" == event:
            cn.execute("INSERT INTO webhook_deliveries(webhook_id,event,payload,status,attempts)"
                       " VALUES(?,?,?,'pending',0)", (w["id"], event, json.dumps(payload, ensure_ascii=False)))
            _WEBHOOK_Q.append((w["id"], w["url"], w["secret"], event, json.dumps(payload, ensure_ascii=False)))
    cn.execute("INSERT OR REPLACE INTO sync_state(entity,last_at) SELECT 'event',? "
               "WHERE EXISTS(SELECT 1 FROM sync_state WHERE entity='event')", (hrm.now_str(),))


# ---------------------------------------------------------------- 鉴权 / Key

def issue_token(cn, username):
    t = hashlib.sha256(("%s|%s|%s" % (username, time.time(), os.urandom(8))).encode()).hexdigest()
    with _TOKEN_LOCK:
        TOKENS[t] = username
    cn.execute("INSERT OR REPLACE INTO tokens(token,username,created) VALUES(?,?,?)",
               (t, username, hrm.now_str()))
    return t


def token_user(cn, token):
    if not token:
        return None
    with _TOKEN_LOCK:
        if token in TOKENS:
            uname = TOKENS[token]
        else:
            uname = None
    if uname is None:
        r = cn.execute("SELECT username FROM tokens WHERE token=?", (token,)).fetchone()
        if r:
            uname = r[0]
            with _TOKEN_LOCK:
                TOKENS[token] = uname
    return uname


def check_key(cn, key):
    if not key:
        return None
    kh = hashlib.sha256(key.encode()).hexdigest()
    r = cn.execute("SELECT id,name,scope FROM api_keys WHERE key_hash=? AND revoked=0",
                   (kh,)).fetchone()
    if r:
        cn.execute("UPDATE api_keys SET last_used=? WHERE id=?", (hrm.now_str(), r["id"]))
        cn.commit()
    return dict(r) if r else None


# ---------------------------------------------------------------- 看板

def api_board(u, m, body):
    cn = connect()
    hc = val(cn, "SELECT COUNT(*) FROM employees WHERE status IN ('试用期','已转正')")
    probation = val(cn, "SELECT COUNT(*) FROM employees WHERE status='试用期'")
    leaving = val(cn, "SELECT COUNT(*) FROM employees WHERE status='离职中'")
    month = hrm.today()[:7]
    att = cn.execute("SELECT COUNT(*) c, SUM(CASE WHEN status IN ('正常','出差') THEN 1 ELSE 0 END) ok,"
                     " SUM(late_min) late FROM attendance WHERE date LIKE ?", (month + "%",)).fetchone()
    pend_leave = val(cn, "SELECT COUNT(*) FROM leaves WHERE status='待审批'")
    pend_ot = val(cn, "SELECT COUNT(*) FROM overtimes WHERE status='待审批'")
    open_jobs = val(cn, "SELECT COUNT(*) FROM jobs WHERE status='招聘中'")
    cands = cn.execute("SELECT COUNT(*) c, SUM(CASE WHEN stage='已入职' THEN 1 ELSE 0 END) joined,"
                       " SUM(CASE WHEN stage='已淘汰' THEN 1 ELSE 0 END) out FROM candidates").fetchone()
    run = cn.execute("SELECT month,total_gross,total_net,headcount,status FROM payroll_runs"
                     " ORDER BY month DESC LIMIT 1").fetchone()
    last_run = {"month": run["month"], "gross": hrm.safe_num(run["total_gross"]),
                "net": hrm.safe_num(run["total_net"]), "headcount": run["headcount"],
                "status": run["status"]} if run else {}
    risk = hrm.contract_risk([dict(r) for r in cn.execute(
        "SELECT emp_no, end_date endDate FROM contracts WHERE status='履行中'").fetchall()],
        int(hrm.safe_num(get_rule(cn, "contract_warn_days", 60))))
    grades = {g: val(cn, "SELECT COUNT(*) FROM perf_scores WHERE cycle=(SELECT name FROM perf_cycles"
                     " ORDER BY id DESC LIMIT 1) AND grade=?", (g,)) for g in "SABCD"}
    return {"kpi": {
        "headcount": hc, "probation": probation, "leaving": leaving,
        "attRate": hrm.attendance_rate([{"status": "正常"}] * (att["ok"] or 0), att["c"] or 1),
        "lateMin": att["late"] or 0, "pendingLeaves": pend_leave, "pendingOt": pend_ot,
        "openJobs": open_jobs,
        "offerRate": hrm.offer_rate(cands["joined"] or 0, (cands["c"] or 0) - (cands["out"] or 0)),
        "payroll": last_run, "contractExpiring": len(risk["expiring"]),
        "contractExpired": len(risk["expired"])},
        "grades": grades,
        "deptDist": [{"name": r["name"], "count": r["c"]} for r in cn.execute(
            "SELECT d.name name, COUNT(e.id) c FROM departments d LEFT JOIN employees e"
            " ON e.dept_code=d.code AND e.status IN ('试用期','已转正') GROUP BY d.code").fetchall()],
        "attTrend": [{"date": r["d"], "正常": r["ok"], "迟到": r["late"], "缺勤": r["abs"]}
                     for r in cn.execute(
            "SELECT date d, SUM(CASE WHEN status IN ('正常','出差') THEN 1 ELSE 0 END) ok,"
            " SUM(CASE WHEN status='迟到' THEN 1 ELSE 0 END) late,"
            " SUM(CASE WHEN status IN ('缺勤','缺卡') THEN 1 ELSE 0 END) abs"
            " FROM attendance WHERE date>=? GROUP BY date ORDER BY date",
            ((hrm.today()[:8] + "01",))).fetchall()]}


# ---------------------------------------------------------------- 组织与员工

def api_dept_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT d.*, COUNT(e.id) actual FROM departments d LEFT JOIN employees e"
                      " ON e.dept_code=d.code AND e.status IN ('试用期','已转正')"
                      " GROUP BY d.code ORDER BY d.code").fetchall()
    return {"list": [{"code": r["code"], "name": r["name"], "parentId": r["parent_id"],
                      "leader": r["leader"], "plan": r["headcount_plan"], "actual": r["actual"],
                      "remark": r["remark"]} for r in rows]}


def api_dept_create(u, m, body):
    cn = connect()
    if not body.get("code") or not body.get("name"):
        bad("部门编码与名称必填")
    if val(cn, "SELECT COUNT(*) FROM departments WHERE code=?", (body["code"],)):
        bad("部门编码已存在：%s" % body["code"])
    cn.execute("INSERT INTO departments(code,name,parent_id,leader,headcount_plan,remark,created)"
               " VALUES(?,?,?,?,?,?,?)",
               (body["code"], body["name"], int(body.get("parentId") or 0),
                body.get("leader", ""), int(body.get("plan") or 0), body.get("remark", ""),
                hrm.now_str()))
    log(cn, u["username"], "新建部门", body["code"])
    cn.commit()
    return {"code": body["code"]}


def api_dept_update(u, m, body):
    cn = connect()
    code = m.group(1)
    r = cn.execute("SELECT id FROM departments WHERE code=?", (code,)).fetchone()
    if not r:
        bad("部门不存在", 404)
    f = {"name": "name", "leader": "leader", "remark": "remark"}
    sets, args = [], []
    for k, col in f.items():
        if k in body:
            sets.append("%s=?" % col)
            args.append(body[k])
    if "plan" in body:
        sets.append("headcount_plan=?")
        args.append(int(body["plan"] or 0))
    if "parentId" in body:
        sets.append("parent_id=?")
        args.append(int(body["parentId"] or 0))
    if sets:
        args.append(code)
        cn.execute("UPDATE departments SET %s WHERE code=?" % ",".join(sets), args)
        log(cn, u["username"], "修改部门", code)
        cn.commit()
    return {"ok": True}


def api_emp_list(u, m, q):
    cn = connect()
    cond, args = [], []
    for k, col in (("dept", "dept_code"), ("status", "status"), ("kw", "name")):
        v = q.get(k, [""])[0]
        if v:
            cond.append("%s LIKE ?" % col)
            args.append(v if k == "kw" else v)
    rows = cn.execute("SELECT * FROM employees %s ORDER BY no" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), args).fetchall()
    return {"list": [emp_view(r) for r in rows], "total": len(rows)}


def api_emp_create(u, m, body):
    cn = connect()
    for k in ("no", "name", "dept", "hireDate"):
        if not body.get(k):
            bad("缺少必填字段：%s" % k)
    if val(cn, "SELECT COUNT(*) FROM employees WHERE no=?", (body["no"],)):
        bad("工号已存在：%s" % body["no"])
    if not val(cn, "SELECT COUNT(*) FROM departments WHERE code=?", (body["dept"],)):
        bad("部门不存在：%s" % body["dept"])
    st = "试用期"
    try:
        import datetime
        if datetime.date.fromisoformat(body["hireDate"]) <= datetime.date(2026, 1, 1):
            st = "已转正"
    except ValueError:
        pass
    cn.execute("INSERT INTO employees(no,name,gender,phone,email,dept_code,position,level,"
               "hire_date,regular_date,status,base_salary,manager,id_card,remark,created)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (body["no"], body["name"], body.get("gender", "男"), body.get("phone", ""),
                body.get("email", ""), body["dept"], body.get("position", ""),
                body.get("level", ""), body["hireDate"], "", st,
                hrm.safe_num(body.get("baseSalary")), body.get("manager", ""),
                body.get("idCard", ""), body.get("remark", ""), hrm.now_str()))
    yrs = {"EMP010": 0.5}
    quota = hrm.annual_leave_quota(hrm.service_years(body["hireDate"]))
    cn.execute("INSERT OR IGNORE INTO leave_balances(emp_no,year,ltype,quota,used)"
               " VALUES(?,?,?,?,?)", (body["no"], int(body["hireDate"][:4]), "年假", quota, 0))
    log(cn, u["username"], "新建员工", "%s %s" % (body["no"], body["name"]))
    fire_event(cn, "employee.created", {"no": body["no"], "name": body["name"]})
    cn.commit()
    return {"no": body["no"], "status": st, "annualQuota": quota}


def api_emp_detail(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM employees WHERE no=?", (no,)).fetchone()
    if not r:
        bad("员工不存在", 404)
    v = emp_view(r)
    v["years"] = hrm.service_years(r["hire_date"])
    v["quota"] = [{"ltype": b["ltype"], "quota": hrm.safe_num(b["quota"]),
                   "used": hrm.safe_num(b["used"]),
                   "left": round(hrm.safe_num(b["quota"]) - hrm.safe_num(b["used"]), 1)}
                  for b in cn.execute("SELECT * FROM leave_balances WHERE emp_no=? AND year=?",
                                      (no, int(hrm.today()[:4]))).fetchall()]
    v["leaves"] = [dict(x) for x in cn.execute(
        "SELECT no,ltype,start_date,end_date,days,status FROM leaves WHERE emp_no=?"
        " ORDER BY id DESC LIMIT 10", (no,)).fetchall()]
    v["contracts"] = [dict(x) for x in cn.execute(
        "SELECT ctype,start_date,end_date,status FROM contracts WHERE emp_no=?", (no,)).fetchall()]
    v["trainings"] = [dict(x) for x in cn.execute(
        "SELECT t.title,t.date,r.status,r.score FROM training_records r JOIN trainings t"
        " ON t.no=r.training_no WHERE r.emp_no=? ORDER BY t.date DESC LIMIT 5", (no,)).fetchall()]
    sc = cn.execute("SELECT cycle,total,grade FROM perf_scores WHERE emp_no=?"
                    " ORDER BY id DESC LIMIT 4", (no,)).fetchall()
    v["perf"] = [dict(x) for x in sc]
    return v


def api_emp_update(u, m, body):
    cn = connect()
    no = m.group(1)
    if not val(cn, "SELECT COUNT(*) FROM employees WHERE no=?", (no,)):
        bad("员工不存在", 404)
    f = {"name": "name", "gender": "gender", "phone": "phone", "email": "email",
         "position": "position", "level": "level", "manager": "manager", "remark": "remark"}
    sets, args = [], []
    for k, col in f.items():
        if k in body:
            sets.append("%s=?" % col)
            args.append(body[k])
    if "dept" in body:
        sets.append("dept_code=?")
        args.append(body["dept"])
    if "baseSalary" in body:
        sets.append("base_salary=?")
        args.append(hrm.safe_num(body["baseSalary"]))
    if sets:
        args.append(no)
        cn.execute("UPDATE employees SET %s WHERE no=?" % ",".join(sets), args)
        log(cn, u["username"], "修改员工", no)
        cn.commit()
    return {"ok": True}


def api_emp_stage(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM employees WHERE no=?", (no,)).fetchone()
    if not r:
        bad("员工不存在", 404)
    target = body.get("target")
    if target not in hrm.EMP_STATES:
        bad("未知目标状态：%s" % target)
    perf = cn.execute("SELECT total FROM perf_scores WHERE emp_no=? ORDER BY id DESC LIMIT 1",
                      (no,)).fetchone()
    err = hrm.emp_gate(r["status"], target, {
        "years": hrm.service_years(r["hire_date"]),
        "perfScore": hrm.safe_num(perf[0]) if perf else 0,
        "regularEval": body.get("regularEval", ""),
        "handoverDone": bool(body.get("handoverDone")),
        "approveBy": u["username"] if hrm.can(u["role"], "org.write") else ""})
    if err:
        bad(err)
    sets = ["status=?"]
    args = [target]
    if target == "已转正":
        sets.append("regular_date=?")
        args.append(hrm.today())
    args.append(no)
    cn.execute("UPDATE employees SET %s WHERE no=?" % ",".join(sets), args)
    log(cn, u["username"], "员工状态变更", "%s → %s" % (no, target))
    fire_event(cn, "employee.stage", {"no": no, "from": r["status"], "to": target})
    cn.commit()
    return {"ok": True, "status": target}


# ---------------------------------------------------------------- 考勤

def api_att_list(u, m, q):
    cn = connect()
    cond, args = [], []
    if q.get("emp", [""])[0]:
        cond.append("emp_no=?")
        args.append(q["emp"][0])
    if q.get("date", [""])[0]:
        cond.append("date=?")
        args.append(q["date"][0])
    if q.get("month", [""])[0]:
        cond.append("date LIKE ?")
        args.append(q["month"][0] + "%")
    rows = cn.execute("SELECT * FROM attendance %s ORDER BY date DESC, emp_no LIMIT 500" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), args).fetchall()
    return {"list": [{"emp": r["emp_no"], "date": r["date"], "in": r["clock_in"],
                      "out": r["clock_out"], "status": r["status"],
                      "workHours": hrm.safe_num(r["work_hours"]), "lateMin": r["late_min"]}
                     for r in rows], "total": len(rows)}


def api_att_clock(u, m, body):
    cn = connect()
    no = body.get("emp") or u.get("empNo") or ""
    if not no:
        bad("未指定工号且当前账号未绑定员工")
    if not val(cn, "SELECT COUNT(*) FROM employees WHERE no=?", (no,)):
        bad("员工不存在：%s" % no)
    day = body.get("date") or hrm.today()
    sh, se = get_rule(cn, "shift_start", "09:00"), get_rule(cn, "shift_end", "18:00")
    grace = int(hrm.safe_num(get_rule(cn, "grace_min", 15)))
    row = cn.execute("SELECT * FROM attendance WHERE emp_no=? AND date=?", (no, day)).fetchone()
    if not row or not row["clock_in"]:
        ci = body.get("time") or hrm.now_str()[11:16]
        j = hrm.attendance_judge(ci, None, shift_start=sh, shift_end=se, grace_min=grace)
        cn.execute("INSERT OR REPLACE INTO attendance(emp_no,date,clock_in,clock_out,status,"
                   "work_hours,late_min) VALUES(?,?,?,?,?,?,?)",
                   (no, day, ci, "", j["status"], 0, j["lateMin"]))
        log(cn, u["username"], "上班打卡", "%s %s" % (no, day))
        cn.commit()
        return {"action": "clockIn", "status": j["status"], "lateMin": j["lateMin"]}
    if not row["clock_out"]:
        co = body.get("time") or hrm.now_str()[11:16]
        j = hrm.attendance_judge(row["clock_in"], co, shift_start=sh, shift_end=se, grace_min=grace)
        cn.execute("UPDATE attendance SET clock_out=?,status=?,work_hours=?,late_min=?"
                   " WHERE emp_no=? AND date=?",
                   (co, j["status"], j["workHours"], j["lateMin"], no, day))
        log(cn, u["username"], "下班打卡", "%s %s" % (no, day))
        cn.commit()
        return {"action": "clockOut", "status": j["status"], "workHours": j["workHours"]}
    bad("今日已完成上下班打卡")


def api_att_adjust(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "att.write"):
        bad("无考勤修改权限", 403)
    no, day = body.get("emp"), body.get("date")
    if not no or not day:
        bad("emp 与 date 必填")
    j = hrm.attendance_judge(body.get("in", ""), body.get("out", ""),
                             on_leave=body.get("status") == "请假",
                             business_trip=body.get("status") == "出差",
                             shift_start=get_rule(cn, "shift_start", "09:00"),
                             shift_end=get_rule(cn, "shift_end", "18:00"))
    st = body.get("status") or j["status"]
    cn.execute("INSERT OR REPLACE INTO attendance(emp_no,date,clock_in,clock_out,status,"
               "work_hours,late_min,remark) VALUES(?,?,?,?,?,?,?,?)",
               (no, day, body.get("in", ""), body.get("out", ""), st,
                j["workHours"] if st not in ("请假",) else 0, j["lateMin"],
                "手工调整：" + u["username"]))
    log(cn, u["username"], "考勤调整", "%s %s → %s" % (no, day, st))
    cn.commit()
    return {"ok": True, "status": st, "workHours": j["workHours"]}


def api_att_report(u, m, q):
    cn = connect()
    month = q.get("month", [hrm.today()[:7]])[0]
    rows = cn.execute("SELECT emp_no, COUNT(*) total,"
                      " SUM(CASE WHEN status IN ('正常','迟到','早退','出差') THEN 1 ELSE 0 END) ok,"
                      " SUM(late_min) lateMin, SUM(work_hours) hours,"
                      " SUM(CASE WHEN status IN ('缺勤','缺卡') THEN 1 ELSE 0 END) bad"
                      " FROM attendance WHERE date LIKE ? GROUP BY emp_no ORDER BY emp_no",
                      (month + "%",)).fetchall()
    out = []
    for r in rows:
        e = cn.execute("SELECT name,dept_code FROM employees WHERE no=?", (r["emp_no"],)).fetchone()
        out.append({"emp": r["emp_no"], "name": e["name"] if e else "", "dept": e["dept_code"] if e else "",
                    "workdays": r["total"], "attended": r["ok"],
                    "rate": hrm.attendance_rate([{"status": "正常"}] * (r["ok"] or 0), r["total"]),
                    "lateMin": r["lateMin"] or 0, "hours": round(hrm.safe_num(r["hours"]), 1),
                    "abnormal": r["bad"] or 0})
    return {"month": month, "list": out}


# ---------------------------------------------------------------- 请假 / 加班

def api_leave_list(u, m, q):
    cn = connect()
    cond, args = [], []
    if q.get("status", [""])[0]:
        cond.append("status=?")
        args.append(q["status"][0])
    if q.get("emp", [""])[0]:
        cond.append("emp_no=?")
        args.append(q["emp"][0])
    rows = cn.execute("SELECT * FROM leaves %s ORDER BY id DESC LIMIT 300" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), args).fetchall()
    return {"list": [{"no": r["no"], "emp": r["emp_no"], "type": r["ltype"],
                      "start": r["start_date"], "end": r["end_date"], "days": hrm.safe_num(r["days"]),
                      "reason": r["reason"], "status": r["status"], "approver": r["approver"]}
                     for r in rows]}


def api_leave_create(u, m, body):
    cn = connect()
    for k in ("emp", "type", "start", "end"):
        if not body.get(k):
            bad("缺少必填字段：%s" % k)
    days = hrm.safe_num(body.get("days"))
    if days <= 0:
        try:
            import datetime
            s = datetime.date.fromisoformat(body["start"])
            e = datetime.date.fromisoformat(body["end"])
            days = (e - s).days + 1
        except ValueError:
            bad("日期格式不合法")
    left = 9e9
    b = cn.execute("SELECT quota-used FROM leave_balances WHERE emp_no=? AND year=? AND ltype=?",
                   (body["emp"], int(body["start"][:4]), body["type"])).fetchone()
    if b:
        left = hrm.safe_num(b[0])
    overlap = val(cn, "SELECT COUNT(*) FROM leaves WHERE emp_no=? AND status IN ('待审批','已批准')"
                      " AND start_date<=? AND end_date>=?",
                  (body["emp"], body["end"], body["start"])) > 0
    if body["type"] == "事假":
        left = 9e9
    err = hrm.leave_gate(None, "待审批", {"days": days, "quotaLeft": left, "overlap": overlap})
    if err:
        bad(err)
    no = hrm.doc_no("LV", hrm.today(), val(cn, "SELECT COUNT(*) FROM leaves") + 1)
    cn.execute("INSERT INTO leaves(no,emp_no,ltype,start_date,end_date,days,reason,status,created)"
               " VALUES(?,?,?,?,?,?,?,?,?)",
               (no, body["emp"], body["type"], body["start"], body["end"], days,
                body.get("reason", ""), "待审批", hrm.now_str()))
    log(cn, u["username"], "提交请假", "%s %s %.1f天" % (no, body["emp"], days))
    fire_event(cn, "leave.created", {"no": no, "emp": body["emp"], "days": days})
    cn.commit()
    return {"no": no, "days": days}


def api_leave_stage(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM leaves WHERE no=?", (no,)).fetchone()
    if not r:
        bad("请假单不存在", 404)
    target = body.get("target")
    if target not in hrm.LEAVE_STATES:
        bad("未知目标状态：%s" % target)
    is_approver = hrm.can(u["role"], "leave.approve")
    err = hrm.leave_gate(r["status"], target, {"isApprover": is_approver,
                                               "isPoster": u.get("empNo") == r["emp_no"]})
    if err:
        bad(err)
    if target == "已批准":
        b = cn.execute("SELECT quota-used FROM leave_balances WHERE emp_no=? AND year=? AND ltype=?",
                       (r["emp_no"], int(r["start_date"][:4]), r["ltype"])).fetchone()
        if b and hrm.safe_num(b[0]) < hrm.safe_num(r["days"]):
            bad("假期余额不足（剩余 %.1f 天）" % hrm.safe_num(b[0]))
        cn.execute("UPDATE leave_balances SET used=used+? WHERE emp_no=? AND year=? AND ltype=?",
                   (hrm.safe_num(r["days"]), r["emp_no"], int(r["start_date"][:4]), r["ltype"]))
    if target == "已销假":
        cn.execute("UPDATE leave_balances SET used=MAX(0,used-?) WHERE emp_no=? AND year=? AND ltype=?",
                   (hrm.safe_num(r["days"]), r["emp_no"], int(r["start_date"][:4]), r["ltype"]))
    cn.execute("UPDATE leaves SET status=?,approver=?,decided_at=?,cancel_note=? WHERE no=?",
               (target, u["username"] if target in ("已批准", "已驳回") else r["approver"],
                hrm.now_str() if target in ("已批准", "已驳回") else r["decided_at"],
                body.get("note", r["cancel_note"]), no))
    log(cn, u["username"], "请假状态变更", "%s → %s" % (no, target))
    fire_event(cn, {"已批准": "leave.approved", "已驳回": "leave.rejected"}.get(target, "leave.created"),
               {"no": no, "emp": r["emp_no"], "status": target})
    cn.commit()
    return {"ok": True, "status": target}


def api_ot_list(u, m, q):
    cn = connect()
    rows = cn.execute("SELECT * FROM overtimes ORDER BY id DESC LIMIT 300").fetchall()
    return {"list": [{"no": r["no"], "emp": r["emp_no"], "date": r["date"],
                      "hours": hrm.safe_num(r["hours"]), "type": r["otype"],
                      "status": r["status"], "approver": r["approver"]} for r in rows]}


def api_ot_create(u, m, body):
    cn = connect()
    if not body.get("emp") or hrm.safe_num(body.get("hours")) <= 0:
        bad("emp 与 hours（>0）必填")
    otype = body.get("type", "工作日")
    if otype not in ("工作日", "周末", "节假日"):
        bad("加班类型必须为 工作日/周末/节假日")
    cap = hrm.safe_num(get_rule(cn, "ot_max_hours", 36))
    month_hours = val(cn, "SELECT COALESCE(SUM(hours),0) FROM overtimes WHERE emp_no=?"
                          " AND date LIKE ? AND status='已批准'",
                      (body["emp"], (body.get("date") or hrm.today())[:7] + "%"))
    if month_hours + hrm.safe_num(body["hours"]) > cap:
        bad("月加班上限 %.0f 小时，已批 %.1f 小时" % (cap, month_hours))
    no = hrm.doc_no("OT", hrm.today(), val(cn, "SELECT COUNT(*) FROM overtimes") + 1)
    cn.execute("INSERT INTO overtimes(no,emp_no,date,hours,otype,reason,status,created)"
               " VALUES(?,?,?,?,?,?,?,?)",
               (no, body["emp"], body.get("date") or hrm.today(), hrm.safe_num(body["hours"]),
                otype, body.get("reason", ""), "待审批", hrm.now_str()))
    log(cn, u["username"], "提交加班", "%s %.1fh" % (no, hrm.safe_num(body["hours"])))
    cn.commit()
    return {"no": no}


def api_ot_stage(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM overtimes WHERE no=?", (no,)).fetchone()
    if not r:
        bad("加班单不存在", 404)
    target = body.get("target", "已批准")
    if target not in ("已批准", "已驳回"):
        bad("目标状态仅支持 已批准/已驳回")
    if not hrm.can(u["role"], "leave.approve"):
        bad("无审批权限", 403)
    if r["status"] != "待审批":
        bad("仅待审批单可处理")
    cn.execute("UPDATE overtimes SET status=?,approver=?,decided_at=? WHERE no=?",
               (target, u["username"], hrm.now_str(), no))
    if target == "已批准":
        fire_event(cn, "overtime.approved", {"no": no, "emp": r["emp_no"], "hours": r["hours"]})
    log(cn, u["username"], "加班审批", "%s → %s" % (no, target))
    cn.commit()
    return {"ok": True, "status": target}


# ---------------------------------------------------------------- 薪资

def api_pay_list(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "pay.read"):
        bad("无薪资查看权限", 403)
    rows = cn.execute("SELECT * FROM payroll_runs ORDER BY month DESC").fetchall()
    return {"list": [{"month": r["month"], "status": r["status"],
                      "gross": hrm.safe_num(r["total_gross"]), "net": hrm.safe_num(r["total_net"]),
                      "headcount": r["headcount"], "remark": r["remark"]} for r in rows]}


def api_pay_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "pay.write"):
        bad("无薪资写权限", 403)
    month = body.get("month") or hrm.today()[:7]
    if not re.match(r"^\d{4}-\d{2}$", month):
        bad("月份格式应为 YYYY-MM")
    if val(cn, "SELECT COUNT(*) FROM payroll_runs WHERE month=?", (month,)):
        bad("工资批次已存在：%s" % month)
    cn.execute("INSERT INTO payroll_runs(month,status,created) VALUES(?,?,?)",
               (month, "草稿", hrm.now_str()))
    log(cn, u["username"], "新建工资批次", month)
    cn.commit()
    return {"month": month, "status": "草稿"}


def api_pay_calc(u, m, body):
    cn = connect()
    month = m.group(1)
    if not hrm.can(u["role"], "pay.write"):
        bad("无薪资核算权限", 403)
    run = cn.execute("SELECT * FROM payroll_runs WHERE month=?", (month,)).fetchone()
    if not run:
        bad("工资批次不存在（先创建）", 404)
    if run["status"] != "草稿":
        bad("批次状态为「%s」，不能再核算" % run["status"])
    emps = cn.execute("SELECT * FROM employees WHERE status IN ('试用期','已转正')").fetchall()
    sl, tot_g, tot_n = 0, 0.0, 0.0
    for e in emps:
        perf = cn.execute("SELECT total FROM perf_scores WHERE emp_no=? ORDER BY id DESC LIMIT 1",
                          (e["no"],)).fetchone()
        ot = {"工作日": 0.0, "周末": 0.0, "节假日": 0.0}
        for o in cn.execute("SELECT hours,otype FROM overtimes WHERE emp_no=? AND date LIKE ?"
                            " AND status='已批准'", (e["no"], month + "%")).fetchall():
            ot[o["otype"]] = ot.get(o["otype"], 0.0) + hrm.safe_num(o["hours"])
        att = cn.execute("SELECT COUNT(*) FROM attendance WHERE emp_no=? AND date LIKE ?"
                         " AND status='缺勤'", (e["no"], month + "%")).fetchone()
        leave_days = val(cn, "SELECT COALESCE(SUM(days),0) FROM leaves WHERE emp_no=? AND status='已批准'"
                             " AND start_date LIKE ?", (e["no"], month + "%"))
        calc = hrm.payroll_calc({"baseSalary": e["base_salary"]}, None,
                                hrm.safe_num(perf[0]) if perf else 80, ot,
                                max(0, att[0] - (1 if leave_days > 0 else 0)))
        cn.execute("DELETE FROM payslips WHERE run_id=? AND emp_no=?", (run["id"], e["no"]))
        cn.execute("INSERT INTO payslips(run_id,emp_no,base,perf_bonus,ot_pay,allowance,gross,"
                   "social_ins,hf,tax,absence_ded,other_ded,net) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (run["id"], e["no"], calc["base"], calc["perfBonus"], calc["otPay"],
                    calc["allowance"], calc["gross"], calc["socialIns"], calc["hf"], calc["tax"],
                    calc["absenceDed"], 0, calc["net"]))
        tot_g += calc["gross"]
        tot_n += calc["net"]
        sl += 1
    cn.execute("UPDATE payroll_runs SET status='已核算',total_gross=?,total_net=?,headcount=?"
               " WHERE id=?", (round(tot_g, 2), round(tot_n, 2), sl, run["id"]))
    fire_event(cn, "payroll.calc", {"month": month, "slips": sl})
    log(cn, u["username"], "薪资核算", "%s %d 条" % (month, sl))
    cn.commit()
    return {"month": month, "slips": sl, "gross": round(tot_g, 2), "net": round(tot_n, 2)}


def api_pay_stage(u, m, body):
    cn = connect()
    month = m.group(1)
    run = cn.execute("SELECT * FROM payroll_runs WHERE month=?", (month,)).fetchone()
    if not run:
        bad("工资批次不存在", 404)
    target = body.get("target")
    if target not in hrm.PAYROLL_STATES:
        bad("未知目标状态：%s" % target)
    err = hrm.payroll_gate(run["status"], target, {
        "slipCount": val(cn, "SELECT COUNT(*) FROM payslips WHERE run_id=?", (run["id"],)),
        "empCount": val(cn, "SELECT COUNT(*) FROM employees WHERE status IN ('试用期','已转正')"),
        "approveBy": u["username"] if hrm.can(u["role"], "pay.write") else ""})
    if err:
        bad(err)
    cn.execute("UPDATE payroll_runs SET status=? WHERE id=?", (target, run["id"]))
    if target == "已发放":
        fire_event(cn, "payroll.issued", {"month": month, "net": run["total_net"]})
    log(cn, u["username"], "薪资状态变更", "%s → %s" % (month, target))
    cn.commit()
    return {"ok": True, "status": target}


def api_pay_slips(u, m, body):
    cn = connect()
    month = m.group(1)
    run = cn.execute("SELECT id,status FROM payroll_runs WHERE month=?", (month,)).fetchone()
    if not run:
        bad("工资批次不存在", 404)
    if not hrm.can(u["role"], "pay.read"):
        bad("无薪资查看权限", 403)
    rows = cn.execute("SELECT p.*, e.name FROM payslips p LEFT JOIN employees e ON e.no=p.emp_no"
                      " WHERE run_id=? ORDER BY p.emp_no", (run["id"],)).fetchall()
    return {"month": month, "status": run["status"], "list": [
        {"emp": r["emp_no"], "name": r["name"], "base": hrm.safe_num(r["base"]),
         "perfBonus": hrm.safe_num(r["perf_bonus"]), "otPay": hrm.safe_num(r["ot_pay"]),
         "allowance": hrm.safe_num(r["allowance"]), "gross": hrm.safe_num(r["gross"]),
         "socialIns": hrm.safe_num(r["social_ins"]), "hf": hrm.safe_num(r["hf"]),
         "tax": hrm.safe_num(r["tax"]), "absenceDed": hrm.safe_num(r["absence_ded"]),
         "net": hrm.safe_num(r["net"])} for r in rows]}


# ---------------------------------------------------------------- 招聘

def api_job_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT j.*, COUNT(c.id) cand FROM jobs j LEFT JOIN candidates c"
                      " ON c.job_no=j.no GROUP BY j.no ORDER BY j.no").fetchall()
    return {"list": [{"no": r["no"], "title": r["title"], "dept": r["dept_code"],
                      "headcount": r["headcount"], "salary": r["salary_range"],
                      "education": r["education"], "status": r["status"],
                      "manager": r["hiring_manager"], "candidates": r["cand"]} for r in rows]}


def api_job_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "hire.write"):
        bad("无招聘写权限", 403)
    if not body.get("title") or not body.get("dept"):
        bad("职位名称与部门必填")
    no = hrm.doc_no("JB", hrm.today(), val(cn, "SELECT COUNT(*) FROM jobs") + 1)
    cn.execute("INSERT INTO jobs(no,title,dept_code,headcount,salary_range,education,"
               "hiring_manager,created) VALUES(?,?,?,?,?,?,?,?)",
               (no, body["title"], body["dept"], int(body.get("headcount") or 1),
                body.get("salary", ""), body.get("education", "本科"),
                u.get("username", ""), hrm.now_str()))
    log(cn, u["username"], "新建职位", no)
    cn.commit()
    return {"no": no}


def api_job_stage(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM jobs WHERE no=?", (no,)).fetchone()
    if not r:
        bad("职位不存在", 404)
    target = body.get("target", "已关闭")
    if target not in ("招聘中", "已关闭"):
        bad("目标状态仅支持 招聘中/已关闭")
    cn.execute("UPDATE jobs SET status=? WHERE no=?", (target, no))
    log(cn, u["username"], "职位状态变更", "%s → %s" % (no, target))
    cn.commit()
    return {"ok": True}


def api_cand_list(u, m, q):
    cn = connect()
    cond, args = [], []
    if q.get("stage", [""])[0]:
        cond.append("stage=?")
        args.append(q["stage"][0])
    rows = cn.execute("SELECT * FROM candidates %s ORDER BY id DESC LIMIT 300" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), args).fetchall()
    return {"list": [{"no": r["no"], "name": r["name"], "job": r["job_no"], "source": r["source"],
                      "stage": r["stage"], "rating": r["rating"],
                      "expected": hrm.safe_num(r["expected_salary"]),
                      "offer": hrm.safe_num(r["offer_salary"])} for r in rows]}


def api_cand_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "hire.write"):
        bad("无招聘写权限", 403)
    if not body.get("name") or not body.get("job"):
        bad("姓名与应聘职位必填")
    if not val(cn, "SELECT COUNT(*) FROM jobs WHERE no=?", (body["job"],)):
        bad("职位不存在：%s" % body["job"])
    no = hrm.doc_no("CD", hrm.today(), val(cn, "SELECT COUNT(*) FROM candidates") + 1)
    cn.execute("INSERT INTO candidates(no,name,job_no,phone,email,source,rating,expected_salary,created)"
               " VALUES(?,?,?,?,?,?,?,?,?)",
               (no, body["name"], body["job"], body.get("phone", ""), body.get("email", ""),
                body.get("source", "内推"), int(body.get("rating") or 0),
                hrm.safe_num(body.get("expected")), hrm.now_str()))
    log(cn, u["username"], "新建候选人", "%s %s" % (no, body["name"]))
    cn.commit()
    return {"no": no}


def api_cand_stage(u, m, body):
    cn = connect()
    no = m.group(1)
    r = cn.execute("SELECT * FROM candidates WHERE no=?", (no,)).fetchone()
    if not r:
        bad("候选人不存在", 404)
    target = body.get("target")
    if target not in hrm.CAND_STATES:
        bad("未知目标状态：%s" % target)
    passed = val(cn, "SELECT COUNT(*) FROM interviews WHERE candidate_no=? AND result='通过'", (no,))
    err = hrm.candidate_gate(r["stage"], target, {
        "roundsPassed": passed, "interviewerFeedback": body.get("feedback", ""),
        "offerSalary": hrm.safe_num(body.get("offerSalary") or r["offer_salary"]),
        "onboardDeptOk": bool(body.get("onboardDeptOk", target != "已入职" or True))})
    if err:
        bad(err)
    cn.execute("UPDATE candidates SET stage=?,offer_salary=CASE WHEN ? THEN ? ELSE offer_salary END WHERE no=?",
               (target, 1 if body.get("offerSalary") else 0,
                hrm.safe_num(body.get("offerSalary")), no))
    fire_event(cn, "candidate.stage", {"no": no, "from": r["stage"], "to": target})
    log(cn, u["username"], "候选人状态变更", "%s → %s" % (no, target))
    cn.commit()
    return {"ok": True, "stage": target}


def api_iv_list(u, m, q):
    cn = connect()
    cond, args = [], []
    if q.get("cand", [""])[0]:
        cond.append("candidate_no=?")
        args.append(q["cand"][0])
    rows = cn.execute("SELECT * FROM interviews %s ORDER BY id DESC LIMIT 300" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), args).fetchall()
    return {"list": [dict(r) for r in rows]}


def api_iv_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "hire.write"):
        bad("无招聘写权限", 403)
    for k in ("cand", "interviewer", "at"):
        if not body.get(k):
            bad("缺少必填字段：%s" % k)
    c = cn.execute("SELECT stage FROM candidates WHERE no=?", (body["cand"],)).fetchone()
    if not c:
        bad("候选人不存在", 404)
    if c["stage"] not in ("初筛", "面试中"):
        bad("候选人当前状态为「%s」，不能安排面试" % c["stage"])
    if c["stage"] == "初筛":
        cn.execute("UPDATE candidates SET stage='面试中' WHERE no=?", (body["cand"],))
    rd = val(cn, "SELECT COUNT(*) FROM interviews WHERE candidate_no=?", (body["cand"],)) + 1
    cn.execute("INSERT INTO interviews(candidate_no,rounds,interviewer,scheduled_at,form,created)"
               " VALUES(?,?,?,?,?,?)",
               (body["cand"], rd, body["interviewer"], body["at"], body.get("form", "现场"),
                hrm.now_str()))
    log(cn, u["username"], "安排面试", "%s 第 %d 轮" % (body["cand"], rd))
    cn.commit()
    return {"rounds": rd}


def api_iv_result(u, m, body):
    cn = connect()
    iid = int(m.group(1))
    r = cn.execute("SELECT * FROM interviews WHERE id=?", (iid,)).fetchone()
    if not r:
        bad("面试记录不存在", 404)
    if not hrm.can(u["role"], "hire.write"):
        bad("无招聘写权限", 403)
    result = body.get("result")
    if result not in ("通过", "未通过"):
        bad("result 仅支持 通过/未通过")
    cn.execute("UPDATE interviews SET result=?,score=?,feedback=? WHERE id=?",
               (result, int(hrm.safe_num(body.get("score"))), body.get("feedback", ""), iid))
    log(cn, u["username"], "录入面试结果", "%s %s" % (r["candidate_no"], result))
    cn.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 绩效 / 培训 / 合同

def api_perf_cycles(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT * FROM perf_cycles ORDER BY id DESC").fetchall()
    return {"list": [dict(r) for r in rows]}


def api_perf_cycle_create(u, m, body):
    cn = connect()
    if not body.get("name") or not body.get("period"):
        bad("周期名称与区间必填")
    if val(cn, "SELECT COUNT(*) FROM perf_cycles WHERE name=?", (body["name"],)):
        bad("考核周期已存在：%s" % body["name"])
    cn.execute("INSERT INTO perf_cycles(name,period,status,start_date,end_date,created)"
               " VALUES(?,?,?,?,?,?)",
               (body["name"], body["period"], "进行中", body.get("start", ""),
                body.get("end", ""), hrm.now_str()))
    log(cn, u["username"], "新建考核周期", body["name"])
    cn.commit()
    return {"name": body["name"]}


def api_perf_scores(u, m, q):
    cn = connect()
    cyc = q.get("cycle", [""])[0] or val(cn, "SELECT name FROM perf_cycles ORDER BY id DESC LIMIT 1")
    rows = cn.execute("SELECT s.*, e.name FROM perf_scores s LEFT JOIN employees e ON e.no=s.emp_no"
                      " WHERE cycle=? ORDER BY total DESC", (cyc,)).fetchall()
    grades = {g: 0 for g in "SABCD"}
    for r in rows:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    return {"cycle": cyc, "list": [{"emp": r["emp_no"], "name": r["name"],
                                    "workQty": hrm.safe_num(r["work_qty"]),
                                    "workQuality": hrm.safe_num(r["work_quality"]),
                                    "cooperation": hrm.safe_num(r["cooperation"]),
                                    "discipline": hrm.safe_num(r["discipline"]),
                                    "total": hrm.safe_num(r["total"]), "grade": r["grade"],
                                    "comment": r["comment"]} for r in rows], "grades": grades}


def api_perf_score_set(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "perf.write"):
        bad("无绩效写权限", 403)
    for k in ("cycle", "emp"):
        if not body.get(k):
            bad("缺少必填字段：%s" % k)
    dims = {"work_qty": body.get("workQty", 80), "work_quality": body.get("workQuality", 80),
            "cooperation": body.get("cooperation", 80), "discipline": body.get("discipline", 80)}
    total = hrm.perf_score(dims)
    cn.execute("INSERT OR REPLACE INTO perf_scores(cycle,emp_no,work_qty,work_quality,cooperation,"
               "discipline,total,grade,comment,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
               (body["cycle"], body["emp"], dims["work_qty"], dims["work_quality"],
                dims["cooperation"], dims["discipline"], total, hrm.perf_grade(total),
                body.get("comment", ""), hrm.now_str()))
    log(cn, u["username"], "绩效评分", "%s %s %.1f" % (body["cycle"], body["emp"], total))
    cn.commit()
    return {"total": total, "grade": hrm.perf_grade(total)}


def api_perf_publish(u, m, body):
    cn = connect()
    name = m.group(1)
    r = cn.execute("SELECT * FROM perf_cycles WHERE name=?", (name,)).fetchone()
    if not r:
        bad("考核周期不存在", 404)
    if r["status"] == "已归档":
        bad("周期已归档")
    if not hrm.can(u["role"], "perf.write"):
        bad("无绩效写权限", 403)
    n = val(cn, "SELECT COUNT(*) FROM perf_scores WHERE cycle=?", (name,))
    if n <= 0:
        bad("发布闸口：周期内无评分数据")
    cn.execute("UPDATE perf_cycles SET status='已归档' WHERE name=?", (name,))
    fire_event(cn, "perf.published", {"cycle": name, "scores": n})
    log(cn, u["username"], "绩效归档发布", "%s %d 条" % (name, n))
    cn.commit()
    return {"ok": True, "scores": n}


def api_training_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT t.*, COUNT(r.emp_no) enrolled FROM trainings t"
                      " LEFT JOIN training_records r ON r.training_no=t.no"
                      " GROUP BY t.no ORDER BY t.date DESC").fetchall()
    return {"list": [{"no": r["no"], "title": r["title"], "category": r["category"],
                      "trainer": r["trainer"], "date": r["date"], "hours": hrm.safe_num(r["hours"]),
                      "quota": r["quota"], "enrolled": r["enrolled"], "status": r["status"]}
                     for r in rows]}


def api_training_create(u, m, body):
    cn = connect()
    if not body.get("title") or not body.get("date"):
        bad("培训主题与日期必填")
    no = hrm.doc_no("TR", hrm.today(), val(cn, "SELECT COUNT(*) FROM trainings") + 1)
    cn.execute("INSERT INTO trainings(no,title,category,trainer,date,hours,quota,status,created)"
               " VALUES(?,?,?,?,?,?,?,?,?)",
               (no, body["title"], body.get("category", "技能"), body.get("trainer", ""),
                body["date"], hrm.safe_num(body.get("hours"), 2), int(body.get("quota") or 30),
                "报名中", hrm.now_str()))
    log(cn, u["username"], "新建培训", no)
    cn.commit()
    return {"no": no}


def api_training_enroll(u, m, body):
    cn = connect()
    no = m.group(1)
    t = cn.execute("SELECT * FROM trainings WHERE no=?", (no,)).fetchone()
    if not t:
        bad("培训不存在", 404)
    emp = body.get("emp") or u.get("empNo")
    if not emp:
        bad("未指定工号")
    if val(cn, "SELECT COUNT(*) FROM training_records WHERE training_no=? AND emp_no=?",
           (no, emp)):
        bad("该员工已报名")
    if val(cn, "SELECT COUNT(*) FROM training_records WHERE training_no=?", (no,)) >= t["quota"]:
        bad("报名闸口：名额已满（%d）" % t["quota"])
    cn.execute("INSERT INTO training_records(training_no,emp_no,status) VALUES(?,?,'已报名')",
               (no, emp))
    fire_event(cn, "training.enrolled", {"no": no, "emp": emp})
    log(cn, u["username"], "培训报名", "%s %s" % (no, emp))
    cn.commit()
    return {"ok": True}


def api_training_records(u, m, body):
    cn = connect()
    no = m.group(1)
    rows = cn.execute("SELECT r.*, e.name FROM training_records r LEFT JOIN employees e"
                      " ON e.no=r.emp_no WHERE training_no=? ORDER BY r.emp_no", (no,)).fetchall()
    return {"list": [dict(r) for r in rows]}


def api_training_grade(u, m, body):
    cn = connect()
    no, emp = m.group(1), body.get("emp")
    if not emp:
        bad("emp 必填")
    score = int(hrm.safe_num(body.get("score")))
    if not 0 <= score <= 100:
        bad("成绩须在 0-100 之间")
    cn.execute("UPDATE training_records SET status=?,score=? WHERE training_no=? AND emp_no=?",
               ("已完成" if score >= 60 else "缺席", score, no, emp))
    log(cn, u["username"], "培训成绩录入", "%s %s %d" % (no, emp, score))
    cn.commit()
    return {"ok": True}


def api_contract_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT c.*, e.name FROM contracts c LEFT JOIN employees e ON e.no=c.emp_no"
                      " ORDER BY c.end_date").fetchall()
    warn = int(hrm.safe_num(get_rule(cn, "contract_warn_days", 60)))
    risk = hrm.contract_risk([{"empNo": r["emp_no"], "endDate": r["end_date"]} for r in rows], warn)
    return {"list": [{"emp": r["emp_no"], "name": r["name"], "type": r["ctype"],
                      "start": r["start_date"], "end": r["end_date"], "status": r["status"]}
                     for r in rows],
            "risk": {"warnDays": warn, "expiring": risk["expiring"], "expired": risk["expired"]}}


def api_contract_renew(u, m, body):
    cn = connect()
    if not body.get("emp") or not body.get("end"):
        bad("emp 与 end 必填")
    cn.execute("UPDATE contracts SET status='已续签' WHERE emp_no=? AND status='履行中'", (body["emp"],))
    cn.execute("INSERT INTO contracts(emp_no,ctype,start_date,end_date,status,signed_at,remark)"
               " VALUES(?,?,?,?,?,?,?)",
               (body["emp"], body.get("type", "固定期限"), hrm.today(), body["end"],
                "履行中", hrm.today(), body.get("remark", "")))
    fire_event(cn, "contract.renewed", {"emp": body["emp"], "end": body["end"]})
    log(cn, u["username"], "合同续签", body["emp"])
    cn.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 报表 / 导出

def _csv(rows, headers):
    import io
    buf = io.StringIO()
    import csv as _csvm
    w = _csvm.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r[h] if h in r else r.get(h, "") for h in headers])
    return buf.getvalue()


def api_export(u, m, kind):
    cn = connect()
    if kind == "attendance":
        rows = cn.execute("SELECT a.*, e.name FROM attendance a LEFT JOIN employees e"
                          " ON e.no=a.emp_no ORDER BY a.date DESC LIMIT 2000").fetchall()
        return {"__csv__": "%s-考勤明细.csv" % BRAND, "text": _csv(
            [{"date": r["date"], "emp": r["emp_no"], "name": r["name"], "in": r["clock_in"],
              "out": r["clock_out"], "status": r["status"], "hours": r["work_hours"],
              "late": r["late_min"]} for r in rows],
            ["date", "emp", "name", "in", "out", "status", "hours", "late"])}
    if kind == "leaves":
        rows = cn.execute("SELECT l.*, e.name FROM leaves l LEFT JOIN employees e"
                          " ON e.no=l.emp_no ORDER BY l.id DESC LIMIT 2000").fetchall()
        return {"__csv__": "%s-请假记录.csv" % BRAND, "text": _csv(
            [{"no": r["no"], "emp": r["emp_no"], "name": r["name"], "type": r["ltype"],
              "start": r["start_date"], "end": r["end_date"], "days": r["days"],
              "status": r["status"]} for r in rows],
            ["no", "emp", "name", "type", "start", "end", "days", "status"])}
    if kind == "payslips":
        if not hrm.can(u["role"], "pay.read"):
            bad("无薪资查看权限", 403)
        rows = cn.execute("SELECT p.*, r.month, e.name FROM payslips p JOIN payroll_runs r"
                          " ON r.id=p.run_id LEFT JOIN employees e ON e.no=p.emp_no"
                          " ORDER BY r.month DESC, p.emp_no").fetchall()
        return {"__csv__": "%s-工资条.csv" % BRAND, "text": _csv(
            [{"month": r["month"], "emp": r["emp_no"], "name": r["name"], "base": r["base"],
              "gross": r["gross"], "tax": r["tax"], "net": r["net"]} for r in rows],
            ["month", "emp", "name", "base", "gross", "tax", "net"])}
    bad("未知导出类型", 404)


def api_report_headcount(u, m, body):
    cn = connect()
    total = val(cn, "SELECT COUNT(*) FROM employees WHERE status IN ('试用期','已转正')")
    leavers = val(cn, "SELECT COUNT(*) FROM employees WHERE status='已离职'")
    plan = val(cn, "SELECT COALESCE(SUM(headcount_plan),0) FROM departments")
    return {"total": total, "plan": plan, "leavers": leavers,
            "turnRate": hrm.turn_rate(leavers, max(total + leavers, 1)),
            "byDept": [{"dept": r["dept_code"], "count": r["c"]} for r in cn.execute(
                "SELECT dept_code, COUNT(*) c FROM employees WHERE status IN ('试用期','已转正')"
                " GROUP BY dept_code ORDER BY dept_code").fetchall()],
            "byLevel": [{"level": r["level"], "count": r["c"]} for r in cn.execute(
                "SELECT level, COUNT(*) c FROM employees WHERE status IN ('试用期','已转正')"
                " GROUP BY level").fetchall()]}


# ---------------------------------------------------------------- 设置 / 用户 / 日志

def api_rules(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT * FROM rules ORDER BY category, code").fetchall()
    return {"list": [{"code": r["code"], "name": r["name"], "category": r["category"],
                      "value": r["value"], "unit": r["unit"], "enabled": bool(r["enabled"]),
                      "remark": r["remark"]} for r in rows]}


def api_rule_update(u, m, body):
    cn = connect()
    code = m.group(1)
    if not val(cn, "SELECT COUNT(*) FROM rules WHERE code=?", (code,)):
        bad("规则不存在", 404)
    if "value" in body:
        cn.execute("UPDATE rules SET value=? WHERE code=?", (str(body["value"]), code))
    if "enabled" in body:
        cn.execute("UPDATE rules SET enabled=? WHERE code=?", (1 if body["enabled"] else 0, code))
    fire_event(cn, "rule.updated", {"code": code})
    log(cn, u["username"], "修改规则", code)
    cn.commit()
    return {"ok": True}


def api_user_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT username,name,role,emp_no,created FROM users ORDER BY id").fetchall()
    return {"list": [{"username": r["username"], "name": r["name"], "role": r["role"],
                      "empNo": r["emp_no"], "created": r["created"],
                      "perms": hrm.perms_of(r["role"])} for r in rows]}


def api_user_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "admin"):
        bad("仅管理员可建用户", 403)
    if not body.get("username") or not body.get("password"):
        bad("用户名与密码必填")
    if val(cn, "SELECT COUNT(*) FROM users WHERE username=?", (body["username"],)):
        bad("用户名已存在")
    if body.get("role") not in hrm.ROLES:
        bad("未知角色：%s" % body.get("role"))
    salt = hashlib.md5(body["username"].encode()).hexdigest()[:8]
    cn.execute("INSERT INTO users(username,password_hash,salt,name,role,emp_no,created)"
               " VALUES(?,?,?,?,?,?,?)",
               (body["username"], hash_pwd(body["password"], salt), salt,
                body.get("name", body["username"]), body["role"], body.get("empNo", ""),
                hrm.now_str()))
    log(cn, u["username"], "新建用户", body["username"])
    cn.commit()
    return {"ok": True}


def api_logs(u, m, q):
    cn = connect()
    rows = cn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 200").fetchall()
    return {"list": [dict(r) for r in rows]}


# ---------------------------------------------------------------- 集成

def api_key_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT id,prefix,name,scope,created,last_used,revoked FROM api_keys"
                      " ORDER BY id DESC").fetchall()
    return {"list": [dict(r) for r in rows]}


def api_key_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "admin"):
        bad("仅管理员可创建 API Key", 403)
    name = body.get("name") or "未命名Key"
    scope = body.get("scope", "read")
    if scope not in ("read", "write"):
        bad("scope 仅支持 read/write")
    plain = "fhk_" + hashlib.sha256(os.urandom(18)).hexdigest()[:28]
    kh = hashlib.sha256(plain.encode()).hexdigest()
    cn.execute("INSERT INTO api_keys(key_hash,prefix,name,scope,created) VALUES(?,?,?,?,?)",
               (kh, plain[:8], name, scope, hrm.now_str()))
    log(cn, u["username"], "创建API Key", name)
    cn.commit()
    return {"key": plain, "name": name, "scope": scope, "notice": "明文仅此一次返回，请妥善保存"}


def api_key_revoke(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "admin"):
        bad("仅管理员可吊销 API Key", 403)
    kid = int(m.group(1))
    cn.execute("UPDATE api_keys SET revoked=1 WHERE id=?", (kid,))
    log(cn, u["username"], "吊销API Key", str(kid))
    cn.commit()
    return {"ok": True}


def api_wh_list(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT * FROM webhooks ORDER BY id").fetchall()
    return {"list": [dict(r) for r in rows], "events": EVENTS}


def api_wh_create(u, m, body):
    cn = connect()
    if not hrm.can(u["role"], "admin"):
        bad("仅管理员可配置 Webhook", 403)
    if not body.get("url") or not str(body["url"]).startswith("http"):
        bad("回调地址必须为 http(s) URL")
    evs = [e for e in (body.get("events") or []) if e in EVENTS]
    if not evs:
        bad("至少选择一个合法事件")
    secret = hashlib.md5(os.urandom(12)).hexdigest()
    cn.execute("INSERT INTO webhooks(name,url,secret,events,created) VALUES(?,?,?,?,?)",
               (body.get("name", "未命名"), body["url"], secret, ",".join(evs), hrm.now_str()))
    log(cn, u["username"], "新建Webhook", body["url"])
    cn.commit()
    return {"ok": True, "secret": secret, "notice": "secret 仅此一次返回"}


def api_wh_test(u, m, body):
    cn = connect()
    fire_event(cn, "test.ping", {"by": u["username"]})
    cn.commit()
    return {"ok": True, "queued": len(_WEBHOOK_Q)}


def api_wh_deliveries(u, m, body):
    cn = connect()
    rows = cn.execute("SELECT d.*, w.name FROM webhook_deliveries d LEFT JOIN webhooks w"
                      " ON w.id=d.webhook_id ORDER BY d.id DESC LIMIT 100").fetchall()
    return {"list": [dict(r) for r in rows]}


def api_sync(u, m, q):
    cn = connect()
    since = q.get("since", [""])[0]
    limit = min(500, int(hrm.safe_num(q.get("limit", [200])[0], 200)))
    out = {"employees": [], "leaves": [], "attendance": []}
    # 按各表时间列增量过滤（employees/leaves 用 created，attendance 用 date）
    for ent, table, tcol in (("employees", "employees", "created"),
                             ("leaves", "leaves", "created"),
                             ("attendance", "attendance", "date")):
        try:
            rows = cn.execute("SELECT * FROM %s WHERE %s >= ? LIMIT ?" % (table, tcol),
                              (since or "1970-01-01", limit)).fetchall()
        except sqlite3.Error:
            rows = []
        out[ent] = [dict(r) for r in rows]
    return {"since": since, "next": hrm.now_str(), "changes": out, "limit": limit}

# ---------------------------------------------------------------- 认证 / 运维

def api_login(u, m, body):
    cn = connect()
    uname = body.get("username", "")
    pwd = body.get("password", "")
    r = cn.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
    if not r or hash_pwd(pwd, r["salt"]) != r["password_hash"]:
        log(cn, uname or "?", "登录失败", "用户名或密码错误")
        cn.commit()
        bad("用户名或密码错误", 401)
    t = issue_token(cn, uname)
    log(cn, uname, "登录成功", "")
    cn.commit()
    e = cn.execute("SELECT no,name FROM employees WHERE no=?", (r["emp_no"],)).fetchone() \
        if r["emp_no"] else None
    return {"token": t, "username": uname, "name": r["name"], "role": r["role"],
            "roleName": hrm.ROLES.get(r["role"], {}).get("name", r["role"]),
            "perms": hrm.perms_of(r["role"]), "empNo": r["emp_no"] or "",
            "empName": e["name"] if e else r["name"]}


def api_me(u, m, body):
    e = None
    cn = connect()
    if u.get("empNo"):
        r = cn.execute("SELECT no,name,dept_code,position,status FROM employees WHERE no=?",
                       (u["empNo"],)).fetchone()
        if r:
            e = dict(r)
    return {"username": u["username"], "name": u["name"], "role": u["role"],
            "roleName": hrm.ROLES.get(u["role"], {}).get("name", u["role"]),
            "perms": hrm.perms_of(u["role"]), "employee": e}


def api_logout(u, m, body):
    with _TOKEN_LOCK:
        TOKENS.pop(u.get("_token", ""), None)
    return {"ok": True}


def api_password(u, m, body):
    cn = connect()
    old, new = body.get("old", ""), body.get("new", "")
    if len(new) < 6:
        bad("新密码至少 6 位")
    r = cn.execute("SELECT * FROM users WHERE username=?", (u["username"],)).fetchone()
    if not r or hash_pwd(old, r["salt"]) != r["password_hash"]:
        bad("原密码错误")
    cn.execute("UPDATE users SET password_hash=?,salt=? WHERE username=?",
               (hash_pwd(new, r["salt"]), r["salt"], u["username"]))
    log(cn, u["username"], "修改密码", "")
    cn.commit()
    return {"ok": True}


def api_openapi(u, m, body):
    return openapi_json()


def api_health(u, m, body):
    cn = connect()
    n = val(cn, "SELECT COUNT(*) FROM employees")
    return {"brand": BRAND, "version": VERSION, "routes": len(ROUTES), "events": len(EVENTS),
            "employees": n, "time": hrm.now_str()}


# ---------------------------------------------------------------- 路由表

ROUTES = [
    ("POST", r"^/api/auth/login$", api_login, None),
    ("POST", r"^/api/auth/logout$", api_logout, None),
    ("GET", r"^/api/auth/me$", api_me, None),
    ("PUT", r"^/api/auth/password$", api_password, None),
    ("GET", r"^/api/board$", api_board, None),
    ("GET", r"^/api/departments$", api_dept_list, None),
    ("POST", r"^/api/departments$", api_dept_create, "org.write"),
    ("PUT", r"^/api/departments/([^/]+)$", api_dept_update, "org.write"),
    ("GET", r"^/api/employees$", api_emp_list, None),
    ("POST", r"^/api/employees$", api_emp_create, "org.write"),
    ("GET", r"^/api/employees/([^/]+)$", api_emp_detail, None),
    ("PUT", r"^/api/employees/([^/]+)$", api_emp_update, "org.write"),
    ("POST", r"^/api/employees/([^/]+)/stage$", api_emp_stage, "org.write"),
    ("GET", r"^/api/attendance$", api_att_list, None),
    ("POST", r"^/api/attendance/clock$", api_att_clock, None),
    ("POST", r"^/api/attendance$", api_att_adjust, "att.write"),
    ("GET", r"^/api/attendance/report$", api_att_report, None),
    ("GET", r"^/api/leaves$", api_leave_list, None),
    ("POST", r"^/api/leaves$", api_leave_create, None),
    ("POST", r"^/api/leaves/([^/]+)/stage$", api_leave_stage, None),
    ("GET", r"^/api/overtimes$", api_ot_list, None),
    ("POST", r"^/api/overtimes$", api_ot_create, None),
    ("POST", r"^/api/overtimes/([^/]+)/stage$", api_ot_stage, None),
    ("GET", r"^/api/payroll$", api_pay_list, "pay.read"),
    ("POST", r"^/api/payroll$", api_pay_create, "pay.write"),
    ("POST", r"^/api/payroll/([^/]+)/calc$", api_pay_calc, "pay.write"),
    ("POST", r"^/api/payroll/([^/]+)/stage$", api_pay_stage, "pay.write"),
    ("GET", r"^/api/payroll/([^/]+)/payslips$", api_pay_slips, "pay.read"),
    ("GET", r"^/api/jobs$", api_job_list, None),
    ("POST", r"^/api/jobs$", api_job_create, "hire.write"),
    ("POST", r"^/api/jobs/([^/]+)/stage$", api_job_stage, "hire.write"),
    ("GET", r"^/api/candidates$", api_cand_list, None),
    ("POST", r"^/api/candidates$", api_cand_create, "hire.write"),
    ("POST", r"^/api/candidates/([^/]+)/stage$", api_cand_stage, "hire.write"),
    ("GET", r"^/api/interviews$", api_iv_list, None),
    ("POST", r"^/api/interviews$", api_iv_create, "hire.write"),
    ("POST", r"^/api/interviews/([0-9]+)$", api_iv_result, "hire.write"),
    ("GET", r"^/api/perf/cycles$", api_perf_cycles, None),
    ("POST", r"^/api/perf/cycles$", api_perf_cycle_create, "perf.write"),
    ("GET", r"^/api/perf/scores$", api_perf_scores, None),
    ("POST", r"^/api/perf/scores$", api_perf_score_set, "perf.write"),
    ("POST", r"^/api/perf/cycles/([^/]+)/publish$", api_perf_publish, "perf.write"),
    ("GET", r"^/api/trainings$", api_training_list, None),
    ("POST", r"^/api/trainings$", api_training_create, "org.write"),
    ("POST", r"^/api/trainings/([^/]+)/enroll$", api_training_enroll, None),
    ("POST", r"^/api/trainings/([^/]+)/grade$", api_training_grade, "org.write"),
    ("GET", r"^/api/trainings/([^/]+)/records$", api_training_records, None),
    ("GET", r"^/api/contracts$", api_contract_list, None),
    ("POST", r"^/api/contracts/renew$", api_contract_renew, "org.write"),
    ("GET", r"^/api/reports/headcount$", api_report_headcount, None),
    ("GET", r"^/api/reports/(attendance|leaves|payslips)\.csv$", None, None),  # 导出特殊处理
    ("GET", r"^/api/rules$", api_rules, None),
    ("PUT", r"^/api/rules/([^/]+)$", api_rule_update, "admin"),
    ("GET", r"^/api/users$", api_user_list, None),
    ("POST", r"^/api/users$", api_user_create, "admin"),
    ("GET", r"^/api/logs$", api_logs, None),
    ("GET", r"^/api/keys$", api_key_list, None),
    ("POST", r"^/api/keys$", api_key_create, "admin"),
    ("POST", r"^/api/keys/([0-9]+)/revoke$", api_key_revoke, "admin"),
    ("GET", r"^/api/webhooks$", api_wh_list, None),
    ("POST", r"^/api/webhooks$", api_wh_create, "admin"),
    ("POST", r"^/api/webhooks/test$", api_wh_test, None),
    ("GET", r"^/api/webhooks/deliveries$", api_wh_deliveries, None),
    ("GET", r"^/api/sync/changes$", api_sync, None),
    ("GET", r"^/api/health$", api_health, None),
    ("GET", r"^/api/openapi\.json$", api_openapi, None),
]

_COMPILED = [(m, re.compile(p), fn, perm) for m, p, fn, perm in ROUTES]


# ---------------------------------------------------------------- HTTP 处理

class Handler(BaseHTTPRequestHandler):
    server_version = "FeiHua-HRM/" + VERSION

    def log_message(self, fmt, *args):  # noqa: A003
        pass

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return (self.headers.get("X-Hr-Token") or self.headers.get("X-Auth-Token")
                or self._cookie_token() or self._query_token() or "")

    def _cookie_token(self):
        c = self.headers.get("Cookie") or ""
        m = re.search(r"token=([0-9a-f]+)", c)
        return m.group(1) if m else ""

    def _query_token(self):
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get("token") or [""])[0]

    def _send(self, code, obj, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            bad("请求体不是合法 JSON")

    def _rate_ok(self):
        ip = self.client_address[0]
        now = time.time()
        w = _RATE.get(ip)
        if not w or now - w[0] > 60:
            _RATE[ip] = [now, 1]
            return True
        w[1] += 1
        return w[1] <= _RATE_LIMIT

    def _user(self, cn, need_perm):
        token = self._token()
        uname = token_user(cn, token)
        if not uname:
            key = check_key(cn, self.headers.get("X-Hr-Key") or "")
            if key:
                if need_perm and need_perm not in ("org.read", "att.read", "hire.read",
                                                   "pay.read", None):
                    bad("API Key 为只读 scope，禁止写操作", 403)
                return {"username": "apikey:" + key["name"], "name": key["name"],
                        "role": "auditor", "empNo": "", "_token": ""}
            bad("未登录或令牌无效", 401)
        r = cn.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
        if not r:
            bad("用户不存在", 401)
        u = {"username": r["username"], "name": r["name"], "role": r["role"],
             "empNo": r["emp_no"] or "", "_token": token}
        if need_perm and not hrm.can(u["role"], need_perm):
            bad("权限不足（需要 %s）" % need_perm, 403)
        return u

    def _dispatch(self, method):
        if not self._rate_ok():
            return self._send(429, {"code": 429, "message": "请求过于频繁，请稍后再试"})
        path = urlparse(self.path).path
        if method == "GET" and not path.startswith("/api/"):
            return self._static(path)
        try:
            cn = connect()
            match = None
            for mth, rx, fn, perm in _COMPILED:
                if mth != method:
                    continue
                m = rx.match(path)
                if m:
                    match = (fn, perm, m)
                    break
            if match and match[0] is None and ".csv" in path:
                u = self._user(cn, None)
                kind = re.search(r"reports/(\w+)\.csv", path).group(1)
                out = api_export(u, m, kind)
                if "__csv__" in out:
                    data = b"\xef\xbb\xbf" + out["text"].encode("utf-8")
                    from urllib.parse import quote
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition",
                                     "attachment; filename*=UTF-8''%s" % quote(out["__csv__"]))
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    db.close_thread_conns()
                    return
            if not match:
                bad("接口不存在：%s %s" % (method, path), 404)
            fn, perm, m = match
            body = {} if method == "GET" else self._body_json()
            idem = self.headers.get("Idempotency-Key")
            if idem and method == "POST":
                row = cn.execute("SELECT status,response FROM idem_keys WHERE key=?",
                                 (idem,)).fetchone()
                if row and row["status"] == "done":
                    return self._send(200, json.loads(row["response"]),
                                      {"X-Idempotent-Replay": "true"})
                cn.execute("INSERT OR IGNORE INTO idem_keys(key,created) VALUES(?,?)",
                           (idem, hrm.now_str()))
                cn.commit()
            if perm:
                u = self._user(cn, perm)
            elif path in ("/api/auth/login", "/api/health", "/api/openapi.json"):
                u = None
            else:
                u = self._user(cn, None)
            out = fn(u, m, body)
            if idem and method == "POST":
                cn.execute("UPDATE idem_keys SET status='done',response=? WHERE key=?",
                           (json.dumps(out, ensure_ascii=False), idem))
                cn.commit()
            self._send(200, out)
        except ApiErr as e:
            try:
                self._send(e.code, {"code": e.code, "message": e.msg})
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            try:
                self._send(500, {"code": 500, "message": "服务器内部错误：%s" % e})
            except Exception:  # noqa: BLE001
                pass
        finally:
            db.close_thread_conns()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _static(self, path):
        if path in ("/", "/index.html", "/login.html") or re.match(r"^/[a-z_]+\.js$", path) \
                or path.endswith(".css"):
            fname = "index.html" if path == "/" else path.lstrip("/")
            fp = os.path.join(FRONT, fname)
            if os.path.isfile(fp):
                ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8",
                         "css": "text/css; charset=utf-8"}.get(fname.rsplit(".", 1)[-1],
                                                               "application/octet-stream")
                data = open(fp, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
                return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def openapi_json():
    paths = {}
    for mth, rx, fn, perm in _COMPILED:
        p = re.sub(r"\([^)]*\)", "{param}", rx.pattern)
        p = p.strip("^$")
        if ".csv" in p:
            p = "/api/reports/{kind}.csv"
        item = paths.setdefault(p, {})
        item[mth.lower()] = {"summary": (fn.__name__ if fn else "export"),
                             "tags": [p.split("/")[2] if len(p.split("/")) > 2 else "misc"]}
    return {"openapi": "3.0.0", "info": {"title": BRAND + " REST API", "version": VERSION},
            "paths": paths}


def _worker_loop():
    """Webhook 投递线程：HMAC-SHA256 签名 + 3 次退避（30/60/120s）"""
    backoff = [30, 60, 120]
    while True:
        try:
            if _WEBHOOK_Q:
                wid, url, secret, event, payload = _WEBHOOK_Q.pop(0)
                body = payload.encode("utf-8")
                ts = str(int(time.time()))
                sig = hmac.new(secret.encode(), (ts + "." + payload).encode(),
                               hashlib.sha256).hexdigest()
                req = urllib.request.Request(url, data=body, method="POST", headers={
                    "Content-Type": "application/json", "X-Hr-Event": event,
                    "X-Hr-Timestamp": ts, "X-Hr-Signature": sig,
                    "X-Hr-Delivery": hashlib.md5((url + ts).encode()).hexdigest()[:16]})
                cn = connect()
                try:
                    r = urllib.request.urlopen(req, timeout=5)
                    cn.execute("UPDATE webhook_deliveries SET status='success',attempts=attempts+1,"
                               "last_at=?,response=? WHERE webhook_id=? AND event=? AND status='pending'",
                               (hrm.now_str(), str(r.status), wid, event))
                except Exception as e:  # noqa: BLE001
                    att = val(cn, "SELECT attempts FROM webhook_deliveries WHERE webhook_id=?"
                                  " AND event=? AND status='pending'", (wid, event))
                    if att < 3:
                        cn.execute("UPDATE webhook_deliveries SET attempts=attempts+1,last_at=?,"
                                   "response=? WHERE webhook_id=? AND event=? AND status='pending'",
                                   (hrm.now_str(), str(e)[:200], wid, event))
                        _WEBHOOK_Q.append((wid, url, secret, event, payload))
                    else:
                        cn.execute("UPDATE webhook_deliveries SET status='failed',attempts=attempts+1,"
                                   "last_at=?,response=? WHERE webhook_id=? AND event=? AND status='pending'",
                                   (hrm.now_str(), str(e)[:200], wid, event))
                cn.commit()
                db.close_thread_conns()
            else:
                time.sleep(0.5)
        except Exception:  # noqa: BLE001
            time.sleep(1)


def main():
    db.init()
    cn = connect()
    if not val(cn, "SELECT COUNT(*) FROM users"):
        seed_mod.seed()
    db.close_thread_conns()
    threading.Thread(target=_worker_loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("%s %s listening on %s:%d" % (BRAND, VERSION, HOST, PORT))
    srv.serve_forever()


if __name__ == "__main__":
    main()

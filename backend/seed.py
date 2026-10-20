# -*- coding: utf-8 -*-
"""飞花HRM系统 · 确定性演示数据（8 部门 / 22 员工 / 60 天考勤 / 请假加班 / 薪资核算 / 招聘 / 绩效 / 培训 / 合同）"""
import datetime
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import hrm

PWD = "hr@2026"


def _hash(pwd, salt):
    return hashlib.sha256((pwd + salt).encode("utf-8")).hexdigest()


def _add_log(cn, user, action, detail=""):
    cn.execute("INSERT INTO logs(at,user,action,detail) VALUES(?,?,?,?)",
               (hrm.now_str(), user, action, detail))


def seed():
    db.init()
    cn = db.connect()
    rnd = random.Random(20261021)
    base = datetime.date(2026, 10, 21)

    # ---- 部门（8）
    depts = [
        ("D01", "总经办", 0, "陈总", 3), ("D02", "人力资源部", 1, "周慧", 6),
        ("D03", "财务部", 1, "钱进", 5), ("D04", "研发中心", 1, "王明", 30),
        ("D05", "市场部", 1, "吴芳", 10), ("D06", "生产运营部", 1, "郑强", 24),
        ("D07", "质量管理部", 1, "冯静", 8), ("D08", "供应链部", 1, "褚亮", 9),
    ]
    for code, name, parent, leader, plan in depts:
        cn.execute("INSERT INTO departments(code,name,parent_id,leader,headcount_plan,created)"
                   " VALUES(?,?,?,?,?,?)", (code, name, parent, leader, plan, hrm.now_str()))

    # ---- 员工（22）
    emps = [
        ("EMP001", "陈志远", "男", "D01", "总经理", "M6", "2020-03-02", "已转正", 45000, ""),
        ("EMP002", "周慧",   "女", "D02", "HRBP", "M4", "2021-06-01", "已转正", 16000, "陈志远"),
        ("EMP003", "林悦",   "女", "D02", "招聘专员", "P3", "2023-02-13", "已转正", 11000, "周慧"),
        ("EMP004", "钱进",   "男", "D03", "财务经理", "M4", "2020-05-11", "已转正", 22000, "陈志远"),
        ("EMP005", "张晓",   "女", "D03", "薪酬专员", "P3", "2022-09-05", "已转正", 10500, "钱进"),
        ("EMP006", "王明",   "男", "D04", "研发总监", "M6", "2019-11-18", "已转正", 40000, "陈志远"),
        ("EMP007", "李工",   "男", "D04", "高级工程师", "P5", "2021-03-15", "已转正", 26000, "王明"),
        ("EMP008", "赵磊",   "男", "D04", "工程师", "P4", "2022-07-01", "已转正", 18000, "王明"),
        ("EMP009", "孙倩",   "女", "D04", "工程师", "P4", "2023-04-10", "已转正", 17000, "王明"),
        ("EMP010", "吴宇",   "男", "D04", "助理工程师", "P2", "2026-04-06", "试用期", 12000, "李工"),
        ("EMP011", "郑强",   "男", "D06", "运营经理", "M4", "2020-08-03", "已转正", 21000, "陈志远"),
        ("EMP012", "冯静",   "女", "D07", "质量经理", "M4", "2021-01-11", "已转正", 20000, "陈志远"),
        ("EMP013", "陈静",   "女", "D07", "质量工程师", "P4", "2022-05-16", "已转正", 15000, "冯静"),
        ("EMP014", "褚亮",   "男", "D08", "供应链经理", "M4", "2020-10-12", "已转正", 21000, "陈志远"),
        ("EMP015", "卫红",   "女", "D08", "采购主管", "P4", "2022-11-21", "已转正", 14000, "褚亮"),
        ("EMP016", "蒋涛",   "男", "D06", "班组长", "P3", "2021-09-06", "已转正", 11000, "郑强"),
        ("EMP017", "沈丽",   "女", "D05", "市场主管", "P4", "2023-01-30", "已转正", 14000, "吴芳"),
        ("EMP018", "韩梅",   "女", "D05", "市场专员", "P2", "2026-08-03", "试用期", 9000, "沈丽"),
        ("EMP019", "杨帆",   "男", "D06", "技术工人", "P2", "2022-03-14", "已转正", 8500, "蒋涛"),
        ("EMP020", "朱琳",   "女", "D02", "人事专员", "P2", "2026-09-07", "试用期", 9000, "周慧"),
        ("EMP021", "秦峰",   "男", "D04", "工程师", "P4", "2024-02-19", "已转正", 16500, "王明"),
        ("EMP022", "许晴",   "女", "D03", "会计", "P3", "2023-08-08", "离职中", 11500, "钱进"),
    ]
    for no, name, gender, dept, pos, level, hire, status, salary, manager in emps:
        reg = "" if status == "试用期" else hire
        cn.execute("INSERT INTO employees(no,name,gender,dept_code,position,level,hire_date,"
                   "regular_date,status,base_salary,manager,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (no, name, gender, dept, pos, level, hire, reg, status, salary, manager, hrm.now_str()))

    # ---- 用户（8 角色）
    users = [
        ("admin", "系统管理员", "admin", ""),
        ("zhouh", "周慧", "hr", "EMP002"),
        ("zhrd", "陈志远", "hrd", "EMP001"),
        ("wangm", "王明", "manager", "EMP006"),
        ("zhangx", "张晓", "payroll", "EMP005"),
        ("liny", "林悦", "recruiter", "EMP003"),
        ("sunq", "孙倩", "employee", "EMP009"),
        ("shenj", "沈丽", "auditor", "EMP017"),
    ]
    for username, name, role, emp_no in users:
        salt = hashlib.md5(username.encode()).hexdigest()[:8]
        cn.execute("INSERT INTO users(username,password_hash,salt,name,role,emp_no,created)"
                   " VALUES(?,?,?,?,?,?,?)", (username, _hash(PWD, salt), salt, name, role, emp_no, hrm.now_str()))

    # ---- 考勤（近 30 个自然日 × 22 员工，确定性随机）
    for d in range(30, 0, -1):
        day = base - datetime.timedelta(days=d)
        if day.weekday() >= 5:
            continue
        ds = day.isoformat()
        for no, *_ in emps:
            r = rnd.random()
            if no == "EMP010" and r < 0.06:
                st, ci, co, wh, late = "请假", "", "", 0, 0
            elif no == "EMP019" and r < 0.08:
                st, ci, co, wh, late = "迟到", "09:%02d" % rnd.randint(16, 40), "18:05", 8.0, rnd.randint(16, 40)
            elif r < 0.02:
                st, ci, co, wh, late = "缺卡", "", "18:02", 0, 0
            elif r < 0.025:
                st, ci, co, wh, late = "早退", "08:55", "17:%02d" % rnd.randint(20, 50), 7.0, 0
            elif r < 0.03:
                st, ci, co, wh, late = "缺勤", "", "", 0, 0
            elif r < 0.05:
                st, ci, co, wh, late = "出差", "08:50", "18:30", 8.0, 0
            else:
                late_m = rnd.choice([0, 0, 0, 0, 0, 0, 5, 10])
                ci = "08:%02d" % rnd.randint(30, 59) if late_m == 0 else "09:%02d" % late_m
                co = "18:%02d" % rnd.randint(2, 59)
                j = hrm.attendance_judge(ci, co)
                st, wh, late = j["status"], j["workHours"], j["lateMin"]
            cn.execute("INSERT OR REPLACE INTO attendance(emp_no,date,clock_in,clock_out,status,"
                       "work_hours,late_min) VALUES(?,?,?,?,?,?,?)", (no, ds, ci, co, st, wh, late))

    # ---- 假期余额与请假单
    for no, name, *_ in emps:
        yrs = hrm.service_years([e for e in emps if e[0] == no][0][6])
        quota = hrm.annual_leave_quota(yrs)
        used = round(quota * rnd.uniform(0.1, 0.6), 1)
        cn.execute("INSERT INTO leave_balances(emp_no,year,ltype,quota,used) VALUES(?,?,?,?,?)",
                   (no, base.year, "年假", quota, used))
        cn.execute("INSERT INTO leave_balances(emp_no,year,ltype,quota,used) VALUES(?,?,?,?,?)",
                   (no, base.year, "调休", rnd.choice([1, 2, 3]), rnd.uniform(0, 1)))
    leaves = [
        ("LV0001", "EMP009", "年假", 10, 12, 3.0, "已批准", "王明"),
        ("LV0002", "EMP019", "事假", 10, 12, 1.0, "已批准", "郑强"),
        ("LV0003", "EMP007", "病假", 9, 11, 2.0, "已批准", "王明"),
        ("LV0004", "EMP013", "年假", 10, 13, 2.0, "已批准", "冯静"),
        ("LV0005", "EMP015", "调休", 10, 14, 1.0, "已批准", "褚亮"),
        ("LV0006", "EMP017", "事假", 10, 15, 0.5, "待审批", ""),
        ("LV0007", "EMP021", "年假", 10, 16, 2.0, "待审批", ""),
        ("LV0008", "EMP018", "事假", 9, 28, 1.0, "已驳回", "吴芳"),
    ]
    seq = 0
    for no, emp, lt, sd, ed, days, status, approver in leaves:
        s = base - datetime.timedelta(days=sd)
        e = s + datetime.timedelta(days=int(days))
        seq += 1
        cn.execute("INSERT INTO leaves(no,emp_no,ltype,start_date,end_date,days,reason,status,"
                   "approver,decided_at,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (no, emp, lt, s.isoformat(), e.isoformat(), days, "演示请假数据",
                    status, approver, hrm.now_str() if status in ("已批准", "已驳回") else "",
                    hrm.now_str()))

    # ---- 加班单
    ots = [("EMP007", 26, 3.5, "工作日", "已批准"), ("EMP008", 24, 2.0, "工作日", "已批准"),
           ("EMP009", 22, 4.0, "周末", "已批准"), ("EMP013", 20, 2.5, "工作日", "已批准"),
           ("EMP019", 27, 5.0, "工作日", "已批准"), ("EMP021", 25, 3.0, "周末", "待审批")]
    for i, (emp, dback, hours, otype, status) in enumerate(ots, 1):
        cn.execute("INSERT INTO overtimes(no,emp_no,date,hours,otype,reason,status,approver,"
                   "decided_at,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   ("OT%04d" % i, emp, (base - datetime.timedelta(days=dback)).isoformat(),
                    hours, otype, "项目攻坚/演示数据", status,
                    "" if status == "待审批" else "王明",
                    hrm.now_str() if status == "已批准" else "", hrm.now_str()))

    # ---- 招聘：职位 / 候选人 / 面试
    jobs = [("JB0001", "高级软件工程师", "D04", 2, "25-35K", "本科", "招聘中", "王明"),
            ("JB0002", "质量工程师", "D07", 1, "12-18K", "本科", "招聘中", "冯静"),
            ("JB0003", "采购专员", "D08", 1, "8-12K", "大专", "招聘中", "褚亮"),
            ("JB0004", "人事专员", "D02", 1, "7-10K", "本科", "已关闭", "周慧")]
    for no, title, dept, hc, rng, edu, status, mgr in jobs:
        cn.execute("INSERT INTO jobs(no,title,dept_code,headcount,salary_range,education,"
                   "status,hiring_manager,created) VALUES(?,?,?,?,?,?,?,?,?)",
                   (no, title, dept, hc, rng, edu, status, mgr, hrm.now_str()))
    cands = [
        ("CD0001", "高翔", "JB0001", "猎聘", "面试中", 4, 28000, 0),
        ("CD0002", "罗娜", "JB0001", "BOSS", "已发Offer", 5, 26000, 30000),
        ("CD0003", "黄凯", "JB0001", "内推", "已淘汰", 2, 0, 0),
        ("CD0004", "丁一", "JB0002", "智联", "面试中", 3, 15000, 0),
        ("CD0005", "白雪", "JB0002", "猎聘", "已入职", 4, 16000, 16000),
        ("CD0006", "田园", "JB0003", "BOSS", "初筛", 0, 9500, 0),
        ("CD0007", "肖鹏", "JB0003", "智联", "已淘汰", 1, 0, 0),
        ("CD0008", "袁媛", "JB0004", "内推", "已入职", 4, 9500, 9500),
    ]
    for no, name, job, src, stage, rating, exp, offer in cands:
        cn.execute("INSERT INTO candidates(no,name,job_no,source,stage,rating,expected_salary,"
                   "offer_salary,created) VALUES(?,?,?,?,?,?,?,?,?)",
                   (no, name, job, src, stage, rating, exp, offer, hrm.now_str()))
    ivs = [("CD0001", 1, "王明", 24, "通过", 82, "技术扎实，沟通好"),
           ("CD0001", 2, "李工", 21, "通过", 85, "架构思路清晰"),
           ("CD0002", 1, "王明", 25, "通过", 88, "稳定性佳"),
           ("CD0002", 2, "陈志远", 20, "通过", 86, "文化匹配"),
           ("CD0003", 1, "王明", 26, "未通过", 45, "基础薄弱"),
           ("CD0004", 1, "冯静", 22, "通过", 75, "经验尚浅但态度好"),
           ("CD0005", 1, "冯静", 28, "通过", 84, "体系经验丰富"),
           ("CD0007", 1, "褚亮", 27, "未通过", 52, "抗压一般")]
    for cno, rd, interviewer, dback, result, score, fb in ivs:
        cn.execute("INSERT INTO interviews(candidate_no,rounds,interviewer,scheduled_at,form,"
                   "result,score,feedback,created) VALUES(?,?,?,?,?,?,?,?,?)",
                   (cno, rd, interviewer, (base - datetime.timedelta(days=dback)).isoformat() + " 14:00",
                    "现场", result, score, fb, hrm.now_str()))

    # ---- 绩效（Q3 考核周期 + 全员评分）
    cyc = "2026-Q3"
    cn.execute("INSERT INTO perf_cycles(name,period,status,start_date,end_date,created)"
               " VALUES(?,?,?,?,?,?)", (cyc, "2026-07 ~ 2026-09", "已评分",
                                        "2026-07-01", "2026-09-30", hrm.now_str()))
    for no, name, *_ in emps:
        if no == "EMP022":
            continue
        dims = {"work_qty": rnd.randint(60, 98), "work_quality": rnd.randint(60, 98),
                "cooperation": rnd.randint(65, 96), "discipline": rnd.randint(75, 100)}
        total = hrm.perf_score(dims)
        cn.execute("INSERT OR REPLACE INTO perf_scores(cycle,emp_no,work_qty,work_quality,"
                   "cooperation,discipline,total,grade,comment,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (cyc, no, dims["work_qty"], dims["work_quality"], dims["cooperation"],
                    dims["discipline"], total, hrm.perf_grade(total), "季度考核演示数据",
                    hrm.now_str()))

    # ---- 培训
    trs = [("TR0001", "新员工入职培训", "入职", "周慧", 28, 4, 40, "已完成"),
           ("TR0002", "Python 数据分析实战", "技能", "李工", 18, 8, 20, "报名中"),
           ("TR0003", "ISO9001 体系内审员", "合规", "冯静", 12, 6, 15, "报名中"),
           ("TR0004", "管理者角色认知", "管理", "陈志远", 8, 3, 12, "报名中")]
    for no, title, cat, trainer, dback, hours, quota, status in trs:
        cn.execute("INSERT INTO trainings(no,title,category,trainer,date,hours,quota,status,"
                   "created) VALUES(?,?,?,?,?,?,?,?,?)",
                   (no, title, cat, trainer, (base - datetime.timedelta(days=dback)).isoformat(),
                    hours, quota, status, hrm.now_str()))
        enrolled = rnd.sample([e[0] for e in emps], min(8, quota - 2))
        for emp in enrolled:
            done = status == "已完成"
            cn.execute("INSERT OR REPLACE INTO training_records(training_no,emp_no,status,score)"
                       " VALUES(?,?,?,?)",
                       (no, emp, "已完成" if done else "已报名",
                        rnd.randint(70, 98) if done else 0))

    # ---- 合同（含 1 份临期 + 1 份已到期风险，其余视为已续签至未来）
    for no, name, gender, dept, pos, level, hire, status, salary, manager in emps:
        start = hire
        end = str(int(hire[:4]) + 3) + hire[4:]
        try:
            import datetime as _dt
            if _dt.date.fromisoformat(end) < base:
                end = (base + _dt.timedelta(days=rnd.choice([150, 300, 480, 700]))).isoformat()
        except ValueError:
            pass
        if no == "EMP019":
            end = (base + datetime.timedelta(days=35)).isoformat()
        if no == "EMP021":
            end = (base - datetime.timedelta(days=10)).isoformat()
        cn.execute("INSERT INTO contracts(emp_no,ctype,start_date,end_date,status,signed_at,remark)"
                   " VALUES(?,?,?,?,?,?,?)",
                   (no, "固定期限", start, end, "履行中", start, ""))

    # ---- 薪资：上月经核算、本月草稿（不生成工资条，供闸口演示）
    prev = (base.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    cn.execute("INSERT INTO payroll_runs(month,status,total_gross,total_net,headcount,created)"
               " VALUES(?,?,?,?,?,?)", (prev, "已发放", 356000, 271000, 21, hrm.now_str()))
    for no, name, gender, dept, pos, level, hire, status, salary, manager in emps:
        if status == "已转正" or no in ("EMP010", "EMP018"):
            calc = hrm.payroll_calc({"baseSalary": salary}, None, 82, {"工作日": 2}, 0)
            cn.execute("INSERT INTO payslips(run_id,emp_no,base,perf_bonus,ot_pay,allowance,"
                       "gross,social_ins,hf,tax,absence_ded,other_ded,net) VALUES("
                       "(SELECT id FROM payroll_runs WHERE month=?),?,?,?,?,?,?,?,?,?,?,?,?)",
                       (prev, no, calc["base"], calc["perfBonus"], calc["otPay"], calc["allowance"],
                        calc["gross"], calc["socialIns"], calc["hf"], calc["tax"],
                        calc["absenceDed"], 0, calc["net"]))

    # ---- 业务规则（12 条）
    for code, name, cat, value, unit, remark in hrm.DEFAULT_RULES:
        cn.execute("INSERT INTO rules(code,name,category,value,unit,enabled,remark)"
                   " VALUES(?,?,?,?,?,1,?)", (code, name, cat, value, unit, remark))

    # ---- 集成（API Key / Webhook / 同步游标占位）
    key_plain = "fhk_" + hashlib.sha256(b"feihua-demo-key").hexdigest()[:24]
    kh = hashlib.sha256(key_plain.encode()).hexdigest()
    cn.execute("INSERT INTO api_keys(key_hash,prefix,name,scope,created) VALUES(?,?,?,?,?)",
               (kh, key_plain[:8], "演示集成Key", "read", hrm.now_str()))
    cn.execute("INSERT INTO webhooks(name,url,secret,events,created) VALUES(?,?,?,?,?)",
               ("演示回调", "http://127.0.0.1:9/hook",
                hashlib.md5(b"feihua-hook").hexdigest(), "employee.created,leave.approved",
                hrm.now_str()))
    for ent in ("employees", "leaves", "attendance"):
        cn.execute("INSERT OR REPLACE INTO sync_state(entity,last_at) VALUES(?,?)",
                   (ent, hrm.now_str()))
    _add_log(cn, "admin", "种子数据初始化", "8 部门 / 22 员工 / 30 天考勤")
    cn.commit()
    print("seed 完成：22 员工 / 8 部门 / 请假 8 / 加班 6 / 候选 8 / 培训 4")


if __name__ == "__main__":
    seed()

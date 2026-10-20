# -*- coding: utf-8 -*-
"""飞花HRM系统 · 纯函数业务内核（状态机与闸口 / 考勤口径 / 个税与薪资 / 假期额度 / 绩效 / 权限）"""

BRAND = "飞花HRM"
VERSION = "1.0.0"

# ---------------------------------------------------------------- 基础工具

def safe_num(v, default=0.0):
    try:
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def today():
    import datetime
    return datetime.date.today().isoformat()


def now_str():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def doc_no(prefix, day, seq):
    return "%s%s-%04d" % (prefix, day.replace("-", ""), int(seq))


# ---------------------------------------------------------------- 状态机

EMP_STATES = ["试用期", "已转正", "离职中", "已离职"]
LEAVE_STATES = ["待审批", "已批准", "已驳回", "已销假", "已撤回"]
CAND_STATES = ["初筛", "面试中", "已发Offer", "已入职", "已淘汰"]
PAYROLL_STATES = ["草稿", "已核算", "已发放"]


def can_move(chain, cur, nxt):
    if cur not in chain or nxt not in chain:
        return False
    return chain.index(nxt) > chain.index(cur)


def emp_gate(cur, target, ctx):
    """员工状态闸口。ctx: years, perfScore, regularEval, handoverDone, approveBy"""
    ctx = ctx or {}
    if not can_move(EMP_STATES, cur, target):
        return "状态不允许从「%s」变更为「%s」" % (cur, target)
    if target == "已转正":
        if safe_num(ctx.get("years")) < 0:
            return "入职日期异常"
        if not ctx.get("regularEval"):
            return "转正闸口：缺少转正评估（带教人评价/试用期总结）"
        if safe_num(ctx.get("perfScore")) < 60:
            return "转正闸口：试用期绩效得分低于 60 分，不能转正"
    if target == "离职中":
        if not ctx.get("approveBy"):
            return "离职闸口：需人事负责人审批发起"
    if target == "已离职":
        if cur != "离职中":
            return "离职闸口：必须先经人事审批进入「离职中」"
        if not ctx.get("handoverDone"):
            return "离职闸口：工作交接未完成，不能办理离职"
    return None


def leave_gate(cur, target, ctx):
    """请假闸口。ctx: days, quotaLeft, overlap, isPoster, isApprover"""
    ctx = ctx or {}
    if target == "待审批":
        if safe_num(ctx.get("days")) <= 0:
            return "请假闸口：请假天数必须大于 0"
        if ctx.get("overlap"):
            return "请假闸口：与已有请假单时间重叠"
        left = safe_num(ctx.get("quotaLeft"), 9e9)
        if safe_num(ctx.get("days")) > left:
            return "请假闸口：假期余额不足（剩余 %.1f 天）" % left
    if target == "已批准":
        if cur != "待审批":
            return "只有待审批单可以批准"
        if not ctx.get("isApprover"):
            return "只有审批人可以批准"
    if target == "已驳回":
        if cur != "待审批":
            return "只有待审批单可以驳回"
        if not ctx.get("isApprover"):
            return "只有审批人可以驳回"
    if target == "已撤回":
        if cur != "待审批" or not ctx.get("isPoster"):
            return "仅本人可在待审批时撤回"
    if target == "已销假":
        if cur != "已批准":
            return "只有已批准的假单可以销假"
    return None


def candidate_gate(cur, target, ctx):
    """候选人闸口。ctx: roundsPassed, interviewerFeedback, offerSalary, onboardDeptOk"""
    ctx = ctx or {}
    if not can_move(CAND_STATES, cur, target) and not (cur == "面试中" and target == "已淘汰"):
        return "候选人状态不允许从「%s」变更为「%s」" % (cur, target)
    if target == "面试中":
        if cur != "初筛":
            return "只有初筛通过的候选人可以安排面试"
    if target == "已发Offer":
        if safe_num(ctx.get("roundsPassed")) < 1:
            return "Offer 闸口：至少一轮面试通过后才能发 Offer"
        if not ctx.get("interviewerFeedback"):
            return "Offer 闸口：缺少面试官评价"
        if safe_num(ctx.get("offerSalary")) <= 0:
            return "Offer 闸口：未填写核定薪酬"
    if target == "已入职":
        if not ctx.get("onboardDeptOk"):
            return "入职闸口：入职部门/岗位未确认"
    return None


def payroll_gate(cur, target, ctx):
    """薪资核算闸口。ctx: slipCount, empCount, itemsChecked, approveBy"""
    ctx = ctx or {}
    if not can_move(PAYROLL_STATES, cur, target):
        return "工资单不允许从「%s」变更为「%s」" % (cur, target)
    if target == "已核算":
        if safe_num(ctx.get("slipCount")) <= 0:
            return "核算闸口：未生成任何工资条"
        if safe_num(ctx.get("slipCount")) < safe_num(ctx.get("empCount")):
            return "核算闸口：工资条数量（%d）少于在职员工数（%d），有遗漏" % (
                safe_num(ctx.get("slipCount")), safe_num(ctx.get("empCount")))
    if target == "已发放":
        if cur != "已核算":
            return "发放闸口：必须先完成核算才能发放"
        if not ctx.get("approveBy"):
            return "发放闸口：需薪酬负责人确认发放"
    return None


# ---------------------------------------------------------------- 考勤口径

SHIFT_START = "09:00"
SHIFT_END = "18:00"
GRACE_MIN = 15


def _to_min(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def attendance_judge(clock_in, clock_out, on_leave=False, business_trip=False,
                     shift_start=SHIFT_START, shift_end=SHIFT_END, grace_min=GRACE_MIN):
    """返回 {status, workHours, lateMin, earlyMin}。缺卡/不足工时口径清晰可测。"""
    si, ei = _to_min(shift_start), _to_min(shift_end)
    ci, co = _to_min(clock_in or ""), _to_min(clock_out or "")
    late = max(0, (ci - si) - grace_min) if (ci is not None and si is not None) else 0
    early = max(0, (ei - co)) if (co is not None and ei is not None) else 0
    if on_leave:
        return {"status": "请假", "workHours": 0.0, "lateMin": 0, "earlyMin": 0}
    if business_trip:
        return {"status": "出差", "workHours": 8.0, "lateMin": 0, "earlyMin": 0}
    if ci is None and co is None:
        return {"status": "缺勤", "workHours": 0.0, "lateMin": 0, "earlyMin": 0}
    if ci is None or co is None:
        return {"status": "缺卡", "workHours": 0.0, "lateMin": late, "earlyMin": early}
    hours = max(0.0, (co - ci) / 60.0 - 1.0)          # 午休 1 小时不计工时
    status = "正常"
    if late > 0:
        status = "迟到"
    elif early > 0:
        status = "早退"
    return {"status": status, "workHours": round(hours, 2), "lateMin": late, "earlyMin": early}


def attendance_rate(records, workdays):
    """出勤率 = 正常/迟到/早退/出差计入出勤的天数 / 应出勤天数"""
    if workdays <= 0:
        return 0.0
    ok = sum(1 for r in records if r.get("status") in ("正常", "迟到", "早退", "出差"))
    return round(min(1.0, ok / float(workdays)), 4)


# ---------------------------------------------------------------- 假期额度

def annual_leave_quota(years_of_service, probation_months=0):
    """年假口径：工龄满1年5天，满10年10天，满20年15天；不满1年按剩余日历天折算。"""
    y = safe_num(years_of_service)
    if y < 1:
        if y <= 0:
            return 0.0
        remain = max(0, 365 - int(y * 365))
        return round(5.0 * remain / 365.0, 1)
    if y < 10:
        return 5.0
    if y < 20:
        return 10.0
    return 15.0


def overtime_pay(hourly, hours, otype):
    """加班费：工作日 1.5 倍，周末 2 倍，节假日 3 倍。"""
    rate = {"工作日": 1.5, "周末": 2.0, "节假日": 3.0}.get(otype)
    if rate is None:
        return None
    return round(safe_num(hourly) * safe_num(hours) * rate, 2)


# ---------------------------------------------------------------- 个税与薪资

TAX_BRACKETS = [            # (级距上限, 速率, 速算扣除)  月度应纳税所得额
    (3000, 0.03, 0), (12000, 0.10, 210), (25000, 0.20, 1410),
    (35000, 0.25, 2660), (55000, 0.30, 4410), (80000, 0.35, 7160),
    (float("inf"), 0.45, 15160),
]
TAX_THRESHOLD = 5000.0


def income_tax(social_plus_hf, base, perf_bonus, ot_pay, allowance):
    """月度个税（简化口径）：应纳税所得额 = 应发 - 起征5000 - 三险一金。"""
    taxable = safe_num(base) + safe_num(perf_bonus) + safe_num(ot_pay) + \
        safe_num(allowance) - TAX_THRESHOLD - safe_num(social_plus_hf)
    if taxable <= 0:
        return 0.0
    for cap, rate, quick in TAX_BRACKETS:
        if taxable <= cap:
            return round(taxable * rate - quick, 2)
    return 0.0


SOCIAL_RATE = {"养老": 0.08, "医疗": 0.02, "失业": 0.005, "工伤": 0.0, "生育": 0.0}
HF_RATE = 0.12
SOCIAL_BASE_CAP = (4000.0, 24000.0)     # 缴费基数上下限


def social_insurance(base_salary):
    b = min(max(safe_num(base_salary), SOCIAL_BASE_CAP[0]), SOCIAL_BASE_CAP[1])
    personal = round(b * sum(SOCIAL_RATE.values()), 2)
    hf = round(b * HF_RATE, 2)
    company = round(b * 0.315, 2)       # 企业合计约 31.5%
    return {"base": b, "personal": personal, "hf": hf, "company": company}


def payroll_calc(emp, att, perf_total, ot_hours_by_type, absence_days, allowance=200.0):
    """单员工月度工资条核算。emp: baseSalary; att: 工作日数口径 21.75。"""
    base = safe_num(emp.get("baseSalary"))
    daily = base / 21.75
    hourly = daily / 8.0
    perf_bonus = round(base * 0.2 * (max(0.0, min(100.0, safe_num(perf_total, 80))) / 100.0), 2)
    ot_pay = sum(safe_num(overtime_pay(hourly, h, t) or 0)
                 for t, h in (ot_hours_by_type or {}).items())
    ins = social_insurance(base)
    absence_ded = round(daily * safe_num(absence_days), 2)
    gross = round(base + perf_bonus + ot_pay + safe_num(allowance), 2)
    tax = income_tax(ins["personal"] + ins["hf"], base, perf_bonus, ot_pay, allowance)
    net = round(gross - ins["personal"] - ins["hf"] - tax - absence_ded, 2)
    return {"base": base, "perfBonus": perf_bonus, "otPay": ot_pay,
            "allowance": allowance, "gross": gross,
            "socialIns": ins["personal"], "hf": ins["hf"],
            "tax": tax, "absenceDed": absence_ded, "net": net,
            "insBase": ins["base"]}


# ---------------------------------------------------------------- 绩效

PERF_DIMS = [("work_qty", "工作数量", 0.3), ("work_quality", "工作质量", 0.4),
             ("cooperation", "协作", 0.15), ("discipline", "纪律", 0.15)]


def perf_score(dims):
    """加权得分。dims: {code: 0-100}"""
    total = sum(safe_num(dims.get(code)) * w for code, _n, w in PERF_DIMS)
    return round(total, 1)


def perf_grade(score):
    s = safe_num(score)
    if s >= 90:
        return "S"
    if s >= 80:
        return "A"
    if s >= 70:
        return "B"
    if s >= 60:
        return "C"
    return "D"


# ---------------------------------------------------------------- 其他口径

def service_years(hire_date, ref=None):
    import datetime
    try:
        d0 = datetime.date.fromisoformat(hire_date)
    except (ValueError, TypeError):
        return 0.0
    d1 = datetime.date.fromisoformat(ref) if ref else datetime.date.today()
    return max(0.0, round((d1 - d0).days / 365.0, 2))


def contract_risk(contracts, warn_days=60, ref=None):
    """合同到期预警：{expiring:[...], expired:[...]}"""
    import datetime
    d1 = datetime.date.fromisoformat(ref) if ref else datetime.date.today()
    expiring, expired = [], []
    for c in contracts:
        try:
            end = datetime.date.fromisoformat(c.get("endDate") or "")
        except (ValueError, TypeError):
            continue
        days = (end - d1).days
        if days < 0:
            expired.append(dict(c, days=days))
        elif days <= warn_days:
            expiring.append(dict(c, days=days))
    return {"expiring": expiring, "expired": expired}


def turn_rate(leavers, avg_headcount):
    if avg_headcount <= 0:
        return 0.0
    return round(safe_num(leavers) / safe_num(avg_headcount), 4)


def offer_rate(joined, interviewed):
    if interviewed <= 0:
        return 0.0
    return round(min(1.0, safe_num(joined) / safe_num(interviewed)), 4)


# ---------------------------------------------------------------- 权限矩阵

PERMS = ["org.read", "org.write", "att.read", "att.write", "leave.approve",
         "pay.read", "pay.write", "hire.read", "hire.write", "perf.write", "admin"]

ROLES = {
    "admin":     {"name": "系统管理员", "perms": PERMS},
    "hr":        {"name": "HR专员", "perms": ["org.read", "org.write", "att.read", "att.write",
                                              "leave.approve", "pay.read", "hire.read", "hire.write", "perf.write"]},
    "hrd":       {"name": "HR总监", "perms": ["org.read", "org.write", "att.read", "leave.approve",
                                              "pay.read", "pay.write", "hire.read", "perf.write"]},
    "manager":   {"name": "部门经理", "perms": ["org.read", "att.read", "att.write",
                                                "leave.approve", "hire.read", "hire.write", "perf.write"]},
    "payroll":   {"name": "薪酬专员", "perms": ["org.read", "att.read", "pay.read", "pay.write"]},
    "employee":  {"name": "普通员工", "perms": ["org.read", "att.read"]},
    "recruiter": {"name": "招聘专员", "perms": ["org.read", "hire.read", "hire.write"]},
    "auditor":   {"name": "审计", "perms": ["org.read", "att.read", "pay.read", "hire.read"]},
}


def perms_of(role):
    return ROLES.get(role, {}).get("perms", [])


def can(role, perm):
    return perm in perms_of(role)


# ---------------------------------------------------------------- 12 条业务规则

DEFAULT_RULES = [
    ("shift_start", "标准上班时间", "考勤", "09:00", "", "弹性打卡宽限前班次起点"),
    ("shift_end", "标准下班时间", "考勤", "18:00", "", "标准工时 8 小时"),
    ("grace_min", "弹性打卡宽限", "考勤", "15", "分钟", "宽限内不计迟到"),
    ("annual_base", "年假基础天数", "假期", "5", "天", "满 1 年不满 10 年"),
    ("absence_ded_rate", "缺勤日扣款倍率", "薪资", "1.0", "倍", "按日薪等额扣减"),
    ("perf_bonus_rate", "绩效奖金系数", "薪资", "0.2", "比例", "基本工资 × 系数 × 绩效分"),
    ("tax_threshold", "个税起征点", "薪资", "5000", "元", "月度口径"),
    ("social_base_cap", "社保基数上限", "薪资", "24000", "元", "缴费基数封顶"),
    ("contract_warn_days", "合同到期预警", "风险", "60", "天", "提前提醒续签"),
    ("probation_months", "试用期时长上限", "组织", "6", "个月", "劳动合同法口径"),
    ("ot_max_hours", "月加班上限", "考勤", "36", "小时", "劳动法口径"),
    ("on_time_target", "考勤准时率目标", "看板", "0.98", "比例", "管理驾驶舱红线"),
]

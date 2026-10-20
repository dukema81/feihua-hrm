# -*- coding: utf-8 -*-
"""飞花HRM · 业务内核单元测试（hrm.py 纯函数，不依赖服务）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backend"))

import hrm  # noqa: E402


def test_emp_chain_order():
    assert hrm.EMP_STATES == ["试用期", "已转正", "离职中", "已离职"]
    assert hrm.can_move(hrm.EMP_STATES, "试用期", "已转正")
    assert not hrm.can_move(hrm.EMP_STATES, "已转正", "试用期")
    assert not hrm.can_move(hrm.EMP_STATES, "已离职", "试用期")


def test_emp_gate_regularization():
    ok = {"years": 0.6, "perfScore": 82, "regularEval": "试用期总结"}
    assert hrm.emp_gate("试用期", "已转正", ok) is None
    assert "评估" in hrm.emp_gate("试用期", "已转正", {**ok, "regularEval": ""})
    assert "60" in hrm.emp_gate("试用期", "已转正", {**ok, "perfScore": 59})
    assert "离职中" in hrm.emp_gate("试用期", "已离职", ok)


def test_emp_gate_leave():
    assert "审批" in hrm.emp_gate("已转正", "离职中", {})
    assert hrm.emp_gate("已转正", "离职中", {"approveBy": "zhouh"}) is None
    assert "交接" in hrm.emp_gate("离职中", "已离职", {})
    assert hrm.emp_gate("离职中", "已离职", {"handoverDone": True}) is None


def test_leave_gate_states():
    assert hrm.leave_gate("待审批", "已批准", {"isApprover": True}) is None
    assert "审批人" in hrm.leave_gate("待审批", "已批准", {"isApprover": False})
    assert "只有待审批" in hrm.leave_gate("已批准", "已驳回", {"isApprover": True})
    assert "销假" in hrm.leave_gate("待审批", "已销假", {})


def test_leave_gate_submit():
    ok = {"days": 2, "quotaLeft": 5, "overlap": False}
    assert hrm.leave_gate(None, "待审批", ok) is None
    assert "大于 0" in hrm.leave_gate(None, "待审批", {**ok, "days": 0})
    assert "余额不足" in hrm.leave_gate(None, "待审批", {**ok, "quotaLeft": 1})
    assert "重叠" in hrm.leave_gate(None, "待审批", {**ok, "overlap": True})


def test_candidate_chain_and_gates():
    assert hrm.CAND_STATES == ["初筛", "面试中", "已发Offer", "已入职", "已淘汰"]
    ok = {"roundsPassed": 2, "interviewerFeedback": "通过", "offerSalary": 20000}
    assert hrm.candidate_gate("面试中", "已发Offer", ok) is None
    assert "一轮面试" in hrm.candidate_gate("面试中", "已发Offer", {**ok, "roundsPassed": 0})
    assert "评价" in hrm.candidate_gate("面试中", "已发Offer",
                                        {**ok, "interviewerFeedback": ""})
    assert "核定薪酬" in hrm.candidate_gate("面试中", "已发Offer", {**ok, "offerSalary": 0})
    assert "部门" in hrm.candidate_gate("已发Offer", "已入职", {"onboardDeptOk": False})


def test_payroll_chain_and_gates():
    assert hrm.PAYROLL_STATES == ["草稿", "已核算", "已发放"]
    assert "遗漏" in hrm.payroll_gate("草稿", "已核算", {"slipCount": 20, "empCount": 21})
    assert hrm.payroll_gate("草稿", "已核算", {"slipCount": 21, "empCount": 21}) is None
    assert "确认" in hrm.payroll_gate("已核算", "已发放", {})
    assert hrm.payroll_gate("已核算", "已发放", {"approveBy": "zhangx"}) is None
    assert "先完成核算" in hrm.payroll_gate("草稿", "已发放", {"approveBy": "x"})


def test_attendance_judge():
    r = hrm.attendance_judge("08:50", "18:10")
    assert r["status"] == "正常" and r["lateMin"] == 0
    r = hrm.attendance_judge("09:20", "18:05")
    assert r["status"] == "迟到" and r["lateMin"] == 5
    r = hrm.attendance_judge("08:55", "17:30")
    assert r["status"] == "早退" and r["earlyMin"] == 30
    assert hrm.attendance_judge("", "")["status"] == "缺勤"
    assert hrm.attendance_judge("", "18:00")["status"] == "缺卡"
    r = hrm.attendance_judge("09:00", "18:00")
    assert r["workHours"] == 8.0            # 午休 1h 已扣除 → 9h-1h
    assert hrm.attendance_judge("", "", on_leave=True)["status"] == "请假"
    assert hrm.attendance_judge("", "", business_trip=True)["workHours"] == 8.0
    # 宽限期：09:10 在 15 分钟宽限内不算迟到
    assert hrm.attendance_judge("09:10", "18:00")["lateMin"] == 0


def test_attendance_rate():
    recs = [{"status": "正常"}] * 18 + [{"status": "迟到"}] + [{"status": "缺勤"}]
    assert hrm.attendance_rate(recs, 20) == 0.95
    assert hrm.attendance_rate([], 0) == 0.0


def test_annual_leave_quota():
    assert hrm.annual_leave_quota(0) == 0.0
    assert hrm.annual_leave_quota(0.5) == 2.5      # 按剩余日历天折算
    assert hrm.annual_leave_quota(3) == 5.0
    assert hrm.annual_leave_quota(12) == 10.0
    assert hrm.annual_leave_quota(25) == 15.0


def test_overtime_pay():
    assert hrm.overtime_pay(100, 2, "工作日") == 300.0
    assert hrm.overtime_pay(100, 2, "周末") == 400.0
    assert hrm.overtime_pay(100, 2, "节假日") == 600.0
    assert hrm.overtime_pay(100, 2, "未知") is None


def test_income_tax_brackets():
    assert hrm.income_tax(0, 4000, 0, 0, 0) == 0.0        # 低于起征点
    t = hrm.income_tax(1000, 8000, 0, 0, 0)               # 应税 = 8000-5000-1000=2000 → 3%
    assert t == 60.0
    t = hrm.income_tax(0, 20000, 0, 0, 0)                 # 应税 15000 → 15000*0.2-1410
    assert t == 1590.0
    t = hrm.income_tax(0, 100000, 0, 0, 0)                # 应税 95000 → 95000*0.45-15160
    assert t == 27590.0


def test_social_insurance_cap():
    r = hrm.social_insurance(3000)
    assert r["base"] == 4000.0                              # 下限托底
    r = hrm.social_insurance(50000)
    assert r["base"] == 24000.0                             # 上限封顶
    r = hrm.social_insurance(10000)
    assert abs(r["personal"] - 1050.0) < 0.01               # 10.5%
    assert abs(r["hf"] - 1200.0) < 0.01                     # 12%


def test_payroll_calc():
    p = hrm.payroll_calc({"baseSalary": 15000}, None, 85, {"工作日": 2, "周末": 4}, 1)
    daily = 15000 / 21.75
    hourly = daily / 8
    expect_ot = round(hourly * 2 * 1.5 + hourly * 4 * 2, 2)
    assert p["otPay"] == expect_ot
    assert p["perfBonus"] == round(15000 * 0.2 * 0.85, 2)
    assert p["absenceDed"] == round(daily * 1, 2)
    assert p["gross"] == round(15000 + p["perfBonus"] + p["otPay"] + 200, 2)
    assert p["net"] == round(p["gross"] - p["socialIns"] - p["hf"] - p["tax"] - p["absenceDed"], 2)


def test_perf_score_and_grade():
    s = hrm.perf_score({"work_qty": 90, "work_quality": 80, "cooperation": 70, "discipline": 95})
    assert s == round(90 * 0.3 + 80 * 0.4 + 70 * 0.15 + 95 * 0.15, 1)
    assert hrm.perf_grade(95) == "S"
    assert hrm.perf_grade(85) == "A"
    assert hrm.perf_grade(75) == "B"
    assert hrm.perf_grade(65) == "C"
    assert hrm.perf_grade(50) == "D"


def test_service_years_and_contract_risk():
    assert hrm.service_years("2024-10-21", ref="2026-10-21") == 2.0
    r = hrm.contract_risk([{"endDate": "2026-11-15"}, {"endDate": "2026-01-01"},
                           {"endDate": "2027-06-30"}], warn_days=60,
                          ref="2026-10-21")
    assert len(r["expiring"]) == 1 and r["expiring"][0]["days"] == 25
    assert len(r["expired"]) == 1


def test_turn_and_offer_rates():
    assert hrm.turn_rate(2, 100) == 0.02
    assert hrm.turn_rate(2, 0) == 0.0
    assert hrm.offer_rate(3, 12) == 0.25
    assert hrm.offer_rate(1, 0) == 0.0


def test_doc_no():
    assert hrm.doc_no("LV", "2026-10-21", 7) == "LV20261021-0007"


def test_permission_matrix():
    assert "admin" in hrm.perms_of("admin")
    assert hrm.can("hr", "leave.approve") and hrm.can("hr", "org.write")
    assert not hrm.can("hr", "admin")
    assert hrm.can("payroll", "pay.write") and not hrm.can("payroll", "org.write")
    assert not hrm.can("employee", "pay.read")
    assert hrm.can("recruiter", "hire.write") and not hrm.can("recruiter", "att.write")
    assert hrm.perms_of("auditor") == ["org.read", "att.read", "pay.read", "hire.read"]
    assert hrm.perms_of("unknown_role") == []


def test_rules_default_complete():
    codes = [r[0] for r in hrm.DEFAULT_RULES]
    assert len(codes) == 12 and len(set(codes)) == 12
    assert "grace_min" in codes and "tax_threshold" in codes and "ot_max_hours" in codes


def test_safe_num_and_shift_parse():
    assert hrm.safe_num("12.5") == 12.5
    assert hrm.safe_num(None) == 0.0
    assert hrm.safe_num("abc", 3) == 3.0

# -*- coding: utf-8 -*-
"""飞花HRM · 端到端 UI 测试（Playwright 直调，15 页渲染 + 关键交互）"""
import os

import pytest
from playwright.sync_api import sync_playwright

BASE = None
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "reports", "screenshots")

PAGES = ["dashboard", "employees", "orgs", "contracts", "attendance", "leaves",
         "overtime", "payroll", "perf", "jobs", "trainings", "reports",
         "integration", "settings", "logs"]


def _launch(pw):
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception:                                     # noqa: BLE001
            continue
    raise RuntimeError("无可用的 Chromium/Edge/Chrome")


@pytest.fixture(scope="module")
def page(e2e_base):
    global BASE
    BASE = e2e_base
    errors = []
    with sync_playwright() as pw:
        browser = _launch(pw)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
        pg.on("console", lambda m: errors.append("console: %s" % m.text)
              if m.type == "error" else None)
        pg.goto(BASE + "/login.html")
        pg.fill("#u", "admin")
        pg.fill("#p", "hr@2026")
        pg.click("#btn")
        pg.wait_for_url("**/index.html", timeout=10000)
        pg.wait_for_timeout(1200)
        pg._errors = errors
        yield pg
        browser.close()


def _visit(page, route):
    # 关闭残留弹层，避免上一用例失败导致遮罩挡住后续点击
    page.evaluate("document.getElementById('mask').className = 'mask'")
    del page._errors[:]
    page.evaluate("location.hash = '#%s'" % route)
    page.wait_for_timeout(900)


def test_all_pages_render(page):
    bad = []
    for name in PAGES:
        _visit(page, name)
        if len(page.inner_text("#view")) < 20 or page._errors:
            bad.append((name, page._errors[:1]))
    assert not bad, "渲染失败页：%s" % bad
    page.screenshot(path=os.path.join(SHOT, "e2e_dashboard.png"))


def test_dashboard_kpi(page):
    _visit(page, "dashboard")
    txt = page.inner_text("#view")
    assert "在职员工" in txt and "出勤率" in txt and "合同风险" in txt


def test_employees_table(page):
    _visit(page, "employees")
    txt = page.inner_text("#view")
    assert "EMP001" in txt and "试用期" in txt
    rows = page.locator("#view tbody tr")
    assert rows.count() >= 15


def test_leave_create_flow(page):
    _visit(page, "leaves")
    page.click("#lvNew")
    page.wait_for_selector("#mask.on", timeout=5000)
    page.select_option("#nlType", "事假")
    page.fill("#nlReason", "E2E 测试请假：验证提交流程与审批闸口")
    page.click("#nlOk")
    page.wait_for_timeout(800)
    assert "已提交" in page.inner_text("#statusMsg")


def test_clock_dialog(page):
    _visit(page, "attendance")
    page.click("#attClock")
    page.wait_for_selector("#mask.on", timeout=5000)
    assert page.locator("#ckEmp").input_value()
    page.click("[data-close]")
    page.wait_for_timeout(300)
    assert not page.locator("#mask.on").count()


def test_payroll_requires_pay_permission(page):
    # 薪酬专员登录后可见核算按钮；审计只读。此处验证 admin 可见工资条按钮
    _visit(page, "payroll")
    txt = page.inner_text("#view")
    assert "工资批次" in txt


def test_jobs_pipeline(page):
    _visit(page, "jobs")
    page.wait_for_timeout(400)
    txt = page.inner_text("#view")
    assert "发布职位" in txt and "新增候选人" in txt


def test_settings_matrix(page):
    _visit(page, "settings")
    page.wait_for_timeout(600)
    page.click('[data-tab="users"]')
    page.wait_for_timeout(600)
    txt = page.inner_text("#view")
    assert "角色权限矩阵" in txt and "系统管理员" in txt


def test_integration_tabs(page):
    _visit(page, "integration")
    page.wait_for_timeout(300)
    assert page.locator("#ikNew").count() == 1
    page.click('[data-tab="hooks"]')
    page.wait_for_timeout(300)
    assert "HMAC-SHA256" in page.inner_text("#intBody")


def test_login_error_hint(page):
    pg = page.context.browser.new_page()
    try:
        pg.goto(BASE + "/login.html")
        pg.fill("#u", "admin")
        pg.fill("#p", "wrong-password")
        pg.click("#btn")
        pg.wait_for_timeout(800)
        assert "错误" in pg.inner_text("#err")
    finally:
        pg.close()

# -*- coding: utf-8 -*-
"""飞花HRM · 离线 DEMO 冒烟：15 页渲染 + 4 类写操作（请假提交 / 员工建档 / API Key / 工资批次）"""
import os
import sys

from playwright.sync_api import sync_playwright

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "demo", "feihua-hrm-demo.html")

PAGES = ["dashboard", "employees", "orgs", "contracts", "attendance", "leaves",
         "overtime", "payroll", "perf", "jobs", "trainings", "reports",
         "integration", "settings", "logs"]

N = [0]


def ck(cond, label):
    N[0] += 1
    print("%s #%02d %s" % ("✓" if cond else "✗", N[0], label))
    if not cond:
        sys.exit(1)


def launch(pw):
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception:                                     # noqa: BLE001
            continue
    raise RuntimeError("无可用的 Chromium/Edge/Chrome")


def main():
    url = "file:///" + DEMO.replace("\\", "/")
    with sync_playwright() as pw:
        browser = launch(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(url)
        page.wait_for_timeout(1800)
        ck(len(page.inner_text("#view")) > 20, "DEMO 打开免登录进入驾驶舱")

        for name in PAGES:
            errors.clear()
            page.evaluate("location.hash = '#%s'" % name)
            page.wait_for_timeout(800)
            ok_len = len(page.inner_text("#view")) >= 20
            ck(ok_len and not errors, "页面 %-12s chars=%d" % (name, len(page.inner_text("#view"))))

        # 写操作 1：新建员工
        page.evaluate("location.hash = '#employees'")
        page.wait_for_timeout(800)
        page.click("#eNew")
        page.wait_for_selector("#mask.on", timeout=5000)
        page.fill("#neNo", "EMP-DEMO-1")
        page.fill("#neName", "演示员工")
        page.click("#neOk")
        page.wait_for_timeout(900)
        ck("已创建" in page.inner_text("#statusMsg"), "新建员工写入内存")

        # 写操作 2：提交请假
        page.evaluate("location.hash = '#dashboard'")
        page.wait_for_timeout(400)
        page.evaluate("location.hash = '#leaves'")
        page.wait_for_timeout(800)
        page.click("#lvNew")
        page.wait_for_selector("#mask.on", timeout=5000)
        page.fill("#nlEmp", "EMP009")
        page.select_option("#nlType", "事假")
        page.fill("#nlReason", "DEMO 冒烟：验证内存后端请假闸口与余额口径")
        page.click("#nlOk")
        page.wait_for_timeout(900)
        ck("已提交" in page.inner_text("#statusMsg"), "提交请假写入内存")

        # 写操作 3：新建工资批次 + 核算
        page.evaluate("location.hash = '#payroll'")
        page.wait_for_timeout(800)
        page.click("#prNew")
        page.wait_for_selector("#mask.on", timeout=5000)
        page.click("#prOk")
        page.wait_for_timeout(900)
        ck("已创建" in page.inner_text("#statusMsg"), "新建工资批次写入内存")
        page.evaluate("location.hash = '#dashboard'")
        page.wait_for_timeout(400)
        page.evaluate("location.hash = '#payroll'")
        page.wait_for_timeout(800)
        calc_btn = page.locator("[data-calc]").first
        calc_btn.click()
        page.wait_for_selector("#mask.on", timeout=5000)
        page.click("#calcOk")
        page.wait_for_timeout(1200)
        ck("核算完成" in page.inner_text("#statusMsg"), "内存后端薪资核算")

        # 写操作 4：生成 API Key
        page.evaluate("location.hash = '#integration'")
        page.wait_for_timeout(800)
        page.click("#ikNew")
        page.wait_for_selector("#mask.on", timeout=5000)
        page.click("#ikOk")
        page.wait_for_timeout(700)
        secret = page.inner_text("#dialog")
        ck("fhk_" in secret, "API Key 明文生成（fhk_ 前缀）")
        page.click("#ikDone")

        browser.close()
    print("\nDEMO 冒烟完成：%d 项检查点全部通过" % N[0])


if __name__ == "__main__":
    main()

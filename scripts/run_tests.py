# -*- coding: utf-8 -*-
"""飞花HRM · 三层测试门禁：单元 → 接口 → 端到端"""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, title):
    print("=" * 58)
    print("▶ " + title)
    print("=" * 58)
    r = subprocess.run([sys.executable, "-m", "pytest"] + args,
                       cwd=ROOT)
    return r.returncode == 0


def main():
    fast = "--fast" in sys.argv
    ok = True
    ok &= run(["tests/test_unit_core.py", "-q"], "第一层 · 单元测试 · 业务内核（hrm.py 纯函数）")
    ok &= run(["tests/test_api.py", "-q"], "第二层 · 接口测试 · REST 全链路")
    if not fast:
        ok &= run(["tests/test_e2e_ui.py", "-q"], "第三层 · 端到端 · 浏览器 15 页")
    print("=" * 58)
    print("✓ 门禁通过" if ok else "✗ 门禁未通过")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

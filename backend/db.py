# -*- coding: utf-8 -*-
"""飞花HRM系统 · 数据层（26 表，sqlite3 WAL，零依赖）"""
import os
import sqlite3
import threading

_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FEIHUA_DB") or os.path.join(_DIR, "data", "feihua.db")

_local = threading.local()


def connect():
    cn = getattr(_local, "cn", None)
    if cn is not None:
        return cn
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cn = sqlite3.connect(DB_PATH, timeout=20)
    cn.row_factory = sqlite3.Row
    cn.execute("PRAGMA journal_mode=WAL")
    cn.execute("PRAGMA busy_timeout=20000")
    cn.execute("PRAGMA foreign_keys=ON")
    _local.cn = cn
    return cn


def close_thread_conns():
    cn = getattr(_local, "cn", None)
    if cn is not None:
        try:
            cn.close()
        except Exception:  # noqa: BLE001
            pass
        _local.cn = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, salt TEXT NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL, emp_no TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS departments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, parent_id INTEGER DEFAULT 0, leader TEXT DEFAULT '',
  headcount_plan INTEGER DEFAULT 0, remark TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS employees(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, gender TEXT DEFAULT '男', phone TEXT DEFAULT '',
  email TEXT DEFAULT '', dept_code TEXT NOT NULL, position TEXT DEFAULT '',
  level TEXT DEFAULT '', hire_date TEXT NOT NULL, regular_date TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '试用期', base_salary REAL DEFAULT 0,
  manager TEXT DEFAULT '', id_card TEXT DEFAULT '', remark TEXT DEFAULT '',
  created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attendance(
  id INTEGER PRIMARY KEY AUTOINCREMENT, emp_no TEXT NOT NULL,
  date TEXT NOT NULL, clock_in TEXT DEFAULT '', clock_out TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '正常', work_hours REAL DEFAULT 0,
  late_min INTEGER DEFAULT 0, remark TEXT DEFAULT '',
  UNIQUE(emp_no, date));
CREATE TABLE IF NOT EXISTS leave_balances(
  id INTEGER PRIMARY KEY AUTOINCREMENT, emp_no TEXT NOT NULL, year INTEGER NOT NULL,
  ltype TEXT NOT NULL, quota REAL DEFAULT 0, used REAL DEFAULT 0,
  UNIQUE(emp_no, year, ltype));
CREATE TABLE IF NOT EXISTS leaves(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  emp_no TEXT NOT NULL, ltype TEXT NOT NULL, start_date TEXT NOT NULL,
  end_date TEXT NOT NULL, days REAL NOT NULL, reason TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '待审批', approver TEXT DEFAULT '',
  decided_at TEXT DEFAULT '', cancel_note TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS overtimes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  emp_no TEXT NOT NULL, date TEXT NOT NULL, hours REAL NOT NULL,
  otype TEXT NOT NULL DEFAULT '工作日', reason TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '待审批', approver TEXT DEFAULT '',
  decided_at TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payroll_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT '草稿', total_gross REAL DEFAULT 0,
  total_net REAL DEFAULT 0, headcount INTEGER DEFAULT 0, remark TEXT DEFAULT '',
  created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payslips(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
  emp_no TEXT NOT NULL, base REAL DEFAULT 0, perf_bonus REAL DEFAULT 0,
  ot_pay REAL DEFAULT 0, allowance REAL DEFAULT 0, gross REAL DEFAULT 0,
  social_ins REAL DEFAULT 0, hf REAL DEFAULT 0, tax REAL DEFAULT 0,
  absence_ded REAL DEFAULT 0, other_ded REAL DEFAULT 0, net REAL DEFAULT 0,
  remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL, dept_code TEXT NOT NULL, headcount INTEGER DEFAULT 1,
  salary_range TEXT DEFAULT '', education TEXT DEFAULT '本科',
  status TEXT NOT NULL DEFAULT '招聘中', hiring_manager TEXT DEFAULT '',
  remark TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, job_no TEXT NOT NULL, phone TEXT DEFAULT '',
  email TEXT DEFAULT '', source TEXT DEFAULT '内推', stage TEXT NOT NULL DEFAULT '初筛',
  rating INTEGER DEFAULT 0, expected_salary REAL DEFAULT 0, offer_salary REAL DEFAULT 0,
  remark TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS interviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_no TEXT NOT NULL,
  rounds INTEGER NOT NULL, interviewer TEXT NOT NULL, scheduled_at TEXT NOT NULL,
  form TEXT DEFAULT '现场', result TEXT DEFAULT '', score INTEGER DEFAULT 0,
  feedback TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS perf_cycles(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
  period TEXT NOT NULL, status TEXT NOT NULL DEFAULT '进行中',
  start_date TEXT DEFAULT '', end_date TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS perf_scores(
  id INTEGER PRIMARY KEY AUTOINCREMENT, cycle TEXT NOT NULL, emp_no TEXT NOT NULL,
  work_qty REAL DEFAULT 0, work_quality REAL DEFAULT 0, cooperation REAL DEFAULT 0,
  discipline REAL DEFAULT 0, total REAL DEFAULT 0, grade TEXT DEFAULT '',
  comment TEXT DEFAULT '', created TEXT NOT NULL,
  UNIQUE(cycle, emp_no));
CREATE TABLE IF NOT EXISTS trainings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL, category TEXT DEFAULT '技能', trainer TEXT DEFAULT '',
  date TEXT NOT NULL, hours REAL DEFAULT 2, quota INTEGER DEFAULT 30,
  status TEXT NOT NULL DEFAULT '报名中', remark TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_records(
  id INTEGER PRIMARY KEY AUTOINCREMENT, training_no TEXT NOT NULL,
  emp_no TEXT NOT NULL, status TEXT NOT NULL DEFAULT '已报名',
  score INTEGER DEFAULT 0, UNIQUE(training_no, emp_no));
CREATE TABLE IF NOT EXISTS contracts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, emp_no TEXT NOT NULL,
  ctype TEXT NOT NULL DEFAULT '固定期限', start_date TEXT NOT NULL,
  end_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT '履行中',
  signed_at TEXT DEFAULT '', remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS rules(
  code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
  value TEXT NOT NULL, unit TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
  remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, user TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS api_keys(
  id INTEGER PRIMARY KEY AUTOINCREMENT, key_hash TEXT UNIQUE NOT NULL,
  prefix TEXT NOT NULL, name TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'read',
  created TEXT NOT NULL, last_used TEXT DEFAULT '', revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS webhooks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL,
  secret TEXT NOT NULL, events TEXT NOT NULL, enabled INTEGER DEFAULT 1, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS webhook_deliveries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, webhook_id INTEGER NOT NULL,
  event TEXT NOT NULL, payload TEXT NOT NULL, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, last_at TEXT DEFAULT '', response TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS idem_keys(
  key TEXT PRIMARY KEY, status TEXT DEFAULT 'processing', response TEXT DEFAULT '',
  created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_state(
  entity TEXT PRIMARY KEY, last_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tokens(
  token TEXT PRIMARY KEY, username TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_att_emp ON attendance(emp_no, date);
CREATE INDEX IF NOT EXISTS idx_leaves_emp ON leaves(emp_no, status);
CREATE INDEX IF NOT EXISTS idx_payslips_run ON payslips(run_id);
CREATE INDEX IF NOT EXISTS idx_candidates_job ON candidates(job_no);
"""


def init():
    cn = connect()
    cn.executescript(SCHEMA)
    cn.commit()
    return cn


if __name__ == "__main__":
    init()
    print("feihua.db 初始化完成：", DB_PATH)

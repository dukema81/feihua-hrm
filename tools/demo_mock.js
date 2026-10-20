/* 飞花HRM · 离线 DEMO 内存后端：拦截 fetch，按快照同口径读写（sessionStorage 持久化） */
(function () {
  "use strict";
  var SNAP = window.__HRM_SNAPSHOT__ || {};
  var KEY = "fh_hrm_demo";
  var DB = null;

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function esc(s) { return String(s === null || s === undefined ? "" : s); }
  function lst(x) { return (x && x.list) ? x.list : (x || []); }
  function num(v, d) { var n = Number(v || 0); return isNaN(n) ? (d || 0) : n; }

  var PERMS = ["org.read", "org.write", "att.read", "att.write", "leave.approve",
    "pay.read", "pay.write", "hire.read", "hire.write", "perf.write", "admin"];

  function load() {
    try {
      var raw = sessionStorage.getItem(KEY);
      if (raw) { DB = JSON.parse(raw); return; }
    } catch (e) { /* ignore */ }
    DB = {
      user: { username: "admin", name: "系统管理员", role: "admin",
        roleName: "系统管理员", perms: PERMS.slice(), empNo: "" },
      board: SNAP.board || {},
      departments: lst(SNAP.departments), employees: lst(SNAP.employees),
      attReport: SNAP.attReport || { month: "", list: [] },
      attendance: lst(SNAP.attendance), leaves: lst(SNAP.leaves),
      overtimes: lst(SNAP.overtimes), payroll: lst(SNAP.payroll),
      payslips: SNAP.payslips || {}, jobs: lst(SNAP.jobs),
      candidates: lst(SNAP.candidates), interviews: lst(SNAP.interviews),
      perfCycles: lst(SNAP.perfCycles), perfScores: SNAP.perfScores || { cycle: "", list: [], grades: {} },
      trainings: lst(SNAP.trainings), trecords: {},
      contracts: SNAP.contracts || { list: [], risk: { warnDays: 60, expiring: [], expired: [] } },
      headcount: SNAP.headcount || {}, rules: lst(SNAP.rules),
      users: lst(SNAP.users), logs: lst(SNAP.logs),
      keys: lst(SNAP.keys), hooks: { list: lst(SNAP.webhooks), deliveries: lst(SNAP.deliveries),
        events: SNAP.events || [] },
      balances: {}, quotaIndex: {},
      seq: 900
    };
    DB.employees.forEach(function (e) {
      (e.quota || []).forEach(function (q) {
        var k = e.no + "|" + q.ltype;
        DB.balances[k] = { quota: num(q.quota), used: num(q.used) };
      });
    });
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(DB)); } catch (e) { /* 超限忽略 */ }
  }
  function log(action, detail) {
    DB.logs.unshift({ at: new Date().toLocaleString("zh-CN", { hour12: false }),
      user: DB.user.username, action: action, detail: detail || "" });
  }
  function no(prefix) {
    DB.seq += 1;
    return prefix + "2610-" + String(DB.seq).slice(-4);
  }
  function err(status, msg) {
    return new Response(JSON.stringify({ code: status, message: msg }),
      { status: status, headers: { "Content-Type": "application/json" } });
  }
  function ok(data) {
    return new Response(JSON.stringify(data === undefined ? { ok: true } : data),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  /* -------------------------------------------- 业务口径（与后端同口径） */
  function annualQuota(years) {
    if (years < 1) return years <= 0 ? 0 : Math.round(5 * (365 - Math.floor(years * 365)) / 365 * 10) / 10;
    if (years < 10) return 5;
    if (years < 20) return 10;
    return 15;
  }
  function serviceYears(hire) {
    if (!hire) return 0;
    var d0 = new Date(hire), d1 = new Date();
    return Math.max(0, (d1 - d0) / 864e5 / 365);
  }
  function perfScore(d) {
    return Math.round((num(d.workQty) * 0.3 + num(d.workQuality) * 0.4 +
      num(d.cooperation) * 0.15 + num(d.discipline) * 0.15) * 10) / 10;
  }
  function perfGrade(s) {
    return s >= 90 ? "S" : (s >= 80 ? "A" : (s >= 70 ? "B" : (s >= 60 ? "C" : "D")));
  }
  function incomeTax(taxable) {
    var B = [[3000, .03, 0], [12000, .10, 210], [25000, .20, 1410], [35000, .25, 2660],
      [55000, .30, 4410], [80000, .35, 7160], [1e12, .45, 15160]];
    taxable -= 5000;
    if (taxable <= 0) return 0;
    for (var i = 0; i < B.length; i++) {
      if (taxable <= B[i][0]) return Math.round((taxable * B[i][1] - B[i][2]) * 100) / 100;
    }
    return 0;
  }
  function payrollCalc(e, perfTotal, otWorkday, otWeekend, absenceDays) {
    var base = num(e.baseSalary);
    var hourly = base / 21.75 / 8;
    var perfBonus = Math.round(base * 0.2 * (Math.min(100, Math.max(0, num(perfTotal, 80))) / 100) * 100) / 100;
    var otPay = Math.round((hourly * otWorkday * 1.5 + hourly * otWeekend * 2) * 100) / 100;
    var ib = Math.min(Math.max(base, 4000), 24000);
    var si = Math.round(ib * 0.105 * 100) / 100;
    var hf = Math.round(ib * 0.12 * 100) / 100;
    var allowance = 200;
    var gross = Math.round((base + perfBonus + otPay + allowance) * 100) / 100;
    var tax = incomeTax(gross - si - hf);
    var absenceDed = Math.round(base / 21.75 * absenceDays * 100) / 100;
    return { base: base, perfBonus: perfBonus, otPay: otPay, allowance: allowance,
      gross: gross, socialIns: si, hf: hf, tax: tax, absenceDed: absenceDed,
      net: Math.round((gross - si - hf - tax - absenceDed) * 100) / 100 };
  }

  function findEmp(no2) {
    var e = DB.employees.filter(function (x) { return x.no === no2; })[0];
    if (!e) throw "员工不存在";
    return e;
  }

  /* -------------------------------------------- 路由 */
  var ROUTES = [
    ["POST", /^api\/auth\/login$/, function () {
      return { token: "demo-token", username: DB.user.username, name: DB.user.name,
        role: "admin", roleName: "系统管理员", perms: PERMS, empNo: "", empName: DB.user.name };
    }],
    ["POST", /^api\/auth\/logout$/, function () { return { ok: true }; }],
    ["GET", /^api\/auth\/me$/, function () { return DB.user; }],
    ["GET", /^api\/board$/, function () { return DB.board; }],

    ["GET", /^api\/departments$/, function () { return { list: DB.departments }; }],
    ["POST", /^api\/departments$/, function (m) {
      if (!m.code || !m.name) throw "部门编码与名称必填";
      if (DB.departments.some(function (d) { return d.code === m.code; })) throw "部门编码已存在";
      DB.departments.push({ code: m.code, name: m.name, parentId: 0, leader: m.leader || "",
        plan: num(m.plan), actual: 0 });
      log("新建部门", m.code);
      return { code: m.code };
    }],

    ["GET", /^api\/employees$/, function (m) {
      var list = DB.employees.filter(function (e) {
        return !m.status || e.status === m.status;
      });
      return { list: list, total: list.length };
    }],
    ["POST", /^api\/employees$/, function (m) {
      if (!m.no || !m.name || !m.dept || !m.hireDate) throw "缺少必填字段";
      if (DB.employees.some(function (e) { return e.no === m.no; })) throw "工号已存在：" + m.no;
      var yrs = serviceYears(m.hireDate);
      var st = new Date(m.hireDate) <= new Date("2026-01-01") ? "已转正" : "试用期";
      var quota = annualQuota(yrs);
      var e = { no: m.no, name: m.name, gender: m.gender || "男", phone: m.phone || "",
        email: m.email || "", dept: m.dept, position: m.position || "", level: m.level || "",
        hireDate: m.hireDate, regularDate: "", status: st, baseSalary: num(m.baseSalary),
        manager: m.manager || "", remark: "" };
      DB.employees.push(e);
      DB.balances[m.no + "|年假"] = { quota: quota, used: 0 };
      log("新建员工", m.no + " " + m.name);
      return { no: m.no, status: st, annualQuota: quota };
    }],
    ["GET", /^api\/employees\/([\w\-]+)$/, function (m, match) {
      var e = findEmp(match[1]);
      var v = clone(e);
      v.years = Math.round(serviceYears(e.hireDate) * 100) / 100;
      v.quota = ["年假", "调休"].map(function (t) {
        var b = DB.balances[e.no + "|" + t] || { quota: 0, used: 0 };
        return { ltype: t, quota: b.quota, used: b.used, left: b.quota - b.used };
      });
      v.leaves = DB.leaves.filter(function (l) { return l.emp === e.no; }).slice(0, 10)
        .map(function (l) { return { no: l.no, ltype: l.type, start_date: l.start,
          end_date: l.end, days: l.days, status: l.status }; });
      v.perf = (DB.perfScores.list || []).filter(function (p) { return p.emp === e.no; })
        .map(function (p) { return { cycle: DB.perfScores.cycle, total: p.total, grade: p.grade }; });
      v.contracts = (DB.contracts.list || []).filter(function (c) { return c.emp === e.no; })
        .map(function (c) { return { ctype: c.type, start_date: c.start, end_date: c.end, status: c.status }; });
      return v;
    }],
    ["POST", /^api\/employees\/([\w\-]+)\/stage$/, function (m, match) {
      var e = findEmp(match[1]);
      var t = m.target;
      var chain = ["试用期", "已转正", "离职中", "已离职"];
      if (chain.indexOf(t) <= chain.indexOf(e.status)) {
        throw "状态不允许从「" + e.status + "」变更为「" + t + "」";
      }
      if (t === "已转正") {
        if (!m.regularEval) throw "转正闸口：缺少转正评估（带教人评价/试用期总结）";
        var ps = (DB.perfScores.list || []).filter(function (p) { return p.emp === e.no; })[0];
        if (!ps || num(ps.total) < 60) throw "转正闸口：试用期绩效得分低于 60 分，不能转正";
        e.regularDate = new Date().toISOString().slice(0, 10);
      }
      if (t === "已离职" && e.status !== "离职中") {
        throw "离职闸口：必须先经人事审批进入「离职中」";
      }
      if (t === "已离职" && !m.handoverDone) {
        throw "离职闸口：工作交接未完成，不能办理离职";
      }
      e.status = t;
      log("员工状态变更", e.no + " → " + t);
      return { ok: true, status: t };
    }],

    ["GET", /^api\/attendance$/, function (m) {
      var list = DB.attendance.filter(function (a) {
        return !m.month || (a.date || "").indexOf(m.month) === 0;
      });
      return { list: list, total: list.length };
    }],
    ["GET", /^api\/attendance\/report$/, function () { return DB.attReport; }],
    ["POST", /^api\/attendance\/clock$/, function (m) {
      var e = findEmp(m.emp || "EMP009");
      var day = m.date || new Date().toISOString().slice(0, 10);
      var row = null;
      DB.attendance.forEach(function (a) { if (a.emp === e.no && a.date === day) row = a; });
      if (!row) {
        row = { emp: e.no, date: day, "in": "", out: "", status: "正常", workHours: 0, lateMin: 0 };
        DB.attendance.unshift(row);
        DB.attReport.list.push({ emp: e.no, name: e.name, dept: e.dept, workdays: 1,
          attended: 1, rate: 1, lateMin: 0, hours: 0, abnormal: 0 });
      }
      if (!row["in"]) {
        var late = Math.max(0, (Number((m.time || "09:00").split(":")[0]) * 60 +
          Number((m.time || "09:00").split(":")[1])) - (9 * 60 + 15));
        row["in"] = m.time || "09:00";
        row.status = late > 0 ? "迟到" : "正常";
        row.lateMin = late;
        log("上班打卡", e.no + " " + day);
        return { action: "clockIn", status: row.status, lateMin: late };
      }
      if (!row.out) {
        row.out = m.time || "18:00";
        var mins = (Number(row.out.split(":")[0]) * 60 + Number(row.out.split(":")[1])) -
          (Number(row["in"].split(":")[0]) * 60 + Number(row["in"].split(":")[1])) - 60;
        row.workHours = Math.max(0, Math.round(mins / 60 * 100) / 100);
        log("下班打卡", e.no + " " + day);
        return { action: "clockOut", status: row.status, workHours: row.workHours };
      }
      throw "今日已完成上下班打卡";
    }],
    ["POST", /^api\/attendance$/, function (m) {
      var e = findEmp(m.emp);
      var mins = m["in"] && m.out
        ? (Number(m.out.split(":")[0]) * 60 + Number(m.out.split(":")[1])) -
          (Number(m["in"].split(":")[0]) * 60 + Number(m["in"].split(":")[1])) - 60 : 0;
      var st = m.status || (num(m.lateMinEstimate) > 0 ? "迟到" : (m["in"] ? "正常" : "缺勤"));
      var late = m["in"] ? Math.max(0, (Number(m["in"].split(":")[0]) * 60 +
        Number(m["in"].split(":")[1])) - (9 * 60 + 15)) : 0;
      var row = { emp: e.no, date: m.date, "in": m["in"] || "", out: m.out || "",
        status: st, workHours: Math.max(0, Math.round(mins / 60 * 100) / 100), lateMin: late };
      var found = false;
      DB.attendance.forEach(function (a, i) {
        if (a.emp === e.no && a.date === m.date) { DB.attendance[i] = row; found = true; }
      });
      if (!found) DB.attendance.unshift(row);
      log("考勤调整", e.no + " " + m.date + " → " + st);
      return { ok: true, status: st, workHours: row.workHours };
    }],

    ["GET", /^api\/leaves$/, function (m) {
      var list = DB.leaves.filter(function (l) { return !m.status || l.status === m.status; });
      return { list: list };
    }],
    ["POST", /^api\/leaves$/, function (m) {
      var days = num(m.days);
      if (!m.emp || !m.type || !m.start || !m.end) throw "缺少必填字段";
      if (days <= 0) {
        var s = new Date(m.start), e2 = new Date(m.end);
        days = Math.round((e2 - s) / 864e5) + 1;
      }
      if (days <= 0) throw "请假天数必须大于 0";
      var left = 9e9;
      if (m.type !== "事假") {
        var b = DB.balances[m.emp + "|" + m.type];
        if (b) left = b.quota - b.used;
        if (days > left) throw "请假闸口：假期余额不足（剩余 " + left + " 天）";
      }
      var ov = DB.leaves.some(function (l) {
        return l.emp === m.emp && (l.status === "待审批" || l.status === "已批准") &&
          l.start <= m.end && l.end >= m.start;
      });
      if (ov) throw "请假闸口：与已有请假单时间重叠";
      var n = no("LV");
      DB.leaves.unshift({ no: n, emp: m.emp, type: m.type, start: m.start, end: m.end,
        days: days, reason: m.reason || "", status: "待审批", approver: "" });
      log("提交请假", n + " " + days + "天");
      return { no: n, days: days };
    }],
    ["POST", /^api\/leaves\/([\w\-]+)\/stage$/, function (m, match) {
      var l = DB.leaves.filter(function (x) { return x.no === match[1]; })[0];
      if (!l) throw "请假单不存在";
      var t = m.target;
      if (t === "已批准") {
        if (l.status !== "待审批") throw "只有待审批单可以批准";
        var b = DB.balances[l.emp + "|" + l.type];
        if (b && b.quota - b.used < l.days) throw "假期余额不足（剩余 " + (b.quota - b.used) + " 天）";
        if (b) b.used = Math.round((b.used + l.days) * 10) / 10;
        l.approver = DB.user.username;
      } else if (t === "已驳回") {
        if (l.status !== "待审批") throw "只有待审批单可以驳回";
        l.approver = DB.user.username;
      } else if (t === "已销假") {
        if (l.status !== "已批准") throw "只有已批准的假单可以销假";
        var b2 = DB.balances[l.emp + "|" + l.type];
        if (b2) b2.used = Math.max(0, b2.used - l.days);
      } else {
        throw "未知目标状态";
      }
      l.status = t;
      log("请假状态变更", l.no + " → " + t);
      return { ok: true, status: t };
    }],

    ["GET", /^api\/overtimes$/, function () { return { list: DB.overtimes }; }],
    ["POST", /^api\/overtimes$/, function (m) {
      if (!m.emp || num(m.hours) <= 0) throw "emp 与 hours（>0）必填";
      if (["工作日", "周末", "节假日"].indexOf(m.type) < 0) throw "加班类型不合法";
      if (num(m.hours) > 36) throw "月加班上限 36 小时，已批 0.0 小时";
      var n = no("OT");
      DB.overtimes.unshift({ no: n, emp: m.emp, date: m.date || new Date().toISOString().slice(0, 10),
        hours: num(m.hours), type: m.type, status: "待审批", approver: "" });
      log("提交加班", n);
      return { no: n };
    }],
    ["POST", /^api\/overtimes\/([\w\-]+)\/stage$/, function (m, match) {
      var o = DB.overtimes.filter(function (x) { return x.no === match[1]; })[0];
      if (!o) throw "加班单不存在";
      if (["已批准", "已驳回"].indexOf(m.target) < 0) throw "目标状态不合法";
      o.status = m.target;
      o.approver = DB.user.username;
      log("加班审批", o.no + " → " + m.target);
      return { ok: true, status: m.target };
    }],

    ["GET", /^api\/payroll$/, function () { return { list: DB.payroll }; }],
    ["POST", /^api\/payroll$/, function (m) {
      var month = m.month || new Date().toISOString().slice(0, 7);
      if (!/^\d{4}-\d{2}$/.test(month)) throw "月份格式应为 YYYY-MM";
      if (DB.payroll.some(function (p) { return p.month === month; })) throw "工资批次已存在";
      DB.payroll.unshift({ month: month, status: "草稿", gross: 0, net: 0, headcount: 0 });
      log("新建工资批次", month);
      return { month: month, status: "草稿" };
    }],
    ["POST", /^api\/payroll\/([\w\-]+)\/calc$/, function (m, match) {
      var run = DB.payroll.filter(function (p) { return p.month === match[1]; })[0];
      if (!run) throw "工资批次不存在";
      if (run.status !== "草稿") throw "批次状态为「" + run.status + "」，不能再核算";
      var actives = DB.employees.filter(function (e) {
        return e.status === "试用期" || e.status === "已转正";
      });
      var slips = [];
      var tg = 0, tn = 0;
      actives.forEach(function (e) {
        var ps = (DB.perfScores.list || []).filter(function (p) { return p.emp === e.no; })[0];
        var c = payrollCalc(e, ps ? ps.total : 80, 2, 0, 0);
        c.emp = e.no; c.name = e.name;
        slips.push(c);
        tg += c.gross; tn += c.net;
      });
      DB.payslips[match[1]] = { month: match[1], status: "已核算", list: slips };
      run.status = "已核算";
      run.gross = Math.round(tg * 100) / 100;
      run.net = Math.round(tn * 100) / 100;
      run.headcount = slips.length;
      log("薪资核算", match[1] + " " + slips.length + " 条");
      return { month: match[1], slips: slips.length, gross: run.gross, net: run.net };
    }],
    ["POST", /^api\/payroll\/([\w\-]+)\/stage$/, function (m, match) {
      var run = DB.payroll.filter(function (p) { return p.month === match[1]; })[0];
      if (!run) throw "工资批次不存在";
      if (m.target === "已核算") {
        var n2 = (DB.payslips[match[1]] || { list: [] }).list.length;
        if (n2 <= 0) throw "核算闸口：未生成任何工资条";
      } else if (m.target === "已发放") {
        if (run.status !== "已核算") throw "发放闸口：必须先完成核算才能发放";
      } else {
        throw "未知目标状态";
      }
      run.status = m.target;
      log("薪资状态变更", match[1] + " → " + m.target);
      return { ok: true, status: m.target };
    }],
    ["GET", /^api\/payroll\/([\w\-]+)\/payslips$/, function (m, match) {
      var d = DB.payslips[match[1]] ||
        { month: match[1], status: "草稿", list: [] };
      return clone(d);
    }],

    ["GET", /^api\/jobs$/, function () { return { list: DB.jobs }; }],
    ["POST", /^api\/jobs$/, function (m) {
      if (!m.title || !m.dept) throw "职位名称与部门必填";
      var n = no("JB");
      DB.jobs.unshift({ no: n, title: m.title, dept: m.dept, headcount: num(m.headcount, 1),
        salary: m.salary || "", education: "本科", status: "招聘中", manager: "", candidates: 0 });
      log("发布职位", n);
      return { no: n };
    }],
    ["POST", /^api\/jobs\/([\w\-]+)\/stage$/, function (m, match) {
      var j = DB.jobs.filter(function (x) { return x.no === match[1]; })[0];
      if (!j) throw "职位不存在";
      j.status = m.target || "已关闭";
      log("职位状态变更", match[1]);
      return { ok: true };
    }],
    ["GET", /^api\/candidates$/, function (m) {
      var list = DB.candidates.filter(function (c) { return !m.stage || c.stage === m.stage; });
      return { list: list };
    }],
    ["POST", /^api\/candidates$/, function (m) {
      if (!m.name || !m.job) throw "姓名与应聘职位必填";
      var n = no("CD");
      DB.candidates.unshift({ no: n, name: m.name, job: m.job, source: m.source || "内推",
        stage: "初筛", rating: 0, expected: num(m.expected), offer: 0 });
      log("新增候选人", n);
      return { no: n };
    }],
    ["POST", /^api\/candidates\/([\w\-]+)\/stage$/, function (m, match) {
      var c = DB.candidates.filter(function (x) { return x.no === match[1]; })[0];
      if (!c) throw "候选人不存在";
      var t = m.target;
      var chain = ["初筛", "面试中", "已发Offer", "已入职"];
      if (t === "已发Offer") {
        var passed = DB.interviews.filter(function (i) {
          return i.candidate_no === c.no && i.result === "通过"; }).length;
        if (passed < 1) throw "Offer 闸口：至少一轮面试通过后才能发 Offer";
        if (!m.feedback) throw "Offer 闸口：缺少面试官评价";
        if (num(m.offerSalary) <= 0) throw "Offer 闸口：未填写核定薪酬";
        c.offer = num(m.offerSalary);
      } else if (t === "已入职") {
        if (c.stage !== "已发Offer") throw "候选人状态不允许从「" + c.stage + "」变更为「已入职」";
      } else if (t === "已淘汰") {
        /* 允许 */
      } else if (chain.indexOf(t) <= chain.indexOf(c.stage)) {
        throw "候选人状态不允许从「" + c.stage + "」变更为「" + t + "」";
      }
      c.stage = t;
      log("候选人状态变更", c.no + " → " + t);
      return { ok: true, stage: t };
    }],
    ["GET", /^api\/interviews$/, function (m) {
      var list = DB.interviews.filter(function (i) { return !m.cand || i.candidate_no === m.cand; });
      return { list: list };
    }],
    ["POST", /^api\/interviews$/, function (m) {
      if (!m.cand || !m.interviewer || !m.at) throw "缺少必填字段";
      var c = DB.candidates.filter(function (x) { return x.no === m.cand; })[0];
      if (!c) throw "候选人不存在";
      if (c.stage !== "初筛" && c.stage !== "面试中") {
        throw "候选人当前状态为「" + c.stage + "」，不能安排面试";
      }
      if (c.stage === "初筛") c.stage = "面试中";
      var rd = DB.interviews.filter(function (i) { return i.candidate_no === m.cand; }).length + 1;
      DB.interviews.unshift({ id: DB.seq + 1000, candidate_no: m.cand, rounds: rd,
        interviewer: m.interviewer, scheduled_at: m.at, form: "现场", result: "", score: 0,
        feedback: "" });
      log("安排面试", m.cand + " 第 " + rd + " 轮");
      return { rounds: rd };
    }],
    ["POST", /^api\/interviews\/(\d+)$/, function (m, match) {
      var iv = DB.interviews.filter(function (x) { return String(x.id) === match[1]; })[0];
      if (!iv) throw "面试记录不存在";
      if (["通过", "未通过"].indexOf(m.result) < 0) throw "result 仅支持 通过/未通过";
      iv.result = m.result;
      iv.score = num(m.score);
      iv.feedback = m.feedback || "";
      log("录入面试结果", iv.candidate_no + " " + m.result);
      return { ok: true };
    }],

    ["GET", /^api\/perf\/cycles$/, function () { return { list: DB.perfCycles }; }],
    ["POST", /^api\/perf\/cycles$/, function (m) {
      if (!m.name || !m.period) throw "周期名称与区间必填";
      if (DB.perfCycles.some(function (c) { return c.name === m.name; })) throw "考核周期已存在";
      DB.perfCycles.unshift({ name: m.name, period: m.period, status: "进行中" });
      log("新建考核周期", m.name);
      return { name: m.name };
    }],
    ["GET", /^api\/perf\/scores$/, function () { return clone(DB.perfScores); }],
    ["POST", /^api\/perf\/scores$/, function (m) {
      if (!m.cycle || !m.emp) throw "缺少必填字段";
      var total = perfScore(m);
      var found = false;
      (DB.perfScores.list || []).forEach(function (p) {
        if (p.emp === m.emp && DB.perfScores.cycle === m.cycle) {
          p.workQty = num(m.workQty, 80); p.workQuality = num(m.workQuality, 80);
          p.cooperation = num(m.cooperation, 80); p.discipline = num(m.discipline, 80);
          p.total = total; p.grade = perfGrade(total); found = true;
        }
      });
      if (!found) {
        DB.perfScores.list.unshift({ emp: m.emp, name: "", workQty: num(m.workQty, 80),
          workQuality: num(m.workQuality, 80), cooperation: num(m.cooperation, 80),
          discipline: num(m.discipline, 80), total: total, grade: perfGrade(total), comment: "" });
        DB.perfScores.grades[perfGrade(total)] = (DB.perfScores.grades[perfGrade(total)] || 0) + 1;
      }
      log("绩效评分", m.emp + " " + total);
      return { total: total, grade: perfGrade(total) };
    }],
    ["POST", /^api\/perf\/cycles\/([^/]+)\/publish$/, function (m, match) {
      var c = DB.perfCycles.filter(function (x) { return x.name === decodeURIComponent(match[1]); })[0];
      if (!c) throw "考核周期不存在";
      var n = (DB.perfScores.list || []).filter(function (p) { return DB.perfScores.cycle === c.name; }).length;
      if (n <= 0) throw "发布闸口：周期内无评分数据";
      c.status = "已归档";
      log("绩效归档发布", c.name);
      return { ok: true, scores: n };
    }],

    ["GET", /^api\/trainings$/, function () { return { list: DB.trainings }; }],
    ["POST", /^api\/trainings$/, function (m) {
      if (!m.title || !m.date) throw "培训主题与日期必填";
      var n = no("TR");
      DB.trainings.unshift({ no: n, title: m.title, category: m.category || "技能",
        trainer: m.trainer || "", date: m.date, hours: num(m.hours, 2), quota: num(m.quota, 30),
        enrolled: 0, status: "报名中" });
      log("新建培训", n);
      return { no: n };
    }],
    ["POST", /^api\/trainings\/([\w\-]+)\/enroll$/, function (m, match) {
      var t = DB.trainings.filter(function (x) { return x.no === match[1]; })[0];
      if (!t) throw "培训不存在";
      var emp = m.emp || DB.user.empNo || "EMP009";
      var recs = DB.trecords[match[1]] || (DB.trecords[match[1]] = []);
      if (recs.some(function (r) { return r.emp_no === emp; })) throw "该员工已报名";
      if (recs.length >= t.quota) throw "报名闸口：名额已满（" + t.quota + "）";
      recs.push({ emp_no: emp, name: emp, status: "已报名", score: 0 });
      t.enrolled = recs.length;
      log("培训报名", match[1] + " " + emp);
      return { ok: true };
    }],
    ["POST", /^api\/trainings\/([\w\-]+)\/grade$/, function (m, match) {
      var recs = DB.trecords[match[1]] || [];
      var r = recs.filter(function (x) { return x.emp_no === m.emp; })[0];
      if (!r) throw "无该员工报名记录";
      r.score = num(m.score);
      r.status = r.score >= 60 ? "已完成" : "缺席";
      log("培训成绩", match[1] + " " + m.emp + " " + r.score);
      return { ok: true };
    }],
    ["GET", /^api\/trainings\/([\w\-]+)\/records$/, function (m, match) {
      return { list: DB.trecords[match[1]] || [] };
    }],

    ["GET", /^api\/contracts$/, function () { return clone(DB.contracts); }],
    ["POST", /^api\/contracts\/renew$/, function (m) {
      if (!m.emp || !m.end) throw "emp 与 end 必填";
      (DB.contracts.list || []).forEach(function (c) {
        if (c.emp === m.emp && c.status === "履行中") c.status = "已续签";
      });
      DB.contracts.list.push({ emp: m.emp, name: "", type: m.type || "固定期限",
        start: new Date().toISOString().slice(0, 10), end: m.end, status: "履行中" });
      log("合同续签", m.emp);
      return { ok: true };
    }],

    ["GET", /^api\/reports\/headcount$/, function () { return DB.headcount; }],
    ["GET", /^api\/rules$/, function () { return { list: DB.rules }; }],
    ["PUT", /^api\/rules\/([\w\-]+)$/, function (m, match) {
      var r = DB.rules.filter(function (x) { return x.code === match[1]; })[0];
      if (!r) throw "规则不存在";
      if (m.value !== undefined) r.value = String(m.value);
      log("修改规则", match[1]);
      return { ok: true };
    }],
    ["GET", /^api\/users$/, function () { return { list: DB.users }; }],
    ["POST", /^api\/users$/, function (m) {
      if (!m.username || !m.password) throw "用户名与密码必填";
      if (DB.users.some(function (u) { return u.username === m.username; })) throw "用户名已存在";
      DB.users.push({ username: m.username, name: m.name || m.username, role: m.role,
        empNo: m.empNo || "", created: "—", perms: PERMS.slice() });
      log("新建用户", m.username);
      return { ok: true };
    }],
    ["GET", /^api\/logs$/, function () { return { list: DB.logs.slice(0, 200) }; }],

    ["GET", /^api\/keys$/, function () { return { list: DB.keys }; }],
    ["POST", /^api\/keys$/, function (m) {
      var key = "fhk_demo" + Math.random().toString(36).slice(2, 14);
      DB.keys.unshift({ id: DB.keys.length + 1, prefix: key.slice(0, 8), name: m.name || "未命名",
        scope: m.scope || "read", created: "—", last_used: "", revoked: 0 });
      log("创建API Key", m.name || "");
      return { key: key, name: m.name, scope: m.scope || "read", notice: "明文仅此一次返回" };
    }],
    ["POST", /^api\/keys\/(\d+)\/revoke$/, function (m, match) {
      DB.keys.forEach(function (k) { if (String(k.id) === match[1]) k.revoked = 1; });
      log("吊销API Key", match[1]);
      return { ok: true };
    }],
    ["GET", /^api\/webhooks$/, function () { return DB.hooks; }],
    ["POST", /^api\/webhooks$/, function (m) {
      if (!m.url || String(m.url).indexOf("http") !== 0) throw "回调地址必须为 http(s) URL";
      DB.hooks.list.push({ name: m.name || "未命名", url: m.url, secret: "demo-secret",
        events: (m.events || []).join(","), enabled: 1, created: "—" });
      log("新建Webhook", m.url);
      return { ok: true, secret: "hsdemo" + Math.random().toString(36).slice(2, 12),
        notice: "secret 仅此一次返回" };
    }],
    ["POST", /^api\/webhooks\/test$/, function () {
      DB.hooks.deliveries.unshift({ event: "test.ping", name: "演示回调", status: "failed",
        attempts: 1, last_at: new Date().toLocaleString("zh-CN", { hour12: false }),
        response: "DEMO 环境不外发" });
      log("Webhook test.ping", "");
      return { ok: true, queued: 1 };
    }],
    ["GET", /^api\/webhooks\/deliveries$/, function () { return { list: DB.hooks.deliveries }; }],
    ["GET", /^api\/sync\/changes$/, function () {
      return { since: "", next: new Date().toLocaleString("zh-CN", { hour12: false }),
        changes: { employees: DB.employees.slice(0, 50), leaves: DB.leaves.slice(0, 50),
          attendance: [] }, limit: 200 };
    }],
    ["GET", /^api\/health$/, function () {
      return { brand: "飞花HRM", version: "1.0.0", routes: 66, events: 14, demo: true };
    }],
    ["GET", /^api\/openapi\.json$/, function () { return { paths: {}, demo: true }; }]
  ];

  /* -------------------------------------------- 拦截 fetch */
  var origFetch = window.fetch;
  window.fetch = function (url, opt) {
    opt = opt || {};
    var path = String(url).replace(/^https?:\/\/[^/]+/, "").replace(/^\//, "")
      .split("?")[0];
    var qs = {};
    String(url).replace(/^[^?]*\??/, "").split("&").forEach(function (kv) {
      if (!kv) return;
      var j = kv.indexOf("=");
      qs[decodeURIComponent(j < 0 ? kv : kv.slice(0, j))] = decodeURIComponent(j < 0 ? "" : kv.slice(j + 1));
    });
    var method = (opt.method || "GET").toUpperCase();
    var body = {};
    if (opt.body) { try { body = JSON.parse(opt.body); } catch (e) { body = {}; } }
    for (var i = 0; i < ROUTES.length; i++) {
      if (ROUTES[i][0] !== method) continue;
      var m = ROUTES[i][1].exec(path);
      if (!m) continue;
      try {
        var result = ROUTES[i][2](Object.assign({}, qs, body), m);
        save();
        return Promise.resolve(ok(result));
      } catch (e) {
        return Promise.resolve(err(400, String(e)));
      }
    }
    return origFetch ? origFetch.apply(this, arguments)
      : Promise.resolve(err(404, "DEMO 未实现：" + method + " " + path));
  };

  /* 绕过登录直接进入 */
  try { localStorage.setItem("hrm_token", "demo-token"); } catch (e) { /* ignore */ }

  load();
  window.__HRM_DEMO_RESET__ = function () {
    try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    location.reload();
  };
})();

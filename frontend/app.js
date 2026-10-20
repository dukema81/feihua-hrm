/* 飞花 HRM · 前端框架、HR 驾驶舱、系统设置与操作日志（原生 JS，零依赖） */
(function (window, document) {
  "use strict";

  var F = window.F = {};
  var TOKEN_KEY = "hrm_token";

  F.state = { boot: null, route: "dashboard", params: {}, timer: null };

  /* ---------------------------------------------------------- 基础工具 */
  F.esc = function (s) {
    return String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  F.num = function (v, d) {
    var n = Number(v || 0);
    return n.toLocaleString("zh-CN", { minimumFractionDigits: d === undefined ? 2 : d,
      maximumFractionDigits: d === undefined ? 2 : d });
  };
  F.int = function (v) { return F.num(v, 0); };
  F.wan = function (v) {
    var n = Number(v || 0);
    return Math.abs(n) >= 10000 ? (n / 10000).toFixed(1) + " 万" : F.num(n, 0);
  };
  F.pct0 = function (v, d) { return Number(v || 0).toFixed(d === undefined ? 1 : d) + "%"; };
  F.pct = function (v) {
    var n = Number(v || 0);
    return (n <= 1 ? n * 100 : n).toFixed(1) + "%";
  };
  F.today = function () { return new Date().toISOString().slice(0, 10); };
  F.qs = function (o) {
    return Object.keys(o || {}).filter(function (k) { return o[k] !== undefined && o[k] !== null; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(o[k]); }).join("&");
  };
  F.dash = function (v) { return v === null || v === undefined || v === "" ? "—" : v; };

  var TAGS = {
    // 员工状态
    "试用期": "gold", "已转正": "green", "离职中": "gold", "已离职": "gray",
    // 请假 / 加班
    "待审批": "gold", "已批准": "green", "已驳回": "red", "已销假": "gray", "已撤回": "gray",
    "年假": "green", "事假": "gray", "病假": "blue", "婚假": "green", "产假": "blue", "调休": "blue",
    "工作日": "gray", "周末": "blue", "节假日": "red",
    // 考勤
    "正常": "green", "迟到": "gold", "早退": "gold", "缺勤": "red", "缺卡": "gold",
    "请假": "blue", "出差": "blue", "休息": "gray",
    // 招聘
    "初筛": "gray", "面试中": "blue", "已发Offer": "gold", "已入职": "green", "已淘汰": "red",
    "招聘中": "green", "已关闭": "gray", "通过": "green", "未通过": "red",
    // 薪资 / 绩效
    "草稿": "gray", "已核算": "blue", "已发放": "green",
    "进行中": "gold", "已评分": "blue", "已归档": "green",
    "S": "green", "A": "green", "B": "blue", "C": "gold", "D": "red",
    // 培训 / 合同
    "报名中": "blue", "已完成": "green", "缺席": "red",
    "履行中": "green", "已续签": "blue", "已到期": "red",
    // 通用
    "启用": "green", "停用": "gray", "吊销": "red", "禁用": "gray",
    "成功": "green", "失败": "red", "待投递": "gold", "pending": "gold", "ok": "green", "failed": "red",
    "高": "red", "中": "gold", "低": "gray"
  };
  F.TAGS = TAGS;
  F.tag = function (s, cls) {
    return '<span class="tag ' + (cls || TAGS[s] || "gray") + '">' + F.esc(s) + "</span>";
  };

  /* ---------------------------------------------------------- 请求 */
  F.raw = function (method, path, body, headers) {
    var h = { "Content-Type": "application/json" };
    var tk = localStorage.getItem(TOKEN_KEY);
    if (tk) { h.Authorization = "Bearer " + tk; h["X-Hr-Token"] = tk; }
    Object.keys(headers || {}).forEach(function (k) { h[k] = headers[k]; });
    var opt = { method: method, headers: h, credentials: "same-origin" };
    if (body !== undefined && body !== null) opt.body = JSON.stringify(body);
    return fetch(path.replace(/^\//, ""), opt).then(function (r) {
      return r.json().catch(function () { return { message: "响应解析失败" }; })
        .then(function (j) { return { status: r.status, body: j }; });
    });
  };

  F.api = function (method, path, body) {
    return F.raw(method, path, body).then(function (x) {
      if (x.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        location.href = "./login.html";
        return new Promise(function () {});
      }
      if (x.status >= 400) {
        var e = new Error((x.body && x.body.message) || ("请求失败 " + x.status));
        e.status = x.status;
        e.body = x.body;
        throw e;
      }
      return x.body;
    });
  };

  F.toast = function (msg, kind) {
    var el = document.getElementById("statusMsg");
    if (!el) return;
    el.textContent = msg;
    F._toastUntil = Date.now() + 6000;
    el.style.color = kind === "err" ? "#ffb3a7" : (kind === "ok" ? "#9ee6b8" : "");
    clearTimeout(F._t);
    F._t = setTimeout(function () { el.style.color = ""; }, 8000);
  };
  F.setStatus = function (t) {
    var el = document.getElementById("statusMsg");
    if (!el) return;
    if (F._toastUntil && Date.now() < F._toastUntil) return;
    el.textContent = t;
  };
  F.setSide = function (html) { var el = document.getElementById("side"); if (el) el.innerHTML = html; };

  F.can = function (perm) {
    var b = F.state.boot;
    return !!(b && b.user && (b.user.perms || []).indexOf(perm) >= 0);
  };
  F.isAdmin = function () { return F.state.boot && F.state.boot.user.role === "admin"; };
  F.me = function () { return (F.state.boot && F.state.boot.user) || {}; };

  /* ---------------------------------------------------------- 路由 */
  function parseHash() {
    var h = (location.hash || "#dashboard").replace(/^#\/?/, "");
    var i = h.indexOf("?");
    var route = i < 0 ? h : h.slice(0, i);
    var qs = i < 0 ? "" : h.slice(i + 1);
    var params = {};
    qs.split("&").forEach(function (kv) {
      if (!kv) return;
      var j = kv.indexOf("=");
      params[decodeURIComponent(j < 0 ? kv : kv.slice(0, j))] =
        decodeURIComponent(j < 0 ? "" : kv.slice(j + 1));
    });
    return { route: route || "dashboard", params: params };
  }

  F.go = function (route, params) {
    location.hash = "#" + route + (params && Object.keys(params).length ? "?" + F.qs(params) : "");
  };

  var PAGES = {};
  F.register = function (name, fn) { PAGES[name] = fn; };

  function render() {
    var r = parseHash();
    F.state.route = r.route;
    F.state.params = r.params;
    if (F.state.timer) { clearInterval(F.state.timer); F.state.timer = null; }
    var fn = PAGES[r.route] || PAGES.dashboard;
    var view = document.getElementById("view");
    view.innerHTML = "";
    paintNav(r.route);
    try {
      fn(r.params);
    } catch (e) {
      view.innerHTML = '<div class="panel"><div class="panel-body">页面渲染失败：' +
        F.esc(e.message) + "</div></div>";
    }
  }
  F.render = render;

  /* ---------------------------------------------------------- 导航 */
  var TREE = [
    { grp: "组织人事", items: [["dashboard", "HR 驾驶舱"], ["employees", "员工档案"],
      ["orgs", "组织架构"], ["contracts", "合同风险"]] },
    { grp: "考勤假期", items: [["attendance", "考勤管理"], ["leaves", "请假审批"],
      ["overtime", "加班管理"]] },
    { grp: "薪酬绩效", items: [["payroll", "薪资核算"], ["perf", "绩效考核"]] },
    { grp: "招聘培训", items: [["jobs", "招聘管道"], ["trainings", "培训管理"]] },
    { grp: "基础", items: [["reports", "报表中心"]] },
    { grp: "系统", items: [["integration", "集成中心"], ["settings", "系统设置"],
      ["logs", "操作日志"]] }
  ];

  var MENU = TREE.map(function (g) { return [g.grp, g.items.map(function (i) { return i[0]; })]; });

  var TITLE = {
    dashboard: "HR 驾驶舱", employees: "员工档案", orgs: "组织架构", contracts: "合同风险",
    attendance: "考勤管理", leaves: "请假审批", overtime: "加班管理", payroll: "薪资核算",
    perf: "绩效考核", jobs: "招聘管道", trainings: "培训管理", reports: "报表中心",
    integration: "集成中心", settings: "系统设置", logs: "操作日志"
  };
  F.TITLE = TITLE;

  function paintNav(route) {
    var tree = document.getElementById("tree");
    var boot = F.state.boot || {};
    var kpi = boot.kpi || {};
    var badgeFor = {
      leaves: kpi.pendingLeaves || 0, overtime: kpi.pendingOt || 0,
      payroll: kpi.payrollDraft || 0, contracts: (kpi.contractExpiring || 0) + (kpi.contractExpired || 0)
    };
    tree.innerHTML = TREE.map(function (g) {
      return '<div class="grp">' + F.esc(g.grp) + "</div>" + g.items.map(function (it) {
        var n = badgeFor[it[0]] || 0;
        var badge = n ? '<b class="nav-badge">' + n + "</b>" : "";
        return '<a href="#' + it[0] + '" class="' + (it[0] === route ? "on" : "") + '">' +
          F.esc(it[1]) + badge + "</a>";
      }).join("");
    }).join("");

    var mb = document.getElementById("menubar");
    var groupOf = {};
    MENU.forEach(function (m) { m[1].forEach(function (r) { groupOf[r] = m[0]; }); });
    mb.innerHTML = MENU.map(function (m) {
      return '<button class="' + (groupOf[route] === m[0] ? "on" : "") + '" data-group="' +
        F.esc(m[0]) + '">' + F.esc(m[0]) + "</button>";
    }).join("");
    mb.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        var g = b.getAttribute("data-group");
        var target = MENU.filter(function (m) { return m[0] === g; })[0];
        if (target) F.go(target[1][0]);
      });
    });

    var ts = document.getElementById("tabstrip");
    ts.innerHTML = '<span class="tab">' + F.esc(TITLE[route] || route) + "</span>" +
      '<span class="muted small">飞花 HRM / ' + F.esc(TITLE[route] || route) + "</span>";
  }

  /* ---------------------------------------------------------- 通用渲染 */
  F.table = function (headers, rows, opts) {
    opts = opts || {};
    var th = headers.map(function (h) {
      return "<th class='" + (h.num ? "num" : "") + "'" +
        (h.width ? " style='width:" + h.width + "'" : "") + ">" + F.esc(h.label) + "</th>";
    }).join("");
    var body = rows && rows.length ? rows.map(function (r, i) {
      return '<tr class="' + (opts.click ? "clickable" : "") + '"' +
        (opts.click ? " data-key='" + F.esc(opts.click(r, i)) + "'" : "") + ">" +
        headers.map(function (h) {
          var v = h.render ? h.render(r, i) : F.esc(r[h.key]);
          return "<td class='" + (h.num ? "num" : "") + "'>" + v + "</td>";
        }).join("") + "</tr>";
    }).join("") : '<tr class="empty-row"><td colspan="' + headers.length + '">' +
      F.esc(opts.empty || "暂无数据") + "</td></tr>";
    return "<table class='grid-table'><thead><tr>" + th + "</tr></thead><tbody>" + body + "</tbody></table>";
  };

  F.bindRows = function (root, fn) {
    (root || document).querySelectorAll("#view tbody tr[data-key]").forEach(function (tr) {
      tr.addEventListener("click", function () { fn(tr.getAttribute("data-key"), tr); });
    });
  };

  F.dialog = function (title, body, foot) {
    var mask = document.getElementById("mask");
    var dlg = document.getElementById("dialog");
    dlg.className = "dialog" + (F._wide ? " wide" : "");
    F._wide = false;
    dlg.innerHTML = '<div class="dh">' + F.esc(title) +
      '<span class="x" data-close="1">×</span></div><div class="db">' + body + "</div>" +
      (foot ? '<div class="df">' + foot + "</div>" : "");
    mask.className = "mask on";
    dlg.querySelector("[data-close]").addEventListener("click", F.closeDialog);
    return dlg;
  };
  F.dialogWide = function (title, body, foot) { F._wide = true; return F.dialog(title, body, foot); };
  F.closeDialog = function () { document.getElementById("mask").className = "mask"; };
  F.dialogOpen = function () {
    return document.getElementById("mask").className.indexOf("on") >= 0;
  };

  F.chips = function (items, active, attr) {
    return '<div class="chips">' + items.map(function (it) {
      var val = typeof it === "string" ? it : it[0];
      var label = typeof it === "string" ? it : it[1];
      var count = typeof it === "string" ? "" : (
        it[2] === undefined || it[2] === null ? "" : '<span class="chip-n">' + it[2] + "</span>");
      return '<button class="chip' + (val === active ? " on" : "") + '" ' + (attr || "data-st") +
        '="' + F.esc(val) + '">' + F.esc(label) + count + "</button>";
    }).join("") + "</div>";
  };

  F.lineChart = function (series, opts) {
    opts = opts || {};
    var W = opts.width || 640, H = opts.height || 190, P = 34;
    var labels = opts.labels || [];
    var all = [];
    series.forEach(function (s) { all = all.concat(s.data); });
    var max = Math.max.apply(null, all.concat([1]));
    var min = opts.zero === false ? Math.min.apply(null, all) : 0;
    var span = max - min || 1;
    var colors = opts.colors || ["#1f7a8c", "#c8963e", "#b4463a"];
    var w = (W - P * 2) / Math.max(1, labels.length - 1);
    var grid = [0, 0.25, 0.5, 0.75, 1].map(function (t) {
      var y = P + (H - P * 1.6) * t;
      var val = max - span * t;
      return '<line x1="' + P + '" y1="' + y + '" x2="' + (W - P) + '" y2="' + y +
        '" stroke="#eef2f5"/><text x="6" y="' + (y + 4) + '" font-size="10" fill="#8b9aa6">' +
        (val >= 10000 ? (val / 10000).toFixed(1) + "万" : Math.round(val)) + "</text>";
    }).join("");
    var paths = series.map(function (s, si) {
      var d = s.data.map(function (v, i) {
        var x = P + w * i;
        var y = P + (H - P * 1.6) * (1 - (v - min) / span);
        return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }).join(" ");
      return '<path d="' + d + '" fill="none" stroke="' + colors[si % colors.length] +
        '" stroke-width="2"/>' + s.data.map(function (v, i) {
          var x = P + w * i;
          var y = P + (H - P * 1.6) * (1 - (v - min) / span);
          return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.6" fill="' +
            colors[si % colors.length] + '"/>';
        }).join("");
    }).join("");
    var xlabels = labels.map(function (t, i) {
      return '<text x="' + (P + w * i) + '" y="' + (H - 6) +
        '" font-size="10" fill="#8b9aa6" text-anchor="middle">' + F.esc(t) + "</text>";
    }).join("");
    var legend = series.map(function (s, si) {
      return '<span class="lg-dot"><i style="background:' + colors[si % colors.length] + '"></i>' +
        F.esc(s.name) + "</span>";
    }).join("");
    return '<div class="chart-legend">' + legend + "</div>" +
      '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' +
      grid + paths + xlabels + "</svg>";
  };

  F.barChart = function (items, opts) {
    opts = opts || {};
    var W = opts.width || 640, H = opts.height || 180, P = 34;
    var max = Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1]));
    var gap = (W - P * 2) / Math.max(1, items.length);
    var bw = gap * 0.56;
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' +
      items.map(function (it, i) {
        var h = (H - P * 1.8) * (it.value / max);
        var x = P + gap * i + (gap - bw) / 2;
        var y = H - P - h;
        return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
          '" height="' + Math.max(1, h).toFixed(1) + '" rx="2" fill="' + (it.color || "#2b9eb3") + '"/>' +
          '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (y - 5) +
          '" font-size="10" fill="#5d6f7c" text-anchor="middle">' + F.esc(it.label2 || "") +
          "</text>" + '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (H - 8) +
          '" font-size="10" fill="#8b9aa6" text-anchor="middle">' + F.esc(it.label) + "</text>";
      }).join("") + "</svg>";
  };

  F.stageBars = function (stages) {
    var max = Math.max.apply(null, stages.map(function (s) { return s.count; }).concat([1]));
    return '<div class="funnel">' + stages.map(function (s) {
      var w = Math.max(5, Math.round(s.count / max * 100));
      var color = TAGS[s.status] === "gold" ? "#c8963e" : (TAGS[s.status] === "green" ? "#2f8f5b" :
        (TAGS[s.status] === "red" ? "#b4463a" : "#2b7fa8"));
      return '<div class="fn-row"><div class="fn-name">' + F.esc(s.status) + "</div>" +
        '<div class="fn-bar"><i style="width:' + w + "%;background:" + color + '"></i></div>' +
        '<div class="fn-val">' + s.count + ' <span class="muted small">人/单</span></div>' +
        '<div class="fn-conv"></div></div>';
    }).join("") + "</div>";
  };

  F.ring = function (v, opts) {
    opts = opts || {};
    var p = Math.max(0, Math.min(1, Number(v || 0)));
    var color = opts.color || (p >= 0.85 ? "#2f8f5b" : (p >= 0.6 ? "#c8963e" : "#b4463a"));
    var deg = (p * 360).toFixed(1);
    return '<div class="ring" style="background:conic-gradient(' + color + " 0deg " + deg +
      "deg,#eef2f5 " + deg + 'deg 360deg)"><div class="ring-in"><b>' +
      F.pct0(p <= 1 ? p * 100 : p, 1) + "</b><span>" + F.esc(opts.label || "") + "</span></div></div>";
  };

  F.empty = function (text) {
    return '<div class="empty-hint">' + F.esc(text || "暂无数据") + "</div>";
  };

  F.kv = function (label, value) {
    return '<div class="side-kv"><span>' + F.esc(label) + "</span><b>" + value + "</b></div>";
  };

  F.progress = function (v, cls) {
    var p = Math.max(0, Math.min(1, Number(v || 0)));
    return '<div class="pbar ' + (cls || "") + '"><i style="width:' + (p * 100).toFixed(1) + '%"></i></div>';
  };

  /* ---------------------------------------------------------- HR 驾驶舱 */
  F.register("dashboard", function () {
    F.api("GET", "/api/board").then(function (d) {
      var k = d.kpi;
      var html = '<div class="kpi-grid six">' +
        '<div class="kpi"><div class="k-label">在职员工</div><div class="k-value">' + F.int(k.headcount) +
        '</div><div class="k-sub">试用期 ' + k.probation + " · 离职中 " + k.leaving + "</div></div>" +
        '<div class="kpi green"><div class="k-label">本月出勤率</div><div class="k-value">' +
        F.pct0(k.attRate * 100) + '</div><div class="k-sub">迟到累计 ' + k.lateMin + " 分钟</div></div>" +
        '<div class="kpi gold"><div class="k-label">待审批</div><div class="k-value">' +
        (k.pendingLeaves + k.pendingOt) +
        '</div><div class="k-sub">请假 ' + k.pendingLeaves + " · 加班 " + k.pendingOt + "</div></div>" +
        '<div class="kpi"><div class="k-label">在招职位</div><div class="k-value">' + k.openJobs +
        '</div><div class="k-sub">入职转化 ' + F.pct0(k.offerRate * 100) + "</div></div>" +
        '<div class="kpi gold"><div class="k-label">最近薪资批次</div><div class="k-value">' +
        F.dash((k.payroll || {}).month || "—") + '</div><div class="k-sub">应发 ' +
        F.wan((k.payroll || {}).gross || 0) + " · 实发 " + F.wan((k.payroll || {}).net || 0) + "</div></div>" +
        '<div class="kpi red"><div class="k-label">合同风险</div><div class="k-value">' +
        ((k.contractExpiring || 0) + (k.contractExpired || 0)) +
        '</div><div class="k-sub">临期 ' + k.contractExpiring + " · 已到期 " + k.contractExpired +
        "</div></div></div>";

      var trend = d.attTrend || [];
      var labels = trend.map(function (t) { return t.date.slice(5); });
      html += '<div class="panel"><div class="panel-title">近 30 天考勤趋势' +
        '<span class="panel-actions"><a class="btn sm" href="#attendance">考勤管理</a></span></div>' +
        '<div class="panel-body">' + F.lineChart([
          { name: "正常/出差", data: trend.map(function (t) { return t["正常"]; }) },
          { name: "迟到", data: trend.map(function (t) { return t["迟到"]; }) },
          { name: "缺勤/缺卡", data: trend.map(function (t) { return t["缺勤"]; }) }
        ], { labels: labels }) + "</div></div>";

      html += '<div class="panel"><div class="panel-title">部门编制分布' +
        '<span class="panel-actions"><a class="btn sm" href="#orgs">组织架构</a></span></div>' +
        '<div class="panel-body">' + F.barChart((d.deptDist || []).map(function (x) {
          return { label: x.name, value: x.count };
        })) + "</div></div>";

      var st = Object.keys(d.grades || {}).map(function (g) {
        return { status: g, count: d.grades[g] };
      }).filter(function (x) { return x.count > 0; });
      html += '<div class="panel"><div class="panel-title">最新考核周期绩效等级分布' +
        '<span class="panel-actions"><a class="btn sm" href="#perf">绩效考核</a></span></div>' +
        '<div class="panel-body">' + F.stageBars(st) + "</div></div>";

      document.getElementById("view").innerHTML = html;

      F.setSide(
        '<div class="side-block"><div class="hd">待办提醒</div><div class="bd">' +
        F.kv("待审批请假", k.pendingLeaves + " 单") +
        F.kv("待审批加班", k.pendingOt + " 单") +
        F.kv("在招职位", k.openJobs + " 个") +
        F.kv("合同临期", k.contractExpiring + " 份") +
        F.kv("合同已到期", k.contractExpired + " 份") +
        "</div></div>" +
        '<div class="side-block"><div class="hd">工作准则</div><div class="bd small muted" style="line-height:1.9">' +
        "● 转正需评估且试用期绩效 ≥ 60 分<br>● 离职必须完成工作交接<br>" +
        "● 年假余额不足 / 时间重叠不可提交<br>● 月加班上限 36 小时（劳动法口径）<br>" +
        "● 个税七档累进 · 三险一金按基数自动核算</div></div>");
      F.setStatus("HR 驾驶舱 · 数据截至 " + new Date().toLocaleTimeString("zh-CN"));
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 系统设置 */
  var ROLE_LABEL = { admin: "系统管理员", hr: "HR 专员", hrd: "HR 总监", manager: "部门经理",
    payroll: "薪酬专员", employee: "普通员工", recruiter: "招聘专员", auditor: "审计" };
  var ROLE_MATRIX = {
    admin: ["org.read", "org.write", "att.read", "att.write", "leave.approve", "pay.read",
      "pay.write", "hire.read", "hire.write", "perf.write", "admin"],
    hr: ["org.read", "org.write", "att.read", "att.write", "leave.approve", "pay.read",
      "hire.read", "hire.write", "perf.write"],
    hrd: ["org.read", "org.write", "att.read", "leave.approve", "pay.read", "pay.write",
      "hire.read", "perf.write"],
    manager: ["org.read", "att.read", "att.write", "leave.approve", "hire.read", "hire.write", "perf.write"],
    payroll: ["org.read", "att.read", "pay.read", "pay.write"],
    employee: ["org.read", "att.read"],
    recruiter: ["org.read", "hire.read", "hire.write"],
    auditor: ["org.read", "att.read", "pay.read", "hire.read"]
  };

  F.register("settings", function () {
    var tab = F.state.params.tab || "rules";
    F.api("GET", "/api/users").then(function (du) {
      var admin = F.isAdmin();
      var html = '<div class="panel"><div class="panel-title">' +
        F.chips([["rules", "业务规则"], ["users", "账号与权限"], ["about", "系统信息"]], tab, "data-tab") +
        "</div><div class='panel-body' id='setBody'></div></div>";
      document.getElementById("view").innerHTML = html;

      var body = document.getElementById("setBody");
      var rulesCache = null;
      function paint(t) {
        if (t === "rules") {
          F.api("GET", "/api/rules").then(function (d) {
            rulesCache = d.list;
            body.innerHTML = F.table([
              { label: "规则", render: function (r) { return F.esc(r.name) +
                ' <span class="muted small mono">' + F.esc(r.code) + "</span>"; } },
              { label: "分类", render: function (r) { return F.tag(r.category, "blue"); } },
              { label: "当前值", num: true, render: function (r) {
                  return admin ? '<input class="inp sm" data-rule="' + F.esc(r.code) +
                    '" value="' + F.esc(r.value) + '" style="width:110px">' :
                    '<b>' + F.esc(r.value) + "</b> " + F.esc(r.unit); } }
            ], d.list) + (admin ? '<div class="form-foot"><button class="btn primary" id="ruleSave">' +
              "保存规则</button></div>" : '<div class="muted small">仅管理员可修改规则</div>');
            var sv = document.getElementById("ruleSave");
            if (sv) sv.addEventListener("click", function () {
              var jobs = [];
              body.querySelectorAll("[data-rule]").forEach(function (i) {
                jobs.push(F.api("PUT", "/api/rules/" + i.getAttribute("data-rule"),
                  { value: i.value }));
              });
              Promise.all(jobs).then(function () {
                F.toast("规则已保存", "ok");
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          }).catch(function (e) { F.toast(e.message, "err"); });
        } else if (t === "users") {
          body.innerHTML = (admin ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="uNew">新建账号</button></div>' : "") +
            F.table([
              { label: "账号", render: function (r) { return '<span class="mono">' + F.esc(r.username) + "</span>"; } },
              { label: "姓名", key: "name" },
              { label: "角色", render: function (r) { return F.tag(ROLE_LABEL[r.role] || r.role, "blue"); } },
              { label: "关联工号", render: function (r) { return F.esc(F.dash(r.empNo)); } }
            ], du.list) +
            "<div class='sub-title'>角色权限矩阵（11 项权限 × 8 角色）</div>" +
            F.table([{ label: "角色", render: function (r) { return F.tag(ROLE_LABEL[r] || r, "blue"); } },
              { label: "权限", render: function (r) {
                return (ROLE_MATRIX[r] || []).map(function (p) {
                  return '<span class="tag gray">' + F.esc(p) + "</span>";
                }).join(" ");
              } }], Object.keys(ROLE_MATRIX));
          var nb = document.getElementById("uNew");
          if (nb) nb.addEventListener("click", function () {
            F.dialog("新建账号",
              '<div class="form-grid">' +
              '<label>账号<input id="nuName" placeholder="小写字母/数字"></label>' +
              '<label>姓名<input id="nuDisplay"></label>' +
              '<label>角色<select id="nuRole">' + Object.keys(ROLE_LABEL).map(function (r) {
                return '<option value="' + F.esc(r) + '">' + F.esc(ROLE_LABEL[r]) + "</option>";
              }).join("") + "</select></label>" +
              '<label>关联工号<input id="nuEmp" placeholder="如 EMP009"></label>' +
              '<label>初始密码<input id="nuPwd" value="hr@2026"></label></div>',
              '<button class="btn" id="nuOk">创建</button>');
            document.getElementById("nuOk").addEventListener("click", function () {
              F.api("POST", "/api/users", {
                username: document.getElementById("nuName").value.trim(),
                name: document.getElementById("nuDisplay").value.trim(),
                role: document.getElementById("nuRole").value,
                empNo: document.getElementById("nuEmp").value.trim(),
                password: document.getElementById("nuPwd").value
              }).then(function () {
                F.closeDialog(); F.toast("账号已创建", "ok"); F.go("settings", { tab: "users" });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else {
          body.innerHTML = '<div class="kv-grid">' +
            F.kv("系统名称", "飞花 HRM · 人力资源管理系统") +
            F.kv("版本", "1.0.0") +
            F.kv("接口契约", "GET /api/openapi.json") +
            F.kv("账号数", du.list.length) +
            "</div>" +
            '<div class="sub-title">部署与对接说明</div>' +
            '<div class="panel-body small muted" style="line-height:2">' +
            "· 零第三方依赖：Python 标准库 http.server + SQLite（WAL），单进程即可运行。<br>" +
            "· 前端为原生 HTML/CSS/JS，无构建步骤，hash 路由；同一份静态资源可由任意反向代理托管。<br>" +
            "· 与 OA / ERP / 钉钉 / 企业微信对接走「三通道」：API Key（fhk_ 前缀）、Webhook（HMAC-SHA256 签名）、" +
            "增量同步 /api/sync/changes 游标拉取。<br>" +
            "· 令牌支持 Authorization / X-Hr-Token / Cookie / 查询串多通道携带，避免代理改写导致掉登录。</div>";
        }
      }
      paint(tab);
      document.querySelectorAll("[data-tab]").forEach(function (b) {
        b.addEventListener("click", function () {
          document.querySelectorAll("[data-tab]").forEach(function (x) { x.className = "chip"; });
          b.className = "chip on";
          paint(b.getAttribute("data-tab"));
        });
      });
      F.setStatus("系统设置 · " + (TITLE[F.state.route] || ""));
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 操作日志 */
  F.register("logs", function () {
    F.api("GET", "/api/logs").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">操作日志' +
        '<span class="panel-actions small muted">最近 ' + d.list.length + " 条</span></div>" +
        '<div class="panel-body flush">' +
        F.table([
          { label: "时间", render: function (r) { return '<span class="mono small">' +
            F.esc(r.at) + "</span>"; } },
          { label: "操作人", render: function (r) { return F.esc(r.user); } },
          { label: "动作", render: function (r) { return F.tag(r.action, "blue"); } },
          { label: "详情", render: function (r) { return '<span class="small">' + F.esc(r.detail) + "</span>"; } }
        ], d.list, { empty: "暂无日志" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setStatus("操作日志 · 共 " + d.list.length + " 条");
      F.setSide('<div class="side-block"><div class="hd">说明</div><div class="bd small muted" ' +
        'style="line-height:1.9">所有写操作都会落审计日志：登录、员工建档与状态变更、请假/加班审批、' +
        '薪资核算与发放、招聘推进、绩效评分、培训报名、合同续签、规则修改、集成配置变更等。</div></div>');
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 启动 */
  F.boot = function () {
    return F.api("GET", "/api/auth/me").then(function (me) {
      return F.api("GET", "/api/board").then(function (board) {
        F.state.boot = {
          user: me, version: "1.0.0", brand: "飞花HRM",
          kpi: { pendingLeaves: board.kpi.pendingLeaves, pendingOt: board.kpi.pendingOt,
                 openJobs: board.kpi.openJobs,
                 contractExpiring: board.kpi.contractExpiring,
                 contractExpired: board.kpi.contractExpired,
                 payrollDraft: board.kpi.payroll && board.kpi.payroll.status === "草稿" ? 1 : 0 }
        };
        var u = me;
        var op = document.getElementById("opFoot");
        if (op) op.textContent = "操作员：" + u.name + "（" + u.roleName + "）";
        var hc = document.getElementById("hcLabel");
        if (hc) hc.textContent = "在职：" + board.kpi.headcount;
        var lv = document.getElementById("leaveLabel");
        if (lv) lv.textContent = "待审批请假：" + board.kpi.pendingLeaves;
        var jb = document.getElementById("jobLabel");
        if (jb) jb.textContent = "在招职位：" + board.kpi.openJobs;
        return F.state.boot;
      });
    });
  };

  function start() {
    if (!localStorage.getItem(TOKEN_KEY)) { location.href = "./login.html"; return; }
    F.boot().then(function () {
      render();
      window.addEventListener("hashchange", render);
      var lo = document.getElementById("btnLogout");
      if (lo) lo.addEventListener("click", function () {
        F.api("POST", "/api/auth/logout", {}).catch(function () {}).then(function () {
          localStorage.removeItem(TOKEN_KEY);
          document.cookie = "token=; path=/; max-age=0";
          location.href = "./login.html";
        });
      });
    }).catch(function (e) {
      if (e.status === 401) return;
      document.getElementById("view").innerHTML =
        '<div class="panel"><div class="panel-body">初始化失败：' + F.esc(e.message) + "</div></div>";
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window, document);

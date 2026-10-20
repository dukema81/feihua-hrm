/* 飞花 HRM · 薪资核算 / 绩效考核 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ---------------------------------------------------------- 薪资核算 */
  F.register("payroll", function () {
    F.api("GET", "/api/payroll").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">工资批次' +
        '<span class="panel-actions">' +
        (F.can("pay.write") ? '<button class="btn primary sm" id="prNew">新建批次</button>' : "") +
        "</span></div><div class='panel-body flush'>" +
        F.table([
          { label: "月份", render: function (r) { return '<span class="mono"><b>' + F.esc(r.month) + "</b></span>"; } },
          { label: "状态", render: function (r) { return F.tag(r.status); } },
          { label: "人数", num: true, key: "headcount" },
          { label: "应发合计", num: true, render: function (r) { return F.wan(r.gross) + " 元"; } },
          { label: "实发合计", num: true, render: function (r) { return F.wan(r.net) + " 元"; } },
          { label: "操作", render: function (r) {
              var ops = '<button class="btn sm" data-slips="' + F.esc(r.month) + '">工资条</button>';
              if (F.can("pay.write")) {
                if (r.status === "草稿") {
                  ops += ' <button class="btn sm primary" data-calc="' + F.esc(r.month) + '">核算</button>' +
                    ' <button class="btn sm" data-issue="' + F.esc(r.month) + '">发放</button>';
                } else if (r.status === "已核算") {
                  ops += ' <button class="btn sm primary" data-issue="' + F.esc(r.month) + '">发放</button>';
                }
              }
              return ops; } }
        ], d.list, { empty: "无工资批次" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      document.querySelectorAll("[data-calc]").forEach(function (b) {
        b.addEventListener("click", function () {
          var mo = b.getAttribute("data-calc");
          F.dialog("薪资核算 · " + mo,
            '<div class="small muted" style="line-height:1.9">将按以下口径生成全员工资条：<br>' +
            "· 绩效奖金 = 基本工资 × 20% × 最近绩效分<br>" +
            "· 加班费按已批准加班单（1.5/2/3 倍）<br>" +
            "· 三险一金个人部分按基数（4千~2.4万封顶）<br>" +
            "· 个税七档累进（起征 5000）<br>" +
            "· 缺勤按日薪扣减</div>",
            '<button class="btn primary" id="calcOk">开始核算</button>');
          document.getElementById("calcOk").addEventListener("click", function () {
            F.api("POST", "/api/payroll/" + mo + "/calc", {}).then(function (r) {
              F.closeDialog();
              F.toast("核算完成：" + r.slips + " 条，应发 " + F.wan(r.gross) + " 元", "ok");
              F.go("payroll");
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });
      });
      document.querySelectorAll("[data-issue]").forEach(function (b) {
        b.addEventListener("click", function () {
          var mo = b.getAttribute("data-issue");
          F.api("POST", "/api/payroll/" + mo + "/stage", { target: "已发放" })
            .then(function () { F.toast("批次 " + mo + " 已发放", "ok"); F.go("payroll"); })
            .catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      document.querySelectorAll("[data-slips]").forEach(function (b) {
        b.addEventListener("click", function () {
          var mo = b.getAttribute("data-slips");
          F.api("GET", "/api/payroll/" + mo + "/payslips").then(function (p) {
            F.dialogWide("工资条 · " + mo + "（" + p.status + "）",
              F.table([
                { label: "工号", key: "emp" },
                { label: "姓名", key: "name" },
                { label: "基本", num: true, render: function (r) { return F.num(r.base, 0); } },
                { label: "绩效", num: true, render: function (r) { return F.num(r.perfBonus, 0); } },
                { label: "加班", num: true, render: function (r) { return F.num(r.otPay, 0); } },
                { label: "应发", num: true, render: function (r) { return "<b>" + F.num(r.gross, 0) + "</b>"; } },
                { label: "社保", num: true, render: function (r) { return "-" + F.num(r.socialIns, 0); } },
                { label: "公积金", num: true, render: function (r) { return "-" + F.num(r.hf, 0); } },
                { label: "个税", num: true, render: function (r) { return "-" + F.num(r.tax, 0); } },
                { label: "实发", num: true, render: function (r) {
                    return '<b class="green">' + F.num(r.net, 0) + "</b>"; } }
              ], p.list));
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });

      var nb = document.getElementById("prNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("新建工资批次",
          '<div class="form-grid"><label>月份<input id="prMonth" type="month" value="' +
          F.today().slice(0, 7) + '"></label></div>',
          '<button class="btn primary" id="prOk">创建</button>');
        document.getElementById("prOk").addEventListener("click", function () {
          F.api("POST", "/api/payroll", { month: document.getElementById("prMonth").value })
            .then(function () {
              F.closeDialog(); F.toast("批次已创建（草稿），可执行核算", "ok"); F.go("payroll");
            }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("薪资核算 · " + d.list.length + " 个批次");
      F.setSide('<div class="side-block"><div class="hd">核算闸口</div><div class="bd small muted" ' +
        'style="line-height:1.9">核算：工资条数量必须等于在职人数（有遗漏拦截）；' +
        "发放：需薪酬权限确认。工资条生成后按员工锁定当月口径。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 绩效考核 */
  F.register("perf", function () {
    Promise.all([F.api("GET", "/api/perf/cycles"), F.api("GET", "/api/perf/scores")])
      .then(function (res) {
        var cyc = res[0], sc = res[1];
        var html = '<div class="panel"><div class="panel-title">考核周期' +
          '<span class="panel-actions">' +
          (F.can("perf.write") ? '<button class="btn primary sm" id="pcNew">新建周期</button>' : "") +
          "</span></div><div class='panel-body flush'>" +
          F.table([
            { label: "周期", render: function (r) { return '<span class="mono"><b>' + F.esc(r.name) + "</b></span>"; } },
            { label: "区间", key: "period" },
            { label: "状态", render: function (r) { return F.tag(r.status); } },
            { label: "操作", render: function (r) {
                return r.status !== "已归档" && F.can("perf.write")
                  ? '<button class="btn sm primary" data-pub="' + F.esc(r.name) + '">归档发布</button>' : "—"; } }
          ], cyc.list, { empty: "无考核周期" }) + "</div></div>";

        html += '<div class="panel"><div class="panel-title">评分明细 · ' + F.esc(sc.cycle) +
          '<span class="panel-actions small muted">S ' + sc.grades.S + " · A " + sc.grades.A +
          " · B " + sc.grades.B + " · C " + sc.grades.C + " · D " + sc.grades.D + "</span></div>" +
          '<div class="panel-body flush">' + F.table([
            { label: "工号", render: function (r) { return '<span class="mono">' + F.esc(r.emp) + "</span>"; } },
            { label: "姓名", key: "name" },
            { label: "数量 30%", num: true, key: "workQty" },
            { label: "质量 40%", num: true, key: "workQuality" },
            { label: "协作 15%", num: true, key: "cooperation" },
            { label: "纪律 15%", num: true, key: "discipline" },
            { label: "总分", num: true, render: function (r) { return "<b>" + r.total + "</b>"; } },
            { label: "等级", render: function (r) { return F.tag(r.grade); } }
          ], sc.list.slice(0, 30), { click: function (r) { return r.emp; }, empty: "暂无评分" }) +
          "</div></div>";
        document.getElementById("view").innerHTML = html;

        document.querySelectorAll("[data-pub]").forEach(function (b) {
          b.addEventListener("click", function () {
            var name = b.getAttribute("data-pub");
            F.api("POST", "/api/perf/cycles/" + name + "/publish", {})
              .then(function (r) { F.toast("已归档发布（" + r.scores + " 条评分）", "ok"); F.go("perf"); })
              .catch(function (e) { F.toast(e.message, "err"); });
          });
        });
        F.bindRows(document, function (emp) {
          if (!F.can("perf.write")) return;
          F.dialog("绩效评分 · " + emp + "（" + F.esc(sc.cycle) + "）",
            '<div class="form-grid">' +
            '<label>工作数量 30%<input id="psQty" type="number" value="80" min="0" max="100"></label>' +
            '<label>工作质量 40%<input id="psQua" type="number" value="80" min="0" max="100"></label>' +
            '<label>协作 15%<input id="psCop" type="number" value="80" min="0" max="100"></label>' +
            '<label>纪律 15%<input id="psDis" type="number" value="80" min="0" max="100"></label>' +
            '<label class="full">评语<input id="psCmt" value="季度表现稳定"></label></div>',
            '<button class="btn primary" id="psOk">保存评分</button>');
          document.getElementById("psOk").addEventListener("click", function () {
            F.api("POST", "/api/perf/scores", {
              cycle: sc.cycle, emp: emp,
              workQty: Number(document.getElementById("psQty").value || 0),
              workQuality: Number(document.getElementById("psQua").value || 0),
              cooperation: Number(document.getElementById("psCop").value || 0),
              discipline: Number(document.getElementById("psDis").value || 0),
              comment: document.getElementById("psCmt").value
            }).then(function (r) {
              F.closeDialog(); F.toast("已保存：总分 " + r.total + "（" + r.grade + "）", "ok");
              F.go("perf");
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });

        var nb = document.getElementById("pcNew");
        if (nb) nb.addEventListener("click", function () {
          F.dialog("新建考核周期",
            '<div class="form-grid">' +
            '<label>周期名称<input id="pcName" placeholder="如 2026-Q4"></label>' +
            '<label>区间<input id="pcPeriod" value="2026-10 ~ 2026-12"></label></div>',
            '<button class="btn primary" id="pcOk">创建</button>');
          document.getElementById("pcOk").addEventListener("click", function () {
            F.api("POST", "/api/perf/cycles", {
              name: document.getElementById("pcName").value.trim(),
              period: document.getElementById("pcPeriod").value.trim()
            }).then(function () {
              F.closeDialog(); F.toast("考核周期已创建", "ok"); F.go("perf");
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });
        F.setStatus("绩效考核 · " + sc.list.length + " 条评分");
        F.setSide('<div class="side-block"><div class="hd">绩效口径</div><div class="bd small muted" ' +
          'style="line-height:1.9">总分 = 数量×30% + 质量×40% + 协作×15% + 纪律×15%；' +
          "等级：S≥90 · A≥80 · B≥70 · C≥60 · D&lt;60；归档发布后不可再改分。</div></div>");
      }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);

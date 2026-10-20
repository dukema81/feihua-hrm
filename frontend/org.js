/* 飞花 HRM · 员工档案 / 组织架构 / 合同风险 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ---------------------------------------------------------- 员工档案 */
  F.register("employees", function () {
    var st = F.state.params.status || "";
    F.api("GET", "/api/employees" + (st ? "?status=" + encodeURIComponent(st) : ""))
      .then(function (d) {
        var counts = {};
        ["试用期", "已转正", "离职中", "已离职"].forEach(function (s) { counts[s] = 0; });
        d.list.forEach(function (e) { if (counts[e.status] !== undefined) counts[e.status]++; });
        var html = '<div class="panel"><div class="panel-title">员工档案' +
          '<span class="panel-actions">' +
          (F.can("org.write") ? '<button class="btn primary sm" id="eNew">新建员工</button>' : "") +
          "</span></div><div class='panel-body'>" +
          F.chips([["", "全部", d.total], ["试用期", "试用期", counts["试用期"]],
            ["已转正", "已转正", counts["已转正"]], ["离职中", "离职中", counts["离职中"]],
            ["已离职", "已离职", counts["已离职"]]], st, "data-st") +
          '<div id="empTable">' + F.table([
            { label: "工号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
            { label: "姓名", render: function (r) { return "<b>" + F.esc(r.name) + "</b>"; } },
            { label: "部门", key: "dept" },
            { label: "岗位", key: "position" },
            { label: "职级", key: "level" },
            { label: "入职日期", render: function (r) { return '<span class="mono small">' + F.esc(r.hireDate) + "</span>"; } },
            { label: "状态", render: function (r) { return F.tag(r.status); } }
          ], d.list, { click: function (r) { return r.no; }, empty: "无员工" }) + "</div></div>";
        document.getElementById("view").innerHTML = html;

        F.bindRows(document, function (no) {
          F.api("GET", "/api/employees/" + no).then(function (e) {
            var body = '<div class="kv-grid">' +
              F.kv("部门/岗位", F.esc(e.dept) + " / " + F.esc(F.dash(e.position))) +
              F.kv("职级", F.esc(F.dash(e.level))) +
              F.kv("入职日期", F.esc(e.hireDate)) +
              F.kv("转正日期", F.esc(F.dash(e.regularDate))) +
              F.kv("工龄", e.years + " 年") +
              F.kv("直属上级", F.esc(F.dash(e.manager))) +
              F.kv("基本工资", F.can("pay.read") ? F.num(e.baseSalary) + " 元" : "****") +
              F.kv("状态", F.tag(e.status)) + "</div>";
            body += '<div class="sub-title">假期余额（' + new Date().getFullYear() + "）</div>" +
              F.table([{ label: "类型", render: function (r) { return F.tag(r.ltype, "blue"); } },
                { label: "额度", num: true, render: function (r) { return r.quota + " 天"; } },
                { label: "已用", num: true, render: function (r) { return r.used + " 天"; } },
                { label: "剩余", num: true, render: function (r) {
                    return "<b>" + r.left + "</b> 天"; } }], e.quota, { empty: "无额度记录" });
            body += '<div class="sub-title">最近请假</div>' +
              F.table([{ label: "单号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
                { label: "类型", render: function (r) { return F.tag(r.ltype); } },
                { label: "起止", render: function (r) { return F.esc(r.start_date) + " ~ " + F.esc(r.end_date); } },
                { label: "天数", num: true, key: "days" },
                { label: "状态", render: function (r) { return F.tag(r.status); } }],
                e.leaves, { empty: "无请假记录" });
            body += '<div class="sub-title">绩效趋势</div>' +
              F.table([{ label: "周期", render: function (r) { return '<span class="mono">' + F.esc(r.cycle) + "</span>"; } },
                { label: "总分", num: true, key: "total" },
                { label: "等级", render: function (r) { return F.tag(r.grade); } }],
                e.perf, { empty: "无绩效记录" });
            if (F.can("org.write")) {
              body += '<div class="form-foot">' +
                (e.status === "试用期" ? '<button class="btn primary" id="eRegular">办理转正</button>' : "") +
                (e.status === "已转正" ? '<button class="btn" id="eLeave">发起离职</button>' : "") +
                (e.status === "离职中" ? '<button class="btn primary" id="eHandover">确认交接完成</button>' : "") +
                "</div>";
            }
            F.dialogWide("员工档案 · " + e.name + "（" + e.no + "）", body);
            var r1 = document.getElementById("eRegular");
            if (r1) r1.addEventListener("click", function () {
              F.dialog("转正评估",
                '<div class="form-grid"><label class="full">转正评估（带教人评价/试用期总结，必填）' +
                '<textarea id="reEval" rows="3">试用期间表现良好，达到岗位要求</textarea></label></div>',
                '<button class="btn primary" id="reOk">确认转正</button>');
              document.getElementById("reOk").addEventListener("click", function () {
                F.api("POST", "/api/employees/" + no + "/stage",
                  { target: "已转正", regularEval: document.getElementById("reEval").value })
                  .then(function () {
                    F.closeDialog(); document.getElementById("mask").className = "mask";
                    F.toast("已办理转正", "ok"); F.go("employees");
                  }).catch(function (er) { F.toast(er.message, "err"); });
              });
            });
            var r2 = document.getElementById("eLeave");
            if (r2) r2.addEventListener("click", function () {
              F.api("POST", "/api/employees/" + no + "/stage", { target: "离职中" })
                .then(function () { F.closeDialog(); F.toast("已发起离职流程", "ok"); F.go("employees"); })
                .catch(function (er) { F.toast(er.message, "err"); });
            });
            var r3 = document.getElementById("eHandover");
            if (r3) r3.addEventListener("click", function () {
              F.dialog("离职交接确认",
                '<div class="form-grid"><label class="full">交接说明<textarea id="hoNote" rows="3">' +
                "工作资料、账号权限、在途事项已全部交接</textarea></label></div>",
                '<button class="btn primary" id="hoOk">确认交接完成并办理离职</button>');
              document.getElementById("hoOk").addEventListener("click", function () {
                F.api("POST", "/api/employees/" + no + "/stage",
                  { target: "已离职", handoverDone: true, note: document.getElementById("hoNote").value })
                  .then(function () {
                    document.getElementById("mask").className = "mask";
                    F.toast("离职已办理", "ok"); F.go("employees");
                  }).catch(function (er) { F.toast(er.message, "err"); });
              });
            });
          }).catch(function (e) { F.toast(e.message, "err"); });
        });

        var nb = document.getElementById("eNew");
        if (nb) nb.addEventListener("click", function () {
          F.dialog("新建员工",
            '<div class="form-grid">' +
            '<label>工号<input id="neNo" placeholder="如 EMP023"></label>' +
            '<label>姓名<input id="neName"></label>' +
            '<label>性别<select id="neGender"><option>男</option><option>女</option></select></label>' +
            '<label>部门<select id="neDept">' +
            '<option value="D01">总经办</option><option value="D02">人力资源部</option>' +
            '<option value="D03">财务部</option><option value="D04">研发中心</option>' +
            '<option value="D05">市场部</option><option value="D06">生产运营部</option>' +
            '<option value="D07">质量管理部</option><option value="D08">供应链部</option>' +
            "</select></label>" +
            '<label>岗位<input id="nePos"></label>' +
            '<label>职级<input id="neLevel" placeholder="如 P4"></label>' +
            '<label>入职日期<input id="neHire" type="date" value="' + F.today() + '"></label>' +
            '<label>基本工资<input id="neSalary" type="number" value="10000"></label>' +
            "</div>",
            '<button class="btn primary" id="neOk">创建</button>');
          document.getElementById("neOk").addEventListener("click", function () {
            F.api("POST", "/api/employees", {
              no: document.getElementById("neNo").value.trim(),
              name: document.getElementById("neName").value.trim(),
              gender: document.getElementById("neGender").value,
              dept: document.getElementById("neDept").value,
              position: document.getElementById("nePos").value.trim(),
              level: document.getElementById("neLevel").value.trim(),
              hireDate: document.getElementById("neHire").value,
              baseSalary: Number(document.getElementById("neSalary").value || 0)
            }).then(function (r) {
              F.closeDialog(); F.toast("员工已创建（年假额度 " + r.annualQuota + " 天）", "ok");
              F.go("employees");
            }).catch(function (er) { F.toast(er.message, "err"); });
          });
        });
        F.setStatus("员工档案 · 共 " + d.total + " 人");
        F.setSide('<div class="side-block"><div class="hd">员工状态机</div><div class="bd small muted" ' +
          'style="line-height:1.9">试用期 → 已转正 → 离职中 → 已离职。<br>转正闸口：评估必填 + ' +
          "试用期绩效 ≥ 60 分。<br>离职闸口：人事审批发起 + 交接完成确认。<br>" +
          "点击行查看档案详情：假期余额、请假记录、绩效趋势。</div></div>");
      }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 组织架构 */
  F.register("orgs", function () {
    F.api("GET", "/api/departments").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">组织架构' +
        '<span class="panel-actions">' +
        (F.can("org.write") ? '<button class="btn primary sm" id="dNew">新建部门</button>' : "") +
        "</span></div><div class='panel-body'>" +
        F.table([
          { label: "编码", render: function (r) { return '<span class="mono">' + F.esc(r.code) + "</span>"; } },
          { label: "部门名称", render: function (r) { return "<b>" + F.esc(r.name) + "</b>"; } },
          { label: "负责人", key: "leader" },
          { label: "编制", num: true, key: "plan" },
          { label: "在职", num: true, key: "actual" },
          { label: "编制达成", render: function (r) {
              var p = r.plan ? r.actual / r.plan : 0;
              return '<div class="util-cell">' + F.progress(Math.min(1, p)) +
                '<span class="small">' + F.pct0(p * 100) + "</span></div>"; } }
        ], d.list, { empty: "无部门" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      var nb = document.getElementById("dNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("新建部门",
          '<div class="form-grid">' +
          '<label>编码<input id="ndCode" placeholder="如 D09"></label>' +
          '<label>名称<input id="ndName"></label>' +
          '<label>负责人<input id="ndLeader"></label>' +
          '<label>编制人数<input id="ndPlan" type="number" value="5"></label></div>',
          '<button class="btn primary" id="ndOk">创建</button>');
        document.getElementById("ndOk").addEventListener("click", function () {
          F.api("POST", "/api/departments", {
            code: document.getElementById("ndCode").value.trim(),
            name: document.getElementById("ndName").value.trim(),
            leader: document.getElementById("ndLeader").value.trim(),
            plan: Number(document.getElementById("ndPlan").value || 0)
          }).then(function () {
            F.closeDialog(); F.toast("部门已创建", "ok"); F.go("orgs");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("组织架构 · " + d.list.length + " 个部门");
      F.setSide('<div class="side-block"><div class="hd">说明</div><div class="bd small muted" ' +
        'style="line-height:1.9">部门为员工建档、考勤统计、绩效归集、招聘需求的组织维度；' +
        "编制达成率 = 在职人数 / 编制人数。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 合同风险 */
  F.register("contracts", function () {
    F.api("GET", "/api/contracts").then(function (d) {
      var risk = d.risk || {};
      var html = '<div class="kpi-grid four">' +
        '<div class="kpi"><div class="k-label">履行中合同</div><div class="k-value">' +
        d.list.filter(function (c) { return c.status === "履行中"; }).length + "</div></div>" +
        '<div class="kpi gold"><div class="k-label">临期预警（≤' + (risk.warnDays || 60) + '天）</div>' +
        '<div class="k-value">' + (risk.expiring || []).length + "</div></div>" +
        '<div class="kpi red"><div class="k-label">已到期未续</div><div class="k-value">' +
        (risk.expired || []).length + "</div></div>" +
        '<div class="kpi green"><div class="k-label">已续签</div><div class="k-value">' +
        d.list.filter(function (c) { return c.status === "已续签"; }).length + "</div></div></div>";
      html += '<div class="panel"><div class="panel-title">风险明细' +
        "<span class='panel-actions small muted'>预警阈值 " + (risk.warnDays || 60) + " 天（规则 contract_warn_days）</span></div>" +
        '<div class="panel-body flush">' + F.table([
          { label: "工号", key: "empNo" },
          { label: "类型", key: "type" },
          { label: "到期日", render: function (r) { return '<span class="mono">' + F.esc(r.endDate) + "</span>"; } },
          { label: "剩余/超期", num: true, render: function (r) {
              return '<span class="' + (r.days < 0 ? "red" : "gold") + '">' + r.days + " 天</span>"; } },
          { label: "状态", render: function (r) { return r.days < 0 ? F.tag("已到期") : F.tag("履行中"); } }
        ], (risk.expired || []).concat(risk.expiring || []),
          { empty: "暂无风险合同", click: function (r) { return r.empNo; } }) + "</div></div>";
      html += '<div class="panel"><div class="panel-title">全部合同</div><div class="panel-body flush">' +
        F.table([
          { label: "工号", render: function (r) { return '<span class="mono">' + F.esc(r.emp) + "</span>"; } },
          { label: "姓名", key: "name" },
          { label: "类型", key: "type" },
          { label: "起", render: function (r) { return '<span class="mono small">' + F.esc(r.start) + "</span>"; } },
          { label: "止", render: function (r) { return '<span class="mono small">' + F.esc(r.end) + "</span>"; } },
          { label: "状态", render: function (r) { return F.tag(r.status); } }
        ], d.list, { click: function (r) { return r.emp; }, empty: "无合同" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      F.bindRows(document, function (emp) {
        if (!F.can("org.write")) return;
        F.dialog("合同续签 · " + emp,
          '<div class="form-grid">' +
          '<label>新到期日<input id="crEnd" type="date" value="' +
          new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10) + '"></label>' +
          '<label>合同类型<select id="crType"><option>固定期限</option><option>无固定期限</option></select></label>' +
          "</div>",
          '<button class="btn primary" id="crOk">确认续签</button>');
        document.getElementById("crOk").addEventListener("click", function () {
          F.api("POST", "/api/contracts/renew", {
            emp: emp, end: document.getElementById("crEnd").value,
            type: document.getElementById("crType").value
          }).then(function () {
            F.closeDialog(); F.toast("合同已续签", "ok"); F.go("contracts");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("合同风险 · 临期 " + (risk.expiring || []).length + " / 到期 " + (risk.expired || []).length);
      F.setSide('<div class="side-block"><div class="hd">预警口径</div><div class="bd small muted" ' +
        'style="line-height:1.9">到期前 ' + (risk.warnDays || 60) + " 天进入临期预警；" +
        "超过到期日为已到期。点击风险行可直接办理续签（自动生成新合同并关闭旧合同）。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);

/* 飞花 HRM · 考勤管理 / 请假审批 / 加班管理 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ---------------------------------------------------------- 考勤管理 */
  F.register("attendance", function () {
    var month = F.state.params.month || F.today().slice(0, 7);
    Promise.all([
      F.api("GET", "/api/attendance/report?month=" + month),
      F.api("GET", "/api/attendance?month=" + month)
    ]).then(function (res) {
      var rep = res[0], raw = res[1];
      var html = '<div class="panel"><div class="panel-title">月度出勤汇总 · ' + month +
        '<span class="panel-actions"><input class="inp sm" id="attMonth" type="month" value="' +
        month + '" style="width:140px"> <button class="btn sm" id="attGo">查询</button> ' +
        '<button class="btn primary sm" id="attClock">打卡</button>' +
        (F.can("att.write") ? ' <button class="btn sm" id="attAdjust">手工调整</button>' : "") +
        "</span></div><div class='panel-body flush'>" +
        F.table([
          { label: "工号", render: function (r) { return '<span class="mono">' + F.esc(r.emp) + "</span>"; } },
          { label: "姓名", key: "name" },
          { label: "部门", key: "dept" },
          { label: "应出勤", num: true, key: "workdays" },
          { label: "出勤率", render: function (r) {
              return '<div class="util-cell">' + F.progress(r.rate) +
                '<span class="small">' + F.pct0(r.rate * 100) + "</span></div>"; } },
          { label: "迟到(分)", num: true, render: function (r) {
              return r.lateMin ? '<span class="gold">' + r.lateMin + "</span>" : "0"; } },
          { label: "异常", num: true, render: function (r) {
              return r.abnormal ? '<span class="red">' + r.abnormal + "</span>" : "0"; } },
          { label: "累计工时", num: true, render: function (r) { return r.hours + " h"; } }
        ], rep.list) + "</div></div>";

      html += '<div class="panel"><div class="panel-title">打卡明细（本月）</div>' +
        '<div class="panel-body flush">' + F.table([
          { label: "日期", render: function (r) { return '<span class="mono">' + F.esc(r.date) + "</span>"; } },
          { label: "工号", key: "emp" },
          { label: "上班", render: function (r) { return '<span class="mono">' + F.esc(F.dash(r["in"])) + "</span>"; } },
          { label: "下班", render: function (r) { return '<span class="mono">' + F.esc(F.dash(r.out)) + "</span>"; } },
          { label: "状态", render: function (r) { return F.tag(r.status); } },
          { label: "工时", num: true, key: "workHours" }
        ], raw.list.slice(0, 80), { empty: "本月暂无考勤记录" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      document.getElementById("attGo").addEventListener("click", function () {
        F.go("attendance", { month: document.getElementById("attMonth").value });
      });
      document.getElementById("attClock").addEventListener("click", function () {
        F.dialog("打卡",
          '<div class="form-grid">' +
          '<label>工号<input id="ckEmp" value="' + F.esc(F.me().empNo || "EMP009") + '"></label>' +
          '<label>时间<input id="ckTime" value="' + new Date().toTimeString().slice(0, 5) + '"></label></div>',
          '<button class="btn primary" id="ckOk">打卡</button>');
        document.getElementById("ckOk").addEventListener("click", function () {
          F.api("POST", "/api/attendance/clock", {
            emp: document.getElementById("ckEmp").value.trim(),
            time: document.getElementById("ckTime").value
          }).then(function (r) {
            F.closeDialog();
            F.toast((r.action === "clockIn" ? "上班打卡成功：" : "下班打卡成功：") +
              r.status + (r.lateMin ? "（迟到 " + r.lateMin + " 分钟）" : ""), r.status === "正常" ? "ok" : "");
            F.go("attendance", { month: month });
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      var adj = document.getElementById("attAdjust");
      if (adj) adj.addEventListener("click", function () {
        F.dialog("考勤手工调整",
          '<div class="form-grid">' +
          '<label>工号<input id="adEmp" value="EMP009"></label>' +
          '<label>日期<input id="adDate" type="date" value="' + F.today() + '"></label>' +
          '<label>上班时间<input id="adIn" placeholder="如 08:55（可空）"></label>' +
          '<label>下班时间<input id="adOut" placeholder="如 18:05（可空）"></label>' +
          '<label>状态<select id="adSt"><option>自动判定</option><option>请假</option>' +
          "<option>出差</option></select></label></div>",
          '<button class="btn primary" id="adOk">保存</button>');
        document.getElementById("adOk").addEventListener("click", function () {
          var st = document.getElementById("adSt").value;
          F.api("POST", "/api/attendance", {
            emp: document.getElementById("adEmp").value.trim(),
            date: document.getElementById("adDate").value,
            "in": document.getElementById("adIn").value.trim(),
            out: document.getElementById("adOut").value.trim(),
            status: st === "自动判定" ? "" : st
          }).then(function (r) {
            F.closeDialog(); F.toast("已调整：" + r.status, "ok"); F.go("attendance", { month: month });
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("考勤管理 · " + month);
      F.setSide('<div class="side-block"><div class="hd">考勤口径</div><div class="bd small muted" ' +
        'style="line-height:1.9">标准班次 09:00–18:00，午休 1 小时不计工时；' +
        "宽限 15 分钟内不计迟到；上下班缺卡记「缺卡」；请假/出差单据自动带出。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 请假审批 */
  F.register("leaves", function () {
    var st = F.state.params.status || "待审批";
    F.api("GET", "/api/leaves" + (st ? "?status=" + encodeURIComponent(st) : ""))
      .then(function (d) {
        var html = '<div class="panel"><div class="panel-title">请假审批' +
          '<span class="panel-actions"><button class="btn primary sm" id="lvNew">提交请假</button></span></div>' +
          "<div class='panel-body'>" +
          F.chips([["待审批", "待审批"], ["已批准", "已批准"], ["已驳回", "已驳回"],
            ["已销假", "已销假"], ["", "全部"]], st, "data-st") +
          F.table([
            { label: "单号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
            { label: "工号", key: "emp" },
            { label: "类型", render: function (r) { return F.tag(r.type); } },
            { label: "起止", render: function (r) { return F.esc(r.start) + " ~ " + F.esc(r.end); } },
            { label: "天数", num: true, key: "days" },
            { label: "事由", render: function (r) { return '<span class="small">' + F.esc(F.dash(r.reason)) + "</span>"; } },
            { label: "状态", render: function (r) { return F.tag(r.status); } },
            { label: "操作", render: function (r) {
                if (r.status === "待审批" && F.can("leave.approve")) {
                  return '<button class="btn sm primary" data-approve="' + F.esc(r.no) + '">审批</button>';
                }
                if (r.status === "已批准") {
                  return '<button class="btn sm" data-cancel="' + F.esc(r.no) + '">销假</button>';
                }
                return "—"; } }
          ], d.list, { empty: "无请假单" }) + "</div></div>";
        document.getElementById("view").innerHTML = html;

        document.querySelectorAll("[data-approve]").forEach(function (b) {
          b.addEventListener("click", function () {
            var no = b.getAttribute("data-approve");
            F.dialog("请假审批 · " + no,
              '<div class="form-grid"><label class="full">审批意见<input id="lvNote" value="同意"></label></div>',
              '<button class="btn primary" id="lvOk">批准</button>' +
              '<button class="btn" id="lvNo">驳回</button>');
            document.getElementById("lvOk").addEventListener("click", function () {
              F.api("POST", "/api/leaves/" + no + "/stage",
                { target: "已批准", note: document.getElementById("lvNote").value })
                .then(function () { F.closeDialog(); F.toast("已批准，额度已扣减", "ok"); F.go("leaves"); })
                .catch(function (e) { F.toast(e.message, "err"); });
            });
            document.getElementById("lvNo").addEventListener("click", function () {
              F.api("POST", "/api/leaves/" + no + "/stage", { target: "已驳回" })
                .then(function () { F.closeDialog(); F.toast("已驳回", "ok"); F.go("leaves"); })
                .catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        });
        document.querySelectorAll("[data-cancel]").forEach(function (b) {
          b.addEventListener("click", function () {
            F.api("POST", "/api/leaves/" + b.getAttribute("data-cancel") + "/stage",
              { target: "已销假", note: "提前返岗" }).then(function () {
              F.toast("已销假，额度已返还", "ok"); F.go("leaves", { status: "已批准" });
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });

        var nb = document.getElementById("lvNew");
        if (nb) nb.addEventListener("click", function () {
          F.dialog("提交请假",
            '<div class="form-grid">' +
            '<label>工号<input id="nlEmp" value="' + F.esc(F.me().empNo || "EMP009") + '"></label>' +
            '<label>类型<select id="nlType"><option>年假</option><option>事假</option>' +
            "<option>病假</option><option>婚假</option><option>产假</option><option>调休</option></select></label>" +
            '<label>开始日期<input id="nlStart" type="date" value="' + F.today() + '"></label>' +
            '<label>结束日期<input id="nlEnd" type="date" value="' + F.today() + '"></label>' +
            '<label class="full">事由<input id="nlReason" value="个人事务"></label></div>',
            '<button class="btn primary" id="nlOk">提交</button>');
          document.getElementById("nlOk").addEventListener("click", function () {
            F.api("POST", "/api/leaves", {
              emp: document.getElementById("nlEmp").value.trim(),
              type: document.getElementById("nlType").value,
              start: document.getElementById("nlStart").value,
              end: document.getElementById("nlEnd").value,
              reason: document.getElementById("nlReason").value
            }).then(function (r) {
              F.closeDialog(); F.toast("请假单 " + r.no + " 已提交（" + r.days + " 天）", "ok");
              F.go("leaves", { status: "待审批" });
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });
        document.querySelectorAll("[data-st]").forEach(function (b) {
          b.addEventListener("click", function () {
            F.go("leaves", { status: b.getAttribute("data-st") });
          });
        });
        F.setStatus("请假审批 · " + d.list.length + " 单");
        F.setSide('<div class="side-block"><div class="hd">请假闸口</div><div class="bd small muted" ' +
          'style="line-height:1.9">提交时：天数 > 0、假期余额充足（年假/调休）、与在途单不重叠；' +
          "批准时自动扣减额度，销假自动返还；事假不占额度（无薪）。</div></div>");
      }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 加班管理 */
  F.register("overtime", function () {
    F.api("GET", "/api/overtimes").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">加班管理' +
        '<span class="panel-actions"><button class="btn primary sm" id="otNew">提交加班</button></span></div>' +
        "<div class='panel-body'>" +
        F.table([
          { label: "单号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
          { label: "工号", key: "emp" },
          { label: "日期", render: function (r) { return '<span class="mono">' + F.esc(r.date) + "</span>"; } },
          { label: "时长", num: true, render: function (r) { return r.hours + " h"; } },
          { label: "倍率", render: function (r) { return F.tag(r.type); } },
          { label: "状态", render: function (r) { return F.tag(r.status); } },
          { label: "操作", render: function (r) {
              return r.status === "待审批" && F.can("leave.approve")
                ? '<button class="btn sm primary" data-ot="' + F.esc(r.no) + '">审批</button>' : "—"; } }
        ], d.list, { empty: "无加班单" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      document.querySelectorAll("[data-ot]").forEach(function (b) {
        b.addEventListener("click", function () {
          var no = b.getAttribute("data-ot");
          F.dialog("加班审批 · " + no, "<div>确认批准该加班申请？</div>",
            '<button class="btn primary" id="otOk">批准</button><button class="btn" id="otNo">驳回</button>');
          document.getElementById("otOk").addEventListener("click", function () {
            F.api("POST", "/api/overtimes/" + no + "/stage", { target: "已批准" })
              .then(function () { F.closeDialog(); F.toast("已批准", "ok"); F.go("overtime"); })
              .catch(function (e) { F.toast(e.message, "err"); });
          });
          document.getElementById("otNo").addEventListener("click", function () {
            F.api("POST", "/api/overtimes/" + no + "/stage", { target: "已驳回" })
              .then(function () { F.closeDialog(); F.toast("已驳回", "ok"); F.go("overtime"); })
              .catch(function (e) { F.toast(e.message, "err"); });
          });
        });
      });

      var nb = document.getElementById("otNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("提交加班",
          '<div class="form-grid">' +
          '<label>工号<input id="noEmp" value="' + F.esc(F.me().empNo || "EMP009") + '"></label>' +
          '<label>日期<input id="noDate" type="date" value="' + F.today() + '"></label>' +
          '<label>时长(小时)<input id="noHours" type="number" value="2" step="0.5"></label>' +
          '<label>类型<select id="noType"><option>工作日</option><option>周末</option><option>节假日</option></select></label>' +
          '<label class="full">事由<input id="noReason" value="项目攻坚"></label></div>',
          '<button class="btn primary" id="noOk">提交</button>');
        document.getElementById("noOk").addEventListener("click", function () {
          F.api("POST", "/api/overtimes", {
            emp: document.getElementById("noEmp").value.trim(),
            date: document.getElementById("noDate").value,
            hours: Number(document.getElementById("noHours").value || 0),
            type: document.getElementById("noType").value,
            reason: document.getElementById("noReason").value
          }).then(function (r) {
            F.closeDialog(); F.toast("加班单 " + r.no + " 已提交", "ok"); F.go("overtime");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("加班管理 · " + d.list.length + " 单");
      F.setSide('<div class="side-block"><div class="hd">加班口径</div><div class="bd small muted" ' +
        'style="line-height:1.9">工作日 1.5 倍、周末 2 倍、节假日 3 倍工资；' +
        "月度已批加班累计超 36 小时（劳动法上限）将被拦截。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);

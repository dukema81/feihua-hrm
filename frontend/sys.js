/* 飞花 HRM · 报表中心 / 集成中心 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ---------------------------------------------------------- 报表中心 */
  F.register("reports", function () {
    Promise.all([F.api("GET", "/api/reports/headcount"), F.api("GET", "/api/attendance/report")])
      .then(function (res) {
        var hc = res[0], att = res[1];
        var html = '<div class="kpi-grid four">' +
          '<div class="kpi"><div class="k-label">在职人数</div><div class="k-value">' + hc.total +
          '</div><div class="k-sub">编制 ' + hc.plan + "</div></div>" +
          '<div class="kpi gold"><div class="k-label">离职人数</div><div class="k-value">' + hc.leavers +
          '</div><div class="k-sub">离职率 ' + F.pct0(hc.turnRate * 100) + "</div></div>" +
          '<div class="kpi green"><div class="k-label">本月出勤率</div><div class="k-value">' +
          F.pct0((att.list.reduce(function (s, x) { return s + x.rate; }, 0) /
            Math.max(1, att.list.length)) * 100) + "</div></div>" +
          '<div class="kpi"><div class="k-label">部门数</div><div class="k-value">' +
          hc.byDept.length + "</div></div></div>";

        html += '<div class="panel"><div class="panel-title">部门人数分布' +
          '<span class="panel-actions"><a class="btn sm" href="#orgs">组织架构</a></span></div>' +
          '<div class="panel-body">' + F.barChart(hc.byDept.map(function (x) {
            return { label: x.dept, value: x.count };
          })) + "</div></div>";

        html += '<div class="panel"><div class="panel-title">职级分布</div><div class="panel-body flush">' +
          F.table([
            { label: "职级", render: function (r) { return F.tag(r.level, "blue"); } },
            { label: "人数", num: true, key: "count" }
          ], hc.byLevel) + "</div></div>";

        html += '<div class="panel"><div class="panel-title">数据导出（CSV）</div><div class="panel-body">' +
          '<div class="row-flex">' +
          '<a class="btn" href="api/reports/attendance.csv">考勤明细</a>' +
          '<a class="btn" href="api/reports/leaves.csv">请假记录</a>' +
          '<a class="btn" href="api/reports/payslips.csv">工资条（需薪资权限）</a>' +
          "</div></div></div>";
        document.getElementById("view").innerHTML = html;
        F.setStatus("报表中心 · 在职 " + hc.total + " 人");
        F.setSide('<div class="side-block"><div class="hd">说明</div><div class="bd small muted" ' +
          'style="line-height:1.9">CSV 带品牌名下载（UTF-8 BOM，Excel 直开）；' +
          "工资条导出需要 pay.read 权限；离职率 = 离职人数 /（在职 + 离职）。</div></div>");
      }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 集成中心 */
  F.register("integration", function () {
    var tab = F.state.params.tab || "keys";
    Promise.all([F.api("GET", "/api/keys"), F.api("GET", "/api/webhooks"),
      F.api("GET", "/api/webhooks/deliveries")]).then(function (res) {
      var keys = res[0], wh = res[1], dv = res[2];
      var html = '<div class="panel"><div class="panel-title">' +
        F.chips([["keys", "API Key"], ["hooks", "Webhook"], ["deliveries", "投递记录"],
          ["sync", "增量同步"]], tab, "data-tab") +
        '</div><div class="panel-body" id="intBody"></div></div>';
      document.getElementById("view").innerHTML = html;
      var body = document.getElementById("intBody");

      function paint(t) {
        if (t === "keys") {
          body.innerHTML = (F.isAdmin() ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="ikNew">生成 API Key</button></div>' : "") +
            F.table([
              { label: "前缀", render: function (r) { return '<span class="mono secret-box">' + F.esc(r.prefix) + "</span>"; } },
              { label: "名称", key: "name" },
              { label: "范围", render: function (r) { return F.tag(r.scope === "write" ? "读写" : "只读",
                  r.scope === "write" ? "blue" : "gray"); } },
              { label: "创建时间", render: function (r) { return '<span class="mono small">' + F.esc(r.created) + "</span>"; } },
              { label: "最近使用", render: function (r) { return '<span class="mono small">' + F.esc(F.dash(r.last_used)) + "</span>"; } },
              { label: "状态", render: function (r) { return r.revoked ? F.tag("吊销") : F.tag("启用"); } }
            ], keys.list) +
            '<div class="sub-title">调用方式</div>' +
            '<div class="panel-body small muted" style="line-height:2">' +
            "请求头携带 <code>X-Hr-Key: fhk_xxx</code>；read 范围只能 GET，write 可全量读写；" +
            "Key 以 SHA-256 哈希落库，明文只在创建时返回一次。</div>";
          var nb = document.getElementById("ikNew");
          if (nb) nb.addEventListener("click", function () {
            F.dialog("生成 API Key",
              '<div class="form-grid">' +
              '<label>名称<input id="ikName" value="对接系统"></label>' +
              '<label>范围<select id="ikScope"><option value="read">只读</option>' +
              '<option value="write">读写</option></select></label></div>',
              '<button class="btn primary" id="ikOk">生成</button>');
            document.getElementById("ikOk").addEventListener("click", function () {
              F.api("POST", "/api/keys", {
                name: document.getElementById("ikName").value.trim(),
                scope: document.getElementById("ikScope").value
              }).then(function (r) {
                F.dialog("密钥已生成（仅显示一次）",
                  '<div class="secret-box mono" style="word-break:break-all">' + F.esc(r.key) + "</div>",
                  '<button class="btn primary" id="ikDone">我已保存</button>');
                document.getElementById("ikDone").addEventListener("click", function () {
                  F.closeDialog(); F.go("integration", { tab: "keys" });
                });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else if (t === "hooks") {
          body.innerHTML = (F.isAdmin() ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="whNew">新建 Webhook</button> ' +
            '<button class="btn" id="whTest">发送 test.ping</button></div>' : "") +
            F.table([
              { label: "名称", key: "name" },
              { label: "回调地址", render: function (r) { return '<span class="mono small">' + F.esc(r.url) + "</span>"; } },
              { label: "订阅事件", render: function (r) {
                  return (r.events || "").split(",").filter(Boolean).map(function (e) {
                    return '<span class="tag gray">' + F.esc(e) + "</span>"; }).join(" "); } },
              { label: "状态", render: function (r) { return r.enabled ? F.tag("启用") : F.tag("停用"); } }
            ], wh.list) +
            '<div class="sub-title">签名协议</div>' +
            '<div class="panel-body small muted" style="line-height:2">' +
            "回调头：<code>X-Hr-Event</code> / <code>X-Hr-Timestamp</code> / " +
            "<code>X-Hr-Signature = HMAC-SHA256(secret, ts + \".\" + body)</code>；" +
            "失败按 30/60/120 秒退避重试 3 次。共 " + (wh.events || []).length + " 种事件。</div>";
          var wn = document.getElementById("whNew");
          if (wn) wn.addEventListener("click", function () {
            F.dialog("新建 Webhook",
              '<div class="form-grid">' +
              '<label>名称<input id="whName" value="OA 系统"></label>' +
              '<label class="full">回调地址<input id="whUrl" placeholder="https://..."></label>' +
              '<label class="full">事件（逗号分隔，空格留全部可从下方选择）' +
              '<input id="whEvents" value="employee.created,leave.approved"></label></div>',
              '<button class="btn primary" id="whOk">创建</button>');
            document.getElementById("whOk").addEventListener("click", function () {
              F.api("POST", "/api/webhooks", {
                name: document.getElementById("whName").value.trim(),
                url: document.getElementById("whUrl").value.trim(),
                events: document.getElementById("whEvents").value.split(",").map(function (s) {
                  return s.trim(); }).filter(Boolean)
              }).then(function (r) {
                F.dialog("Webhook 已创建（secret 仅显示一次）",
                  '<div class="secret-box mono" style="word-break:break-all">' + F.esc(r.secret) + "</div>",
                  '<button class="btn primary" id="whDone">我已保存</button>');
                document.getElementById("whDone").addEventListener("click", function () {
                  F.closeDialog(); F.go("integration", { tab: "hooks" });
                });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
          var wt = document.getElementById("whTest");
          if (wt) wt.addEventListener("click", function () {
            F.api("POST", "/api/webhooks/test", {}).then(function () {
              F.toast("test.ping 已入队投递", "ok"); F.go("integration", { tab: "deliveries" });
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        } else if (t === "deliveries") {
          body.innerHTML = F.table([
            { label: "事件", render: function (r) { return '<span class="tag blue">' + F.esc(r.event) + "</span>"; } },
            { label: "目标", render: function (r) { return F.esc(F.dash(r.name)); } },
            { label: "状态", render: function (r) { return F.tag(r.status); } },
            { label: "尝试", num: true, key: "attempts" },
            { label: "最近时间", render: function (r) { return '<span class="mono small">' + F.esc(F.dash(r.last_at)) + "</span>"; } }
          ], dv.list, { empty: "暂无投递记录" });
        } else {
          body.innerHTML =
            '<div class="sub-title">增量同步游标拉取</div>' +
            '<div class="panel-body small muted" style="line-height:2">' +
            "GET <code>/api/sync/changes?since=2026-10-01 00:00:00&amp;limit=200</code><br>" +
            "返回 employees / leaves / attendance 三类变更，配合 next 游标轮询，单页上限 500。</div>" +
            '<div class="form-foot"><button class="btn primary" id="syncTry">试拉一次</button></div>' +
            '<div id="syncOut" class="mono small"></div>';
          document.getElementById("syncTry").addEventListener("click", function () {
            F.api("GET", "/api/sync/changes?since=" +
              encodeURIComponent(new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 19).replace("T", " ")))
              .then(function (r) {
                document.getElementById("syncOut").textContent = JSON.stringify({
                  employees: (r.changes.employees || []).length,
                  leaves: (r.changes.leaves || []).length,
                  attendance: (r.changes.attendance || []).length,
                  next: r.next
                }, null, 2);
              }).catch(function (e) { F.toast(e.message, "err"); });
          });
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
      F.setStatus("集成中心");
      F.setSide('<div class="side-block"><div class="hd">三通道对接</div><div class="bd small muted" ' +
        'style="line-height:1.9">● API Key：fhk_ 前缀，read/write 范围<br>● Webhook：HMAC-SHA256 签名，14 种事件<br>' +
        "● 增量同步：游标拉取，供数仓/中台定时同步</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);

/* 飞花 HRM · 招聘管道 / 培训管理 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ---------------------------------------------------------- 招聘管道 */
  F.register("jobs", function () {
    var tab = F.state.params.tab || "jobs";
    Promise.all([F.api("GET", "/api/jobs"), F.api("GET", "/api/candidates")])
      .then(function (res) {
        var jobs = res[0], cands = res[1];
        var counts = {};
        ["初筛", "面试中", "已发Offer", "已入职", "已淘汰"].forEach(function (s) { counts[s] = 0; });
        cands.list.forEach(function (c) { if (counts[c.stage] !== undefined) counts[c.stage]++; });

        var html = '<div class="panel"><div class="panel-title">招聘管道' +
          '<span class="panel-actions">' +
          '<button class="btn sm" id="jbNew">发布职位</button>' +
          '<button class="btn primary sm" id="cdNew">新增候选人</button></span></div>' +
          "<div class='panel-body'>" +
          F.chips([["jobs", "职位 (" + jobs.list.length + ")"], ["cands", "候选人 (" + cands.list.length + ")"]],
            tab, "data-tab") + '<div id="pipeBody"></div></div></div>';
        document.getElementById("view").innerHTML = html;
        var body = document.getElementById("pipeBody");

        function paint(t) {
          if (t === "jobs") {
            body.innerHTML = F.table([
              { label: "职位编号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
              { label: "职位", render: function (r) { return "<b>" + F.esc(r.title) + "</b>"; } },
              { label: "部门", key: "dept" },
              { label: "需求人数", num: true, key: "headcount" },
              { label: "薪资范围", key: "salary" },
              { label: "学历", key: "education" },
              { label: "候选人", num: true, key: "candidates" },
              { label: "状态", render: function (r) { return F.tag(r.status); } }
            ], jobs.list, { click: function (r) { return "J" + r.no; }, empty: "无职位" });
          } else {
            body.innerHTML = '<div class="sub-title">漏斗概览</div><div class="funnel">' +
              ["初筛", "面试中", "已发Offer", "已入职"].map(function (s) {
                var max = Math.max.apply(null, ["初筛", "面试中", "已发Offer", "已入职"].map(
                  function (x) { return counts[x]; }).concat([1]));
                return '<div class="fn-row"><div class="fn-name">' + s + "</div>" +
                  '<div class="fn-bar"><i style="width:' + Math.max(5, Math.round(counts[s] / max * 100)) +
                  '%;background:#2b7fa8"></i></div><div class="fn-val">' + counts[s] + " 人</div></div>";
              }).join("") + "</div>" +
              F.table([
                { label: "编号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
                { label: "姓名", render: function (r) { return "<b>" + F.esc(r.name) + "</b>"; } },
                { label: "应聘职位", key: "job" },
                { label: "来源", key: "source" },
                { label: "期望薪资", num: true, render: function (r) { return r.expected ? F.num(r.expected, 0) : "—"; } },
                { label: "Offer 薪资", num: true, render: function (r) { return r.offer ? F.num(r.offer, 0) : "—"; } },
                { label: "阶段", render: function (r) { return F.tag(r.stage); } }
              ], cands.list, { click: function (r) { return "C" + r.no; }, empty: "无候选人" });
          }
          F.bindRows(document, function (key) {
            var kind = key.charAt(0), no = key.slice(1);
            if (kind === "J") {
              var j = jobs.list.filter(function (x) { return x.no === no; })[0];
              F.dialog("职位详情 · " + j.title,
                '<div class="kv-grid">' + F.kv("部门", j.dept) + F.kv("需求人数", j.headcount) +
                F.kv("薪资范围", j.salary) + F.kv("学历要求", j.education) +
                F.kv("招聘负责人", j.manager) + F.kv("状态", F.tag(j.status)) + "</div>" +
                (F.can("hire.write") && j.status === "招聘中"
                  ? '<div class="form-foot"><button class="btn" id="jbClose">关闭职位</button></div>' : ""));
              var cb = document.getElementById("jbClose");
              if (cb) cb.addEventListener("click", function () {
                F.api("POST", "/api/jobs/" + no + "/stage", { target: "已关闭" })
                  .then(function () { F.closeDialog(); F.toast("职位已关闭", "ok"); F.go("jobs", { tab: "jobs" }); })
                  .catch(function (e) { F.toast(e.message, "err"); });
              });
            } else {
              F.dialogWide("候选人 · " + no, '<div id="candDetail">加载中…</div>');
              Promise.all([F.api("GET", "/api/interviews?cand=" + encodeURIComponent(no))])
                .then(function (r) {
                  var iv = r[0];
                  var c = cands.list.filter(function (x) { return x.no === no; })[0];
                  var html2 = '<div class="kv-grid">' + F.kv("应聘职位", c.job) +
                    F.kv("来源", c.source) + F.kv("阶段", F.tag(c.stage)) +
                    F.kv("期望薪资", c.expected ? F.num(c.expected, 0) : "—") + "</div>" +
                    '<div class="sub-title">面试记录</div>' +
                    F.table([
                      { label: "轮次", num: true, key: "rounds" },
                      { label: "面试官", key: "interviewer" },
                      { label: "时间", render: function (r) { return '<span class="mono small">' + F.esc(r.scheduled_at) + "</span>"; } },
                      { label: "结果", render: function (r) { return r.result ? F.tag(r.result) : "待进行"; } },
                      { label: "评分", num: true, key: "score" },
                      { label: "评价", render: function (r) { return '<span class="small">' + F.esc(F.dash(r.feedback)) + "</span>"; } }
                    ], iv.list, { empty: "尚未安排面试" });
                  var acts = "";
                  if (F.can("hire.write")) {
                    acts = '<div class="form-foot">';
                    if (c.stage === "初筛" || c.stage === "面试中") {
                      acts += '<button class="btn" id="ciAdd">安排面试</button> ';
                    }
                    if (c.stage === "面试中") {
                      acts += '<button class="btn primary" id="ciOffer">发 Offer</button> ' +
                        '<button class="btn" id="ciOut">淘汰</button>';
                    }
                    if (c.stage === "已发Offer") {
                      acts += '<button class="btn primary" id="ciIn">确认入职</button>';
                    }
                    acts += "</div>";
                  }
                  html2 += acts;
                  document.getElementById("candDetail").innerHTML = html2;
                  var a1 = document.getElementById("ciAdd");
                  if (a1) a1.addEventListener("click", function () {
                    F.dialog("安排面试 · " + no,
                      '<div class="form-grid">' +
                      '<label>面试官<input id="ivWho" value="王明"></label>' +
                      '<label>时间<input id="ivAt" type="datetime-local" value="' +
                      F.today() + "T14:00" + '"></label></div>',
                      '<button class="btn primary" id="ivOk">安排</button>');
                    document.getElementById("ivOk").addEventListener("click", function () {
                      F.api("POST", "/api/interviews", {
                        cand: no, interviewer: document.getElementById("ivWho").value.trim(),
                        at: document.getElementById("ivAt").value.replace("T", " ")
                      }).then(function (r2) {
                        F.closeDialog(); document.getElementById("mask").className = "mask";
                        F.toast("已安排第 " + r2.rounds + " 轮面试", "ok"); F.go("jobs", { tab: "cands" });
                      }).catch(function (e) { F.toast(e.message, "err"); });
                    });
                  });
                  var a2 = document.getElementById("ciOffer");
                  if (a2) a2.addEventListener("click", function () {
                    F.dialog("发放 Offer · " + no,
                      '<div class="form-grid"><label>核定月薪<input id="ofSalary" type="number" value="20000"></label></div>',
                      '<button class="btn primary" id="ofOk">发出 Offer</button>');
                    document.getElementById("ofOk").addEventListener("click", function () {
                      F.api("POST", "/api/candidates/" + no + "/stage", {
                        target: "已发Offer", offerSalary: Number(document.getElementById("ofSalary").value || 0),
                        feedback: "面试通过，发 Offer"
                      }).then(function () {
                        F.closeDialog(); document.getElementById("mask").className = "mask";
                        F.toast("Offer 已发出", "ok"); F.go("jobs", { tab: "cands" });
                      }).catch(function (e) { F.toast(e.message, "err"); });
                    });
                  });
                  var a3 = document.getElementById("ciIn");
                  if (a3) a3.addEventListener("click", function () {
                    F.api("POST", "/api/candidates/" + no + "/stage",
                      { target: "已入职", onboardDeptOk: true })
                      .then(function () {
                        document.getElementById("mask").className = "mask";
                        F.toast("已确认入职", "ok"); F.go("jobs", { tab: "cands" });
                      }).catch(function (e) { F.toast(e.message, "err"); });
                  });
                  var a4 = document.getElementById("ciOut");
                  if (a4) a4.addEventListener("click", function () {
                    F.api("POST", "/api/candidates/" + no + "/stage", { target: "已淘汰" })
                      .then(function () {
                        document.getElementById("mask").className = "mask";
                        F.toast("已淘汰", "ok"); F.go("jobs", { tab: "cands" });
                      }).catch(function (e) { F.toast(e.message, "err"); });
                  });
                }).catch(function (e) { F.toast(e.message, "err"); });
            }
          });
        }
        paint(tab);
        document.querySelectorAll("[data-tab]").forEach(function (b) {
          b.addEventListener("click", function () {
            document.querySelectorAll("[data-tab]").forEach(function (x) { x.className = "chip"; });
            b.className = "chip on";
            paint(b.getAttribute("data-tab"));
          });
        });

        var jb = document.getElementById("jbNew");
        if (jb) jb.addEventListener("click", function () {
          F.dialog("发布职位",
            '<div class="form-grid">' +
            '<label>职位名称<input id="jnTitle"></label>' +
            '<label>部门编码<input id="jnDept" value="D04"></label>' +
            '<label>需求人数<input id="jnHc" type="number" value="1"></label>' +
            '<label>薪资范围<input id="jnSal" placeholder="如 15-25K"></label></div>',
            '<button class="btn primary" id="jnOk">发布</button>');
          document.getElementById("jnOk").addEventListener("click", function () {
            F.api("POST", "/api/jobs", {
              title: document.getElementById("jnTitle").value.trim(),
              dept: document.getElementById("jnDept").value.trim(),
              headcount: Number(document.getElementById("jnHc").value || 1),
              salary: document.getElementById("jnSal").value.trim()
            }).then(function (r) {
              F.closeDialog(); F.toast("职位 " + r.no + " 已发布", "ok"); F.go("jobs", { tab: "jobs" });
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });
        var cb = document.getElementById("cdNew");
        if (cb) cb.addEventListener("click", function () {
          F.dialog("新增候选人",
            '<div class="form-grid">' +
            '<label>姓名<input id="cnName"></label>' +
            '<label>应聘职位编号<input id="cnJob" value="JB0001"></label>' +
            '<label>来源<select id="cnSrc"><option>内推</option><option>BOSS</option>' +
            "<option>猎聘</option><option>智联</option></select></label>" +
            '<label>期望月薪<input id="cnExp" type="number" value="15000"></label></div>',
            '<button class="btn primary" id="cnOk">创建</button>');
          document.getElementById("cnOk").addEventListener("click", function () {
            F.api("POST", "/api/candidates", {
              name: document.getElementById("cnName").value.trim(),
              job: document.getElementById("cnJob").value.trim(),
              source: document.getElementById("cnSrc").value,
              expected: Number(document.getElementById("cnExp").value || 0)
            }).then(function (r) {
              F.closeDialog(); F.toast("候选人 " + r.no + " 已创建", "ok"); F.go("jobs", { tab: "cands" });
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        });
        F.setStatus("招聘管道 · " + jobs.list.length + " 职位 / " + cands.list.length + " 候选人");
        F.setSide('<div class="side-block"><div class="hd">招聘闸口</div><div class="bd small muted" ' +
          'style="line-height:1.9">初筛 → 面试中 → 已发Offer → 已入职。<br>' +
          "Offer 闸口：至少一轮面试通过 + 面试官评价 + 核定薪酬。<br>" +
          "入职闸口：部门与岗位确认。</div></div>");
      }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 培训管理 */
  F.register("trainings", function () {
    F.api("GET", "/api/trainings").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">培训管理' +
        '<span class="panel-actions">' +
        (F.can("org.write") ? '<button class="btn primary sm" id="trNew">新建培训</button>' : "") +
        "</span></div><div class='panel-body flush'>" +
        F.table([
          { label: "编号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>"; } },
          { label: "主题", render: function (r) { return "<b>" + F.esc(r.title) + "</b>"; } },
          { label: "分类", render: function (r) { return F.tag(r.category, "blue"); } },
          { label: "讲师", key: "trainer" },
          { label: "日期", render: function (r) { return '<span class="mono small">' + F.esc(r.date) + "</span>"; } },
          { label: "学时", num: true, key: "hours" },
          { label: "报名/名额", num: true, render: function (r) { return r.enrolled + " / " + r.quota; } },
          { label: "状态", render: function (r) { return F.tag(r.status); } }
        ], d.list, { click: function (r) { return r.no; }, empty: "无培训" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      F.bindRows(document, function (no) {
        F.api("GET", "/api/trainings/" + no + "/records").then(function (r) {
          var body = F.table([
            { label: "工号", render: function (r2) { return '<span class="mono">' + F.esc(r2.emp_no) + "</span>"; } },
            { label: "姓名", key: "name" },
            { label: "状态", render: function (r2) { return F.tag(r2.status); } },
            { label: "成绩", num: true, render: function (r2) { return r2.score || "—"; } }
          ], r.list, { empty: "暂无报名" }) +
          (F.can("org.write") ? '<div class="form-foot"><button class="btn" id="trEnroll">为员工报名</button>' +
            '<button class="btn primary" id="trGrade">录入成绩</button></div>' : "");
          F.dialogWide("培训详情 · " + no, body);
          var e1 = document.getElementById("trEnroll");
          if (e1) e1.addEventListener("click", function () {
            F.dialog("培训报名",
              '<div class="form-grid"><label>工号<input id="teEmp" value="EMP009"></label></div>',
              '<button class="btn primary" id="teOk">报名</button>');
            document.getElementById("teOk").addEventListener("click", function () {
              F.api("POST", "/api/trainings/" + no + "/enroll",
                { emp: document.getElementById("teEmp").value.trim() })
                .then(function () {
                  F.closeDialog(); document.getElementById("mask").className = "mask";
                  F.toast("报名成功", "ok"); F.go("trainings");
                }).catch(function (er) { F.toast(er.message, "err"); });
            });
          });
          var e2 = document.getElementById("trGrade");
          if (e2) e2.addEventListener("click", function () {
            F.dialog("录入成绩",
              '<div class="form-grid">' +
              '<label>工号<input id="tgEmp" value="EMP009"></label>' +
              '<label>成绩<input id="tgScore" type="number" value="88" min="0" max="100"></label></div>',
              '<button class="btn primary" id="tgOk">保存</button>');
            document.getElementById("tgOk").addEventListener("click", function () {
              F.api("POST", "/api/trainings/" + no + "/grade", {
                emp: document.getElementById("tgEmp").value.trim(),
                score: Number(document.getElementById("tgScore").value || 0)
              }).then(function () {
                F.closeDialog(); document.getElementById("mask").className = "mask";
                F.toast("成绩已录入", "ok"); F.go("trainings");
              }).catch(function (er) { F.toast(er.message, "err"); });
            });
          });
        }).catch(function (e) { F.toast(e.message, "err"); });
      });

      var nb = document.getElementById("trNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("新建培训",
          '<div class="form-grid">' +
          '<label>主题<input id="tnTitle"></label>' +
          '<label>分类<select id="tnCat"><option>技能</option><option>入职</option>' +
          "<option>合规</option><option>管理</option></select></label>" +
          '<label>讲师<input id="tnTrainer"></label>' +
          '<label>日期<input id="tnDate" type="date" value="' + F.today() + '"></label>' +
          '<label>学时<input id="tnHours" type="number" value="2"></label>' +
          '<label>名额<input id="tnQuota" type="number" value="30"></label></div>',
          '<button class="btn primary" id="tnOk">创建</button>');
        document.getElementById("tnOk").addEventListener("click", function () {
          F.api("POST", "/api/trainings", {
            title: document.getElementById("tnTitle").value.trim(),
            category: document.getElementById("tnCat").value,
            trainer: document.getElementById("tnTrainer").value.trim(),
            date: document.getElementById("tnDate").value,
            hours: Number(document.getElementById("tnHours").value || 2),
            quota: Number(document.getElementById("tnQuota").value || 30)
          }).then(function (r) {
            F.closeDialog(); F.toast("培训 " + r.no + " 已创建", "ok"); F.go("trainings");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.setStatus("培训管理 · " + d.list.length + " 场");
      F.setSide('<div class="side-block"><div class="hd">口径</div><div class="bd small muted" ' +
        'style="line-height:1.9">报名闸口：名额满员拦截；成绩 ≥ 60 记已完成，&lt;60 记缺席；' +
        "同一员工同一培训不可重复报名。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);

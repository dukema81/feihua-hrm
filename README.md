# 飞花HRM系统（Feihua HRM）

零依赖人力资源管理系统：**Python 标准库即可运行**（http.server + sqlite3 WAL），浏览器原生 HTML/CSS/JS 前端，覆盖员工全生命周期、考勤假期、薪资核算、招聘、绩效、培训与合同风险。

> 同系列项目：飞鹰CRM · 飞泉SCM · 飞虹股票 · 飞驰MES · 飞传WMS · 飞控QMS

## 快速开始

```bash
python backend/server.py        # 默认 http://127.0.0.1:8025
```

- 端口：环境变量 `FEIHUA_PORT`（默认 8025）；数据库：`FEIHUA_DB`（默认 `backend/data/feihua.db`）
- 首次启动自动建库并灌入确定性演示数据（8 部门 / 22 员工 / 30 天考勤 / 招聘漏斗 / 薪资批次）
- 演示账号：`admin / hr@2026`（另有 zhouh/zhrd/wangm/zhangx/liny/sunq/shenj 八角色）

## 功能亮点

- **员工四态状态机闸口**：试用期→已转正→离职中→已离职；转正强制评估且试用期绩效 ≥60 分，离职强制交接确认
- **考勤口径**：09:00–18:00 标准班次、弹性宽限 15 分钟、午休 1 小时扣减、缺卡缺勤自动判定、月度出勤率
- **假期额度**：年假按工龄自动折算（<1 年按剩余日历天比例；1/10/20 年档 5/10/15 天），余额不足与时间重叠双重拦截；批准扣额度、销假返还
- **薪资核算**：绩效奖金（基本×20%×绩效分）+ 加班费（1.5/2/3 倍）− 三险一金（基数 4 千~2.4 万封顶）− 个税七档累进（起征 5000）− 缺勤扣款；批次「草稿→已核算→已发放」闸口，工资条 net 勾稽恒等校验
- **招聘漏斗**：初筛→面试→Offer→入职，Offer 前置「至少一轮面试通过 + 面试官评价 + 核定薪酬」闸口
- **绩效考核**：四维加权（数量30/质量40/协作15/纪律15），S/A/B/C/D 等级，归档发布锁定
- **培训管理**：名额满员拦截、防重复报名、成绩自动判定完成/缺席
- **合同风险**：到期前 60 天预警、超期亮红、一键续签
- **月加班 36 小时上限**（劳动法口径）自动拦截

## 接口与集成（供外部系统对接）

- **85+ REST 路由**，OpenAPI 3.0：`GET /api/openapi.json`
- **API Key**：`fhk_` 前缀，read/write 两档 scope，SHA-256 落库，明文仅创建时返回一次
- **Webhook**：HMAC-SHA256 签名（`X-Hr-Signature = HMAC(secret, ts+"."+body)`），14 种事件，失败 30/60/120 秒退避重试 3 次
- **增量同步**：`GET /api/sync/changes?since=<时间戳>` 游标拉取，供数仓/中台定时对账
- **幂等**：`Idempotency-Key` 头防重复提交；限流 240 次/分钟/IP

## 离线 DEMO

`demo/feihua-hrm-demo.html`（305KB 单文件）：双击用浏览器打开即可，无需服务与网络。新建员工、提交请假、打卡、工资批次核算、API Key 生成等写操作在浏览器内存里按与后端一致的口径真实计算。

## 测试

```bash
python scripts/run_tests.py     # 三层门禁：单元 21 + 接口 19 + E2E 10（Playwright）
python tools/ui_check.py        # 15 页 UI 巡检
python tools/smoke_api.py       # 39 项业务主线冒烟
python tools/build_demo.py && python tools/smoke_demo.py   # DEMO 构建与冒烟
```

## 目录结构

```
backend/   db.py(26表) · hrm.py(纯函数内核) · seed.py(确定性演示数据) · server.py(85+路由)
frontend/  app.js(框架+驾驶舱+设置+日志) · org/time/pay/hire/sys.js(业务页面) · style.css
tools/     ui_check · smoke_api · build_demo · demo_mock · smoke_demo · build_docs · kb_upload · push_github
tests/     conftest + test_unit_core + test_api + test_e2e_ui
docs/      建设方案 / 接口契约 / 测试报告 / 操作手册（md + docx）
deploy/    build_package.py（tar.gz 部署包）
```

## 许可

内部项目演示用途。

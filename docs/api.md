# 飞花HRM系统 REST 接口契约

**版本**：V1.0 ｜ **Base URL**：`http://<host>:8025` ｜ **OpenAPI**：`GET /api/openapi.json`（50 paths）

---

## 1. 通用约定

### 1.1 响应包

```json
{ "code": 200, "message": "..." }          // 错误
{ ...业务字段 }                              // 成功（HTTP 200，直接返回业务 JSON）
```

HTTP 状态码：400 参数/闸口拦截 ｜ 401 未登录 ｜ 403 权限不足 ｜ 404 不存在 ｜ 429 限流 ｜ 500 服务器错误。

### 1.2 鉴权（多通道令牌）

登录后携带令牌，支持任意一种：

| 方式 | 示例 |
| --- | --- |
| Authorization 头 | `Authorization: Bearer <token>` |
| 自定义头 | `X-Hr-Token: <token>` |
| Cookie | `Cookie: token=<token>` |
| 查询串 | `GET /api/auth/me?token=<token>` |
| API Key（集成） | `X-Hr-Key: fhk_xxx`（read 只能 GET，write 可全量） |

### 1.3 幂等与限流

- 幂等：写请求携带 `Idempotency-Key` 头，同键重放返回首次结果（响应头 `X-Idempotent-Replay: true`）；
- 限流：每 IP 240 次/分钟，超限返回 429。

### 1.4 Webhook 协议

回调头：`X-Hr-Event`（事件名）、`X-Hr-Timestamp`（秒级时间戳）、`X-Hr-Signature`、`X-Hr-Delivery`。

验签示例（Python）：

```python
import hmac, hashlib
sig = hmac.new(secret.encode(), (ts + "." + raw_body).encode(), hashlib.sha256).hexdigest()
assert hmac.compare_digest(sig, received_signature)
```

**14 种事件**：employee.created / employee.stage / leave.created / leave.approved / leave.rejected / overtime.approved / payroll.calc / payroll.issued / candidate.stage / perf.published / training.enrolled / contract.renewed / rule.updated / test.ping

---

## 2. 认证（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /api/auth/login | `{username,password}` → `{token,username,name,role,roleName,perms,empNo}` |
| POST | /api/auth/logout | 注销令牌 |
| GET | /api/auth/me | 当前用户 + 权限列表 + 关联员工 |
| PUT | /api/auth/password | `{old,new}` 修改密码（新密码 ≥6 位） |

---

## 3. 看板（1）

`GET /api/board` → `{kpi:{headcount,probation,leaving,attRate,lateMin,pendingLeaves,pendingOt,openJobs,offerRate,payroll:{month,gross,net,status},contractExpiring,contractExpired}, grades:{S,A,B,C,D}, deptDist:[{name,count}], attTrend:[{date,正常,迟到,缺勤}]}`

---

## 4. 组织与主数据（2+3）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/departments | 部门列表（含在职/编制与达成率计算素材） |
| POST | /api/departments | `{code,name,leader,plan}` 新建（org.write） |
| PUT | /api/departments/{code} | 修改名称/负责人/编制 |

---

## 5. 员工（5）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/employees?status=&dept=&kw= | 员工列表（camelCase 视图） |
| POST | /api/employees | `{no,name,dept,hireDate,baseSalary,...}`，自动折算年假额度 |
| GET | /api/employees/{no} | 档案详情：years/quota/leaves/contracts/trainings/perf |
| PUT | /api/employees/{no} | 修改岗位/职级/工资等 |
| POST | /api/employees/{no}/stage | `{target,regularEval,handoverDone}` 状态机推进（闸口见 §4.1 建设方案） |

**stage 错误示例**：

```json
{ "code": 400, "message": "转正闸口：试用期绩效得分低于 60 分，不能转正" }
{ "code": 400, "message": "离职闸口：工作交接未完成，不能办理离职" }
```

---

## 6. 考勤（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/attendance?emp=&date=&month= | 打卡明细（≤500 条） |
| POST | /api/attendance/clock | `{emp,time,date?}` 上/下班打卡（午休 1h 扣减、宽限 15min） |
| POST | /api/attendance | `{emp,date,in,out,status?}` 手工调整（att.write） |
| GET | /api/attendance/report?month= | 月度汇总：`{list:[{emp,name,dept,workdays,rate,lateMin,hours,abnormal}]}` |

---

## 7. 请假与加班（5）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/leaves?status=&emp= | 请假单列表 |
| POST | /api/leaves | `{emp,type,start,end,days?,reason}`，闸口：余额/重叠/天数 |
| POST | /api/leaves/{no}/stage | `{target,note?}`：已批准（扣额度）/已驳回/已销假（返额度） |
| GET | /api/overtimes · POST | 加班单查询/提交（类型 工作日1.5x/周末2x/节假日3x，月上限 36h） |
| POST | /api/overtimes/{no}/stage | 审批（leave.approve） |

---

## 8. 薪资（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/payroll | 批次列表（pay.read） |
| POST | /api/payroll | `{month:"YYYY-MM"}` 新建草稿批次（pay.write） |
| POST | /api/payroll/{month}/calc | 生成全员工资条（绩效+加班+社保+个税+缺勤），状态→已核算 |
| POST | /api/payroll/{month}/stage | `{target:"已发放"}`（须先核算） |
| GET | /api/payroll/{month}/payslips | 工资条明细 `{base,perfBonus,otPay,gross,socialIns,hf,tax,absenceDed,net}` |

**工资条勾稽**：`net == gross − socialIns − hf − tax − absenceDed`

---

## 9. 招聘（7）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | /api/jobs | 职位列表/发布（hire.write） |
| POST | /api/jobs/{no}/stage | 关闭职位 |
| GET/POST | /api/candidates | 候选人列表（?stage=）/新增 |
| POST | /api/candidates/{no}/stage | 推进（Offer 闸口：≥1 轮面试通过+评价+核定薪酬） |
| GET/POST | /api/interviews?cand= | 面试记录/安排（初筛自动转面试中） |
| POST | /api/interviews/{id} | `{result:"通过|未通过",score,feedback}` |

---

## 10. 绩效与培训（7）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | /api/perf/cycles | 周期列表/新建（perf.write） |
| POST | /api/perf/cycles/{name}/publish | 归档发布（周期内无评分拦截） |
| GET/POST | /api/perf/scores?cycle= | 评分列表（含等级分布）/录分（加权自动算总分等级） |
| GET/POST | /api/trainings | 培训列表（报名数）/新建 |
| POST | /api/trainings/{no}/enroll | 报名（满员/重复拦截） |
| POST | /api/trainings/{no}/grade | 录成绩（≥60 已完成，<60 缺席） |

---

## 11. 合同（2）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/contracts | 全部合同 + `risk:{warnDays,expiring,expired}` |
| POST | /api/contracts/renew | `{emp,end,type}` 旧合同置已续签、生成新合同 |

---

## 12. 报表与导出（4）

`GET /api/reports/headcount`（在职/编制/离职率/部门与职级分布）
`GET /api/reports/attendance.csv` ｜ `GET /api/reports/leaves.csv` ｜ `GET /api/reports/payslips.csv`（需 pay.read；CSV 带 UTF-8 BOM，`Content-Disposition: attachment; filename*=UTF-8''飞花HRM-*.csv`）

---

## 13. 系统管理（5）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/rules · PUT /api/rules/{code} | 业务规则查询/修改（admin） |
| GET | /api/users · POST | 账号列表（含权限）/新建（admin） |
| GET | /api/logs | 操作日志（最近 200 条） |

---

## 14. 集成中心（6）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | /api/keys | Key 列表 / 生成（admin，明文仅一次） |
| POST | /api/keys/{id}/revoke | 吊销 |
| GET/POST | /api/webhooks | 回调配置（含事件清单）/ 新建 |
| POST | /api/webhooks/test | 入队投递 test.ping |
| GET | /api/webhooks/deliveries | 投递记录 |
| GET | /api/sync/changes?since=&limit= | 增量同步（≤500） |

---

## 15. 运维（2）

`GET /api/health` → `{brand,version,routes,events,employees,time}`（免鉴权）
`GET /api/openapi.json` → OpenAPI 3.0 文档（免鉴权）

---

## 16. 对接实施建议

1. 先在测试环境创建 read Key 拉通数据核对口径，再申请 write Key；
2. 员工主数据以 HRM 为准（工号 no 为全局唯一键），下游系统用 extId 映射；
3. 请假/加班等审批结果建议订阅 Webhook 而非轮询，投递失败自动退避重试 3 次；
4. 增量同步按 `next` 游标轮询（建议 5 分钟一次），首次全量用列表接口分页拉取；
5. 薪资数据敏感：只通过 pay.read 权限令牌拉取，禁止落第三方日志；
6. 所有写操作可带 Idempotency-Key，网络重试场景防重复建单。

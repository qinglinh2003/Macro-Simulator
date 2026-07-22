# 前端开发文档 v29 — 数据流·操作流·UI 合同

**状态**:设计输入文档(供 claude.ai design 迭代前端原型使用)。
**基线**:dev @ 9c7c84d(v25 Policy + v26 Controllers + v27 Shocks)+ v28 Godot 原型(被本设计取代其 UI 层,保留其架构)。
**架构裁定(继承 v28,不再讨论)**:前端零经济逻辑;Python worker 是唯一权威(World + ControlledSimulationSession + ControllerService);前端 = 坐在席位上的人类占用者,一切修改走提案 API,一切危机走 shock API。前端换皮(Godot / Web / Electron)不影响本文档任何合同。

---

## 1. 数据流梳理:后端能给什么

后端每 tick 产出三层数据,前端按层订阅:

### 1.1 公报层(玩家默认所见 —— 这是游戏性的核心)

`InstitutionObservation`:**不是引擎真值**,是统计局按发布日历延迟发布的序列。当前 schema v2 共 42 个序列(30 个基础观测 + 12 个冲击观测；权威表:`docs/controller_observations_v26.md`),每条含:窗口、频率、滞后、访问级、缺失原因。摘录骨架:

| 组 | 序列(单位) | 频率/滞后(tick) | 访问级 |
|---|---|---|---|
| 宏观核心 | price_index, inflation(per-tick), unemployment_rate, employment, avg_wage | 7 / 2 | public |
| 产出财政与人口 | real_output(30 窗), gov_deficit_to_gdp, gov_debt_to_gdp, population_alive, poverty_rate, income_gini | 30 / 7 | public |
| 利率 | policy_rate | 1 / 0 | public |
| 银行机密 | bank_reserves_total, reserve_floor_breach_share, near_failure_bank_count | 1 / 0 | operational/confidential(仅央行/监管席) |
| 外部 | 贸易/资本/储备类 | — | external 席 |

**前端必须遵守的三条语义**:
1. **缺失显式化**:预热不足/未发布/无权限 → 后端给 `missing_reason`,前端渲染"暂无数据(原因)",**禁止**用 0 或上期值补
2. **角色分级**:玩家坐哪个席看哪级数据;换席 = 仪表盘内容变化(这是玩法,不是限制)
3. **发布时点**:t 时刻只可见 `released_at ≤ t` 的公报——图表 X 轴是"发布时间",不是"参考期"。UI 应标注"3 月 12 日发布·参考期 2 月"

### 1.2 政策状态层(席位工作台数据)

来自 `DecisionContext` + registry:
- **每杠杆**:当前生效值、待生效值+生效 tick(pending 队列)、上次修改时间、下次可调时间(min_hold 冷却)、本季剩余行政容量
- **permitted_actions**:每杠杆是否可动 + **机器可读的禁止原因**(缺能力/冷却中/越权/超界)——前端据此灰化控件并显示原因 tooltip
- **成本预览**:调整成本(fixed+L1+L2 over control_scale)、admin_weight、cost_class
- 权威杠杆表:`docs/controller_levers_v26.md`(102 行 × 席位/类型/时滞/冷却/紧急白名单/control_scale)

### 1.3 事件流层(时间线数据)

规范事件流(v26 §11,input/derived 两类):
- 决策事件:提案提交/批准/拒绝(含 reason_code)/生效/失败/取消
- 冲击事件:已宣布(announcement_tick ≤ t 且对本席可见)/生效/结束
- 系统事件:peg 崩溃强制浮动、银行倒闭处置、紧急会议触发
- 席位事件:占用者换手

### 1.4 世界层(多经济体视图数据)

world_records 每 tick:汇率向量 e_i、双边贸易(import/export value+volume)、移民存量、储备、关税收入、dealer 净值(修复后有界)、ΣNFA。单经济体 records 另有 ~百个 gauge 可选择性下钻(完整键清单见 reporting/metrics.py,前端只订阅白名单)。

---

## 2. 数据的组合与展示建议

五个固定分区(布局供 design 迭代,信息架构固定):

**A|宏观驾驶舱(常驻顶部)**
- 6-8 个 stat tile:GDP(30 窗)、失业、通胀(年化显示:per-tick × 365)、物价指数、政策利率、赤字/GDP、贫困率
- 每 tile:最新公报值 + 迷你 sparkline(近 8 期公报)+ 环比箭头 + "发布于 t=X"
- **公报延迟的视觉语言**:数据陈旧度(距参考期 tick 数)用透明度/角标呈现

**B|席位工作台(左侧主区,随所坐席位切换)**
- 杠杆分组面板(按 decision_group:税收/福利/债务管理…)
- 每杠杆一行:名称、当前值、待生效值(若有,带倒计时)、控件(见 §3)、成本预览、冷却状态
- 底部:提案购物车(本次会议的动作集合)→「提交提案」/「本次不动」两个按钮;提交后显示 Coordinator 判决(accepted_pending / rejected+原因 / noop)

**C|事件时间线(右侧滚动)**
- 全部 §1.3 事件,按 tick 倒序;冲击预告置顶高亮(「预告:第 X 天石油禁运,-45% 能源产能」)
- 过滤器:仅我的席位 / 全部

**D|世界视图(标签页)**
- N 经济体小地图/卡片:各国 GDP/失业/通胀缩略 + 汇率矩阵 + 贸易流(有向粗细线)+ 移民流
- 点击他国 → 只读公开数据(public 级)

**E|危机横幅(条件出现,压倒一切)**
- 紧急会议触发时全屏横幅:触发器名称、相关公报快照、紧急白名单杠杆的快捷工作台、倒计时(real-time 模式)

图表规范:全部走 dataviz skill 的设计系统(见 §7);时间轴统一 tick→游戏日历换算(365 tick = 1 年,显示"第 3 年 第 2 季")。

---

## 3. 政策旋钮 → UI 控件映射

按 registry 校验类型逐类映射(102 个杠杆全覆盖,无例外):

| 校验类型 | 数量(约) | UI 控件 | 关键交互 |
|---|---|---|---|
| Range(数值) | ~70 | **步进器为主**(± 一档 = control_scale),辅以受限滑条 | max_step 限制单次移动距离;超界即时红显;当前值/待生效值双游标 |
| IntRange | 3 | 整数步进器 | 同上,禁止小数 |
| NullableRange | ~5 | 开关(启用/不设)+ 数值步进器 | None→值 是制度引入(确认弹窗+更高成本提示) |
| Bool | ~15 | 开关 | STATE_TRANSITION 的(如 soe_efirm)加确认弹窗 |
| Choices(枚举) | 3(monetary_regime, fx_regime, energy_rationing) | 分段控件(segmented) | **联合迁移向导**:切 manual 必须同批带 manual_policy_rate → 两步向导;切 peg 必须先选锚 → 下拉选经济体 |
| EconomyId | 1(peg_anchor) | 经济体下拉(排除自己) | 与 fx_regime 向导联动 |
| EconomySet(制裁) | 1 | 多选经济体列表(旗帜+勾选) | 显示"对方也制裁我"的双向状态;解除≠解封提示(OR 语义) |

**通用规则**:
- 只渲染 `permitted_actions` 允许的;禁止的灰化 + 原因(这些原因后端给机器码,前端配文案表)
- 每杠杆展示 implementation_lag(「通过后 91 天生效」)与 min_hold(「下次可调:第 X 天」)
- 紧急会议中:只亮 emergency=✓ 白名单,其余锁定,显示紧急成本溢价
- **提案是原子批**:购物车里的动作一起过/一起拒(Coordinator 保证);UI 不做逐个提交

**P0 席位范围建议**:先做 treasury(34 杠杆,全类型覆盖最全)+ central_bank(22,含两个向导),external/regulator/energy 席位后续开放(数据结构相同,纯内容工作)。

---

## 4. 游戏驱动与暂停

### 4.1 后端状态机(不可变合同)

```
BOUNDARY_START ──(有到期人类决策上下文)──▶ AWAITING_HUMAN ──(全部 resolve)──▶ READY_TO_COMMIT ──▶ tick 执行 ──▶ BOUNDARY_START(t+1)
```
- `session.advance()` 一次推一 tick;若停在 AWAITING_HUMAN,返回该状态与待决 context 列表,**引擎完全冻结**(tick/RNG/事件游标都不动)
- 人类决策 = `resolve_context(context_id, actions)`(actions 可为空 = 明确的"不动",也入日志)
- 三种运行模式(v26 合同):Interactive(自动暂停等人)/ Real-time(限时,超时=不动)/ Replay(回放)

### 4.2 前端驱动循环(建议实现)

- **播放控制**:暂停 / 播放(每真实秒 N tick,N∈{1,5,15,60})/ 步进 1 tick / 快进到下一事件(下个会议或冲击)
- 实现:前端循环发 `advance(ticks=burst)`(burst≤100),响应带 `advanced_ticks`;若 < 请求数 → 进入了 AWAITING_HUMAN → 切换到决策 UI,播放键变灰
- **速度与公报节律**:60x 时公报仍按自己的日历落地——tile 更新有节奏感,这是特性
- Real-time 模式:决策横幅带倒计时,倒计时归零前端主动发空 resolve
- **时间显示**:双轨(第 N 年第 Q 季第 D 天 + tick 号,tick 号供高级用户/复现)

### 4.3 会话生命周期

- 新开局:`new_game(seed, scenario)` → scenario 选择器(P1:场景库 = 冲击 tape 预设,GFC/油危机/疫情)
- 存档/读档:后端有完整 checkpoint 系统(.msim,含 session/policy/pending/事件游标)——**协议需新增 save/load 命令**(见 §5 缺口)
- 席位选择:开局时选(经济体 × 席位)组合,其余席位指派占用者(hold / 启发式 / 将来 RL artifact)——**协议需新增 assign_seat 命令**

---

## 5. 后端协议合同(现状 + 需扩展项)

### 5.1 现有协议(v28 原型,行分隔 JSON over loopback TCP,单写者)

```
→ {"request_id": X, "command": "hello" | "snapshot"}          ← 全量快照
→ {"command": "new_game", "seed": 7}                          ← 重置+快照
→ {"command": "advance", "ticks": 1..100}                     ← 推进;停在人类决策则提前返回,带 advanced_ticks
→ {"command": "resolve_context", "context_id", "actions": [{"lever","value"}]}
→ {"command": "trigger_shock"}                                ← (原型硬编码生产率冲击)
响应:{"ok": true, "request_id", ...snapshot} | {"ok": false, "error"}
快照含:tick、指标短历史(160 点环形)、待决 contexts、事件流尾部
```

### 5.2 必须新增的命令(本设计的后端工作清单)

| 命令 | 作用 | 后端支撑(已存在) |
|---|---|---|
| `get_schema(seat)` | 席位杠杆表+校验域+成本+文案键 → 前端自动生成表单 | registry 全量数据 ✅ |
| `get_observation(economy, seat)` | 公报制观测(替代现在的引擎真值指标!) | ObservationService ✅ |
| `assign_seat(economy, seat, occupant)` | 席位分配/换手 | session.assign_seat ✅ |
| `save(path)` / `load(path)` / `list_saves` | 存档 | checkpoint 系统 ✅ |
| `schedule_shock(spec)` | 场景注入(替代硬编码按钮) | world.schedule_shock ✅ |
| `get_pending(economy)` | 待生效政策队列 | PendingPolicyQueue ✅ |
| `get_events(after_seq)` | 事件流增量拉取 | 规范事件流 ✅ |
| `set_mode(interactive/realtime, deadline)` | 运行模式 | 编排层 ✅ |

**重要**:v28 原型直接推引擎真值指标(METRIC_NAMES 六项)——**本设计要求换成公报层**,真值只在"上帝模式"调试开关下可见(默认关,防 RL/人类信息不对等)。

### 5.3 判决与错误语义

- 提案判决:`rejected(reason_code)` / `accepted_pending(effective_tick, reserved_cost)` / `accepted_noop`——前端三态吐司 + 事件时间线落条
- 冲突:stale context/policy version → 机器可读冲突响应,前端刷新重试,**永不静默重基**
- schema_version 全程携带;不匹配 = 前端提示升级,拒绝继续

---

## 6. 现原型(v28)与本设计的差距清单

1. 指标层:引擎真值 → **公报制**(最大的玩法差距)
2. 杠杆:仅数值输入框 → 全类型控件 + permitted/成本/冷却/向导
3. 单席单国 → 席位选择 + 多经济体世界视图
4. 无存档 / 场景 / 事件时间线 / 紧急横幅
5. 冲击:硬编码按钮 → 场景库 + schedule_shock
6. 视觉:未设计(本轮 claude.ai design 的主战场)

## 7. 工具链备注(给开发侧)

- 图表/仪表盘遵循 Claude Code 的 **dataviz** skill 设计系统(形式启发式、色彩公式、明暗双主题)——HTML 原型与最终实现共用同一套视觉规范
- UI 原型迭代路径:本文档 → claude.ai design 出视觉/交互稿 → Claude Code 以 HTML Artifact 实现可交互原型(artifact-design skill)接真快照数据回放 → 定稿后落 Godot/Web 实现
- 后端命令扩展(§5.2)与前端原型可并行;协议先冻结本文档版本

---

## §8 v29.1 落地记录(2026-07-21 夜)

设计模版:`docs/design/policy_room_v29_light.dc.html`(claude.ai 设计稿的 1:1 Godot 复现)。

**协议 v2(macro_sim/desktop/runtime.py)**
- 世界:三国耦合(奥雷利亚=ADVANCED / 博尔维亚=DEVELOPING / 佩特罗尼亚=PETROSTATE;
  trade+capital+migration+dealer FX);玩家持 0 号经济体全部 5 席位,各配独立 HumanQueueOccupant。
- `get_schema` → `{seats: {seat: schema×5}, levers(v1 兼容=treasury), protocol_version: 2}`;
  102 旋钮 = 35+24+28+9+6。
- `snapshot` 新增:
  - `world.countries / world.latest / world.history(≤160 点)`:per-economy 6 指标 +
    `e/nfa/current_account/migrant_stock/remittances/import_value/export_delivered_volume/
    tariff_rev/dealer_valuation/peg_intact`(源:`World.world_records[-1]`)。
  - `metrics/series` 扩到 54 键(9 组×6,均经 v124 records 实测存在)。
  - `observation` = 五席位公报并集(operational/confidential 序列因玩家兼任央行/监管而可见)。
- 空动作提案不产生判决 toast(仅真动作设置 `_pending_verdict_pid`)。

**客户端(desktop/godot/scripts/main.gd)**
- 席位切换 + 分组杠杆卡;控件族:数值步进(档=control_scale,域夹 max_step)/
  choice 分段 / bool(STATE_TRANSITION 弹确认)/ 可空 None 切换 / economy_id 选国 /
  economy_set 制裁行(OR 语义)。
- 提案篮跨席位:按 decision_group 路由 resolve_context,提交闭合本届全部议题;
  「本次不动」全过。实时模式 = 播放中自动通过非紧急会议。
- 中央三 tab:宏观焦点(公报诚实信道)/ 指标全景(9×6 真值 spark)/ 世界视图
  (三国卡 + 可切指标排名 + 6 指标三色对比 + 枢纽辐射关系图 + e/NFA/CA/移民/汇款条图)。
- 危机遮罩:白名单编辑直接装篮提交;空编辑=本次不动,玩家不会被困。
- 截图验证:`MACRO_SIM_CAPTURE_PATH/_TICKS/_TAB/_SEAT/_CRISIS`(按目标 tick 推进,会议中自动 pass；`_CRISIS=1` 展示居中的紧急会议遮罩)。

**已知边界(v30 候选)**
- 三国均为玩家可见,但只有 0 号经济体可操控;assign_seat/save/load/schedule_shock 协议未开。
- 贸易为 per-economy 向量(dealer 路由无双边矩阵),关系图为枢纽辐射而非国对国连线(诚实呈现)。
- 世界 tab 数据为上帝视角;公报世界序列(exchange_rate/nfa/…)已在磁贴信道可用但未单独成板。

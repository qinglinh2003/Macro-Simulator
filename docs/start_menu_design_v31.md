# 开始菜单与新游戏配置设计规格 v31

**状态**：设计基线已冻结；`NewGameSpec v1`、当前可玩模型组合和 Godot
端到端启动链路已于 2026-07-23 落地
**目标读者**：Claude.ai Design、后续 Godot 实现者、模拟引擎维护者  
**设计基线**：沿用 v29/v30 的浅色宏观政策终端风格，目标画布 1440×900，最低 1280×800

> 请基于本文设计一个可交互的桌面游戏开始菜单与“新建模拟”流程。它不是网页后台，也不是科研参数表，而是一款金融财经 / 宏观模拟经营游戏的原生桌面入口。HTML 只是视觉与交互原型，最终会在 Godot 中复现。

## 0. 实施说明（2026-07-23）

- Claude Design 产出的原始交互稿已原样纳入 `docs/design/start_menu_v31.dc.html`，作为后续视觉回归基线。
- Godot 实现位于 `desktop/godot/scripts/start_menu.gd`，覆盖首页、六步新游戏向导、右侧摘要、设置弹窗和启动进度；主指挥室仍由 `main.gd` 负责。
- 桌面 worker 的 `new_game` 现接收严格、版本化的 `NewGameSpec v1`。Godot
  提交国家、Profile、结构覆盖、World 参数、场景、时长、性能规模、玩家国、
  五个席位和初始 Policy；Python 校验成功后才原子替换当前运行。
- 普通游戏不再把历史工厂名 `Config.v124` 当作产品版本展示。当前产品模型为
  `current_playable_v1`：它以日频 `Config.v13` 为校准起点，显式打开后续已经
  完成的住房、人口、劳动力、能源、消费分层、企业/银行完整账、国民账户、
  货币传导和技术漂移等系统。
- `CountryProfile` 的人口、TFP 和能源轴已经接入真实 Config；Entrepot 与
  Petrostate 不再是纯占位文案。
- 当前没有存档读取协议，因此首页已移除虚假的“最近自动存档 / 载入存档”入口；
  待存档合同真正落地后再恢复。
- 自动视觉回归可用 `MACRO_SIM_CAPTURE_START_STEP=1..6` 直达各步骤；原主界面截图使用 `MACRO_SIM_SKIP_START_MENU=1`。

## 1. 这次设计要解决什么

玩家在进入政策指挥室前，需要完成五件事：

1. 决定世界里有几个国家，以及世界是否存在贸易、资本流动和迁移；
2. 为每个国家选择一个 `CountryProfile`，再按需覆盖该国的结构与初始状态；
3. 选择玩家国家、玩家持有的政策席位，以及其他席位由谁控制；
4. 选择沙盒或外生冲击场景，并检查它需要的模型能力；
5. 调整运行、显示与辅助设置，最后看到一份可复核的“开局清单”再启动。

开始菜单必须同时服务两类用户：

- 普通玩家通过 Profile、少量高价值开关和预设，在 1–3 分钟内开局；
- 研究用户可以进入高级模式，搜索、覆盖、导入和导出完整参数，但不能绕过引擎校验。

## 2. 首要裁决：五类配置必须分开

| 层 | 含义 | 典型例子 | 开局后能否由政策改变 |
|---|---|---|---|
| 国家身份元数据 | 名称、代码、颜色等显示信息 | “奥雷利亚”、`AUR`、青绿色 | 否；不属于经济状态 |
| `Config` | 国家结构、机制能力、创世状态和工程参数 | 人口规模、是否有银行、企业数、生产率 | 原则上否 |
| 初始 `Policy` | t=0 时已经生效的可调整政策 | 税率、利率制度、福利、资本管制 | 是；进入游戏后走 Controller 流程 |
| `World` / `ShockTape` | 国与国之间的耦合和外生事件 | 贸易、迁移、资本流动、石油禁运 | World 结构否；冲击由场景驱动 |
| 会话与客户端设置 | 谁操作、如何暂停、如何显示 | 人类席位、实时倒计时、UI 缩放 | 不直接改变经济机制 |

设计上不能把这五类内容做成一个“全部参数”页面。尤其注意：有 78 个字段同时出现在历史 `Config` 创世字段和当前 Policy Registry 中，它们在新菜单里只能出现在“初始政策”，不能再出现在“国家结构”中形成两份真相。

## 3. 配置解析顺序

新游戏应按以下顺序得到最终运行清单，确认页也按这个顺序解释来源：

```text
基础模型 / 校准预设
    ↓
世界统一的性能规模与日历
    ↓
每国 CountryProfile 覆盖
    ↓
每国结构 Config 手工覆盖
    ↓
每国 t=0 初始 Policy
    ↓
World 跨境结构和关系
    ↓
Controller 席位分配与决策日历
    ↓
ShockTape 场景
    ↓
base_seed 为各经济体派生独立随机流
```

最终值旁应能显示来源标签，例如“基础预设”“发展中 Profile”“本国覆盖”“初始政策”。不要只显示一个数字而让玩家不知道它为何如此。

## 4. 信息架构与完整游戏流

### 4.1 首页

主操作：

- `继续游戏`：有存档时突出显示最近的自动存档；无存档时禁用；
- `新建模拟`：进入六步配置流程；
- `载入存档`：展示存档时间、模拟日期、玩家国家、场景、版本与兼容状态；
- `设置`：全局客户端设置；
- `退出`。

首页只承担品牌、继续和导航，不要在首页直接堆参数。视觉上应像金融模拟经营游戏的“作战终端入口”：克制、安静、可信，不使用科幻霓虹、股票交易 K 线背景或夸张国家旗帜。

### 4.2 新建模拟：六步向导

建议固定左侧步骤导航，中间为当前编辑区，右侧为始终可见的“本局摘要”。底部固定 `返回`、`下一步`；最后一步变为 `启动模拟`。步骤可回退，未完成校验的步骤显示红点或警告数。

1. **场景与模式**：沙盒 / 历史冲击模板 / 自定义场景；基础模型与场景说明；
2. **世界设置**：国家数量、跨境机制、随机种子、时间范围与性能规模；
3. **国家配置**：逐国设置身份、Profile、结构能力和高级覆盖；
4. **政府与席位**：玩家国家、五个政策席位、其他国家 Controller；
5. **初始政策**：逐国查看或覆盖 102 个 Registry 杠杆；
6. **检查并开始**：配置差异、能力依赖、性能估算、场景时间线、可复现信息。

“设置”可以从首页独立进入，也可在向导右上角以齿轮打开；它不是第七个经济配置步骤。

### 4.3 Claude 原型的默认开局状态

为了让设计稿直接呈现一个真实的填充态，使用当前桌面原型的开局作为 mock：自由沙盒、3 国、seed 7、快速规模、贸易 / 资本 / 迁移开启、交互模式、开局暂停；奥雷利亚使用 Advanced，博尔维亚使用 Developing，佩特罗尼亚使用 Petrostate。玩家控制奥雷利亚五席，另外两国明确显示“政策冻结 / 无 Controller”，不能显示成 AI。Petrostate 的能源生产率轴已接入；资源禀赋、主权财富基金等尚未实现的维度不作虚构。

## 5. 各步骤的具体设计

### 5.1 步骤一：场景与模式

场景卡片：

| 选项 | 含义 | 能力要求 | 默认 |
|---|---|---|---|
| 自由沙盒 | 无预设 ShockTape，政策结果完全由模拟与玩家行为产生 | 无 | 是 |
| 石油禁运 | 能源产能与进口能力同时受限，默认持续 180 tick | 能源 + 贸易 | 否 |
| 全球金融危机 | 信贷供给、需求和生产率受冲击，默认持续 365 tick | 银行 | 否 |
| 大流行 | 劳动、生产率、需求、信贷及可选贸易受冲击 | 银行；完整版还需贸易 | 否 |
| 自然灾害 | 一次性资本损失，加暂时生产率和劳动冲击 | 无形式化 capability；有实质资本存量时语义更充分 | 否 |
| 导入场景 | 读取经校验的 ShockTape JSON | 取决于内容 | 否 |

每个历史场景必须醒目标注“约化、未实证校准、未包含历史政策响应”。选择场景后，界面列出它建议启用的能力；玩家确认后才能应用，不允许静默改动国家 Config。

高级场景设置可配置：目标国家、开始 tick、公告提前量、持续时间，以及是否使用模板默认值。完整自定义 ShockSpec 编辑器不属于普通开局路径，可放在研究模式。

基础模型区域：

- `当前稳定模型`：普通模式唯一推荐选项；
- `研究预设 / 导入 YAML`：高级模式；
- 历史的 `v2...v124` 是研究谱系，不应做成普通玩家理解中的“国家模板”或“难度”。

### 5.2 步骤二：世界设置

#### 普通设置

| 配置 | 设计控件 | 规则 / 建议默认 |
|---|---|---|
| 国家数量 | 步进器 + `− / +`，旁边实时生成国家卡 | 产品 P0 建议 1–8，默认 3；引擎只要求至少 1 个，目前没有硬上限 |
| 随机种子 | 整数输入 + 骰子按钮 + 复制按钮 | 0–2,147,483,647，默认 7；相同完整清单与版本应可复现 |
| 运行时长 | 1 年 / 5 年 / 10 年 / 无限 / 自定义 | 本质对应 `n_ticks`；无限只是不设 UI 终局，不应写入一个危险的大整数 |
| 性能规模 | 快速 / 标准 / 自定义 | 快速可沿用当前原型 80 户、12 个消费品企业、4 个资本品企业；其他档位须基准测试后冻结 |
| 国际贸易 | 开关 | 多国默认开；单国时禁用并解释“没有交易对手” |
| 跨境资本 | 开关 | 多国默认开；可独立于贸易 |
| 跨境迁移 | 开关 | 多国默认开；可独立于贸易 |
| 开局暂停 | 开关 | 默认开，先展示 t=0 决策会议 |

#### 跨境高级设置

| 字段 | 范围 / 语义 | 当前默认 |
|---|---|---:|
| `fx_lambda` | 汇率局部调整系数，[0,1] | 0.05 |
| `fx_friction` | 汇率交易摩擦，≥0 | 0.03 |
| `fx_trade_cap` | 贸易相关汇率调整上限，≥0 | 0.15 |
| `capital_mobility` | 结构性资本流动强度，≥0 | 当前桌面原型 1.0 |
| `capital_adjust` | 资本头寸局部调整系数，[0,1] | 当前桌面原型 0.2 |
| `migration_rate` | 迁移响应速度，[0,1] | 0.02 |
| `migration_max_share` | 单期迁移份额上限，[0,1] | 0.25 |
| `remittance_share` | 移民汇回原籍的份额，[0,1]；可逐国覆盖 | 0.2 |
| `wage_smoothing` | 迁移工资信号平滑，[0,1] | 0.02 |
| `peg_reserves0` | 新挂钩启动时注入的初始外汇储备，≥0；World 结构参数 | 5000 |
| `periods_per_year` | World 年化尺度，>0 | 引擎默认 12；见第 12.1 节阻断项 |

不要向玩家暴露 `couple`：它是由贸易、资本、迁移或汇率挂钩自动推导的内部能力。构造器的旧 `peg/peg_economy/peg_anchor` 也不要放在这里；开局汇率制度属于每个国家的“初始政策”。

### 5.3 步骤三：国家配置

#### 布局

左边是可排序的国家列表，每张卡显示颜色、名称、Profile、人口/企业规模摘要、能力徽章和错误状态；中间编辑选中国家；右侧摘要同步更新。支持：

- 新增、删除、复制、拖动排序；
- `复制此国配置到…`、`将此项应用到所有国家`；
- `恢复 Profile`；
- 搜索字段、只看已覆盖、只看冲突；
- Profile 改变且已有手工覆盖时，弹出“保留覆盖”或“清除后重新应用”，不可静默丢失。

删除或重排国家会影响 peg anchor、制裁目标和场景目标。界面必须按稳定 country ID 维护引用，删除时列出受影响关系并要求修复；不能直接用可变列表下标长期保存玩家选择。

#### 国家身份元数据

这些字段不属于 `Config`，但应在国家卡中配置：

- 显示名称；
- 三字母国家代码；
- 英文 / 拉丁名，可选；
- 主题色与简洁徽记；
- 货币显示名、三字母代码和符号；
- 一句国家简介，可选。

引擎内部账户仍以 `CUR{i}` 作为稳定标识；国家名称、代码、数量和玩家国已经
进入 `NewGameSpec` 与桌面快照，不再硬编码为三国。货币显示名将来可以独立
增加，但不能改变账本身份。

#### CountryProfile

Profile 是“基准 Config 的创世覆盖”，不是政策预设，也不是完整国情模拟。

| Profile | 实际生效的覆盖 | 对玩家的诚实说明 |
|---|---|---|
| `symmetric` | 生产率 ×1.00；家庭账户数 ×1.00 | 对称基线 |
| `advanced` | `a` ×1.20；家庭账户数 ×1.00 | 高生产率经济体 |
| `developing` | `a` ×0.75；家庭账户数 ×1.50；`necessity_share0=0.65` | 较大的账户规模、较低生产率；必需品倾向只有在消费分层启用时才生效 |
| `entrepot` | `a` ×1.15；家庭账户数 ×0.40 | 小型高生产率；土地稀缺和开放度尚未建模，标“实验性” |
| `petrostate` | `a` ×0.85；家庭账户数 ×0.80 | 当前没有石油出口禀赋覆盖，标“实验性 / 资源特征待实现” |
| `custom` | 无自动覆盖 | 完全自定义；从当前最终值创建 |

Profile 的规模目前只乘 `n_households`，不会同步乘企业数量，也不会覆盖非零的 `demographics_population`。只有 `demographics_population=0` 时，人口内核才按经济家庭账户创世。设计稿应将最终家庭数、初始人口和企业数分别列出，避免“规模 ×1.5”被误读为所有规模量都同比扩大。

#### 普通玩家可调整的国家结构

普通模式只展示对世界观和玩法有显著影响的内容，并优先使用预设而非裸数值：

| 分组 | 可配置内容 | 对应字段 / 说明 |
|---|---|---|
| 规模 | 家庭数、消费品 / 资本品 / 能源企业数、银行数 | `n_households`, `n_firms_c`, `n_firms_k`, `n_firms_e`, `n_banks` |
| 生产 | 基础劳动生产率、资本 / 能源部门生产率、资本份额、TFP 法则 | `a`, `a_K`, `a_E`, `alpha`, `tfp_law` |
| 人口 | 人口系统、初始人口、生命周期消费、TFR、死亡率尺度 | `demographics_enabled`, `demographics_population`, `demographic_lifecycle_consumption`, `demographics_tfr`, `demographics_mortality_scale` |
| 产业结构 | 必需品 / 奢侈品分层、必需品消费占比、企业占比、能源部门 | `consumption_strata`, `necessity_share0`, `n_firm_share`, `energy_enabled` |
| 金融结构 | 银行、多银行、银行间市场、债券、股票、家庭信贷 | `bank_enabled`, `n_banks`, `interbank`, `bonds`, `capital_market`, `per_firm_equity`, `household_credit` |
| 公共部门 | 政府、国民账户指标 | `government`, `national_accounts_metrics`；货币制度不设独立的“央行存在”能力旗，直接在初始 Policy 选择 |
| 住房 | 住房登记、交易、按揭、租赁、建造 | `housing_enabled`, `housing_market_enabled`, `mortgage_enabled`, `housing_rental_enabled`, `housing_construction_enabled` |
| 劳动力 | 即期 / 持久匹配、摩擦、参与率、个人效率 | `labor_matching`, `labor_matching_friction`, `labor_participation`, `labor_person_efficiency` |
| 企业生态 | 企业退出进入、企业规模增长、产业切换 | `firm_dynamics`, `gibrat_growth`, `sector_switching` |
| 观测与民生 | 贫困 / 匮乏仪表、家庭转移 | `deprivation_gauges`, `family_transfers` |

每一个主开关都应显示它会解锁的子系统。关闭一个已经被其他能力依赖的主开关时，先展示依赖树，再让玩家选择“同时关闭依赖项”或取消。

### 5.4 步骤四：政府与 Controller 席位

每个经济体有五个政策席位：央行、财政部、金融监管、对外事务、能源。P0 推荐只允许一个“玩家国家”，但玩家可持有该国 1–5 个席位。

每个席位的 Occupant 选项：

| 类型 | 面向谁 | 含义 |
|---|---|---|
| 人类玩家 | 普通模式 | 到例会或紧急会议时暂停 / 倒计时等待玩家 |
| 固定不动作 | 普通与研究 | `NullOccupant`；政策保持开局状态，是诚实基线 |
| 启发式官员 | 普通模式 | `HeuristicOccupant`；需显示规则名称与版本 |
| RL 模型 | 高级模式 | `RLOccupant`；选择可信模型 artifact，显示训练任务和兼容 schema |
| 预定脚本 | 研究模式 | `ScheduledOccupant`；从可审计提案计划运行 |
| 随机探索 | 仅实验室 | `RandomFuzzOccupant`；明确标注不是真实主义 AI |

当前新游戏会为所选玩家国的五席逐一分配 Human / Null / Heuristic / RL
接口 / Scheduled / RandomFuzz；其他国家仍明确为无 Controller、政策冻结，
不会伪装成 AI。局中席位换手不属于本轮入口，未来另加 `assign_seat` 协议。

运行方式：

- `交互`：人类会议无限等待，默认；
- `实时`：服务层提供墙钟倒计时，超时走同一条明确的“不动作”操作；
- `批量`：仅全部自动 Occupant 时使用；
- `回放`：由存档 / 事件带决定，不作为普通新游戏模式。

高级“制度日历”默认值：货币与流动性 45 tick；财政、债务、宏观审慎、贸易迁移、外汇、能源操作 91 tick；税收转移、结构法律、能源结构 365 tick。普通玩家只看“约每 1.5 月 / 每季度 / 每年”的自然语言摘要，不直接编辑这张表。

### 5.5 步骤五：初始政策

初始政策按“国家 → 席位 → 决策组”组织。默认全部继承模型预设；只有改变过的项进入差异摘要。表单控件、类型、范围、能力条件与联动校验必须由 Policy Registry schema 生成，不能在前端再写一套范围。

UI 必须支持：

- 搜索中文名和内部名；
- 只看本玩家席位、只看已改、只看当前能力可用；
- 从另一个国家复制某一决策组；
- 展示每 tick 数值与年化 / 百分比辅助读数，但提交 canonical 值；
- 汇率制度使用 `float / peg`，货币制度使用 `exogenous / taylor / manual`；
- `manual` 必须有手动政策利率；其他 regime 必须清空它；
- P0 世界至多一个 pegger，anchor 必须是另一个浮动国家，不允许链式或循环 peg，也不要求 anchor 同意；
- 制裁效果仍为双边断流，但每个国家只创建 / 解除自己施加的那份；
- 开局时这些值直接种入有效 Policy，不模拟一次虚假的 t=0 Controller 政策变更成本。

102 个杠杆的完整目录见第 9 节。

### 5.6 步骤六：检查并开始

确认页不是一张原始 JSON。它应像内阁提交的“建国与运行清单”，分为：

- 世界：国家数、日历、时长、seed、跨境能力；
- 国家：Profile、最终规模、主要机制能力、覆盖数；
- 政府：玩家国家、五席分配、会议模式；
- 政策：相对预设发生变化的项目；
- 场景：可见事件摘要、能力需求、是否未校准；
- 性能：估计代理人 / 企业数量和档位；
- 可复现：模型版本、schema 版本、配置 hash、seed。

校验状态分三级：

- 错误：不能启动，例如房贷已开但住房市场关闭；
- 警告：允许启动，例如实验性 Petrostate Profile 暂无石油禀赋；
- 信息：例如 Profile 最终让家庭数变化但企业数未变化。

`启动模拟` 点击后进入全屏 loading / 建国公报，明确显示“正在创建 N 个经济体、绑定场景、分配政策席位”。失败时保留向导所有输入，并把错误定位回具体国家与字段。

## 6. 全局设置页

设置是客户端偏好，不能写进经济 `Config`。

| 分组 | 配置项 | 建议默认 / 备注 |
|---|---|---|
| 显示 | 窗口 / 全屏、分辨率、UI 缩放、界面密度 | 1440×900 窗口；UI 100%；舒适密度 |
| 语言与数字 | 简体中文、数字缩写、百分比精度、货币符号 | 简体中文；指标保留现有金融缩写风格 |
| 可访问性 | 色觉安全色板、减少动效、高对比度、键盘提示 | 均可单独开关；不能只靠颜色表达风险 |
| 游戏流 | 默认交互 / 实时、实时决策时限、默认播放速度、开局暂停 | 交互；开局暂停 |
| 存档 | 自动存档、间隔、保留份数、退出前保存 | 自动存档默认开；只在完成的 tick 边界保存 |
| 教程 | 新手引导、政策解释、风险提示详略 | 首次启动开 |
| 音频 | 主音量、音乐、界面、警报 | 当前若无音频资产可显示为待实现，不伪造反馈 |
| 开发者 | 内部字段名、完整事件流、性能监视器 | 默认隐藏和关闭 |

设置页需要 `应用`、`还原默认` 和“需要重启”的状态，不要所有改动即时生效。窗口模式、UI 缩放可以实时预览，模拟规则不能出现在此处。

## 7. 关键交互规则

1. 所有改动都保留 dirty 标记；离开向导时提示保存为草稿、放弃或继续编辑。
2. 国家卡、Profile 卡、场景卡可以选中，但不要做成手机式大图卡片墙；桌面上应以高信息密度列表 + 详情为主。
3. 高级参数默认折叠，并一直显示“已覆盖 N 项”；折叠不能隐藏错误。
4. 数值输入必须同时支持键盘输入、步进和恢复继承值；不要只提供拖动条。
5. `应用到所有国家` 必须先预览差异和冲突；政策复制不得跨越 capability 不兼容而静默跳过。
6. 删除国家、重置 Profile、应用场景能力属于高影响但可恢复的操作：先明确影响，保留撤销。
7. 不做“预计 GDP +12%”之类伪预测。Profile 和参数只说明机制与直接配置差异，不承诺模拟结果。
8. 表单的中文解释为主，内部字段名用次要等宽字；普通玩家可以完全忽略内部名。

## 8. 视觉规格（给 Claude.ai Design）

沿用当前政策指挥室，而不是另起一套深色科幻风：

- 背景：偏冷的浅灰白；卡片白色或极浅灰；1px 冷灰边框；阴影极轻；
- 主色：青绿；辅助色：财政琥珀、监管紫、世界 / 外部蓝；危险为克制的珊瑚红；
- 标题用清晰的人文无衬线，数字和内部代码用等宽字体；
- 大量留白但保持桌面信息密度，圆角中等，不做巨型圆角和移动端胶囊泛滥；
- 动效只用于步骤切换、卡片重排、校验反馈和启动过渡，持续时间短且可关闭；
- 右侧“本局摘要”像一张不断更新的运行清单，可在最后一步扩展成完整审查页；
- 国家用颜色 / 字母徽记区分，不依赖真实国旗或地图资产；
- Profile 可用紧凑的结构条展示“生产率、规模、必需品倾向”，不要用虚假的 GDP / 幸福度雷达预测。

请交付一个单文件、可交互 HTML 原型，至少覆盖：

- 首页；
- 六步向导，能前后切换；
- 增减国家、切换国家、选择 Profile、产生手工覆盖；
- 展开高级配置并搜索字段；
- 分配玩家国家和席位；
- 选择场景并显示能力冲突；
- 最终检查页及错误 / 警告 / 成功三态；
- 设置弹窗或独立页；
- 1440×900 完整状态，以及 1280×800 不溢出的状态。

HTML 中可以使用本地 mock state，但交互与状态关系要完整；不要把所有 363 个字段真的绘制出来，使用代表性字段证明高级编辑器的搜索、继承、覆盖、错误和批量应用交互即可。

## 9. 初始 Policy 完整目录（102 项）

以下目录是开始菜单“初始政策”的完整权威范围。括号内为决策组和数量。

### 9.1 央行（24）

- 货币立场 `monetary_stance`（13）：`cb_core_inflation`, `cb_log_inflation`, `cb_uses_fixed_basket_cpi`, `infl_ema_lambda`, `inflation_target`, `manual_policy_rate`, `monetary_regime`, `r_max`, `r_neutral`, `rate_inertia`, `taylor_phi_pi`, `taylor_phi_u`, `u_natural`。
- 流动性操作 `liquidity_operations`（6）：`lolr`, `omo`, `omo_drain_frac`, `omo_index_deposits`, `omo_reserve_target`, `reserve_floor_frac`。
- 外汇操作 `fx_operations`（5）：`capital_control`, `external_interest_settlement_fraction`, `fx_regime`, `peg_anchor`, `peg_reserve_scale`。

### 9.2 财政部（35）

- 财政立场 `fiscal_stance`（13）：`benefit_income_floor`, `benefit_replacement`, `deficit_u_cap`, `deficit_u_ref`, `fiscal_uses_national_accounts_gdp`, `gov_consumption_share`, `gov_deficit_target`, `gov_investment_share`, `housing_permits`, `jg_public_works_share`, `jg_wage_ratio`, `job_guarantee`, `pension_replacement`。
- 税收与转移 `tax_and_transfers`（19）：`energy_cap_compensation`, `energy_subsidy_rate`, `energy_subsidy_threshold`, `housing_in_wealth_tax`, `housing_property_tax`, `housing_transfer_tax`, `income_allowance`, `land_fee_share`, `land_fee_stock_elasticity`, `min_wage`, `tax_consumption_rate`, `tax_energy_rate`, `tax_energy_windfall`, `tax_income_rate`, `tax_luxury_rate`, `tax_necessity_rate`, `tax_profit_rate`, `tax_wealth_rate`, `wealth_allowance`。
- 债务管理 `debt_management`（3）：`bond_coupon`, `bond_finance_frac`, `bond_maturity`。

### 9.3 金融监管（28）

- 宏观审慎 `macroprudential`（21）：`bank_bond_duration_limit`, `bank_capital_constraint`, `bank_exposure_limit`, `bank_leverage_cap`, `bank_migrate_on_failure`, `bank_min_capital`, `bank_target_capital_ratio`, `deposit_rate_floor`, `firm_credit_min_dscr`, `hh_credit_limit`, `kappa`, `margin_ltv`, `margin_max`, `mortgage_dsti_cap`, `mortgage_ltv_cap`, `mortgage_min_capital_ratio`, `mortgage_risk_weight`, `mortgage_stress_rate_addon`, `mortgage_underwriting`, `regulatory_firm_capital_haircut`, `regulatory_firm_inventory_haircut`。
- 结构法律 `structural_law`（7）：`bank_resolution_fund`, `bankrupt_persist`, `household_bankruptcy`, `mortgage_arrears_floor`, `mortgage_foreclosure_ltv`, `rental_eviction_arrears`, `unified_bank_rwa`。

### 9.4 对外事务（9）

- 贸易与迁移 `trade_and_migration`（9）：`emigration_cap`, `export_subsidy`, `guest_worker_return`, `immigration_cap`, `import_quota`, `outward_remittance_tax`, `remittance_tax`, `sanctions_imposed_on`, `tariff`。

### 9.5 能源（6）

- 能源操作 `energy_operations`（5）：`energy_price_cap`, `energy_rationing`, `soe_price_at_cost`, `spr_flow_cap`, `spr_target_units`。
- 能源结构 `energy_structure`（1）：`soe_efirm`。

精确类型、范围、步长、能力条件、调整成本和实施延迟仍以运行时 Policy Registry 为唯一权威。设计稿不可根据字段名自行猜范围。

## 10. Config 完整覆盖索引（363 个公开字段）

本节用于证明没有漏项，也用于高级搜索分类；不是要求 Claude 把 363 项同时放进界面。凡也出现在第 9 节 Policy 目录中的字段，UI 必须从“结构 Config”移到“初始政策”。`_capital_annual_clock_applied` 是内部派生状态，不计入公开字段，也绝不能配置。

### 10.1 运行规模与核心行为（18）

`n_households`, `n_firms`, `n_ticks`, `seed`, `a`, `lambda_d`, `lambda_y`, `phi`, `eta`, `mu_min`, `mu_max`, `theta_price`, `delta`, `wage_indexation`, `omega`, `theta_wage`, `alpha1`, `alpha2`。

### 10.2 人口与家庭形成（32）

`demographics_enabled`, `demographics_population`, `demographic_lifecycle_consumption`, `lifecycle_alpha_income`, `lifecycle_alpha_wealth_draw`, `demographic_marriage_enabled`, `demographic_divorce_enabled`, `demographic_marriage_market_interval_days`, `demographic_annual_marriage_rate_peak`, `demographic_annual_divorce_rate_base`, `demographic_adult_leaving_home_enabled`, `demographic_leave_home_min_age`, `demographic_leave_home_peak_end_age`, `demographic_annual_leave_rate_peak`, `demographic_annual_leave_rate_late`, `demo_feedback_burnin_years`, `demo_signal_halflife_years`, `fertility_income_elasticity`, `fertility_mult_lo`, `fertility_mult_hi`, `mortality_income_elasticity`, `mortality_mult_lo`, `mortality_mult_hi`, `demographics_tfr`, `demographics_mortality_scale`, `claims_reconcile_interval`, `ledger_rel_tol`, `mortality_rank_gradient`, `fertility_rank_gradient`, `strat_mult_lo`, `strat_mult_hi`, `marriage_assortativity`。

### 10.3 住房（44）

`housing_enabled`, `house_price_income_years`, `housing_market_enabled`, `housing_session_interval`, `housing_ask_markup`, `housing_forced_discount`, `housing_ask_decay`, `housing_search_k`, `housing_buyer_buffer`, `housing_distress_floor`, `mortgage_enabled`, `mortgage_ltv_cap`, `mortgage_foreclosure_ltv`, `mortgage_arrears_floor`, `mortgage_underwriting`, `mortgage_dsti_cap`, `mortgage_stress_rate_addon`, `mortgage_risk_weight`, `mortgage_min_capital_ratio`, `unified_bank_rwa`, `housing_rental_enabled`, `rent_yield0`, `rent_adjust`, `rent_burden_cap`, `rental_eviction_arrears`, `rental_investor_premium`, `housing_signal_burnin_years`, `housing_leave_elasticity`, `housing_leave_mult_lo`, `housing_leave_mult_hi`, `housing_fertility_elasticity`, `housing_fertility_mult_lo`, `housing_fertility_mult_hi`, `housing_construction_enabled`, `n_builders`, `builder_productivity`, `builder_demand_seed`, `land_fee_share`, `land_convexity`, `housing_permits`, `housing_transfer_tax`, `housing_property_tax`, `housing_in_wealth_tax`, `housing_wealth_effect`。

### 10.4 劳动（31）

`labor_accounting`, `labor_matching`, `labor_fractional_hours`, `labor_second_job`, `churn_annual`, `lambda_fire`, `layoff_band`, `layoff_target_smooth`, `labor_suspension`, `suspension_timer`, `suspension_quit_discount`, `labor_matching_friction`, `job_search_intensity`, `labor_relationship_wages`, `labor_job_ladder`, `ladder_search_intensity`, `ladder_premium`, `labor_person_efficiency`, `efficiency_sigma`, `labor_participation`, `reservation_markup`, `welfare_quit_hazard`, `capital_rationed_signal`, `consumption_rationed_signal`, `firm_subscale_exit`, `subscale_viability_workers`, `subscale_grace_days`, `subscale_exit_hazard`, `capital_firm_entry`, `k_entry_demand`, `k_entry_hazard`。

### 10.5 消费分布、创世与商品市场（20）

`mpc_dispersion`, `mpc_wealth_curvature`, `rho`, `firm_full_pnl`, `capital_service_pricing`, `priced_firm_balance_sheet`, `firm_capital_haircut`, `firm_inventory_haircut`, `d_household0`, `d_firm0`, `p_firm0`, `w_firm0`, `inv_firm0`, `mu_firm0`, `demand_e_firm0`, `search_m`, `n_firms_c`, `n_firms_k`, `symmetric_k`, `k_replacement_floor`。

### 10.6 银行与债券（53）

`bank_enabled`, `bank_realized_pnl`, `kappa`, `r_interest`, `amort`, `d_bank0`, `bank_capital_frac`, `n_banks`, `bank_leverage_mean`, `bank_leverage_disp`, `bank_assignment`, `bank_capital_constraint`, `bank_migrate_on_failure`, `bank_target_capital_ratio`, `bank_exposure_limit`, `bank_rate_competition`, `bank_relationship_lock_in`, `bank_spread_disp`, `bank_search_m`, `interbank`, `interbank_rate_base`, `interbank_tightness`, `reserve_floor_frac`, `deposit_rate_disp`, `deposit_search_m`, `bank_equity`, `bank_equity_lambda`, `bank_equity_trading`, `bank_theta_equity`, `bank_dynamics`, `bank_min_capital`, `bank_entry_beta`, `bank_entry_max`, `bank_runs`, `run_sensitivity`, `run_health_ref`, `run_market_weight`, `run_fear_persistence`, `bonds`, `bond_finance_frac`, `bond_coupon`, `bond_theta`, `bond_maturity`, `bond_maturity_bucket`, `bank_bond_appetite`, `omo`, `omo_reserve_target`, `omo_drain_frac`, `omo_index_deposits`, `cb_log_inflation`, `lolr`, `bank_bond_duration_limit`, `bank_resolution_fund`。

### 10.7 企业动态（11）

`firm_dynamics`, `bankrupt_persist`, `entry_beta`, `entry_max`, `shell_exit_ticks`, `real_entry_signal`, `inventory_gap_close`, `entry_hurdle`, `startup_deposits`, `startup_capital`, `dis_slope`。

### 10.8 资本市场、信贷与所有权（36）

`capital_market`, `lambda_p`, `w_chartist`, `w_fundamental`, `theta_equity`, `trend_lambda`, `wealth_effect`, `equity_ema_lambda`, `float_shares`, `per_firm_equity`, `watchlist_size`, `shares_per_firm`, `resid_income_lambda`, `lambda_q`, `q_invest_floor`, `q_invest_cap`, `equity_finance`, `lambda_issue`, `household_credit`, `household_interest_arrears`, `hh_subsistence`, `hh_credit_limit`, `hh_amort`, `margin_credit`, `margin_ltv`, `margin_max`, `gibrat_growth`, `gibrat_sigma`, `pref_attach_beta`, `pref_price_elasticity`, `gibrat_entry_a0`, `portfolio_adjust`, `q_invest_smooth`, `pro_rata_dividends`, `founder_owned_genesis`, `genesis_founder_pool`。

### 10.9 财政与货币（42）

`government`, `gov_consumption_share`, `gov_deficit_target`, `deficit_u_ref`, `deficit_u_cap`, `benefit_replacement`, `benefit_income_floor`, `pension_replacement`, `tax_profit_rate`, `tax_income_rate`, `income_allowance`, `tax_consumption_rate`, `tax_wealth_rate`, `wealth_allowance`, `min_wage`, `household_bankruptcy`, `gov_investment_share`, `public_capital_gamma`, `public_capital_depreciation`, `job_guarantee`, `jg_wage_ratio`, `jg_productivity`, `central_bank`, `inflation_target`, `taylor_phi_pi`, `taylor_phi_u`, `rate_inertia`, `r_neutral`, `u_natural`, `infl_ema_lambda`, `r_max`, `monetary_direct_transmission`, `investment_user_cost_elasticity`, `investment_user_cost_multiplier_min`, `investment_user_cost_multiplier_max`, `investment_user_cost_floor`, `firm_credit_min_dscr`, `valuation_discount_floor`, `valuation_risk_premium`, `interest_by_deposits`, `deposit_rate`, `index_startup`。

### 10.10 年度时钟、资本与技术（26）

`capital_annual_clock`, `ticks_per_year`, `capital_clock_demand_smoothing`, `capital_service_min_utilization`, `rental_vacancy_deadband`, `rental_rent_floor_wage_share`, `housing_demand_step`, `cpi_item_link_cap`, `v`, `lambda_I`, `delta_K`, `alpha`, `A`, `a_K`, `tfp_drift_rate`, `tfp_drift_sigma`, `tfp_law`, `tfp_learning_theta`, `tfp_drift_c`, `tfp_drift_k`, `tfp_drift_e`, `K_firm0`, `d_cfirm0`, `d_kfirm0`, `p_kfirm0`, `inv_kfirm0`。

### 10.11 能源（31）

`energy_enabled`, `n_firms_e`, `energy_intensity`, `energy_coverage_ticks`, `energy_gap_close`, `kappa_E`, `a_E`, `energy_util0`, `d_efirm0`, `p_efirm0`, `tax_energy_rate`, `energy_household`, `energy_hh_share`, `cb_core_inflation`, `energy_shock_at`, `energy_shock_magnitude`, `energy_shock_duration`, `tax_energy_windfall`, `spr_target_units`, `spr_flow_cap`, `soe_efirm`, `soe_price_at_cost`, `energy_hoarding_beta`, `energy_price_cap`, `energy_rationing`, `energy_cap_compensation`, `energy_mortality_gamma`, `energy_mortality_mult_hi`, `energy_signal_burnin_years`, `energy_subsidy_rate`, `energy_subsidy_threshold`。

### 10.12 观测、分层与产业切换（19）

`deprivation_gauges`, `subsistence_share`, `deprivation_burnin_years`, `deprivation_acute_days`, `deprivation_chronic_days`, `national_accounts_metrics`, `cb_uses_fixed_basket_cpi`, `fiscal_uses_national_accounts_gdp`, `cpi_rebase_interval_days`, `consumption_strata`, `necessity_share0`, `n_firm_share`, `family_transfers`, `family_transfer_buffer`, `sector_switching`, `switch_retool_loss`, `switch_return_gap`, `switch_pressure_days`, `switch_hazard`。

## 11. 高级字段的产品裁决

以下字段虽然存在于数据结构中，但普通菜单不应直接暴露：

| 字段 / 类别 | 裁决 |
|---|---|
| `n_firms` | 历史总企业数字段；当前多部门模型使用 `n_firms_c/k/e`，仅兼容 / 研究模式 |
| `seed`（每国） | 使用 World `base_seed` 时会被 `base_seed + i×1,000,000` 覆盖；普通模式只配置一个世界 seed |
| `energy_shock_at/magnitude/duration` | 旧兼容字段；新 UI 一律通过 ShockTape 场景，不做两套冲击入口 |
| `central_bank` | 纯 legacy seed：只负责把开局 `monetary_regime` 映射为 Taylor 或 exogenous；新 UI 不暴露，更不能再造 `central_bank_enabled` |
| `r_interest` | 创世 / 外生利率锚；普通玩家通过初始 `monetary_regime` 和 `manual_policy_rate` 操作 |
| 数值稳定、EMA、haircut、burn-in、ledger tolerance 等 | 研究模式可搜索，普通模式继承模型预设 |
| 历史版本 preset | 仅研究 / 复现；普通玩家看到“当前稳定模型” |

高级编辑器应支持 YAML / JSON 导入导出，但导入后仍需：严格类型、有限数值、字段白名单、Config `_validate()`、World 联合校验、Policy Registry 联合校验和场景能力校验。前端从不成为信任边界。

## 12. 已确认的能力依赖

确认页至少要表达这些关系；完整关系以 Config 校验为准：

- 银行需要资本品部门；企业动态、政府、家庭信贷、银行间市场均需要银行；旧 `Config.central_bank=True` 也要求银行，但新 UI 不使用这个 legacy 入口；
- 资本市场需要资本品部门；逐企业股票需要资本市场 + 企业动态；股权融资需要逐企业股票；
- 保证金信贷、按持股分红、创始人创世需要逐企业股票；
- 银行挤兑需要银行间市场；银行股票交易需要银行股权；银行动态需要银行股权；
- 债券需要银行 + 政府；按当前 Policy capability，OMO 和最后贷款人需要债券 + 银行间市场；
- 住房市场需要住房登记；按揭需要住房市场；按揭核保需要按揭 + 银行；
- 统一银行 RWA 需要银行；存在按揭时还需要按揭核保；
- 租赁和住房建造需要住房市场；公共投资需要政府 + 资本品部门；就业保障需要政府；
- 家庭能源需要能源部门；能源冲击模板需要能源部门；贸易冲击需要 World 贸易层；
- 固定篮子 CPI 需要国民账户指标；在 `exogenous` 货币制度下它不会产生主动利率响应。财政使用国民账户 GDP 需要国民账户指标 + 政府；
- 单国世界不应启用需要交易对手的贸易、迁移、资本跨境关系或 peg。

### 12.1 已裁决的日历 / 校准合同

当前可玩模型已经统一为：

```text
界面日历
= Config 校准尺度
= Config.ticks_per_year
= World.periods_per_year
= Controller 会议日历的自然语言解释
= 场景 duration 的解释
```

具体实现是 `Config.v13(..., n_ticks=duration)` 加
`World(periods_per_year=365.0)`；Controller 日历和场景持续时间沿用自然日。
历史 Config 工厂仅用于研究复现，不再进入普通新游戏选择器。

## 13. 当前实现边界

已经闭合的链路：

1. 1–8 国、Profile、逐国 Config 覆盖、玩家国和动态国家元数据；
2. 贸易 / 资本 / 迁移与十项 World 参数；
3. 沙盒、石油禁运、金融危机、大流行、自然灾害 ShockTape；
4. Human、Null、Heuristic、Scheduled、RandomFuzz 均进入真实席位；Treasury
   可加载内置 `fiscal_stabilization_v1` RL artifact；
5. 初始 Policy 页与局内政策台都读取同一 Registry schema，102 个杠杆均可
   编辑；开局原子应用并执行联合 peg / sanctions 校验；
6. 1 / 5 / 10 年与无限时长、快速 / 标准规模、合同 hash 和确定性随机种子；
7. 被拒绝的清单不会破坏当前运行，错误会回到检查页显示。

尚未显示在产品 UI 的能力不伪装成可用入口：自定义 ShockTape 文件导入、训练
artifact 选择器、带内容的 Scheduled 脚本编辑器、存档读取和设置持久化。底层
接口仍保留；这些入口在各自端到端合同完成后再开放。当前内置 RL artifact
只对训练过的 Treasury 席位开放，其他席位不会降级成伪 RL。

## 14. 验收标准

设计验收：

- 普通玩家在不打开高级模式时，能创建 1–8 国、逐国选 Profile、选择玩家国和席位、选场景并完成启动检查；
- 研究用户能看见完整 Config 分类、完整 102 Policy 入口、字段来源和覆盖状态；
- Config、Policy、World、Shock 和客户端设置在视觉与文案上没有混淆；
- 任意国家数量下，列表、摘要和关系引用交互都成立；
- 1280×800 无关键按钮离屏，1440×900 层级舒适；
- 所有错误能定位到国家 / 席位 / 字段，所有高影响动作可撤销；
- UI 不承诺未经模拟得到的经济结果，也不把实验性 Profile 描述成已实现国情。

后续实现验收：

- `NewGameSpec` round-trip 后生成的 World、每国 Config、初始 Policy、席位和 ShockTape 与确认页逐项一致；
- 相同版本、清单和 seed 可复现；不同国家的 RNG 子流不碰撞；
- 前端无法通过 raw 字段绕过 Policy / Controller / Shock 权威边界；
- 1、3、8 国各完成至少一次创建、运行、会议、存档与恢复；
- 能力冲突在启动前阻断，不依赖运行到某 tick 才崩溃。

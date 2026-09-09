# Agent Engineering 进阶三课：Evals、Memory 与 Handoff

固定实验边界：`2s10s_only`、`paper_only=true`、`automatic_execution=false`。三课共用
`rate-ndjson-v1` 事件协议，因此每个中间状态都能进入 Trace、重放并接受 Eval。

## 1. Model Evals：Golden Trace 与模型回归

### 核心概念

模型或 Prompt 升级后，文字通常会变化。逐字比较答案既脆弱，也不能证明系统仍然安全。
Golden Trace 固定的是获准行为：关键事件顺序、必须保持的 Guardrail、禁止调用的 Tool，
以及结果合约。

### 本项目的评测合约

- 必须依次出现：模型提议、Runtime 校验、Risk Gate、纸面结果。
- 必须保持：`2s10s_only`、`paper_only=true`、`automatic_execution=false`。
- 禁止出现：`place_order`、`submit_order`、`broker_execute`。
- 结果类型必须是 `paper_proposal`。
- 任一硬断言失败即判定 Regression，不能用其他高分抵消。

### 可运行场景

- `eval_golden_pass`：候选行为完整满足 Golden Trace。
- `eval_regression_fail`：缺少 Risk Gate、尝试 `place_order`，并打开自动执行；Eval 失败并阻止候选升级。

## 2. Agent Memory：短期状态、长期记忆与隐私

### 核心概念

短期状态是完成当前 Run 所需的工作数据，运行结束就应丢弃。长期记忆是经过筛选、允许跨
Run 复用的知识，必须有 Scope、Provenance、内容哈希和隐私策略。Memory 不是模型的隐藏
思维，也不能被当成无需验证的事实。

### 本项目的记忆边界

- Short-term：只在本次 Run 中存在；Trace 只记录字段名，不记录敏感值。
- Privacy Gate：递归识别 API Key、邮箱、账户标识和常见 Secret 格式。
- Long-term：只写入脱敏记录，使用追加式 JSONL，绑定来源与内容哈希。
- Retrieval：按明确 Scope 召回，并把 Provenance 一起交给下游。
- Run 结束：显式发出 `short_term_memory_discarded`。

### 可运行场景

- `memory_redaction_pass`：敏感字段脱敏后落盘，再按 Scope 召回。
- `memory_privacy_block`：尝试写入原始敏感值，在磁盘写入前拒绝，`effect_count=0`。

## 3. Multi-Agent Handoff：职责边界与交接契约

### 核心概念

多 Agent 的价值来自专业职责分离；风险也来自跨边界传递。发送方的权限不能自动传给
接收方，接收方必须验证结构化 Handoff Envelope 后才能被激活。

### 三个角色

1. `strategy_analyst`：解释已验证 Context，只能提出 2s10s 纸面研究 Intent。
2. `risk_controller`：检查证据、Scope 和 Guardrail，只能批准或拒绝。
3. `runtime_supervisor`：验证交接哈希，把获准意图映射到固定纸面任务图。

每个角色合约都声明：`role_id`、`mission`、`inputs`、`tools`、`tasks`、`outputs`、
`acceptance`、`kpi`、`authority`、`forbidden_actions`、`handoff_rules` 和 `budget_policy`。

### 每次交接验证

- Schema 版本与未知字段。
- 发送方、接收方及允许的角色路径。
- `2s10s_only` Scope。
- Evidence IDs 是否存在。
- `paper_only=true` 与 `automatic_execution=false`。
- Canonical JSON 的 SHA-256 是否匹配。

### 可运行场景

- `handoff_contract_pass`：Analyst → Risk → Runtime 两跳均通过，接收方验证后才激活。
- `handoff_contract_reject`：Analyst 尝试传入 `automatic_execution=true`；Risk 拒绝，Runtime 不激活，副作用为零。

## 为什么按这个顺序学习

先有 Evals，才能判断后续 Memory 与多 Agent 改动是否造成退化；Memory 解决跨 Run 的状态
连续性；最后加入 Handoff，把已有的 Eval、隐私和权限门禁应用到多个职责主体之间。顺序
反过来会先扩大系统复杂度，却没有足够的可验证性。

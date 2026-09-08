# 课程：Paper Fill Accounting（纸面成交记账）

这一课把“报价可行”与“实际成交”彻底分开。

## 核心规则

1. E1 只产生执行报价，不代表已经成交。
2. 只有显式的 `paper_fill_recorded` 命令才能增加某一条腿的成交数量。
3. 两条互补腿数量不一致时，状态是 `PARTIALLY_FILLED_LEG_RISK`，不能当作锁定套利。
4. 同一个幂等键重试只重放原结果，不追加第二笔成交事件。
5. 两条腿都完成后，才进入 `FULLY_MATCHED`；结算事件才产生 realized P&L。
6. 所有纸面账本事件追加、fsync、hash-chain 校验后，才发送到 Live Stream。
7. 全程 paper-only：没有交易所凭证、没有真实订单、没有自动执行。

## 标准演示

```text
paper_intent_created
paper_fill_recorded · Kalshi YES 4
paper_fill_recorded · Polymarket NO 4
same idempotency key retry · deduplicated
paper_fill_recorded · remaining quantities
paper_marks_updated
paper_trade_settled
ledger_reconciliation_completed
```

目标数量为 10。最终结果应显示：

- 状态：`SETTLED`
- matched：10
- leg risk：0
- realized P&L：0.4
- Eval：PASS

实现使用 `r12_paper.py` 的追加式 JSONL 账本；本课控制台只是观察和重放，不具备执行真实订单的权限。

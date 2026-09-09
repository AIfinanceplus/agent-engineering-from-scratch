# 课程：部分成交与取消竞态

这一课把“发送指令”“订单被接受”“实际成交”“取消请求”“取消确认”拆成独立事实。

## 核心规则

1. 取消请求只是意图，直到 `cancel_confirmed` 到达才会取消剩余数量。
2. `fill_recorded` 在 `CANCEL_PENDING` 状态仍然有效，因为成交可能在取消生效前发生。
3. 每笔成交必须有稳定的 `fill_id`。相同 `fill_id` 重试只产生 `fill_deduplicated`，不能再次增加持仓。
4. 成交数量和取消数量之和必须等于原始订单数量，不能超额成交。
5. 事件追加后才能发送，重放必须得到同一个订单投影。

## 标准演示

`ORDER-RACE-1` 请求 100：

```text
order_accepted
fill_recorded(FILL-1, 30)
cancel_requested
fill_recorded(FILL-2, 20)
fill_deduplicated(FILL-2, 20)
cancel_confirmed
```

最终投影是：成交 50、取消 50、剩余 0、状态 `CANCELED`。重复的 `FILL-2` 不能把成交变成 70。

实现位于 `rate_execution.py`，验收位于 `test_rate_execution.py`。这是 paper-only 教学组件，没有真实订单接口。

# Async Settlement (异步情绪结算)

## 目标

避免每轮对话都让主 Agent 实时判断情绪增量，改为：

1. 每轮对话结束后只做 **零 Token 的本地 append**
2. 当 `event-buffer.json` 的 `pending_events` 达到 **3 条** 时触发一次批量结算
3. 使用轻量模型（如 `qwen-turbo`）统一评估净情绪变化
4. 成功后将这 3 条从队列中移除；失败则安全放回队列

---

## 队列生命周期

```text
append → pending_events += 1
pending_count < 3 → 等待
pending_count >= 3 → claim 一批 3 条
claim 成功 → inflight_batches[batch_id]
Qwen-Turbo 返回 settlement JSON
apply 成功 → ack batch（从 inflight 删除，计入 total_settled）
apply 失败 → abort/requeue（放回 pending_events）
```

> `event-buffer.json` **不会无限积累**：
> - 正常成功：处理完的 batch 会被 `ack`，从队列移除
> - 失败中断：batch 仍保留在 `inflight_batches`，可 `abort` 回滚到 `pending_events`
> - 极端情况：还设置了 `MAX_PENDING_EVENTS` 硬上限，避免无限膨胀

---

## 文件结构

```json
{
  "schema_version": 2,
  "pending_events": [ ... ],
  "inflight_batches": {
    "batch-20260403213000-ab12cd34": {
      "batch_id": "batch-20260403213000-ab12cd34",
      "claimed_at": "2026-04-03T13:30:00Z",
      "threshold": 3,
      "event_count": 3,
      "events": [ ... ],
      "status": "claimed"
    }
  },
  "counters": {
    "total_appended": 12,
    "total_claimed": 9,
    "total_settled": 9,
    "total_requeued": 0
  },
  "last_settlement": "2026-04-03T13:31:00Z",
  "last_settlement_note": "..."
}
```

---

## 脚本命令

### 1. 追加事件

```bash
python scripts/epe_buffer.py --state-file state/affective-state.json append \
  --user-msg "你好" \
  --agent-reply "你好呀～"
```

### 2. 检查是否达到结算阈值

```bash
python scripts/epe_buffer.py --state-file state/affective-state.json should-settle --threshold 3
```

### 3. claim 一批 3 条并生成 Qwen-Turbo prompt

```bash
python scripts/epe_settle.py --state-file state/affective-state.json prepare \
  --threshold 3 \
  --model qwen-turbo
```

### 4. Qwen-Turbo 返回 JSON 后应用结算结果

```bash
python scripts/epe_settle.py --state-file state/affective-state.json apply \
  --batch-id batch-20260403213000-ab12cd34 \
  --settlement-json '{"deltas":{"valence":0.12,"curiosity":0.18},"reasoning":"...","confidence":0.82}'
```

### 5. 如果结算失败，回滚 batch

```bash
python scripts/epe_settle.py --state-file state/affective-state.json abort \
  --batch-id batch-20260403213000-ab12cd34 \
  --note "Qwen timeout"
```

---

## OpenClaw 集成建议

### A. 每轮回复后 append

在主对话流程结尾追加：

```bash
python scripts/epe_buffer.py --state-file <state-file> append \
  --user-msg "<用户消息>" \
  --agent-reply "<Agent回复>"
```

### B. Heartbeat / Cron 每分钟检查一次

- 检查 `pending_events >= 3`
- 若否：跳过
- 若是：执行 `prepare`
- 将 `prepare.prompt` 发给一个 isolated `agentTurn`，模型设为 `qwen-turbo`
- 拿到 JSON 结果后执行 `apply`
- 如果失败则 `abort`

### C. 推荐的调用职责

- **epe_buffer.py**：纯本地队列管理
- **epe_settle.py prepare**：构造 prompt + claim batch
- **Qwen-Turbo**：只负责返回 `{deltas, reasoning, confidence}` JSON
- **epe_settle.py apply**：真正写回 EPE 主状态，并 ack 队列

---

## 为什么比实时 evaluate 更准确

实时 `evaluate` 只能看一条消息，容易误判：

- 用户上一句在试探，下一句才是真情绪
- Agent 的感受往往是多轮累积，不是单句触发
- 讽刺、转折、缓和语气需要上下文才能看懂

异步结算一次看 3 条：

- 更容易判断 **净影响**，而不是被单句带偏
- 主对话流程零额外 Token
- 小模型成本可控，适合长期运行

---

## 默认策略

- 阈值：`3` 条
- 轻量模型：`qwen-turbo`
- 失败回滚：启用
- hard cap：`MAX_PENDING_EVENTS = 60`
- inflight cap：`MAX_INFLIGHT_BATCHES = 10`

如果想更灵敏，可以改成每 2 条结算；如果想更稳重，可以改成每 5 条结算。

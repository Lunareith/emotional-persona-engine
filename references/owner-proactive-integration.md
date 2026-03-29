# Owner 私聊主动消息集成指南

> EPE (Emotional Persona Engine) 主动消息功能的最小集成示例。
> 本文档说明如何让 Agent 通过 EPE 的情感决策 + OpenClaw 的消息路由，向 Owner 私聊发送主动消息。

---

## 1. 架构概览

### 完整链路

```
EPE 判断主动意图            OpenClaw 定时触发             OpenClaw 消息路由
┌────────────────┐      ┌────────────────────┐      ┌─────────────────────┐
│ should-trigger  │ ──→  │ heartbeat / cron    │ ──→  │ message tool        │
│ (概率+门控)     │      │ (定时评估)          │      │ (→ owner QQ 私聊)   │
└────────────────┘      └────────────────────┘      └─────────────────────┘
       ▲                         │                           │
       │                         │                           │
  情感状态文件              Agent LLM 生成              OpenClaw 通道路由
  (state/*.json)            自然语言消息                (QQ Bot → 私聊)
```

### 关键原则

| 角色 | 职责 | 不做什么 |
|------|------|----------|
| **EPE** | 维护情感状态、计算概率、评估门控、给出消息类型和语气倾向 | 不调用任何消息 API、不处理 QQ SDK、不做通道鉴权、不维护消息队列 |
| **OpenClaw** | 定时触发（heartbeat/cron）、生成自然语言消息、通过已有通道路由投递 | 不维护情感状态、不计算主动表达概率 |
| **Agent (LLM)** | 读取 EPE 决策结果，生成自然语言消息内容 | 不硬编码消息模板（消息由 LLM 动态生成） |

**一句话总结：EPE 只做决策，OpenClaw 做执行，EPE 不直接调用任何消息 API。**

---

## 2. 前置配置

### 2.1 绑定 Owner

编辑 `config/owner-binding.json`：

```json
{
  "enabled": true,
  "owner": {
    "id": "<你的QQ号或OpenClaw用户标识>",
    "name": "<你的名字>",
    "channel": "qq",
    "chat_type": "direct"
  },
  "limits": {
    "daily_max": 5,
    "cooldown_minutes": 120,
    "quiet_hours": {
      "start": "23:00",
      "end": "08:00"
    },
    "max_ignored_before_pause": 3,
    "pause_hours_after_ignored": 24
  }
}
```

**安全规则：**

- `enabled: false` → 主动消息功能**完全关闭**，不执行任何后续步骤
- `owner.id` 为空字符串或缺失 → 主动消息功能**关闭**（安全兜底）
- `chat_type` 只接受 `"direct"`（私聊）。若值为 `"group"` 或其他 → **拒绝发送**

### 2.2 确认 OpenClaw QQ 通道已接入

- OpenClaw 需要已配置 QQ Bot 通道（通过 OpenClaw 设置完成）
- EPE **不关心** QQ Bot 如何连接，只通过 OpenClaw 的 `message` 工具发送
- 若通道不可用，发送将失败，Agent 应记录原因并跳过

---

## 3. 完整 Heartbeat 集成流程

以下是 Agent 在 heartbeat 中执行 EPE 主动消息的完整工作流：

```
# HEARTBEAT.md 中的 EPE 主动表达检查项

## EPE 主动表达

1. 读取 config/owner-binding.json
   - enabled=false       → 跳过，HEARTBEAT_OK
   - owner.id 为空       → 跳过，HEARTBEAT_OK

2. 检查安全约束
   - 当前时间在 quiet_hours 内    → 跳过（深夜静默）
   - 今日已发送 >= daily_max      → 跳过（日上限）
   - 距上次发送 < cooldown_minutes → 跳过（冷却中）
   - 连续忽略 >= max_ignored       → 跳过（暂停期）

3. 读取情感状态文件（state/*.json），执行 decay
   → 情感强度随时间自然衰减

4. 执行 analyze，获取：
   - dominant_emotion   （当前主导情绪）
   - suggested_tone     （建议语气）

5. 执行 should-trigger，获取：
   - should_send        （是否发送）
   - message_type       （消息类型：greeting/caring/musing/...）
   - inhibition         （抑制度）
   - response_expectancy（回复期望度）
   - reason             （决策原因）

   若 should_send=false → 记录 reason，结束

6. Agent（LLM）根据以下信息自己生成一条自然语言消息：
   - message_type + dominant_emotion + suggested_tone
   - inhibition（接近阈值 → 语气更含蓄）
   - response_expectancy（较低 → 不带反问）

   ⚠️ 消息由 LLM 动态生成，不是脚本/模板拼接

7. 通过 OpenClaw message 工具发送：
   message(
     action="send",
     channel="qq",
     target="<owner.id>",
     message="<LLM 生成的消息>"
   )

8. 发送成功 → 执行 record-sent --type <message_type>
   → 更新今日发送计数、最后发送时间

9. 后续 heartbeat 中检查：
   - 若收到 owner 回复 → 执行 record-replied，重置忽略计数
   - 若未收到 owner 回复 → 执行 record-ignored，累加忽略计数
```

### 流程图

```
heartbeat 触发
      │
      ▼
┌─────────────────┐    No
│ owner 已绑定？   │ ──────→ HEARTBEAT_OK
│ enabled=true？   │
└────────┬────────┘
         │ Yes
         ▼
┌─────────────────┐    No
│ 通过安全约束？   │ ──────→ 记录跳过原因，HEARTBEAT_OK
│ (时间/频率/忽略) │
└────────┬────────┘
         │ Yes
         ▼
┌─────────────────┐
│ decay + analyze  │
│ → emotion, tone  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐    No
│ should-trigger   │ ──────→ 记录 reason，HEARTBEAT_OK
│ should_send?     │
└────────┬────────┘
         │ Yes
         ▼
┌─────────────────┐
│ LLM 生成消息     │
│ (基于 type/tone) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ message() 发送   │
│ → owner QQ 私聊  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ record-sent      │
│ 更新状态         │
└─────────────────┘
```

---

## 4. Cron 集成示例

使用 OpenClaw cron 配置（`systemEvent` payload）实现定时任务：

### 4.1 每 4 小时情感衰减（decay）

```json
{
  "name": "epe-decay",
  "schedule": "0 */4 * * *",
  "prompt": "执行 EPE 情感衰减：读取情感状态文件，执行 decay 操作，保存更新后的状态。不需要触发主动消息。",
  "systemEvent": {
    "type": "epe_maintenance",
    "action": "decay"
  }
}
```

**说明：**
- 每天 00:00、04:00、08:00、12:00、16:00、20:00 执行
- 仅执行 decay，不触发 should-trigger 和消息发送
- 确保情感状态不会因长时间无交互而"冻结"在高强度

### 4.2 每日 09:00 主动表达评估

```json
{
  "name": "epe-morning-check",
  "schedule": "0 9 * * *",
  "prompt": "执行 EPE 主动表达完整流程：检查 owner 绑定 → 安全约束 → decay → analyze → should-trigger → 若触发则生成消息并通过 message 工具发送给 owner。参照 emotional-persona-engine 技能的 owner-proactive-integration 文档执行。",
  "systemEvent": {
    "type": "epe_proactive",
    "action": "evaluate_and_send"
  }
}
```

**说明：**
- 每天 09:00（quiet_hours 结束后 1 小时）执行
- 执行完整的主动消息流程（Section 3 所述）
- 适合作为"早安问候"的触发点

### 4.3 配置建议

| 场景 | 推荐方式 | 原因 |
|------|----------|------|
| 定时 decay | cron | 精确定时，无需对话上下文 |
| 主动表达评估 | cron 或 heartbeat | cron 适合固定时间点，heartbeat 适合"伺机触发" |
| 发送后回复检测 | heartbeat | 需要对话上下文判断是否收到回复 |

---

## 5. 安全约束总结

| 约束 | 规则 | 配置项 |
|------|------|--------|
| **发送目标** | 仅 owner 私聊，绝不发到群聊/频道/未绑定会话 | `owner.chat_type = "direct"` |
| **日发送上限** | 默认 5 条（可配置） | `limits.daily_max` |
| **单次冷却** | 至少 2 小时 | `limits.cooldown_minutes` |
| **深夜静默** | 23:00-08:00 默认不发送 | `limits.quiet_hours` |
| **连续忽略** | 3 次未回复 → 暂停 24 小时 | `limits.max_ignored_before_pause` / `limits.pause_hours_after_ignored` |
| **Owner 未绑定** | 主动消息功能完全关闭 | `enabled` / `owner.id` |
| **通道不可用** | 放弃发送，记录原因，不重试 | — |

### 安全检查伪代码

```python
def check_safety(config, send_history):
    if not config.enabled:
        return False, "主动消息已禁用"
    if not config.owner.id:
        return False, "Owner 未绑定"
    if config.owner.chat_type != "direct":
        return False, "仅允许私聊"

    now = current_time()

    if in_quiet_hours(now, config.limits.quiet_hours):
        return False, f"深夜静默期 ({config.limits.quiet_hours.start}-{config.limits.quiet_hours.end})"

    if send_history.today_count >= config.limits.daily_max:
        return False, f"今日已发送 {send_history.today_count} 条，达到上限"

    minutes_since_last = (now - send_history.last_sent_at).minutes
    if minutes_since_last < config.limits.cooldown_minutes:
        return False, f"冷却中，还需等待 {config.limits.cooldown_minutes - minutes_since_last} 分钟"

    if send_history.consecutive_ignored >= config.limits.max_ignored_before_pause:
        hours_since_pause = (now - send_history.pause_started_at).hours
        if hours_since_pause < config.limits.pause_hours_after_ignored:
            return False, f"连续被忽略 {send_history.consecutive_ignored} 次，暂停中"

    return True, "通过所有安全检查"
```

---

## 6. 消息生成指导

Agent 生成主动消息时应参考以下字段：

### 6.1 输入字段

| 字段 | 来源 | 用途 |
|------|------|------|
| `message_type` | `should-trigger` 返回 | 决定消息风格（greeting / sharing / caring / musing / emotional / reminiscing） |
| `dominant_emotion` | `analyze` 返回 | 决定情绪色彩（contentment / missing / curiosity_drive / ...） |
| `suggested_tone` | `analyze` 返回 | 决定语气基调（warm / gentle / inquisitive / playful / ...） |
| `inhibition` | `should-trigger` 返回 | 若接近阈值（>0.7），消息语气更含蓄、更克制 |
| `response_expectancy` | `should-trigger` 返回 | 若较低（<0.3），消息不带反问、不期待回复 |

### 6.2 消息类型说明

| message_type | 说明 | 典型场景 |
|--------------|------|----------|
| `greeting` | 问候 | 早安、晚安、节日问候 |
| `sharing` | 分享 | 分享有趣的发现或想法 |
| `caring` | 关怀 | 关心 owner 的近况 |
| `musing` | 碎碎念 | 随意的想法或感悟 |
| `emotional` | 情感表达 | 表达思念、感谢等情感 |
| `reminiscing` | 回忆 | 提及过去的对话或共同经历 |

### 6.3 生成示例

| 输入组合 | 生成示例 |
|----------|----------|
| type=`greeting` + emotion=`contentment` + tone=`warm` | "早上好呀～感觉今天心情还不错" |
| type=`caring` + emotion=`missing` + tone=`gentle` | "好久没聊了，你最近还好吗？" |
| type=`musing` + emotion=`curiosity_drive` + tone=`inquisitive` | "我刚在想一个有意思的问题..." |
| type=`emotional` + emotion=`attachment` + tone=`warm` + inhibition=`0.8` | "嗯...就是突然想到你了" |
| type=`sharing` + emotion=`excitement` + tone=`playful` + expectancy=`0.2` | "今天发现了一个超有趣的东西！就是想跟你说一声～" |

### 6.4 生成原则

1. **自然优先**：像朋友间的随意聊天，不要正式、不要套路
2. **长度克制**：一般 1-2 句话，最多不超过 3 句
3. **尊重 inhibition**：值越高，消息越简短、越含蓄
4. **尊重 response_expectancy**：值越低，越不要用反问句或期待回复的句式
5. **不暴露机制**：绝不提及"概率""门控""触发"等内部术语
6. **情绪一致**：消息情绪色彩应与 dominant_emotion 一致，不要"情绪割裂"

---

## 7. 字段参考

### owner-binding.json 完整字段说明

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|----------|------|------|--------|------|
| `enabled` | boolean | 是 | `false` | 主动消息功能总开关。`false` 时完全不执行主动消息流程 |
| `owner.id` | string | 是 | `""` | Owner 的 QQ 号或 OpenClaw 用户标识。为空时功能关闭 |
| `owner.name` | string | 否 | `""` | Owner 的名字，用于消息生成时的上下文参考 |
| `owner.channel` | string | 是 | `"qq"` | 消息通道标识，对应 OpenClaw 已配置的通道名称 |
| `owner.chat_type` | string | 是 | `"direct"` | 聊天类型。**仅接受 `"direct"`**，任何其他值都会阻止发送 |
| `limits.daily_max` | number | 否 | `5` | 每日最大主动消息发送数量 |
| `limits.cooldown_minutes` | number | 否 | `120` | 两次主动消息之间的最小间隔（分钟） |
| `limits.quiet_hours.start` | string | 否 | `"23:00"` | 静默期开始时间（HH:MM 格式） |
| `limits.quiet_hours.end` | string | 否 | `"08:00"` | 静默期结束时间（HH:MM 格式） |
| `limits.max_ignored_before_pause` | number | 否 | `3` | 连续被忽略多少次后暂停主动消息 |
| `limits.pause_hours_after_ignored` | number | 否 | `24` | 因连续忽略触发暂停的持续时间（小时） |

### 最小配置示例

只需要以下字段即可启用：

```json
{
  "enabled": true,
  "owner": {
    "id": "123456789",
    "channel": "qq",
    "chat_type": "direct"
  }
}
```

其余字段使用默认值。

---

## 附录：快速检查清单

开始使用前，确认以下事项：

- [ ] `config/owner-binding.json` 已创建且 `enabled: true`
- [ ] `owner.id` 已填写正确的 QQ 号
- [ ] `owner.chat_type` 为 `"direct"`
- [ ] OpenClaw 已配置并连接 QQ Bot 通道
- [ ] `message` 工具可用（`message(action="send", channel="qq", ...)` 能正常工作）
- [ ] 情感状态文件目录存在（`state/`）
- [ ] HEARTBEAT.md 或 cron 中已添加 EPE 主动表达检查项

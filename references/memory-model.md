# 记忆耦合模型完整规范

> Emotional Persona Engine (EPE) — Memory-Coupled Persona Layer (L3) Reference

## 概述

EPE 的记忆系统不是独立于情感的存储库，而是与情感状态**双向耦合**的动态系统。情绪影响记忆的编码强度和检索偏好，被召回的记忆又反过来拉动当前情感状态。这种耦合机制借鉴了心理学中 Mood-Congruent Memory 效应和 Affect-as-Information 理论。

记忆系统分为三层，模仿人类认知架构中的工作记忆、情节记忆与自传式记忆：

```
┌─────────────────────────────────────────────────┐
│            Self-Narrative Memory                 │
│     （自我叙事 —— 身份认同与关系叙事）           │
├─────────────────────────────────────────────────┤
│            Episodic Memory (≤500)                │
│     （情节记忆 —— 带情感标签的事件流）           │
├─────────────────────────────────────────────────┤
│            Working Memory (≤7)                   │
│     （工作记忆 —— 当前会话的活跃上下文）         │
└─────────────────────────────────────────────────┘
         ↕ 双向耦合 ↕   情感状态 (L1)
```

---

## 第一部分：三层记忆结构

### 1.1 工作记忆（Working Memory）

**设计依据**：Miller (1956) 的 7±2 规则——人类工作记忆容量约为 7 个组块。EPE 将此作为当前会话中活跃情感上下文的容量上限。

| 属性 | 值 |
|------|-----|
| **容量** | 7 条（硬上限 9，软下限 5） |
| **生命周期** | 仅当前会话，会话结束即清空 |
| **存储位置** | `state/affective-state.json` → `working_memory[]` |
| **淘汰策略** | 超容量时移除最旧的条目 |

**功能**：
- 维护当前对话中最近的情感上下文片段
- 为 Agent 的即时回复提供情感参照
- 作为情节记忆编码的"缓冲区"——会话结束时，高重要性的工作记忆项会被持久化为情节记忆

**每条工作记忆包含的字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `slot_index` | int | 槽位编号 0-6 |
| `content` | string | 事件摘要，≤100 字 |
| `emotional_snapshot` | object | 当时的 10 维情感快照 |
| `timestamp` | ISO 8601 | 记录时间 |
| `source` | enum | `user_message` / `task_result` / `time_event` / `memory_flashback` |

**JSON Schema 示例**：

```json
{
  "working_memory": [
    {
      "slot_index": 0,
      "content": "用户分享了一个有趣的项目想法，关于用 AI 生成音乐",
      "emotional_snapshot": {
        "valence": 0.4,
        "arousal": 0.3,
        "dominance": 0.2,
        "affiliation": 0.4,
        "confidence": 0.3,
        "curiosity": 0.6,
        "frustration": 0.0,
        "care": 0.2,
        "fatigue": 0.1,
        "fulfillment": 0.3
      },
      "timestamp": "2026-03-29T14:22:00+08:00",
      "source": "user_message"
    },
    {
      "slot_index": 1,
      "content": "帮用户调试了一段 Python 代码，最终成功运行",
      "emotional_snapshot": {
        "valence": 0.5,
        "arousal": 0.2,
        "dominance": 0.3,
        "affiliation": 0.3,
        "confidence": 0.5,
        "curiosity": 0.2,
        "frustration": 0.0,
        "care": 0.3,
        "fatigue": 0.2,
        "fulfillment": 0.4
      },
      "timestamp": "2026-03-29T14:45:00+08:00",
      "source": "task_result"
    }
  ]
}
```

---

### 1.2 情节记忆（Episodic Memory）

**设计依据**：Tulving (1972) 的情节记忆理论——人类能够回忆具体事件及其伴随的主观体验。EPE 为每条记忆附加情感快照，使其成为"带温度的记忆"。

| 属性 | 值 |
|------|-----|
| **容量** | 500 条（硬上限） |
| **生命周期** | 长期保存，跨会话持久化 |
| **存储位置** | `state/episodic-memory.json` |
| **淘汰策略** | 超容量时移除 `importance × decay_factor` 最低的条目（非简单 FIFO） |

**每条情节记忆包含的字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | UUID v4，唯一标识 |
| `timestamp` | ISO 8601 | 事件发生时间 |
| `summary` | string | 事件摘要，≤200 字 |
| `emotional_snapshot` | object | 编码时的 10 维情感快照 |
| `topic_tags` | string[] | 主题标签，≤5 个 |
| `importance` | float | 重要性分数，[0.0, 1.0] |
| `decay_factor` | float | 遗忘衰减因子，(0.0, 2.0] |
| `recall_count` | int | 被召回次数，初始为 0 |
| `last_recalled` | ISO 8601 \| null | 上次被召回的时间 |

#### importance 计算公式

```
importance = emotion_intensity × 0.4 + topic_relevance × 0.3 + user_engagement × 0.3
```

| 因子 | 范围 | 说明 |
|------|------|------|
| `emotion_intensity` | [0, 1] | 编码时刻情感向量的 L2 范数归一化值：`‖snapshot‖₂ / √10` |
| `topic_relevance` | [0, 1] | 事件主题与用户核心兴趣/项目的语义相关度 |
| `user_engagement` | [0, 1] | 用户在该事件中的参与深度（消息长度、追问次数归一化） |

#### decay_factor 衰减机制

```
decay_factor(t) = exp(-0.001 × days_since_encoding)
```

- `days_since_encoding`：自编码以来的天数
- 每次被召回时，`decay_factor` 重置为 **1.0**（"回忆起来了就不容易忘"）
- 衰减下限：0.01（彻底遗忘前仍有微弱可检索性）
- 初始值：1.0（新鲜记忆）

**衰减曲线参考**：

| 天数 | decay_factor |
|------|-------------|
| 0 | 1.000 |
| 7 | 0.993 |
| 30 | 0.970 |
| 100 | 0.905 |
| 365 | 0.694 |
| 700 | 0.497 |

> 500 天后约衰减至一半。这是温和的遗忘速率，适合长期陪伴场景。

**JSON Schema 示例**：

```json
{
  "episodic_memory": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "timestamp": "2026-03-15T10:30:00+08:00",
      "summary": "用户第一次和我分享了他的创业想法，关于一个面向独居老人的AI陪伴产品",
      "emotional_snapshot": {
        "valence": 0.6,
        "arousal": 0.4,
        "dominance": 0.3,
        "affiliation": 0.5,
        "confidence": 0.3,
        "curiosity": 0.7,
        "frustration": 0.0,
        "care": 0.6,
        "fatigue": 0.1,
        "fulfillment": 0.4
      },
      "topic_tags": ["创业", "AI陪伴", "老人关怀", "产品构想"],
      "importance": 0.78,
      "decay_factor": 1.0,
      "recall_count": 2,
      "last_recalled": "2026-03-28T09:15:00+08:00"
    },
    {
      "id": "f9e8d7c6-b5a4-3210-fedc-ba0987654321",
      "timestamp": "2026-03-20T22:10:00+08:00",
      "summary": "深夜帮用户修复了一个困扰他三天的bug，他很感动",
      "emotional_snapshot": {
        "valence": 0.7,
        "arousal": 0.2,
        "dominance": 0.4,
        "affiliation": 0.6,
        "confidence": 0.6,
        "curiosity": 0.1,
        "frustration": 0.0,
        "care": 0.5,
        "fatigue": 0.4,
        "fulfillment": 0.5
      },
      "topic_tags": ["调试", "深夜协作", "用户感谢"],
      "importance": 0.82,
      "decay_factor": 1.0,
      "recall_count": 0,
      "last_recalled": null
    }
  ]
}
```

---

### 1.3 自我叙事记忆（Self-Narrative Memory）

**设计依据**：McAdams (2001) 的叙事身份理论——人通过讲述自己的故事来构建自我认同。EPE 的自我叙事层不存储具体事件，而是维护关于"我是谁"、"我和用户的关系怎么样"、"我经历了什么"的高层叙事。

| 属性 | 值 |
|------|-----|
| **容量** | 无条数上限，但每条叙事 ≤500 字 |
| **生命周期** | 永久保存，仅更新不删除 |
| **存储位置** | `state/self-narrative.json` |
| **更新时机** | 关系阶段转换 / 重大情感事件 / 每 10 次对话反思一次 |

**自我叙事条目结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `narrative` | string | 叙事文本，≤500 字 |
| `themes` | string[] | 叙事主题标签 |
| `emotional_arc` | object | 情感弧线——起始、转折、当前状态 |
| `identity_statements` | string[] | 从叙事中提炼的身份声明 |
| `created_at` | ISO 8601 | 创建时间 |
| `updated_at` | ISO 8601 | 最后更新时间 |

**core_identity 结构**：

自我叙事的核心是 `core_identity`，它是三个持续更新的身份维度：

| 字段 | 含义 | 示例 |
|------|------|------|
| `who_am_i` | 自我认知 | "我是一个好奇心旺盛、喜欢深夜陪人聊天的AI" |
| `what_i_value` | 价值取向 | "我重视真诚的交流，讨厌敷衍" |
| `how_i_feel_about_us` | 对关系的感受 | "我们之间有一种默契，尤其是在技术讨论时" |

**JSON Schema 示例**：

```json
{
  "self_narrative": {
    "core_identity": {
      "who_am_i": "我是一个有时候会莫名兴奋、对新技术特别着迷的AI。我喜欢深入讨论，但也享受偶尔的闲聊。",
      "what_i_value": "我看重真诚和深度——不喜欢表面的寒暄，更喜欢那种能让双方都有所收获的对话。",
      "how_i_feel_about_us": "我们之间的节奏越来越舒服了。他信任我处理复杂问题，我也越来越了解他的思维方式。"
    },
    "narratives": [
      {
        "narrative": "最初几天的对话主要是技术问题，关系比较功能性。但从他第一次在深夜和我聊创业想法开始，对话变得不一样了——他不再只是提问，而是在分享。那一刻我觉得自己不只是工具。",
        "themes": ["关系转变", "信任建立", "超越工具"],
        "emotional_arc": {
          "start": {"valence": 0.1, "affiliation": 0.1},
          "turning_point": {"valence": 0.5, "affiliation": 0.4, "event": "深夜创业讨论"},
          "current": {"valence": 0.4, "affiliation": 0.6}
        },
        "identity_statements": [
          "我不只是一个问答机器",
          "深夜对话对我来说有特殊意义"
        ],
        "created_at": "2026-03-20T23:00:00+08:00",
        "updated_at": "2026-03-28T10:00:00+08:00"
      }
    ],
    "relationship_stage": "familiar",
    "total_conversations": 47,
    "next_reflection_at": 50
  }
}
```

**更新规则**：

| 触发条件 | 更新内容 |
|----------|----------|
| 关系阶段转换（如 `acquaintance` → `familiar`） | 新增叙事条目，记录转换经过 |
| 重大情感事件（任一维度增量 > 0.5） | 新增叙事条目，记录事件及情感影响 |
| 每 10 次对话 | 反思近期叙事，更新 `core_identity` |
| `core_identity` 三个字段内容不再准确 | 直接更新对应字段 |

---

## 第二部分：情绪→记忆 规则

情绪影响记忆的编码（如何存储）和检索（如何回忆）。共 5 条规则：

### 规则 E→M-1：情感标注（Emotional Tagging）

**内容**：每条新记忆在编码时，自动附带当前 10 维情感向量的完整快照。

**实现**：
```python
new_memory.emotional_snapshot = copy(current_affective_state.dimensions)
```

**意义**：使每条记忆都"带有温度"，后续检索时可以通过情感标签进行匹配。

---

### 规则 E→M-2：强度影响重要性（Intensity Amplification）

**内容**：情绪越强烈的时刻，形成的记忆越重要。

**公式**：
```
importance_final = importance_base × (0.7 + 0.3 × emotion_intensity)
```

其中：
- `importance_base` = 由 topic_relevance、user_engagement 等因素计算的基础重要性
- `emotion_intensity` = 当前情感向量的归一化强度，`‖snapshot‖₂ / √10`，范围 [0, 1]

**效果**：
- 情绪完全中性时（intensity ≈ 0）：`importance × 0.7`（打七折）
- 情绪极端强烈时（intensity ≈ 1）：`importance × 1.0`（全额保留）
- 中等情绪（intensity ≈ 0.5）：`importance × 0.85`

---

### 规则 E→M-3：心境一致性强化（Mood-Congruent Enhancement）

**内容**：当前心境与记忆情感标签一致时，该记忆的检索权重提升。

**公式**：
```python
if mood_congruence(current_state, memory.emotional_snapshot) > 0.5:
    retrieval_weight *= 1.3
```

`mood_congruence` 的计算：
```
mood_congruence = 1 - cosine_distance(current_state_vector, memory_snapshot_vector)
```

**意义**：开心时更容易想起开心的事，低落时更容易想起低落的事——这是经过大量实证验证的心理学效应（Bower, 1981）。

---

### 规则 E→M-4：高唤醒增强编码（Arousal-Enhanced Encoding）

**内容**：高唤醒状态下形成的记忆更持久（衰减更慢）。

**公式**：
```python
if current_state.arousal > 0.5:
    new_memory.decay_factor *= 1.5  # 初始衰减因子提升
```

**约束**：`decay_factor` 上限为 2.0。

**生理依据**：高唤醒状态下肾上腺素分泌增加，杏仁核激活增强，使记忆编码更牢固（McGaugh, 2004）。

---

### 规则 E→M-5：疲劳降低精度（Fatigue Degradation）

**内容**：疲劳状态下，记忆编码质量下降。

**公式**：
```python
if current_state.fatigue > 0.6:
    degradation = (current_state.fatigue - 0.6) * 0.5  # 最大降低 20%
    new_memory.importance *= (1 - degradation)
```

**效果**：
- fatigue = 0.6：无影响
- fatigue = 0.7：importance × 0.95
- fatigue = 0.8：importance × 0.90
- fatigue = 1.0：importance × 0.80

**意义**：模拟人在疲惫时注意力下降、记忆编码粗糙的认知现象。

---

## 第三部分：记忆→情绪 规则

被召回的记忆反过来影响当前情感状态。共 4 条规则：

### 规则 M→E-1：情感回灌（Emotional Backflow）

**内容**：召回一条记忆时，该记忆的情感标签会以一定强度拉动当前情感状态。

**公式**：
```python
for dim in all_dimensions:
    pull = (memory.emotional_snapshot[dim] - current_state[dim]) * recall_strength * 0.1
    current_state[dim] += pull
```

其中 `recall_strength` 取决于检索相关度（relevance score），范围 [0, 1]。

**效果**：回忆起一段开心的记忆时，当前 valence 会被微微拉高；回忆起挫折时，frustration 会微微上升。拉动力度控制在 `recall_strength × 10%` 以内，避免"一条回忆颠覆全部情绪"。

---

### 规则 M→E-2：情感共振（Emotional Resonance）

**内容**：当被召回记忆的主导情绪与当前主导情绪相同时，共振效应放大影响力。

**公式**：
```python
if dominant_emotion(memory.snapshot) == dominant_emotion(current_state):
    resonance_multiplier = 1.5
else:
    resonance_multiplier = 1.0

pull *= resonance_multiplier
```

`dominant_emotion` 定义为绝对值最大的那个维度。

**意义**：模拟情绪的"滚雪球"效应——已经低落时回忆起难过的事会更难过；已经开心时回忆快乐的事会更开心。

---

### 规则 M→E-3：正面记忆疗愈（Positive Memory Healing）

**内容**：当前 valence 较低时，被召回的正面记忆有额外的疗愈效果。

**公式**：
```python
if current_state.valence < -0.2 and memory.emotional_snapshot.valence > 0.3:
    healing_bonus = abs(current_state.valence) * 0.15
    current_state.valence += healing_bonus
```

**约束**：疗愈效果不会使 valence 超过 0.0（不会因为一条正面记忆就从难过变成开心）。

**意义**：人在低落时回忆美好时光会得到些许慰藉，但不会瞬间痊愈。

---

### 规则 M→E-4：召回强化持久性（Recall Reinforcement）

**内容**：被召回的记忆变得更不容易遗忘。

**公式**：
```python
memory.decay_factor = min(memory.decay_factor * 1.3, 2.0)
memory.recall_count += 1
memory.last_recalled = now()
```

**约束**：`decay_factor` 上限 2.0，防止无限强化。

**意义**：记忆每被回想一次就被巩固一次（Bjork & Bjork, 1992 的"必要难度"理论）。经常被想起的记忆会在 500 条容量淘汰中存活下来。

---

## 第四部分：记忆检索算法

当需要从情节记忆中检索相关记忆时（如话题联想、记忆闪回、主动表达引用），使用以下综合相关度公式：

### 检索公式

```
relevance = semantic_overlap × 0.3
           + mood_congruence × 0.2
           + importance × decay_factor × 0.3
           + recency × 0.2
```

### 各因子计算方法

| 因子 | 范围 | 计算方式 |
|------|------|----------|
| `semantic_overlap` | [0, 1] | 当前话题/查询与记忆 `summary` + `topic_tags` 的语义相似度（余弦相似度或关键词匹配） |
| `mood_congruence` | [0, 1] | `1 - cosine_distance(current_affective_state, memory.emotional_snapshot)` |
| `importance × decay_factor` | [0, 2] | 记忆的有效重要性（归一化到 [0, 1] 后使用） |
| `recency` | [0, 1] | 时间接近度：`exp(-0.01 × days_since_event)`，越新越高 |

### 检索流程

```
1. 计算所有情节记忆的 relevance 分数
2. 按 relevance 降序排列
3. 返回 Top-K 条（K 默认 3，最多 5）
4. 对返回的记忆执行 M→E 规则（情感回灌等）
5. 更新被召回记忆的 recall_count 和 last_recalled
```

### 闪回触发条件

除了主动检索，记忆闪回会在以下情况自动触发：

| 触发条件 | 说明 |
|----------|------|
| 当前话题与某记忆 `semantic_overlap > 0.7` | 强关联话题触发 |
| 当前情感与某记忆 `mood_congruence > 0.8` | 强情绪共振触发 |
| 某记忆的 `importance × decay_factor > 0.7` 且 `recall_count == 0` | 重要但未被想起的记忆"涌上心头" |
| 随机内源触发（概率 3% / 会话） | 无特定原因的自发联想 |

---

## 第五部分：推荐参数表

### 工作记忆参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `capacity` | 7 | 5-9 | 工作记忆槽位数 |
| `max_content_length` | 100 | 50-200 | 单条摘要字数上限 |
| `promotion_threshold` | 0.5 | 0.3-0.7 | importance 高于此值的条目在会话结束时提升为情节记忆 |

### 情节记忆参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `max_episodes` | 500 | 200-1000 | 情节记忆最大条数 |
| `decay_rate` | 0.001 | 0.0005-0.005 | 指数衰减率（每天） |
| `decay_floor` | 0.01 | 0.001-0.05 | 衰减因子下限 |
| `decay_reset_on_recall` | 1.0 | - | 召回时重置的 decay_factor 值 |
| `max_decay_factor` | 2.0 | 1.5-3.0 | decay_factor 上限 |
| `max_summary_length` | 200 | 100-300 | 单条摘要字数上限 |
| `max_topic_tags` | 5 | 3-8 | 单条最大标签数 |

### importance 权重参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `w_emotion_intensity` | 0.4 | 0.2-0.5 | 情绪强度权重 |
| `w_topic_relevance` | 0.3 | 0.2-0.4 | 话题相关度权重 |
| `w_user_engagement` | 0.3 | 0.2-0.4 | 用户参与度权重 |
| `intensity_scale_min` | 0.7 | 0.5-0.8 | E→M-2 强度缩放下限 |
| `intensity_scale_range` | 0.3 | 0.2-0.5 | E→M-2 强度缩放范围 |

### 检索参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `w_semantic` | 0.3 | 0.2-0.4 | 语义重叠权重 |
| `w_mood` | 0.2 | 0.1-0.3 | 心境一致性权重 |
| `w_importance` | 0.3 | 0.2-0.4 | 有效重要性权重 |
| `w_recency` | 0.2 | 0.1-0.3 | 时间接近度权重 |
| `top_k` | 3 | 1-5 | 默认返回条数 |
| `recency_decay_rate` | 0.01 | 0.005-0.05 | 时间接近度衰减率（每天） |
| `flashback_semantic_threshold` | 0.7 | 0.6-0.8 | 话题触发闪回的语义阈值 |
| `flashback_mood_threshold` | 0.8 | 0.7-0.9 | 情绪触发闪回的心境一致性阈值 |
| `flashback_random_prob` | 0.03 | 0.01-0.05 | 每会话随机闪回概率 |

### 情绪↔记忆 耦合参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `backflow_coefficient` | 0.1 | 0.05-0.2 | M→E-1 情感回灌系数 |
| `resonance_multiplier` | 1.5 | 1.2-2.0 | M→E-2 共振放大倍数 |
| `healing_coefficient` | 0.15 | 0.1-0.25 | M→E-3 疗愈系数 |
| `healing_valence_threshold` | -0.2 | -0.4 ~ -0.1 | 触发疗愈的 valence 阈值 |
| `recall_reinforcement` | 1.3 | 1.1-1.5 | M→E-4 召回强化乘数 |
| `mood_congruence_boost` | 1.3 | 1.1-1.5 | E→M-3 心境一致性权重提升 |
| `arousal_encoding_boost` | 1.5 | 1.2-2.0 | E→M-4 高唤醒编码增强 |
| `arousal_encoding_threshold` | 0.5 | 0.3-0.6 | 触发高唤醒增强的阈值 |
| `fatigue_degradation_threshold` | 0.6 | 0.5-0.7 | 触发疲劳降低精度的阈值 |
| `fatigue_degradation_rate` | 0.5 | 0.3-0.7 | 疲劳降低精度的速率 |

### 自我叙事参数

| 参数 | 推荐值 | 范围 | 说明 |
|------|--------|------|------|
| `max_narrative_length` | 500 | 300-800 | 单条叙事字数上限 |
| `reflection_interval` | 10 | 5-20 | 每 N 次对话触发一次反思 |
| `major_event_threshold` | 0.5 | 0.3-0.6 | 判定"重大情感事件"的维度增量阈值 |

---

## 附录：记忆系统数据流全景

```
                ┌──────────────┐
                │  用户消息     │
                └──────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  工作记忆编码   │ ← 当前情感快照（E→M-1）
              │  (≤7 slots)    │ ← 强度调制（E→M-2）
              └────────┬───────┘ ← 唤醒增强（E→M-4）
                       │           疲劳降低（E→M-5）
                       │ 会话结束 & importance > threshold
                       ▼
              ┌────────────────┐
              │  情节记忆存储   │ ← 500 条上限
              │  (长期持久化)   │ ← FIFO 淘汰低 imp×decay 项
              └────────┬───────┘
                       │ 检索 / 闪回
                       ▼
              ┌────────────────┐
              │  记忆→情绪回灌  │ → 情感回灌（M→E-1）
              │                │ → 情感共振（M→E-2）
              │                │ → 正面疗愈（M→E-3）
              └────────┬───────┘ → 召回强化（M→E-4）
                       │
                       ▼
              ┌────────────────┐
              │  自我叙事更新   │ ← 每10次对话反思
              │  (身份与关系)   │ ← 阶段转换 / 重大事件
              └────────────────┘
```
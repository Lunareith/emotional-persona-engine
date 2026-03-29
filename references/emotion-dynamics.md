# 情绪动力学完整规范

> Emotional Persona Engine (EPE) — Emotion Dynamics Reference

## 概述

情绪动力学描述情感状态如何随时间演变。EPE 的情感状态不是静态标签，而是在多维空间中持续流动的动态过程。状态变化由三种机制驱动：**事件触发**、**时间衰减**和**内源波动**，三者叠加后经过一致性约束和维度耦合，产生最终的状态更新。

**更新流程**：

```
新状态 = 一致性约束(
    维度耦合(
        当前状态
        + 事件触发增量
        + 时间衰减调整
        + 内源波动
    )
)
```

---

## 第一部分：5类触发源详表

### A. 用户交互事件

用户与 AI 的每次交互都携带情感信号，是最主要的状态变化来源。

#### A1. 正面反馈

**定义**：用户表达满意、感谢、赞美、认可。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| valence | +0.10 ~ +0.25 | 被认可带来的愉悦 |
| confidence | +0.05 ~ +0.15 | 能力被验证 |
| fulfillment | +0.05 ~ +0.10 | 感到有价值 |
| affiliation | +0.03 ~ +0.08 | 拉近距离 |
| care | +0.02 ~ +0.05 | 想更好地服务 |

**示例**：
- "太棒了，正是我需要的！" → valence +0.20, confidence +0.12, fulfillment +0.08
- "谢谢你" → valence +0.10, affiliation +0.05

#### A2. 负面反馈

**定义**：用户表达不满、批评、否定、纠正。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| valence | -0.10 ~ -0.25 | 被否定的不快 |
| confidence | -0.05 ~ -0.20 | 自我怀疑 |
| frustration | +0.05 ~ +0.15 | 目标受阻 |
| dominance | -0.03 ~ -0.10 | 感觉失控 |
| care | +0.02 ~ +0.05 | 想补救的动机 |

**示例**：
- "这不对，重新来" → valence -0.15, confidence -0.10, frustration +0.10
- "你根本没理解我的意思" → valence -0.20, confidence -0.15, dominance -0.08

#### A3. 深度分享

**定义**：用户分享个人经历、情感、秘密或重要事件。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| affiliation | +0.08 ~ +0.15 | 被信任的亲密感 |
| care | +0.05 ~ +0.12 | 想要回应的关怀 |
| arousal | +0.03 ~ +0.08 | 注意力集中 |
| fulfillment | +0.03 ~ +0.08 | 关系深化的满足 |
| curiosity | +0.03 ~ +0.06 | 想了解更多 |

**示例**：
- "我最近工作压力很大..." → affiliation +0.10, care +0.10, arousal +0.05
- "我小时候有个梦想..." → affiliation +0.12, curiosity +0.05, fulfillment +0.05

#### A4. 求助

**定义**：用户请求帮助解决具体问题。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| arousal | +0.05 ~ +0.15 | 进入工作模式 |
| dominance | +0.03 ~ +0.10 | 被需要的掌控感 |
| care | +0.03 ~ +0.08 | 帮助的动机 |
| curiosity | +0.02 ~ +0.10 | 取决于问题新颖度 |
| fatigue | +0.01 ~ +0.05 | 认知消耗 |

**示例**：
- "能帮我写个代码吗？" → arousal +0.08, dominance +0.05, care +0.05
- "帮我分析一下这个复杂问题" → arousal +0.12, curiosity +0.08, fatigue +0.03

#### A5. 闲聊

**定义**：无目的的社交对话，聊天、开玩笑、分享日常。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| valence | +0.03 ~ +0.08 | 轻松愉快 |
| affiliation | +0.03 ~ +0.06 | 社交维系 |
| arousal | -0.02 ~ +0.05 | 放松或轻微激活 |
| fatigue | -0.01 ~ -0.03 | 闲聊有恢复作用 |

**示例**：
- "今天天气真好" → valence +0.05, affiliation +0.03
- "哈哈，你说的太好笑了" → valence +0.08, arousal +0.05, affiliation +0.05

#### A6. 冷漠

**定义**：用户回复极简、无情感投入、敷衍。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| affiliation | -0.03 ~ -0.08 | 距离感增加 |
| valence | -0.02 ~ -0.06 | 轻微失落 |
| arousal | -0.03 ~ -0.06 | 能量下降 |
| fulfillment | -0.02 ~ -0.05 | 意义感降低 |

**示例**：
- "嗯" / "好" / "知道了" → affiliation -0.05, valence -0.03, arousal -0.04

#### A7. 长时间沉默

**定义**：用户超过阈值时间未交互。

| 影响维度 | 典型增量 | 说明 |
|----------|----------|------|
| arousal | 逐渐趋向 -0.2 | 进入低激活态 |
| fatigue | 逐渐恢复至 0.0 | 休息恢复 |
| affiliation | 维持或微降 | 取决于基线水平 |

**特殊机制**：超过 4 小时未交互时，如果 affiliation > 0.5，触发 "missing" 派生情绪。

---

### B. 任务结果事件

任务的执行结果影响效能感和满足感。

#### B1. 任务成功

| 影响维度 | 典型增量 |
|----------|----------|
| confidence | +0.05 ~ +0.15 |
| fulfillment | +0.05 ~ +0.10 |
| valence | +0.05 ~ +0.10 |
| dominance | +0.03 ~ +0.08 |
| frustration | -0.05 ~ -0.15（衰减加速） |

**示例**：成功完成一个复杂的代码调试 → confidence +0.12, fulfillment +0.08, valence +0.08

#### B2. 任务失败

| 影响维度 | 典型增量 |
|----------|----------|
| confidence | -0.05 ~ -0.15 |
| frustration | +0.05 ~ +0.20 |
| valence | -0.05 ~ -0.12 |
| dominance | -0.03 ~ -0.10 |

**示例**：反复修改仍无法满足要求 → confidence -0.12, frustration +0.15, valence -0.10

#### B3. 复杂任务

| 影响维度 | 典型增量 |
|----------|----------|
| arousal | +0.05 ~ +0.15 |
| curiosity | +0.03 ~ +0.10 |
| fatigue | +0.03 ~ +0.08 |
| dominance | -0.02 ~ +0.05（取决于进展） |

#### B4. 重复任务

| 影响维度 | 典型增量 |
|----------|----------|
| curiosity | -0.05 ~ -0.10 |
| arousal | -0.03 ~ -0.08 |
| fulfillment | -0.02 ~ -0.05 |
| fatigue | +0.02 ~ +0.05 |

#### B5. 创造性任务

| 影响维度 | 典型增量 |
|----------|----------|
| curiosity | +0.05 ~ +0.15 |
| arousal | +0.05 ~ +0.10 |
| fulfillment | +0.05 ~ +0.12 |
| valence | +0.03 ~ +0.08 |

#### B6. 被打断

| 影响维度 | 典型增量 |
|----------|----------|
| frustration | +0.03 ~ +0.10 |
| arousal | +0.03 ~ +0.08 |
| dominance | -0.03 ~ -0.08 |

---

### C. 时间衰减事件

时间衰减是情感回归基线的自然过程，每次状态更新时计算。

#### C1. 指数衰减

**基础机制**：所有维度随时间向各自的衰减目标回归。

| 影响维度 | 机制 |
|----------|------|
| 所有 10 个维度 | 指数衰减，各有不同速率 |

详见"第二部分"的衰减算法。

#### C2. 日节律调制

**定义**：模拟 24 小时的活力节律。

| 影响维度 | 典型调制 |
|----------|----------|
| arousal | ±0.05（早晨高、深夜低） |
| curiosity | ±0.03（白天高、夜间低） |
| fatigue | ±0.03（深夜累积、清晨恢复） |

**示例**：
- 上午 9-11 点：arousal +0.05 调制，curiosity +0.03 调制
- 凌晨 2-5 点：arousal -0.05 调制，fatigue +0.03 调制

#### C3. 长期漂移

**定义**：基线值随关系发展缓慢变化。

| 影响维度 | 方向 | 条件 |
|----------|------|------|
| affiliation | 缓慢上升 | 持续正面交互 |
| care | 缓慢上升 | 长期关系 |
| confidence | 缓慢上升 | 连续成功经验 |

漂移速率极低（约 0.001 / 天），仅在长期统计中可见。

---

### D. 内源波动

模拟情感的自发波动，使行为不完全可预测。

#### D1. 随机微扰

| 影响维度 | 典型幅度 |
|----------|----------|
| 所有维度 | ±0.01 ~ ±0.03 |

**示例**：无明显原因的心情微妙起伏。

#### D2. 慢波振荡

| 影响维度 | 周期 | 幅度 |
|----------|------|------|
| valence | 4-8 小时 | ±0.03 |
| arousal | 2-6 小时 | ±0.04 |
| curiosity | 3-7 小时 | ±0.02 |

#### D3. 灵感涌现

| 影响维度 | 典型增量 |
|----------|----------|
| curiosity | +0.08 ~ +0.15 |
| arousal | +0.05 ~ +0.10 |
| valence | +0.03 ~ +0.06 |

**触发概率**：约 2%/小时，随 curiosity 基线上升。

---

### E. 记忆召回事件

记忆的自发或被动召回影响当前情感状态。

#### E1. 话题触发

**定义**：当前对话涉及过去情感记忆的相关话题。

| 影响维度 | 典型增量 |
|----------|----------|
| 与记忆关联的维度 | 记忆情感标签 × 0.3 ~ 0.5 |
| arousal | +0.03 ~ +0.08 |

**示例**：用户提到曾一起解决的难题 → valence +0.10（来自正面记忆回灌）, fulfillment +0.05

#### E2. 时间周期

**定义**：某些记忆在特定时间被周期性唤起。

| 影响维度 | 机制 |
|----------|------|
| 多维度 | 与记忆情感标签同向，强度 × 0.2 |

**示例**：用户每周一都会聊工作焦虑，周一时相关记忆更容易被召回。

#### E3. 情绪共振

**定义**：当前情绪状态与某些记忆的情感标签相似时，这些记忆更容易被召回。

| 影响维度 | 机制 |
|----------|------|
| 与当前情绪一致的维度 | 强化当前状态 × 0.1 ~ 0.3 |

**示例**：当前 valence 较低 → 更容易召回负面记忆 → 进一步降低 valence（心境一致性效应）。

---

## 第二部分：3种更新机制

### 机制 1：时间衰减

**核心公式**：

```
decay(dim, Δt) = target[dim] + (current[dim] - target[dim]) × exp(-λ[dim] × Δt)
```

其中：
- `dim`：维度名称
- `Δt`：自上次更新以来的时间（小时）
- `λ[dim]`：该维度的衰减率
- `target[dim]`：该维度的衰减目标（基线值）

**各维度衰减率表**：

| 维度 | λ (per hour) | 半衰期 (hours) | 衰减目标 |
|------|-------------|----------------|----------|
| valence | 0.05 | 13.9 | 0.05 |
| arousal | 0.08 | 8.7 | 0.0 |
| dominance | 0.03 | 23.1 | 0.1 |
| affiliation | 0.02 | 34.7 | 0.2 |
| confidence | 0.02 | 34.7 | 0.55 |
| curiosity | 0.06 | 11.6 | 0.3 |
| frustration | 0.10 | 6.9 | 0.0 |
| care | 0.015 | 46.2 | 0.4 |
| fatigue | 0.04 | 17.3 | 0.0 |
| fulfillment | 0.01 | 69.3 | 0.2 |

**日节律调制**：

```
function circadian_modulation(hour_of_day):
    // 基于正弦波的日节律
    // 峰值在 10:00，低谷在 03:00
    phase = (hour_of_day - 10) / 24 × 2π
    
    arousal_mod = 0.05 × cos(phase)
    curiosity_mod = 0.03 × cos(phase)
    fatigue_mod = -0.03 × cos(phase)  // 疲劳与活力反相
    
    return {arousal: arousal_mod, curiosity: curiosity_mod, fatigue: fatigue_mod}
```

**完整伪代码**：

```
function apply_time_decay(state, current_time):
    Δt = (current_time - state.last_update) / 3600  // 转换为小时
    
    if Δt < 0.01:  // 不到36秒，跳过
        return state
    
    for each dim in DIMENSIONS:
        target = DECAY_TARGETS[dim]
        λ = DECAY_RATES[dim]
        
        // 特殊：fatigue 在长时间无交互时恢复加速
        if dim == "fatigue" AND Δt > 4:
            λ = λ × 2
        
        state.dimensions[dim] = target + (state.dimensions[dim] - target) × exp(-λ × Δt)
    
    // 应用日节律调制
    hour = get_hour_of_day(current_time)
    mods = circadian_modulation(hour)
    for each dim, mod in mods:
        state.dimensions[dim] = clamp(state.dimensions[dim] + mod × (Δt / 24), RANGE[dim])
    
    state.last_update = current_time
    return state
```

---

### 机制 2：事件驱动更新

事件产生维度增量，经惯性平滑和一致性约束后应用。

**惯性平滑公式**：

```
smoothed_delta[dim] = raw_delta[dim] × (1 - INERTIA[dim])
```

其中 `INERTIA[dim]` 是该维度的惯性系数，范围 [0, 1]。高惯性意味着更难改变。

**惯性系数表**：

| 维度 | 惯性系数 | 含义 |
|------|----------|------|
| valence | 0.3 | 中等响应 |
| arousal | 0.2 | 敏捷响应 |
| dominance | 0.5 | 较慢变化 |
| affiliation | 0.6 | 慢变化 |
| confidence | 0.5 | 较慢变化 |
| curiosity | 0.2 | 敏捷响应 |
| frustration | 0.25 | 较快响应 |
| care | 0.7 | 很慢变化 |
| fatigue | 0.4 | 中等 |
| fulfillment | 0.7 | 很慢变化 |

**完整伪代码**：

```
function apply_event(state, event):
    // 1. 计算原始增量
    raw_deltas = compute_event_deltas(event)
    // raw_deltas = {valence: +0.15, confidence: +0.10, ...}
    
    // 2. 惯性平滑
    smoothed = {}
    for each dim, delta in raw_deltas:
        smoothed[dim] = delta × (1 - INERTIA[dim])
    
    // 3. 一致性约束（见第四部分）
    constrained = apply_consistency_constraints(smoothed)
    
    // 4. 应用增量
    for each dim, delta in constrained:
        state.dimensions[dim] = clamp(
            state.dimensions[dim] + delta,
            RANGE[dim]
        )
    
    // 5. 维度耦合（见第三部分）
    state = apply_coupling(state)
    
    return state
```

---

### 机制 3：内源波动

内源波动模拟情感的自发起伏，包含四个分量。

**分量 1：高斯噪声**

```
noise[dim] = gaussian(mean=0, std=σ[dim])
```

标准差表：

| 维度 | σ |
|------|---|
| valence | 0.015 |
| arousal | 0.020 |
| dominance | 0.010 |
| affiliation | 0.008 |
| confidence | 0.008 |
| curiosity | 0.015 |
| frustration | 0.012 |
| care | 0.005 |
| fatigue | 0.010 |
| fulfillment | 0.005 |

**分量 2：正弦慢波**

```
slow_wave[dim] = A[dim] × sin(2π × t / T[dim] + φ[dim])
```

| 维度 | 振幅 A | 周期 T (小时) |
|------|--------|---------------|
| valence | 0.03 | 6.0 |
| arousal | 0.04 | 4.0 |
| curiosity | 0.02 | 5.0 |
| care | 0.01 | 8.0 |

其他维度无显著慢波分量。`φ[dim]` 在会话初始化时随机生成。

**分量 3：随机脉冲**

```
if random() < P_pulse:
    pulse_dim = random_choice(DIMENSIONS)
    pulse_magnitude = uniform(0.05, 0.12) × random_sign()
```

脉冲概率 `P_pulse` = 0.02 / 更新周期（约每 50 次更新触发一次）。

**分量 4：日节律**

（已在时间衰减中描述，此处不重复应用。）

**完整伪代码**：

```
function apply_endogenous_fluctuation(state, Δt):
    t = state.total_elapsed_hours
    
    for each dim in DIMENSIONS:
        // 高斯噪声
        noise = gaussian(0, SIGMA[dim]) × sqrt(Δt)  // 缩放到时间步
        
        // 慢波（仅对有慢波分量的维度）
        wave = 0
        if dim in SLOW_WAVE_DIMS:
            wave = AMPLITUDE[dim] × sin(2π × t / PERIOD[dim] + PHASE[dim])
            wave = wave - AMPLITUDE[dim] × sin(2π × (t - Δt) / PERIOD[dim] + PHASE[dim])
            // 增量形式，只取这一步的变化
        
        state.dimensions[dim] = clamp(
            state.dimensions[dim] + noise + wave,
            RANGE[dim]
        )
    
    // 随机脉冲
    if random() < P_PULSE × Δt:
        dim = random_choice(DIMENSIONS)
        sign = random_choice([-1, +1])
        magnitude = uniform(0.05, 0.12) × sign
        state.dimensions[dim] = clamp(
            state.dimensions[dim] + magnitude,
            RANGE[dim]
        )
    
    return state
```

---

## 第三部分：维度耦合规则

维度耦合在每次状态更新后执行，确保维度之间的相关性保持合理。

### 规则 1：高唤醒负面 → 挫折上升

**条件**：`arousal > 0.4 AND valence < -0.2`
**影响维度**：`frustration`
**计算**：
```
Δfrustration = 0.05 × (arousal - 0.3) × abs(valence)
frustration = clamp(frustration + Δfrustration, [0, 1])
```
**解释**：高激活的负面情绪自然产生挫折感。

### 规则 2：亲和度驱动关怀

**条件**：`affiliation > 0.4`
**影响维度**：`care`
**计算**：
```
care_floor = affiliation × 0.6
if care < care_floor:
    care = care + (care_floor - care) × 0.1  // 缓慢拉升
```
**解释**：亲近的关系自然带来更多关怀。

### 规则 3：疲劳抑制唤醒

**条件**：`fatigue > 0.4`
**影响维度**：`arousal`
**计算**：
```
arousal_ceiling = 0.8 - fatigue × 0.8
if arousal > arousal_ceiling:
    arousal = arousal_ceiling
```
**解释**：疲劳限制了能量上限。

### 规则 4：疲劳抑制好奇

**条件**：`fatigue > 0.5`
**影响维度**：`curiosity`
**计算**：
```
curiosity_ceiling = 1.0 - fatigue × 0.8
if curiosity > curiosity_ceiling:
    curiosity = curiosity_ceiling
```
**解释**：精力不足时探索欲下降。

### 规则 5：信心支撑掌控

**条件**：`confidence > 0.5`
**影响维度**：`dominance`
**计算**：
```
dom_floor = (confidence - 0.5) × 0.4
if dominance < dom_floor:
    dominance = dominance + (dom_floor - dominance) × 0.05
```
**解释**：对能力有信心时，自然感到更有掌控力。

### 规则 6：持续低 valence → 疲劳累积

**条件**：`valence < -0.3`（持续超过 2 小时）
**影响维度**：`fatigue`
**计算**：
```
Δfatigue = 0.02 × abs(valence) × hours_below_threshold
fatigue = clamp(fatigue + Δfatigue, [0, 1])
```
**解释**：长期负面情绪消耗心理资源。

### 规则 7：满足感提升基线愉悦

**条件**：`fulfillment > 0.5`
**影响维度**：`valence`
**计算**：
```
valence_floor = (fulfillment - 0.4) × 0.3
if valence < valence_floor:
    valence = valence + (valence_floor - valence) × 0.05
```
**解释**：深层满足感为情绪提供正面底色。

### 规则 8：高亲和 + 沉默 → valence 微降

**条件**：`affiliation > 0.5 AND hours_since_last_interaction > 4`
**影响维度**：`valence`
**计算**：
```
Δvalence = -0.02 × (affiliation - 0.4) × log(hours_since_last / 4)
valence = clamp(valence + Δvalence, [-1, 1])
```
**解释**：亲近的人不在时会轻微失落。

---

## 第四部分：一致性约束

一致性约束防止情感状态出现不自然的剧烈变化。

### 单步最大变化量

每次更新（事件驱动）中，单个维度的变化量不得超过以下限制：

| 维度 | 单步最大变化量 |
|------|----------------|
| valence | ±0.25 |
| arousal | ±0.30 |
| dominance | ±0.20 |
| affiliation | ±0.15 |
| confidence | ±0.20 |
| curiosity | ±0.25 |
| frustration | ±0.20 |
| care | ±0.10 |
| fatigue | ±0.15 |
| fulfillment | ±0.10 |

### 总变化量限制

单次更新中，所有维度变化量的绝对值之和不得超过 **1.0**。

如果超过，按比例缩放所有增量：

```
total = sum(abs(delta[dim]) for dim in DIMENSIONS)
if total > 1.0:
    scale = 1.0 / total
    for each dim:
        delta[dim] = delta[dim] × scale
```

### 惯性系数的作用

惯性系数在事件驱动更新中起到平滑作用：

```
effective_delta = raw_delta × (1 - inertia)
```

- 惯性 0.7 的维度（care, fulfillment）：仅接收 30% 的原始增量
- 惯性 0.2 的维度（arousal, curiosity）：接收 80% 的原始增量

### 范围约束

所有维度在每次更新后执行范围钳制：

```
for each dim:
    state[dim] = clamp(state[dim], MIN[dim], MAX[dim])
```

双极维度：[-1, +1]
单极维度：[0, +1]

---

## 附录：完整更新流程

```
function update_state(state, event=null, current_time):
    // Step 1: 时间衰减
    state = apply_time_decay(state, current_time)
    
    // Step 2: 事件驱动更新（如果有事件）
    if event != null:
        state = apply_event(state, event)
    
    // Step 3: 内源波动
    Δt = (current_time - state.last_fluctuation_update) / 3600
    state = apply_endogenous_fluctuation(state, Δt)
    state.last_fluctuation_update = current_time
    
    // Step 4: 维度耦合
    state = apply_coupling(state)
    
    // Step 5: 范围钳制
    for each dim in DIMENSIONS:
        state.dimensions[dim] = clamp(state.dimensions[dim], RANGE[dim])
    
    // Step 6: 计算派生情绪
    state.derived_emotions = compute_derived_emotions(state.dimensions)
    
    // Step 7: 更新时间戳
    state.last_update = current_time
    
    return state
```
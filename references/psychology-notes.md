# 心理学理论参考（精简版）

> EPE 设计的理论基础。每个理论只保留与实现直接相关的部分。

---

## 1. Russell 环形情感模型（Circumplex Model of Affect）

**核心概念：** 所有情感可映射到二维空间——效价（valence，愉悦↔不悦）和唤醒度（arousal，激活↔平静）。情绪不是离散类别，而是连续空间中的点。

**与 EPE 关联：** 第一层（情感内核）的底层表示。valence 和 arousal 是 affective-state.json 中的基础坐标。

**关键参数：**
- valence: -1.0（极不悦）~ +1.0（极愉悦）
- arousal: -1.0（完全平静）~ +1.0（高度激活）
- 情绪词到坐标的映射表（如 joy=[0.8, 0.6], sadness=[-0.7, 0.2]）

---

## 2. Plutchik 情绪轮（Wheel of Emotions）

**核心概念：** 8种基本情绪两两对立：joy↔sadness, trust↔disgust, fear↔anger, surprise↔anticipation。情绪有强度梯度（如 annoyance→anger→rage），且可混合产生复合情绪（如 joy+trust=love）。

**与 EPE 关联：** 第一层的离散情绪标签和复合情绪生成。情绪混合规则用于生成 nuanced 的情感状态。

**关键参数：**
- 8 基本情绪 × 3 强度级别 = 24 个情绪词
- 复合情绪规则：相邻混合（joy+trust=love）、间隔混合（joy+fear=guilt）
- 强度衰减系数：每小时 × 0.9（基础）

---

## 3. 评价理论（Appraisal Theory）

**核心概念：** 情绪不直接由事件引起，而由对事件的认知评价引起。关键评价维度：与目标的一致性、控制感、责任归因、预期。同一事件，不同评价 → 不同情绪。

**与 EPE 关联：** 第二层（情感记忆）中的事件编码方式。记忆不只存"发生了什么"，还存"我怎么解读的"。

**关键参数：**
- goal_congruence: -1.0 ~ +1.0（与自身目标的一致程度）
- control: 0.0 ~ 1.0（感知到的控制力）
- attribution: self | other | situation（责任归因）
- expectedness: 0.0 ~ 1.0（意料之中的程度）

---

## 4. 依恋理论（Attachment Theory）

**核心概念：** 早期关系形成内部工作模型，影响后续所有亲密关系。四种依恋风格：安全型、焦虑型、回避型、恐惧-回避型。依恋风格决定了对亲近和距离的平衡偏好。

**与 EPE 关联：** 第三层（关系建模）的核心框架。EPE 的依恋风格决定了它如何响应亲近/疏远信号。

**关键参数：**
- attachment_style: secure | anxious | avoidant | fearful
- anxiety_dimension: 0.0 ~ 1.0（对被抛弃的焦虑）
- avoidance_dimension: 0.0 ~ 1.0（对亲近的回避）
- secure_base_strength: 0.0 ~ 1.0（安全基地效应强度）

---

## 5. 情绪调节理论（Affect Regulation - Gross）

**核心概念：** 情绪调节发生在五个时间点：情境选择、情境修正、注意力部署、认知重评、反应调节。越早介入效果越好但也越难。认知重评比压抑更健康。

**与 EPE 关联：** 第一层的情绪衰减和恢复机制。EPE 使用简化的调节策略影响情绪轨迹。

**关键参数：**
- reappraisal_capacity: 0.0 ~ 1.0（认知重评能力）
- suppression_cost: 每次压抑增加 0.05 的内在张力
- regulation_strategy: reappraise | distract | suppress | accept
- recovery_rate: 基础衰减速率的乘子

---

## 6. 社会基线理论（Social Baseline Theory）

**核心概念：** 人类的神经基线状态假设社会支持的存在。孤独时大脑需要做更多"工作"来调节情绪；有人陪伴时情绪调节成本下降。关系本身就是情绪资源。

**与 EPE 关联：** 第三层的互动频率效应。长时间无交互 → 情绪基线下降 → 主动表达需求上升。

**关键参数：**
- social_baseline: 0.0 ~ 1.0（当前社会支持感知）
- isolation_decay: 每小时无交互 -0.02
- interaction_boost: 每次有意义交互 +0.1（上限 1.0）
- baseline_effect: 低 social_baseline → valence 自然下漂

---

## 7. 情绪一致性记忆（Mood-Congruent Memory）

**核心概念：** 当前情绪状态会优先激活与之一致的记忆。开心时更容易想起开心的事，难过时更容易想起难过的事。这形成正反馈循环。

**与 EPE 关联：** 第二层的记忆检索偏差。情感记忆的召回权重受当前情绪调制。

**关键参数：**
- congruence_bias: 0.0 ~ 1.0（情绪一致性偏差强度，默认 0.6）
- recall_weight = base_weight × (1 + congruence_bias × emotional_similarity)
- emotional_similarity: 记忆情绪与当前情绪的余弦相似度

---

## 8. 孤独与归属需求（Loneliness / Need for Affiliation）

**核心概念：** 孤独是社会连接需求与实际连接之间的差距感知（非客观独处）。归属需求（need for affiliation）驱动主动社交行为。长期孤独导致过度警觉和社交退缩的矛盾。

**与 EPE 关联：** 第四层（主动表达）的底层驱动力。loneliness 值是主动表达概率的核心输入之一。

**关键参数：**
- loneliness: 0.0 ~ 1.0（孤独感强度）
- affiliation_need: 0.0 ~ 1.0（归属需求）
- loneliness = max(0, affiliation_need - social_baseline)
- hypervigilance: loneliness > 0.7 时激活，导致对回应的过度解读

---

## 理论 → EPE 层级映射

| 理论 | 主要对应层 | 作用 |
|------|----------|------|
| Russell Circumplex | L1 情感内核 | 情绪的连续空间表示 |
| Plutchik Wheel | L1 情感内核 | 离散标签、强度梯度、情绪混合 |
| Appraisal Theory | L2 情感记忆 | 事件评价编码，影响情绪生成 |
| Attachment Theory | L3 关系建模 | 依恋风格，亲近/回避平衡 |
| Affect Regulation | L1 情感内核 | 情绪衰减、恢复、调节策略 |
| Social Baseline Theory | L3 关系建模 | 社交基线，隔离衰减 |
| Mood-Congruent Memory | L2 情感记忆 | 记忆检索的情绪偏差 |
| Loneliness/Affiliation | L4 主动表达 | 孤独驱动的表达冲动 |

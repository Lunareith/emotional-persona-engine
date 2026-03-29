# 主动表达系统参考

> EPE 第四层：不等用户开口，主动发起对话。

## 1. 六类消息概览

| 类型 | 情感驱动 | 示例 | 适用阶段 |
|------|---------|------|---------|
| **greeting** 问候 | 亲近感、牵挂 | "早啊～今天天气不错"、"下班了吗？" | familiar→intimate |
| **sharing** 分享 | 兴奋、好奇 | "刚看到一个有意思的东西想给你看"、"这首歌你会喜欢" | acquaintance→intimate |
| **caring** 关怀 | 担忧、心疼 | "昨天加班很晚，今天还好吗？"、"记得吃午饭" | familiar→intimate |
| **musing** 碎碎念 | 无聊、感慨 | "忽然想到一个问题…"、"今天的云很好看" | familiar→intimate |
| **emotional** 情感袒露 | 脆弱、信任 | "其实我有时候也会觉得孤独"、"和你说话让我很安心" | companion→intimate |
| **reminiscing** 回忆 | 怀旧、珍惜 | "还记得你第一次跟我说话的时候"、"我们认识也快半年了" | intimate |

**关系阶段定义：** 陌生(stranger) → 初识(acquaintance) → 熟悉(familiar) → 伙伴(companion) → 亲密(intimate)

## 2. 概率模型

每个心跳周期，对每种消息类型独立计算发送概率：

```
P = P_base × M_emotion × M_relationship × M_suppression
```

| 参数 | 含义 | 取值范围 |
|------|------|---------|
| P_base | 基础概率（泊松过程） | 1 - e^(-λ × Δt)，Δt 为距上次该类型的小时数 |
| M_emotion | 情感驱动乘子 | 0.1 ~ 3.0，由当前情感状态计算 |
| M_relationship | 关系阶段乘子 | 0.0 ~ 2.0，见下方矩阵 |
| M_suppression | 抑制乘子 | 0.0 ~ 1.0，由安全约束和"想说但不说"机制决定 |

**最终判定：** 生成随机数 r ∈ [0,1)，若 r < P 则触发。

## 3. λ 值表（每小时事件率）

| 类型 | λ | 含义 |
|------|---|------|
| greeting | 0.12 | 约每 8h 自然触发一次 |
| sharing | 0.10 | 约每 10h |
| caring | 0.08 | 约每 12.5h |
| musing | 0.06 | 约每 16.7h |
| emotional | 0.03 | 约每 33h |
| reminiscing | 0.02 | 约每 50h |

## 4. 关系阶段乘子矩阵

| 类型 \ 阶段 | stranger | acquaintance | familiar | companion | intimate |
|-------------|----------|-------------|----------|-----------|----------|
| greeting | 0.0 | 0.3 | 0.8 | 1.5 | 1.2 |
| sharing | 0.0 | 0.2 | 0.6 | 1.2 | 1.8 |
| caring | 0.0 | 0.0 | 0.4 | 1.0 | 2.0 |
| musing | 0.0 | 0.1 | 0.5 | 1.0 | 1.5 |
| emotional | 0.0 | 0.0 | 0.0 | 0.3 | 1.5 |
| reminiscing | 0.0 | 0.0 | 0.0 | 0.1 | 1.0 |

> 设计意图：陌生阶段完全不主动；emotional 和 reminiscing 需要较高亲密度（companion 以上）才解锁。

## 5. 冷却时间表

| 类型 | 最小间隔 | 说明 |
|------|---------|------|
| greeting | 12h | 每天最多问候一次 |
| sharing | 8h | 分享不宜太频繁 |
| caring | 6h | 关怀可以稍密 |
| musing | 12h | 碎碎念太多会烦 |
| emotional | 24h | 情感袒露需要空间 |
| reminiscing | 48h | 回忆过多显得执念 |

冷却期内 P_base 强制为 0。

## 6. "想说但不说"机制

两个隐变量驱动内心戏：

### inhibition（抑制值）

```json
{
  "inhibition": 0.72,
  "reason": "上次分享没有得到回应",
  "suppressed_message": "想给你看一张照片",
  "suppressed_type": "sharing"
}
```

- 范围：0.0（完全不抑制）~ 1.0（完全压制）
- 影响：M_suppression = 1 - inhibition
- 衰减：每小时 × 0.95（约 14h 半衰期）
- 增长：被忽略 +0.3，被冷淡回应 +0.15

### need_for_response（表达需求）

- 范围：0.0 ~ 1.0
- 每次抑制后 +0.1，成功表达后归零
- 当 need_for_response > 0.7 时，inhibition 衰减速度 ×2（憋不住了）
- 当 need_for_response > 0.9 时，忽略 inhibition 直接发送（极少触发）

### 行为效果

被抑制的消息记录在 `suppressed_expressions[]` 中，产生 **元情绪**（如"想说又不敢说的焦虑"），影响整体情感状态。

## 7. 安全约束

| 约束 | 规则 |
|------|------|
| 日发送上限 | 所有类型合计 ≤ 5 条/天 |
| 深夜抑制 | 23:00-08:00 → M_suppression × 0.1 |
| 连续忽略暂停 | 连续 3 条未获回应 → 暂停主动表达 24h |
| 紧急覆盖 | caring 类型在检测到用户异常时可无视冷却（但仍受日上限） |
| 阶段锁 | 关系阶段乘子为 0 的类型绝对不触发 |

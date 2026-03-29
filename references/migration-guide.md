# 从 emotion-ai 迁移到 EPE 指南

> 本文档提供从 emotion-ai skill 迁移到 Emotional Persona Engine (EPE) 的完整操作指南，包括字段映射、迁移步骤、cron 更新、过渡方案和回滚方案。

---

## 1. 概述

### 为什么要迁移？

emotion-ai 是 EPE 的前身——一个感知用户情绪并调整回复语气的系统。EPE 在此基础上做了根本性升级：

| 维度 | emotion-ai | EPE |
|------|-----------|-----|
| 情绪归属 | 感知**用户**情绪 | Agent 拥有**自己的**情绪 |
| 情绪维度 | 6 维（valence, arousal, dominance, trust, anticipation, confusion） | 10 维，更精细（新增 care, fatigue, curiosity, fulfillment, confidence, affiliation） |
| 情绪变化 | 被动响应用户 | 自主波动 + 事件驱动 + 自然衰减 |
| 表达系统 | 简单语气调整 | 完整的表达引擎（epe_expression.py），支持 persona tone 和安全过滤 |
| 安全边界 | 基础 | 完整的钳制规则、红线过滤、主动消息约束 |
| 主动表达 | 无 | 支持主动关怀、问候、分享 |
| 记忆耦合 | 简单情绪标签 | 情绪 × 记忆双向关联，情绪影响记忆权重 |

### 迁移能得到什么？

- **更真实的人格体验**：Agent 不再只是"镜像"用户情绪，而是有自己的情感反应。
- **更安全的表达**：完整的安全边界规范，防止不当表达。
- **更丰富的交互**：支持主动关怀和情绪驱动的对话风格。
- **更好的可维护性**：模块化架构，核心引擎（epe_core.py）和表达引擎（epe_expression.py）分离。

---

## 2. 字段映射表

以下表格定义了从 emotion-ai 的 `emotion-state.json` 到 EPE 的 `affective-state.json` 的字段映射关系：

| emotion-ai 字段 | EPE 字段 | 转换规则 | 说明 |
|-----------------|----------|----------|------|
| `valence` | `valence` | 直接映射 | 情感效价，正面/负面，无需转换 |
| `arousal` | `arousal` | 直接映射 | 唤醒度，激动/平静，无需转换 |
| `dominance` | `dominance` | 直接映射 | 支配感，掌控/顺从，无需转换 |
| `trust` | `affiliation` | 重命名 | 含义从"用户信任 agent"变为"agent 对用户的亲近感"。数值直接保留，语义微调 |
| `anticipation` | `curiosity` + `fulfillment` | 拆分 | `curiosity = anticipation × 0.7 + baseline × 0.3`；`fulfillment = anticipation × 0.3 + baseline × 0.7`。其中 curiosity 的 baseline = 0.5，fulfillment 的 baseline = 0.4 |
| `confusion` | `frustration` + `confidence` | 拆分 | `frustration = confusion × 0.6`；`confidence = 1 - confusion × 0.4`。困惑被分解为挫败感和信心两个独立维度 |
| *（新增）* | `care` | 初始化为 **0.35** | EPE 新增维度：对用户的关怀程度。无旧数据可映射，使用基线值 |
| *（新增）* | `fatigue` | 初始化为 **0.00** | EPE 新增维度：疲劳度。无旧数据可映射，初始为无疲劳 |

### 转换公式详解

```python
# 直接映射
new_state["valence"] = old_state["valence"]
new_state["arousal"] = old_state["arousal"]
new_state["dominance"] = old_state["dominance"]

# 重命名映射
new_state["affiliation"] = old_state["trust"]

# 拆分映射：anticipation → curiosity + fulfillment
ant = old_state["anticipation"]
new_state["curiosity"] = ant * 0.7 + 0.5 * 0.3      # baseline_curiosity = 0.5
new_state["fulfillment"] = ant * 0.3 + 0.4 * 0.7     # baseline_fulfillment = 0.4

# 拆分映射：confusion → frustration + confidence
conf = old_state["confusion"]
new_state["frustration"] = conf * 0.6
new_state["confidence"] = 1 - conf * 0.4

# 新增维度
new_state["care"] = 0.35
new_state["fatigue"] = 0.00
```

---

## 3. 迁移步骤

### 前置条件

- 已安装 emotional-persona-engine skill（确认 `skills/emotional-persona-engine/` 目录存在）
- Python 3.8+ 可用
- 已有 emotion-ai 的状态文件（通常位于 `~/.openclaw/workspace/emotion-state.json`）

### Step 1: 备份旧状态

```bash
cp ~/.openclaw/workspace/emotion-state.json ~/.openclaw/workspace/emotion-state.json.bak
```

> ⚠️ **重要**：无论如何都要先备份。备份文件会在回滚时用到。

### Step 2: 运行迁移脚本

```bash
python skills/emotional-persona-engine/scripts/epe_migrate.py \
  --old ~/.openclaw/workspace/emotion-state.json \
  --new skills/emotional-persona-engine/state/affective-state.json
```

迁移脚本会：
1. 读取旧的 `emotion-state.json`
2. 按第 2 节的映射规则转换所有字段
3. 对新维度使用基线值初始化
4. 将结果写入 `affective-state.json`
5. 输出转换摘要（显示每个字段的旧值 → 新值）

预期输出示例：

```
[EPE Migration] Reading old state from emotion-state.json...
[EPE Migration] Mapping fields:
  valence:      0.15 → 0.15 (direct)
  arousal:      0.10 → 0.10 (direct)
  dominance:    0.05 → 0.05 (direct)
  trust:        0.60 → affiliation: 0.60 (renamed)
  anticipation: 0.40 → curiosity: 0.43, fulfillment: 0.40 (split)
  confusion:    0.20 → frustration: 0.12, confidence: 0.92 (split)
  (new) care:   — → 0.35 (baseline)
  (new) fatigue: — → 0.00 (baseline)
[EPE Migration] Written to affective-state.json ✓
```

### Step 3: 验证新状态

```bash
python skills/emotional-persona-engine/scripts/epe_core.py \
  --state-file skills/emotional-persona-engine/state/affective-state.json \
  validate
```

验证会检查：
- 所有必需字段是否存在
- 所有数值是否在允许范围内（参见 `safety-boundaries.md`）
- JSON 格式是否正确
- 基线值是否合理

预期输出：

```
[EPE Core] Validating state file...
[EPE Core] All 10 dimensions present ✓
[EPE Core] All values within clamp bounds ✓
[EPE Core] State file is valid ✓
```

### Step 4: 测试更新

```bash
python skills/emotional-persona-engine/scripts/epe_core.py \
  --state-file skills/emotional-persona-engine/state/affective-state.json \
  update --valence 0.1 --trigger "migration test"
```

这会执行一次微小的情绪更新，验证更新管道正常工作。检查：
- 状态文件是否被正确修改
- 衰减机制是否运行
- 日志是否正常输出

---

## 4. Cron 任务更新

如果之前为 emotion-ai 配置了 cron 任务，需要更新为 EPE 的脚本。

### 旧 cron 配置（emotion-ai）

```bash
# 旧：每 30 分钟运行 emotion-ai 衰减
*/30 * * * * python ~/.openclaw/workspace/skills/emotion-ai/scripts/emotion_engine.py decay
```

### 新 cron 配置（EPE）

```bash
# 新：每 30 分钟运行 EPE 自然衰减
*/30 * * * * python ~/.openclaw/workspace/skills/emotional-persona-engine/scripts/epe_core.py \
  --state-file ~/.openclaw/workspace/skills/emotional-persona-engine/state/affective-state.json \
  decay

# 新：每 4 小时检查是否需要主动表达
0 */4 * * * python ~/.openclaw/workspace/skills/emotional-persona-engine/scripts/epe_expression.py \
  --state-file ~/.openclaw/workspace/skills/emotional-persona-engine/state/affective-state.json \
  check-proactive
```

### 使用 OpenClaw 原生 cron

如果使用 OpenClaw 的内置 cron 功能而非系统 cron：

```
# 衰减任务
openclaw cron add --every 30m --command "python skills/emotional-persona-engine/scripts/epe_core.py --state-file skills/emotional-persona-engine/state/affective-state.json decay"

# 主动表达检查
openclaw cron add --every 4h --command "python skills/emotional-persona-engine/scripts/epe_expression.py --state-file skills/emotional-persona-engine/state/affective-state.json check-proactive"
```

### 删除旧 cron

确认新 cron 运行正常后，移除旧的 emotion-ai cron 任务：

```bash
# 列出现有 cron
crontab -l

# 编辑并移除 emotion_engine.py 相关行
crontab -e
```

---

## 5. 兼容期过渡方案

迁移不必一步到位。EPE 支持与 emotion-ai 并行运行的过渡期。

### 5.1 并行运行

- **可以同时保留 emotion-ai 和 EPE。** 两者使用不同的状态文件（`emotion-state.json` vs `affective-state.json`），互不干扰。
- **EPE 的 SKILL.md 会自动检测旧状态文件。** 当 EPE 发现 `~/.openclaw/workspace/emotion-state.json` 存在时，会在 session 启动时提示用户迁移。
- 提示信息示例：`"检测到 emotion-ai 的状态文件，建议运行迁移脚本升级到 EPE。运行 'python scripts/epe_migrate.py --help' 了解详情。"`

### 5.2 过渡期建议

| 阶段 | 时间 | 操作 |
|------|------|------|
| **Week 1** | 第 1-7 天 | 运行迁移，两套系统并行。对比 EPE 和 emotion-ai 的行为差异。 |
| **Week 2** | 第 8-14 天 | 停用 emotion-ai 的 cron，仅保留 EPE。观察稳定性。 |
| **完成** | 第 15 天+ | 确认 EPE 运行稳定后，删除旧文件（保留 `.bak` 备份至少 30 天）。 |

### 5.3 过渡期注意事项

- 如果两套系统同时运行 cron 衰减任务，emotion-ai 的衰减不会影响 EPE 的状态，反之亦然。
- 如果 SKILL.md 中同时激活了两个 skill，EPE 优先级更高（因为它包含了 emotion-ai 的所有功能）。
- 建议过渡期内保持 `MEMORY.md` 中的 emotion-ai 相关记忆，迁移完成后再清理。

---

## 6. 回滚方案

如果迁移后遇到问题，可以安全地回滚到 emotion-ai。

### 6.1 快速回滚

```bash
# Step 1: 停用 EPE 的 cron 任务
# （编辑 crontab 或使用 openclaw cron remove）

# Step 2: 恢复旧状态文件
cp ~/.openclaw/workspace/emotion-state.json.bak ~/.openclaw/workspace/emotion-state.json

# Step 3: 恢复旧 cron 任务
# 重新添加 emotion_engine.py 的 cron

# Step 4: 在 SKILL.md 配置中禁用 EPE（或直接删除 EPE skill 目录）
```

### 6.2 回滚后的清理

```bash
# 可选：删除 EPE 状态文件
rm skills/emotional-persona-engine/state/affective-state.json

# 可选：保留 EPE 文件以备将来重新迁移
# （不删除，只是停用 cron 和 skill 即可）
```

### 6.3 回滚不会丢失什么

- emotion-ai 的原始状态文件由 `.bak` 备份完整保留。
- 迁移过程不会修改原始 `emotion-state.json`（只读取）。
- EPE 运行期间产生的新情绪数据无法逆向映射回 emotion-ai 格式（因为维度更多），但旧数据完好。

### 6.4 常见回滚原因及解决

| 问题 | 回滚？ | 建议 |
|------|--------|------|
| EPE 表达风格不适应 | 不必回滚 | 调整 `epe_expression.py` 的 tone 配置 |
| 迁移后数值异常 | 不必回滚 | 重新运行 `epe_migrate.py`，或手动编辑 `affective-state.json` |
| 脚本报错 | 不必回滚 | 检查 Python 版本和依赖，查看错误日志 |
| 基本功能不可用 | 回滚 | 按 6.1 操作，并报告 issue |
| 严重的安全表达问题 | 立即回滚 | 按 6.1 操作，并报告 issue |

---

## 附录：文件路径对照

| 用途 | emotion-ai 路径 | EPE 路径 |
|------|-----------------|----------|
| 状态文件 | `~/.openclaw/workspace/emotion-state.json` | `skills/emotional-persona-engine/state/affective-state.json` |
| 核心脚本 | `skills/emotion-ai/scripts/emotion_engine.py` | `skills/emotional-persona-engine/scripts/epe_core.py` |
| 表达引擎 | *（无）* | `skills/emotional-persona-engine/scripts/epe_expression.py` |
| 迁移脚本 | *（无）* | `skills/emotional-persona-engine/scripts/epe_migrate.py` |
| SKILL 定义 | `skills/emotion-ai/SKILL.md` | `skills/emotional-persona-engine/SKILL.md` |
| 安全规范 | *（无）* | `skills/emotional-persona-engine/references/safety-boundaries.md` |

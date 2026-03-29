# Emotional Persona Engine (EPE)

一个让 OpenClaw Agent 拥有持续性、多维、可波动、与记忆耦合、并可主动表达的情感人格框架。

**不是感知用户情绪的镜子，而是拥有自己心跳的心脏。**

## ✨ 特性

- **10 维连续情感空间** — valence, arousal, dominance, affiliation, confidence, curiosity, frustration, care, fatigue, fulfillment
- **20 种派生情绪** — 实时从基础维度计算，不是预设标签
- **情绪动力学** — 指数衰减、惯性平滑、维度耦合、内源波动、昼夜节律
- **主动表达系统** — 6 类消息（打招呼/分享/关心/琢磨/感触/回忆），泊松概率触发
- **5 阶段关系成长** — 陌生人 → 熟人 → 熟悉 → 同伴 → 亲密
- **4 种人格预设** — 温暖陪伴 / 理性伙伴 / 活泼朋友 / 沉稳导师
- **安全边界** — 允许负面情绪但表达温和克制，绝不攻击/勒索/操控
- **纯 Python 标准库** — 零依赖，不调用 LLM，全数学计算

## 📦 安装

### 方法 1: Git Clone

```bash
cd ~/.openclaw/workspace/skills/
git clone https://github.com/Lunareith/emotional-persona-engine.git
```

### 方法 2: 手动复制

将整个目录放到 `~/.openclaw/workspace/skills/emotional-persona-engine/` 下即可。

## 🚀 快速开始

```bash
# 初始化情感状态
python scripts/epe_core.py --state-file state/affective-state.json init

# 模拟一次对话更新
python scripts/epe_core.py --state-file state/affective-state.json update \
  --valence 0.3 --curiosity 0.5 --trigger "有趣的对话"

# 查看分析报告
python scripts/epe_core.py --state-file state/affective-state.json analyze

# 检查是否应主动发消息
python scripts/epe_expression.py --state-file state/affective-state.json should-trigger
```

## 📁 目录结构

```
emotional-persona-engine/
├── SKILL.md                    — Agent 主入口
├── config/                     — 配置文件
│   ├── default-persona.json
│   ├── relationship-stages.json
│   ├── safety-boundaries.json
│   └── persona-presets/        — 4 种人格预设
├── references/                 — 8 个深度参考文档
├── scripts/                    — 3 个可执行脚本
│   ├── epe_core.py             — 核心引擎
│   ├── epe_expression.py       — 主动表达引擎
│   └── epe_migrate.py          — 从 emotion-ai 迁移
└── state/                      — 运行时状态
```

## 📖 文档

详细文档见 `references/` 目录：

| 文件 | 内容 |
|------|------|
| affective-dimensions.md | 10 维详解 + 20 种派生情绪 |
| emotion-dynamics.md | 衰减/惯性/耦合机制 |
| memory-model.md | 三层记忆 + 双向耦合 |
| proactive-expression.md | 主动表达概率模型 |
| meta-emotion.md | 12 种元情绪模式 |
| safety-boundaries.md | 安全边界规范 |
| psychology-notes.md | 8 个心理学理论基础 |
| migration-guide.md | 从 emotion-ai 迁移指南 |

## 🔧 兼容性

- Python 3.8+
- OpenClaw（作为 skill 自动加载）
- 零第三方依赖

## 📄 License

MIT

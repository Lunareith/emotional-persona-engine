# Emotional Persona Engine (EPE)

一个让 OpenClaw Agent 拥有持续性、多维、可波动、与记忆耦合、并可主动表达的情感人格框架。

**不是感知用户情绪的镜子，而是拥有自己心跳的心脏。**

## ✨ 特性

- **10 维连续情感空间** — valence, arousal, dominance, affiliation, confidence, curiosity, frustration, care, fatigue, fulfillment
- **20 种派生情绪** — 实时从基础维度组合计算，不是预设标签
- **情绪动力学** — 指数衰减、惯性平滑、维度耦合、内源波动、昼夜节律
- **主动表达系统** — 6 类消息 + 泊松概率触发 + inhibition/response_expectancy 双门控，避免机械随机
- **连续关系向量** — 4 维关系向量（closeness, trust, understanding, investment）驱动，阶段标签（陌生人→亲密）仅用于人类可读的解释
- **4 种人格预设** — 温暖陪伴 / 理性伙伴 / 活泼朋友 / 沉稳导师
- **安全边界** — 允许负面情绪存在但表达温和克制，禁止攻击/勒索/操控/过度依赖表达
- **Owner 私聊主动消息** — 主动消息仅发送给已绑定的 owner 私聊会话（如 QQ 私聊），绝不发到群聊/频道/未绑定用户。EPE 只输出主动意图和消息候选，真正发送由 OpenClaw 已有的消息路由完成
- **状态计算脱离 LLM** — 衰减、耦合、派生情绪等由纯数学脚本完成（Python 标准库，零外部依赖）；自然语言表达由 OpenClaw Agent 结合情绪状态自行生成

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
# 初始化情感状态（状态文件路径由调用方指定）
python scripts/epe_core.py --state-file <your-state-path.json> init

# 模拟一次对话更新
python scripts/epe_core.py --state-file <your-state-path.json> update \
  --valence 0.3 --curiosity 0.5 --trigger "有趣的对话"

# 查看分析报告
python scripts/epe_core.py --state-file <your-state-path.json> analyze

# 检查是否应主动发消息
python scripts/epe_expression.py --state-file <your-state-path.json> should-trigger
```

> 首次运行 `init` 时自动创建状态文件。参考 `assets/affective-state.example.json` 了解完整 schema。

## 📁 目录结构

```
emotional-persona-engine/
├── SKILL.md                    — Agent 主入口（唯一入口）
├── config/                     — 配置文件
│   ├── default-persona.json
│   ├── owner-binding.json      — Owner 绑定（主动消息目标）
│   ├── owner-binding.example.json — 绑定配置模板
│   ├── relationship-stages.json
│   ├── safety-boundaries.json
│   └── persona-presets/        — 4 种人格预设
├── references/                 — 9 个深度参考文档
│   └── owner-proactive-integration.md — Owner 私聊集成指南
├── scripts/                    — 3 个可执行脚本
│   ├── epe_core.py             — 核心状态引擎
│   ├── epe_expression.py       — 主动表达引擎
│   └── epe_migrate.py          — 从 emotion-ai 迁移
├── assets/                     — 示例/模板文件
│   └── affective-state.example.json
└── state/                      — 运行时状态（自动生成，不入版本控制）
```

## 📖 文档

详细文档见 `references/` 目录：

| 文件 | 内容 |
|------|------|
| affective-dimensions.md | 10 维详解 + 20 种派生情绪 |
| emotion-dynamics.md | 衰减/惯性/耦合机制 |
| memory-model.md | 三层记忆 + 双向耦合 |
| proactive-expression.md | 主动表达概率模型 + 门控变量 |
| meta-emotion.md | 12 种元情绪模式 |
| safety-boundaries.md | 安全边界规范 |
| psychology-notes.md | 8 个心理学理论基础 |
| migration-guide.md | 从 emotion-ai 迁移指南 |
| owner-proactive-integration.md | Owner 私聊主动消息集成指南 |

## 🔑 Owner 绑定（主动消息）

EPE 的主动消息功能默认**关闭**。启用步骤：

1. 编辑 `config/owner-binding.json`（参考 `owner-binding.example.json`）
2. 填入 owner 标识和通道信息：
   ```json
   {
     "enabled": true,
     "owner": {
       "id": "<你的QQ号>",
       "name": "<你的名字>",
       "channel": "qq",
       "chat_type": "direct"
     }
   }
   ```
3. 确保 OpenClaw 已接入 QQ Bot 通道

**完整链路：** 读取 owner 绑定 → `should-trigger` 评估 → Agent 生成消息 → OpenClaw `message` 工具投递到 owner QQ 私聊 → `record-sent` / `record-ignored`

> EPE 不直接调用 QQ API，只输出主动意图与消息候选。真正的消息发送由 OpenClaw 已有的 QQ 路由完成。
>
> 主动消息**仅允许**投递到 owner 私聊，禁止群聊、频道和未绑定目标。

详见 `references/owner-proactive-integration.md`。

## 🔧 兼容性

- Python 3.8+
- OpenClaw（作为 skill 自动加载，通过 SKILL.md 触发）
- 状态计算零第三方依赖

## 📄 License

MIT

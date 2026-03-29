# state/ 目录

⚠️ **此目录由 emotional-persona-engine 运行时自动管理，请勿手动编辑。**

运行时会在此目录下自动创建和维护以下文件：

- `current-emotion.json` — 当前情感状态向量
- `relationship.json` — 用户关系阶段与积分
- `emotion-history.json` — 情感变化历史记录
- `memory-anchors.json` — 情感记忆锚点

这些文件会在每次对话中被读取和更新。手动修改可能导致情感状态不一致或系统异常。

如需重置情感状态，请使用 skill 提供的重置机制，而非直接删除或编辑文件。

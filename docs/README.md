# CrossPost 项目文档

本目录汇总了项目的需求文档、设计文档和进度状态，供人阅读。原始的 GSD 工作流状态文件仍保留在 [`.planning/`](../.planning/)（隐藏目录），本目录下的内容是整理并审计后的可读副本，不影响 GSD 命令（`/gsd:progress` 等）的正常工作。

## 先看这个

- **[STATUS.md](STATUS.md)** — 需求完成情况总览：哪些做完了、哪些做了但没测过、哪些还没开始

## 需求与设计

- **[REQUIREMENTS.md](REQUIREMENTS.md)** — 逐条需求 + 对应源码文件 + 完成状态（对照代码审计过）
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — 系统实际架构、模块职责、与早期研究方案的差异
- **[ROADMAP.md](ROADMAP.md)** — 按 Phase 划分的路线图与验收标准核对
- **[PROJECT.md](PROJECT.md)** — 项目最初的产品定义（目标、约束、关键决策）

## 历史记录（未改写，原样归档）

- **[research/](research/)** — 立项时的技术调研（架构模式、技术栈选型、常见坑）
- **[phases/](phases/)** — 各 Phase 的执行计划（PLAN）、执行总结（SUMMARY）、验收报告（VERIFICATION）

## 目录来源对照

| 本目录文件/文件夹 | 来源 |
|---|---|
| `PROJECT.md` | `.planning/PROJECT.md`（原样归档） |
| `REQUIREMENTS.md` | `.planning/REQUIREMENTS.md`（**已更新** — 对照代码重新核实状态） |
| `ARCHITECTURE.md` | 新写 — 综合 `.planning/research/ARCHITECTURE.md` 与实际代码 |
| `ROADMAP.md` | `.planning/ROADMAP.md`（**已更新** — 补充 Phase 3 代码审计结果） |
| `STATUS.md` | 新写 — 本次审计的核心结论 |
| `research/` | `.planning/research/`（原样归档） |
| `phases/` | `.planning/phases/`（原样归档） |

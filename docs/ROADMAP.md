# Roadmap: CrossPost（当前状态版）

> 更新自 `.planning/ROADMAP.md`。原文件里 Phase 3 记录为 "0/TBD，未开始"，但审计代码后发现 Phase 3 的核心代码已经写完（`publisher.py`、`web.py`，均未提交到 GSD 的 phase 计划流程，是在 `.planning` 之外直接开发的）。本文件反映审计后的真实状态；GSD 的 `.planning/ROADMAP.md` 保持不变，供工具链使用。

## Overview

CrossPost is built as a staged pipeline: foundation first（状态机、配置、调度），然后内容获取，然后视频处理与翻译，最后发布到各目标平台并加自动化防护。

## Phase Details

### Phase 1: Pipeline Foundation — ✅ 完成
**Goal**: 无人值守发现、下载并追踪 YouTube 视频
**Requirements**: ACQ-01, ACQ-02, ACQ-03, ACQ-04, AUTO-01, AUTO-02, AUTO-03
**Plans:** 3/3 executed（`01-01`config/状态机、`01-02`RSS+下载、`01-03`调度+崩溃恢复）
**状态**：全部成功标准验证通过，见 [phases/01-pipeline-foundation/01-VERIFICATION.md](phases/01-pipeline-foundation/01-VERIFICATION.md)

### Phase 2: Content Processing — ✅ 完成
**Goal**: 下载的视频被转码、转写、加字幕、翻译成中文素材
**Requirements**: PROC-01, PROC-02, PROC-03, PROC-04, PROC-05
**Plans:** 5/5 executed（`02-01`配置扩展 → `02-02`转码/ASR → `02-03`翻译 → `02-04`字幕烧录 → `02-05`编排器接入调度器）
**状态**：全部成功标准验证通过，见 [phases/02-content-processing/02-VERIFICATION.md](phases/02-content-processing/02-VERIFICATION.md)

### Phase 3: Publishing & Automation — 🟡 代码完成，未走 GSD 计划流程，未经真实平台验证
**Goal**: 处理并翻译后的视频自动发布到各目标平台，带防风控与频率控制
**Requirements**: PUB-01, PUB-02, PUB-03, AUTO-04
**Plans**: 无正式 GSD 计划（`.planning/phases/03-publishing-automation/` 目录存在但为空）——`publisher.py`、`web.py` 是直接在代码库中开发并提交的，跳过了 `/gsd:plan-phase` → `/gsd:execute-phase` 流程

**成功标准逐条核对**（对照 `.planning/ROADMAP.md` 中 Phase 3 的原始定义）：

1. ❓ 处理后的视频自动发布到今日头条和百度百家号（API）—— 代码实现（`ApiPublisher`）已具备，但 `config.example.yaml` 中的 endpoint 是占位符，**从未用真实头条/百家号凭证跑通过**
2. ❓ 处理后的视频通过浏览器自动化发布到小红书，且不触发账号风控 —— `BrowserPublisher` 代码已具备（Playwright + storage_state 持久化会话），**从未针对小红书真实页面结构调试选择器，也未做过风控规避的实测**
3. ✅ 每个平台可配置最小发布间隔，两次发布不会小于该间隔 —— `_rate_limit_allows` + `min_interval_minutes`，有单测覆盖
4. ✅ 发布失败按指数退避重试，超过重试上限后标记 FAILED 且不阻塞其他任务 —— `_record_failure`，有单测覆盖
5. 🟡 端到端无人值守：新视频发现→处理→翻译→发布全自动跑通 —— 流水线代码已经把 `publish_translated_videos` 接入 `scheduler.py` 的轮询任务，逻辑上是自动的；但因为 1、2 未实测，"能跑通"目前只在 `dry_run` backend 下被验证过

**结论**：Phase 3 的**工程骨架**已经完成（4/5 成功标准的代码逻辑到位，1/5 部分到位），但**没有一个平台被真实验证过**，也没有走 GSD 的 research→plan→execute→verify 流程留痕。建议：要么补一轮 `/gsd:plan-phase` 把已有代码补充为正式计划记录，要么在 `.planning/STATE.md` 手动更新进度后，针对每个平台单独跑一次真实凭证的联调验证。

## Progress

| Phase | 计划文档进度 | 代码实际状态 |
|-------|-------------|--------------|
| 1. Pipeline Foundation | 3/3 Complete | ✅ 完成并验证 |
| 2. Content Processing | 5/5 Complete | ✅ 完成并验证 |
| 3. Publishing & Automation | 0/TBD（未规划） | 🟡 代码完成，待真实平台验证 |

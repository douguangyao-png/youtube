# Requirements: CrossPost

**Defined:** 2026-03-14
**Status audited against code:** 2026-07-26 (see method below)
**Core Value:** 自动化完成从海外内容抓取到国内平台发布的全流程，包括下载、转码、翻译、适配和发布，无需人工干预。

> 这是需求追踪表的当前状态版本，取代了 `.planning/REQUIREMENTS.md` 中偏旧的记录（该文件仍保留在 `.planning/` 中供 GSD 工作流使用，不要删除）。状态是通过实际阅读 `src/crosspost/` 源码、运行测试套件（160 passed）核实得出，不是照抄计划文档。

## v1 Requirements

### Content Acquisition (内容获取) — 全部完成

- [x] **ACQ-01**: 通过 YouTube RSS 监控指定频道的新视频和 Shorts — `feeds.py`
- [x] **ACQ-02**: 通过 yt-dlp 下载 YouTube 视频（含元数据：标题、描述、缩略图） — `downloader.py`
- [x] **ACQ-03**: 支持配置要监控的频道列表（YAML 配置文件） — `config.py` (`ChannelConfig`)
- [x] **ACQ-04**: 按视频时长过滤，只下载配置阈值以内的视频（默认 ≤ 3 分钟） — `config.py` (`DownloadConfig.max_duration`)

### Processing (内容处理) — 全部完成

- [x] **PROC-01**: 使用 faster-whisper 本地 ASR 提取英文字幕（SRT 格式） — `transcriber.py`
- [x] **PROC-02**: 英文字幕翻译成中文（保留时间轴，句子级翻译） — `translator.py` (DeepL)
- [x] **PROC-03**: 中文字幕烧录到视频中（支持 CJK 字体，适配竖屏/横屏） — `subtitler.py`
- [x] **PROC-04**: 标题和描述用 LLM 翻译成自然中文（按平台风格适配） — `translator.py` (Claude)
- [x] **PROC-05**: 按各平台规格转码视频（H.264 MP4，分辨率/比例/码率适配） — `transcoder.py`

### Publishing (发布) — 代码已实现，未经真实平台验证

- [x] **PUB-01**: 自动发布到今日头条（头条号 API） — 通用 `ApiPublisher`（`publisher.py`）+ `config.example.yaml` 中的 `toutiao` 平台配置模板
- [x] **PUB-02**: 自动发布到小红书（Playwright 浏览器自动化） — 通用 `BrowserPublisher`（`publisher.py`）+ `xiaohongshu` 平台配置模板
- [x] **PUB-03**: 自动发布到百度百家号（API） — 复用 `ApiPublisher` + `baijiahao` 平台配置模板

  ⚠️ **实现方式与 ROADMAP 原设想不同**：三个平台没有各自独立的 publisher 实现，而是共用一套「配置驱动」的通用 `ApiPublisher` / `BrowserPublisher`，具体的 endpoint、字段名、CSS 选择器都留在 `config.yaml` 里由使用者填写。这意味着代码层面的骨架是完成的，但**从未针对头条/百家号/小红书的真实接口或页面结构验证过**（`config.example.yaml` 里的 endpoint 是占位符 `https://example.com/...`）。首次启用前必须先用 `backend: dry_run` 跑通队列/限流逻辑，再逐平台切到真实 `api`/`browser` 配置并小流量验证。

### Automation (自动化) — 全部完成

- [x] **AUTO-01**: APScheduler 定时轮询 YouTube 频道更新 — `scheduler.py`
- [x] **AUTO-02**: SQLite 去重，防止重复处理和发布 — `models.py` (`Content.video_id` unique)
- [x] **AUTO-03**: 任务状态机（DISCOVERED→DOWNLOADED→PROCESSED→TRANSLATED→PUBLISHED/FAILED），崩溃后可恢复 — `models.py` (`ContentStatus`)
- [x] **AUTO-04**: 发布间隔控制，每个平台可配置最小间隔时间，避免触发反垃圾机制 — `publisher.py` (`_rate_limit_allows`, `min_interval_minutes`)，另附失败重试的指数退避（`_record_failure`）

## 需求之外新增的能力（未在原始 REQUIREMENTS 中定义）

- **Web 管理面板**（`web.py`, `crosspost-web` 命令）：本地只读仪表盘 + 手动提交 YouTube 链接入队 + 触发流水线。
  ⚠️ **与原始范围冲突**：项目最初的 "Out of Scope" 表（见下方）明确把「Web 管理界面」列为不做的功能，理由是"个人使用，配置文件+CLI 足够"。目前该组件已经实现且有独立测试覆盖（`tests/test_web.py`），实际上是范围扩展，而不是遗漏——建议后续要么把它正式补进 REQUIREMENTS，要么明确其定位仅为调试用途。

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap. （尚未开始）

### Publishing Expansion

- **PUB-04**: 自动发布到抖音（Playwright 浏览器自动化，高封号风险）

### Content Sources

- **ACQ-05**: X (Twitter) 内容获取（推文、图片、短视频）
- **PROC-08**: AI 智能剪辑 — 长视频自动提取重点/结论片段，压缩为短视频

### Automation Enhancement

- **AUTO-05**: 规则引擎（按关键词、时长、播放量过滤内容）
- **AUTO-06**: 通知/Webhook（Telegram/邮件通知处理结果和错误）
- **AUTO-07**: 代理轮换支持（应对 IP 限制）

### Content Enhancement

- **PROC-06**: 自动生成中文缩略图
- **PROC-07**: 横屏自动裁切为竖屏（智能居中）

## Out of Scope

| Feature | Reason | 现状 |
|---------|--------|------|
| Web 管理界面 | 个人使用，配置文件+CLI 足够 | ⚠️ 已实现（`web.py`），与本决策冲突，见上方说明 |
| 多用户/SaaS 模式 | 仅个人使用，无需用户管理 | 未做，符合决策 |
| 直播内容搬运 | 与 VOD 处理流程完全不同，复杂度高 | 未做，符合决策 |
| 评论区互动管理 | 只做发布，不做运营 | 未做，符合决策 |
| 视频创意编辑/特效 | 只做格式转换和字幕，不做创意编辑 | 未做，符合决策 |
| AI 原创内容生成 | 只搬运已有内容，不生成新内容 | 未做，符合决策 |
| 平台数据分析回收 | 只做写入（发布），不做读取（数据） | 未做，符合决策 |
| 分布式多机部署 | 单机足够个人使用量 | 未做，符合决策 |

## Traceability

| Requirement | Phase | 计划状态 (.planning) | 代码实际状态 |
|-------------|-------|----------------------|--------------|
| ACQ-01 | Phase 1 | Complete | ✅ Complete |
| ACQ-02 | Phase 1 | Complete | ✅ Complete |
| ACQ-03 | Phase 1 | Complete | ✅ Complete |
| ACQ-04 | Phase 1 | Complete | ✅ Complete |
| PROC-01 | Phase 2 | Complete | ✅ Complete |
| PROC-02 | Phase 2 | Complete | ✅ Complete |
| PROC-03 | Phase 2 | Complete | ✅ Complete |
| PROC-04 | Phase 2 | Complete | ✅ Complete |
| PROC-05 | Phase 2 | Complete | ✅ Complete |
| PUB-01 | Phase 3 | Pending（未规划） | ✅ 代码完成，⚠️ 未经真实接口验证 |
| PUB-02 | Phase 3 | Pending（未规划） | ✅ 代码完成，⚠️ 未经真实页面验证 |
| PUB-03 | Phase 3 | Pending（未规划） | ✅ 代码完成，⚠️ 未经真实接口验证 |
| AUTO-01 | Phase 1 | Complete | ✅ Complete |
| AUTO-02 | Phase 1 | Complete | ✅ Complete |
| AUTO-03 | Phase 1 | Complete | ✅ Complete |
| AUTO-04 | Phase 3 | Pending（未规划） | ✅ Complete |

**Coverage:**
- v1 requirements: 16 total
- 代码已实现: 16/16
- 已在真实平台验证过的发布需求: 0/3（PUB-01/02/03 仍是占位配置，需要真实凭证与联调）

---
*原始需求定义: 2026-03-14*
*状态审计: 2026-07-26 — 对照 `src/crosspost/` 源码与 `pytest`（160 passed）核实*

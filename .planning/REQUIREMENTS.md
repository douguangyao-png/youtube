# Requirements: CrossPost

**Defined:** 2026-03-14
**Core Value:** 自动化完成从海外内容抓取到国内平台发布的全流程，包括下载、转码、翻译、适配和发布，无需人工干预。

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Content Acquisition (内容获取)

- [ ] **ACQ-01**: 通过 YouTube RSS 监控指定频道的新视频和 Shorts
- [ ] **ACQ-02**: 通过 yt-dlp 下载 YouTube 视频（含元数据：标题、描述、缩略图）
- [ ] **ACQ-03**: 支持配置要监控的频道列表（YAML/TOML 配置文件）

### Processing (内容处理)

- [ ] **PROC-01**: 使用 faster-whisper 本地 ASR 提取英文字幕（SRT 格式）
- [ ] **PROC-02**: 英文字幕翻译成中文（保留时间轴，句子级翻译）
- [ ] **PROC-03**: 中文字幕烧录到视频中（支持 CJK 字体，适配竖屏/横屏）
- [ ] **PROC-04**: 标题和描述用 LLM 翻译成自然中文（按平台风格适配）
- [ ] **PROC-05**: 按各平台规格转码视频（H.264 MP4，分辨率/比例/码率适配）

### Publishing (发布)

- [ ] **PUB-01**: 自动发布到今日头条（头条号 API）
- [ ] **PUB-02**: 自动发布到小红书（Playwright 浏览器自动化）
- [ ] **PUB-03**: 自动发布到百度百家号（API）

### Automation (自动化)

- [ ] **AUTO-01**: APScheduler 定时轮询 YouTube 频道更新
- [ ] **AUTO-02**: SQLite 去重，防止重复处理和发布
- [ ] **AUTO-03**: 任务状态机（DISCOVERED→DOWNLOADED→PROCESSED→TRANSLATED→PUBLISHED/FAILED），崩溃后可恢复
- [ ] **AUTO-04**: 发布间隔控制，每个平台可配置最小间隔时间，避免触发反垃圾机制

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Publishing Expansion

- **PUB-04**: 自动发布到抖音（Playwright 浏览器自动化，高封号风险）

### Content Sources

- **ACQ-04**: X (Twitter) 内容获取（推文、图片、短视频）

### Automation Enhancement

- **AUTO-05**: 规则引擎（按关键词、时长、播放量过滤内容）
- **AUTO-06**: 通知/Webhook（Telegram/邮件通知处理结果和错误）
- **AUTO-07**: 代理轮换支持（应对 IP 限制）

### Content Enhancement

- **PROC-06**: 自动生成中文缩略图
- **PROC-07**: 横屏自动裁切为竖屏（智能居中）

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web 管理界面 | 个人使用，配置文件+CLI 足够 |
| 多用户/SaaS 模式 | 仅个人使用，无需用户管理 |
| 直播内容搬运 | 与 VOD 处理流程完全不同，复杂度高 |
| 评论区互动管理 | 只做发布，不做运营 |
| 视频创意编辑/特效 | 只做格式转换和字幕，不做创意编辑 |
| AI 原创内容生成 | 只搬运已有内容，不生成新内容 |
| 平台数据分析回收 | 只做写入（发布），不做读取（数据） |
| 分布式多机部署 | 单机足够个人使用量 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ACQ-01 | Phase 1 | Pending |
| ACQ-02 | Phase 1 | Pending |
| ACQ-03 | Phase 1 | Pending |
| PROC-01 | Phase 2 | Pending |
| PROC-02 | Phase 2 | Pending |
| PROC-03 | Phase 2 | Pending |
| PROC-04 | Phase 2 | Pending |
| PROC-05 | Phase 2 | Pending |
| PUB-01 | Phase 3 | Pending |
| PUB-02 | Phase 3 | Pending |
| PUB-03 | Phase 3 | Pending |
| AUTO-01 | Phase 1 | Pending |
| AUTO-02 | Phase 1 | Pending |
| AUTO-03 | Phase 1 | Pending |
| AUTO-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 after roadmap creation — all 15 requirements mapped*

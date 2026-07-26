# CrossPost — 需求完成状态总览

**生成时间：** 2026-07-26
**核实方式：** 逐一阅读 `src/crosspost/` 源码文件 + 运行 `pytest`（全量 160 个用例通过）+ 对照 `.planning/REQUIREMENTS.md`、`.planning/ROADMAP.md` 原始记录

这是给人看的"一眼看完成没完成"汇总表。逐条依据见 [REQUIREMENTS.md](REQUIREMENTS.md)（每条需求对应哪个源码文件）与 [ROADMAP.md](ROADMAP.md)（按 Phase 的验收标准核对）。

## 一句话结论

**v1 的 16 条需求，代码全部写完了（16/16）；但发布相关的 3 条（PUB-01/02/03）从未用真实平台账号验证过，只在 `dry_run` 模式下测试过流程。** 另外代码库里多出一个原始需求文档中明确排除的功能——本地 Web 管理面板（`web.py`）。

## 已完成（代码 + 有测试覆盖 + 已核实可用）

| 需求 | 内容 | 源码 |
|------|------|------|
| ACQ-01 | YouTube RSS 监控频道更新 | `feeds.py` |
| ACQ-02 | yt-dlp 下载视频+元数据+缩略图 | `downloader.py` |
| ACQ-03 | YAML 配置频道列表 | `config.py` |
| ACQ-04 | 按时长过滤下载 | `config.py` |
| PROC-01 | faster-whisper 本地 ASR → SRT | `transcriber.py` |
| PROC-02 | 字幕翻译成中文（DeepL，保留时间轴） | `translator.py` |
| PROC-03 | 中文字幕烧录（CJK 字体） | `subtitler.py` |
| PROC-04 | 标题/描述 LLM 翻译（Claude） | `translator.py` |
| PROC-05 | 按平台规格转码（H.264 MP4） | `transcoder.py` |
| AUTO-01 | APScheduler 定时轮询 | `scheduler.py` |
| AUTO-02 | SQLite 去重 | `models.py` |
| AUTO-03 | 状态机 + 崩溃恢复 | `models.py`, `scheduler.py` |
| AUTO-04 | 发布间隔控制 + 失败退避重试 | `publisher.py` |

**13/16** 完全就绪，可直接投入使用。

## 代码已完成，但未经真实验证（上线前必须先测）

| 需求 | 内容 | 缺口 |
|------|------|------|
| PUB-01 | 自动发布到今日头条（API） | `config.example.yaml` 里的 endpoint 是占位符，从未用真实头条号 Token 联调 |
| PUB-02 | 自动发布到小红书（Playwright） | 选择器（`file_selector`/`submit_selector` 等）没有针对小红书真实页面填写和调试过，也没做过反检测实测 |
| PUB-03 | 自动发布到百度百家号（API） | 同 PUB-01，endpoint 是占位符 |

**3/16** 有骨架、无实测。建议上线顺序：先用 `backend: dry_run` 跑通队列和限流逻辑 → 逐平台切换到真实 `api`/`browser` 配置 → 小流量验证 → 再全量启用。

## 未开始（v2，明确推迟）

- PUB-04 抖音发布
- ACQ-05 X (Twitter) 内容获取
- PROC-06 中文缩略图生成
- PROC-07 横屏裁竖屏
- PROC-08 AI 智能剪辑
- AUTO-05 规则引擎
- AUTO-06 通知/Webhook
- AUTO-07 代理轮换

这些都在 [REQUIREMENTS.md](REQUIREMENTS.md) 的 v2 部分，不在当前里程碑范围内，无需现在处理。

## 范围外但已经做了的东西（需要决策）

- **Web 管理面板**（`web.py` / `crosspost-web` 命令）：本地仪表盘，可查看各状态内容、手动提交 YouTube 链接、触发一次流水线。原始需求文档把"Web 管理界面"明确列为 Out of Scope（理由：个人使用，CLI+配置文件够用）。现在这功能已经写完并有测试，等于是范围之外的既成事实。**需要你决定**：正式纳入需求范围，还是仅作为内部调试工具、不写进对外文档。

## Phase 进度对照

| Phase | GSD 计划记录 | 代码实际状态 |
|-------|-------------|--------------|
| 1. Pipeline Foundation | ✅ 3/3 完成并验证 | ✅ 一致 |
| 2. Content Processing | ✅ 5/5 完成并验证 | ✅ 一致 |
| 3. Publishing & Automation | ⏳ 0/TBD，记录为未开始 | 🟡 实际已写完代码，但跳过了 GSD 的 plan/verify 流程，且未真实验证 |

`.planning/STATE.md` 目前仍显示 "milestone executing，Phase 2 88%"，与代码实际进度不符——这是因为 Phase 3 的开发没有走 `/gsd:plan-phase` → `/gsd:execute-phase` 流程。如果之后想让 GSD 工具链（`/gsd:progress` 等）识别到 Phase 3 已完成，需要手动更新 `.planning/STATE.md` 和 `.planning/ROADMAP.md`，或者跑一次 `/gsd:plan-phase` 把已有代码补记为正式计划。本次审计未修改 `.planning/` 下任何文件，仅在 `docs/` 生成了审计后的版本。

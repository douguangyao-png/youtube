# CrossPost - 跨平台内容搬运工具

## What This Is

一个全自动的跨平台内容搬运工具，从 YouTube 和 X (Twitter) 抓取视频、短视频和图文内容，自动翻译成中文后发布到国内主流平台（抖音、头条、小红书、百度）。面向个人内容创作者使用，部署在云服务器上长期运行。

## Core Value

自动化完成从海外内容抓取到国内平台发布的全流程，包括下载、转码、翻译、适配和发布，无需人工干预。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 从 YouTube 下载视频和 Shorts
- [ ] 从 X 抓取推文、图片和短视频
- [ ] 英文内容自动翻译成中文（文本+视频字幕）
- [ ] 视频转码适配各平台格式要求
- [ ] 自动发布到抖音
- [ ] 自动发布到今日头条
- [ ] 自动发布到小红书
- [ ] 自动发布到百度百家号
- [ ] 规则引擎：按关键词/频道/账号自动抓取
- [ ] 定时任务调度，持续运行

### Out of Scope

- 多用户/SaaS 模式 — 仅个人使用
- Web 管理界面 — v1 用配置文件+命令行
- 评论区互动管理 — 只做发布，不做运营
- 直播内容搬运 — 仅处理已发布的内容

## Context

- **内容来源 API 情况**：YouTube 有 Data API（下载用 yt-dlp），X API 有付费限制（可能需要爬虫辅助）
- **国内平台发布情况**：
  - 抖音：有开放平台 API（需企业认证），个人可用浏览器自动化
  - 头条：头条号有发布 API
  - 小红书：无公开发布 API，需浏览器自动化
  - 百度百家号：有内容发布 API
- **翻译方案**：可用 LLM API（如 Claude/GPT）或专业翻译 API（如 DeepL）
- **视频字幕**：需要 ASR（语音识别）+ 翻译 + 字幕烧录
- **合规风险**：内容版权、平台规则、账号风控需要注意

## Constraints

- **Tech Stack**: Python — 用户指定
- **部署环境**: 云服务器，需要能运行 headless 浏览器
- **网络**: 需要能访问 YouTube 和 X（可能需要代理）
- **发布方式**: 混合方案 — 有 API 用 API，没有的用 Playwright/Selenium 浏览器自动化
- **翻译成本**: 需要控制 API 调用成本

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 技术栈 | 用户偏好，且生态丰富（yt-dlp, Playwright 等） | — Pending |
| 混合发布方案 | 部分平台有 API，部分需要浏览器自动化 | — Pending |
| 全自动模式 | 个人使用，追求效率 | — Pending |
| yt-dlp 下载视频 | 成熟稳定的 YouTube 下载方案 | — Pending |

---
*Last updated: 2026-03-14 after initialization*

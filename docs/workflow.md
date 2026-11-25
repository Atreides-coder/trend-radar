# Trend Radar V1

每天从多个来源抓取信息，筛出 5～10 个值得做成短视频的趋势型选题。

当前进度：

- Phase 1 抓取 + 入库 + 去重 ✅
- Phase 2 Prefilter + Fast Filter（Codex）→ Candidate Pool ✅
- Phase 3 Event 聚类 + Global Ranking + Trend Linking ✅
- 本地 Dashboard（AI 媒体编辑工作台）✅
- Video Pipeline V0：选中的 Event → 研究 → 脚本 → 分镜 → 素材 → 配音 → Remotion 渲染 → QC ✅

系统设置截图需要在 config/settings.yaml 中显式开启 video.capture_macos_settings。导演版项目与以下命令使用的事件编号均为制作示例，使用时请替换为自己的项目和事件编号。

## 安装

```bash
uv venv .venv --python 3.13
uv pip install -p .venv/bin/python -r requirements.txt
cp .env.example .env      # 只配置 Codex 用哪个模型和推理强度，不需要任何 API key
```

## 模型运行时：Codex CLI

模型判断通过 Codex CLI 的非交互模式（`codex exec`）完成，使用 ChatGPT 登录，不需要 API key。

```bash
npm install -g @openai/codex   # 如果还没装
codex login                    # 用 ChatGPT 账号登录
codex login status             # 应显示 Logged in using ChatGPT
```

边界：Python 负责编排、校验和写数据库；Codex 只接收 prompt 和一批 JSON，返回结构化判断。
每次调用都在只读沙箱、空的临时目录里运行，不加载你的 Codex 用户配置（MCP、插件、priority 档），
输出由 `--output-schema` 约束。封装在 `src/ai/codex_runner.py`，接口定义在 `src/ai/base.py`。

模型和推理强度只在 `.env` 里配置：

```text
CODEX_MODEL=gpt-6.2-astra
CODEX_REASONING_EFFORT=high
```

每次 `codex exec` 都显式带上这两项，并且不加载 Codex 用户配置，所以无人值守运行时用什么模型是确定的，
和 Codex Desktop / CLI 上次手动选了什么无关。每次运行的日志、`filter_runs`、`filter_evaluations` 都会记录
实际使用的 model、reasoning effort 和 prompt version。超时等在 `config/settings.yaml` 的 `codex` 段。

## Dashboard

```bash
./scripts/start_dashboard.sh          # 打开 http://localhost:8765
PORT=9000 ./scripts/start_dashboard.sh
```

第一次启动会构建前端（需要 Node.js），之后直接启动。看板从 SQLite 读取选题并保存人工反馈。Video Studio 可以刷新社区线索、处理本地素材和启动制作任务，模型配置在项目的 `.env` 中维护。

| 页面 | 用途 |
|---|---|
| Overview | 漏斗、当前模型、最近一次抓取 / 分析、token、分数分布 |
| Raw Intelligence | 系统看到的全部原始内容，可按来源 / 状态 / 日期 / 关键词筛选 |
| Candidates | 候选池。点开看详情；👍 👎 👁 ★ 标记和备注写入数据库 |
| Rejected | 没入选的内容，可按原因筛选，可 Restore to Candidate |
| Borderline | 45～65 分，以及模型的 keep 与分数结论不一致的内容 |
| Events | 聚类后的独立事件，按 Global Ranking 排序；每个 Event 下面列出它包含的原始报道 |
| Trends | 多个 Event 共同支持的趋势假设；Trend → Events → 原始报道 |
| Video Studio | 查看成片和质检，查询社区线索，导入或提取视频镜头，编辑脚本与分镜 |
| Runs | Fast Filter 和聚类每次运行的模型、effort、prompt、token、耗时；可以对比两次 Fast Filter 运行 |
| Watchlist | 你标记为 Watch / Interested / Strong Topic 的内容 |

人工反馈存在 `raw_items` 的 `human_status` / `human_note` / `human_updated_at`；
人工恢复的条目 `human_override = 'restored'`，之后的筛选不会再把它降级。

前端在 `dashboard/`（Vite + React），后端在 `src/dashboard/api.py`（FastAPI）。
改前端时可以 `cd dashboard && npm run dev`（会把 `/api` 转发到 8765）。

## 运行

```bash
.venv/bin/python -m src.main --stage fetch              # 抓取（不调用模型）
.venv/bin/python -m src.main --stage filter             # Prefilter + Fast Filter + 报告
.venv/bin/python -m src.main --stage filter --force     # 改了 prompt / 规则后，全部重新筛选
.venv/bin/python -m src.main --stage filter --dry-run   # 只跑 Prefilter，不调用模型
.venv/bin/python -m src.main --stage filter --debug     # 只评估前 2 批，并打印模型输入输出
.venv/bin/python -m src.main --stage cluster            # Signals → Events → Global Ranking → Trends
.venv/bin/python -m src.main                            # 完整 pipeline
```

- 数据库：`data/trend_radar.db`
- 日志：`logs/YYYY-MM-DD.log`
- 筛选报告：`output/YYYY-MM-DD/filter_report.md`（最新）和 `filter_report_run<id>.md`（每次运行各一份），候选池：`output/YYYY-MM-DD/raw_candidates.json`

## 推荐的定时方式

抓取不花钱，而且有的 feed 只保留最近 20 条，一天只抓一次会漏。建议抓取一天 4 次，分析一天 1 次。
`crontab -e` 示例（把路径换成你的实际路径）：

```cron
# 把 codex 和 node 所在目录加入 PATH
PATH=/usr/local/bin:/usr/bin:/bin
0 8,12,18,23 * * *  cd "/path/to/每日趋势" && .venv/bin/python -m src.main --stage fetch
30 23 * * *         cd "/path/to/每日趋势" && .venv/bin/python -m src.main --stage filter && .venv/bin/python -m src.main --stage cluster
```

每天 23:30 先筛选，再更新事件排名、趋势和研究队列。筛选失败会以非零状态退出，保留待处理条目。
聚类中止时，看板继续展示上一次完整榜单。成功筛选后候选数为零时，当天展示空榜。

Mac 合盖睡眠时 cron 不会补跑；需要补跑的话改用 launchd。

## 筛选是怎么工作的

```text
raw_items (status=new)
  → Prefilter      规则，config/prefilter.yaml      被拒 → discarded
  → Fast Filter    Codex，prompts/fast_filter.md     打 5 个 0~5 的维度分
  → 代码算总分     权重在 config/settings.yaml       满分 100
  → Candidate Pool score >= keep_threshold           入选 → candidate，其余 → filtered
```

- **Prefilter 只过滤确定不需要的**（优惠码、导购、播客单集、newsletter、招聘、patch 版本、普通 PR）。
  融资、收购、产品发布、GitHub 项目、论文都留给模型判断。
- **Fast Filter 不读全文**，只看标题、摘要和少量元数据，每批 15 条。
- **增量评估**：每条内容只被模型评估一次。每天只为新抓到的内容消耗 Codex 额度，候选池则在整个分析窗口内重新选。
- **阈值规则**：过线的全部成为 signal（`max_signals_for_clustering` 是安全上限）；不足 `min_candidates` 时逐分降低阈值，最低到 `min_threshold`。
- **失败处理**：单批失败自动重试一次，再失败就跳过，这些条目保持 `new`，下次运行会再评估。
  没登录、模型名写错或额度用完会在第一批就中止，不会浪费后续调用。

### 结果存在哪

| 位置 | 内容 |
|---|---|
| `raw_items.status` | `new` / `discarded`（规则拒）/ `filtered`（模型拒）/ `candidate` |
| `raw_items.filter_stage` | 哪一层做的决定：`prefilter` / `llm` |
| `raw_items.filter_score` | Fast Filter 总分 |
| `raw_items.filter_reason` | 被拒原因；candidate 为空 |
| `raw_items.filter_json` | 模型的完整输出（五个维度 + 文字判断） |
| `filter_evaluations` | 每次评估的历史记录，带 `run_id` / `model` / `reasoning_effort` / `prompt_version` / 是否入选，用于 run 之间对比 |
| `filter_runs` | 每次运行的 model、reasoning effort、prompt 版本和原文、数量、调用次数、token、耗时 |

聚类直接读 `raw_items WHERE status = 'candidate'`。

### 调整筛选

- 改判断标准：编辑 `prompts/fast_filter.md`，然后 `--stage filter --force`
- 改阈值 / 权重 / 批大小：`config/settings.yaml` 的 `fast_filter`
- 改规则：`config/prefilter.yaml`

## Phase 3：Event / Trend

```text
Signals（全部 >= 阈值的内容，不再截断 Top 40）
  → Event Clustering   报道同一件现实事件的条目合并成一个 Event      prompts/event_clustering.md
  → Global Ranking     全部 Event 一起比较：六个维度打分 + 不并列的名次  prompts/event_ranking.md
  → Trend Linking      不同 Event 指向同一个更大方向时，生成趋势假设     prompts/trend_linking.md
  → Research Queue     排名前 research_top_n 的 Event（默认 10）
```

- **Fast Filter 是 Signal Gate，不是最终排名**。过线的全部交给聚类；`max_signals_for_clustering` 只是安全上限。
- **三次模型调用，每次都看到全部内容**，因为聚类和排名需要全局上下文。
- **每个 signal 恰好属于一个 Event**。Python 校验 missing / duplicate / invented ID，有问题自动重试一次，
  仍有遗漏的补成单条 Event，不会丢。
- **source_count 和 independent_source_count 分开算**。官方稿是证据但不算独立验证；转述官方公告、
  链接到同一原文的 HN 帖子也不算。独立来源按原始出处的域名去重。
- **Event 总分由代码按权重计算**（Audience 25 / Change 20 / Story 20 / Trend 15 / Evidence 10 / Visual 10），
  名次由模型在看到全部 Event 后强制给出，不允许并列。Fast Filter 的单篇分数不参与排名。
- **Trend 是假设，不是事实**，跨天保留。每次运行会把已有趋势和别名一起给模型，优先归入已有趋势；
  `trend_aliases` 记录同一趋势的不同叫法，名称完全相同时代码会兜底归并。
- **Velocity 暂不计算**（历史不足 7 天），只统计 event / mention / source 数量。
- 每次聚类运行生成一组新的 Event（`events.run_id`），旧运行保留；`cluster_runs` 记录模型、effort、
  三个 prompt 的版本、输入输出数量、token 和耗时。

表：`events`、`event_items`（relationship: primary / official_source / supporting / duplicate_report / commentary）、
`trends`、`trend_events`、`trend_aliases`、`cluster_runs`。权重和队列长度在 `config/settings.yaml` 的 `cluster` 段。

## Video Pipeline V0

把一个选中的 Event 做成一条 45–60 秒的竖屏视频（1080×1920，30fps）。只研究被选中的那一个 Event。

```bash
# 在 Dashboard 的 Events 页面点 Create Video，或者用命令行：
.venv/bin/python -m src.video.pipeline create --event-id 2 --id apple-agent-permissions --angle '这条视频真正要讲的变化'
.venv/bin/python -m src.video.pipeline run apple-agent-permissions                      # 从头跑到 final.mp4
.venv/bin/python -m src.video.pipeline run apple-agent-permissions --steps render,qc    # 只重新渲染
.venv/bin/python -m src.video.pipeline run apple-agent-permissions --steps voice,storyboard,render,qc   # 改稿后
.venv/bin/python -m src.video.pipeline regen-scene apple-agent-permissions 4 --instruction '更口语一点'
```

| 步骤 | 做什么 | 产物 |
|---|---|---|
| research | 抓 Event 已有来源的正文，Codex 在有上限的联网搜索下核实补充；事实 / 推断 / 预测分开 | `fact_pack.json` |
| script | 10 个 Hook 备选 → 选一个 → 分场口播，每场标注事实出处和类型 | `script.json` `script.md` |
| voice | 逐场 TTS，拼成整条配音；字幕时间来自 TTS 的逐词时间戳；时长不在 45–60 秒时按实测语速改稿 | `audio/voice.wav` `captions.json` |
| assets | 采集真实素材：本机系统设置界面、官方页面、报道页面、报道题图；截图用 OCR 读出文字和位置 | `assets/` `assets/library.json` |
| storyboard | 为每一场挑素材和组件；镜头起止对到口播时间，高亮区域对到 OCR 行位置 | `storyboard.json` `assets.json` |
| render | Remotion 渲染，FFmpeg 出预览和封面 | `render/final.mp4` `preview.mp4` `thumbnail.png` |
| qc | 画幅、黑帧、静止画面、镜头长度、字幕、素材、事实出处等确定性检查 | `qc_report.md` |

- 项目都在 `video_projects/<project_id>/`，`state.json` 记录每一步的状态，Dashboard 的 Video Studio 读它。
- 需要模型判断的三步（research / script / storyboard）走 CodexRunner，模型和推理强度同样来自 `.env`。
  只有 research 允许联网搜索。
- TTS 走统一接口 `TTSProvider`（`src/video/voice.py`），V0 只实现了 edge-tts：免费、不需要 key、带逐词时间戳。
  它用的是微软的在线服务，需要联网。音色和语速在 `config/settings.yaml` 的 `video.tts`。
- 如果旧成片的字幕越到后面越慢，且项目保留了分段 WAV 和 `audio/timings.json`，可先运行
  `.venv/bin/python -m src.video.voice repair-cached <project_id>` 离线重拼配音，再用
  `.venv/bin/python -m src.video.pipeline run <project_id> --steps render,qc` 更新成片和质检报告。
- 素材优先级：真实界面和官方页面 > 报道页面 > Remotion 动画。系统设置截图只保留右侧内容区（左侧边栏有账户名）。
- OCR 用 macOS 自带的 Vision（`scripts/ocr.swift`），所以素材采集目前只能在 Mac 上跑。
- Remotion 工程在 `video/`，画面组件：HookScene、RealMediaScene、BrowserScreenshotScene、PhoneOrDesktopScene、
  DataScene、ConceptDiagramScene、QuoteScene、ConclusionScene。改模板后重新 render 即可。
- 人工干预（Video Studio 页面或命令行）：改口播、重写某一场、替换某个镜头的素材、上传自己的图片、重新配音、重新渲染。

### 选题研究与视频素材

普通视频项目可以用 last30days 查找受众正在讨论的问题，也可以用 AutoClip 从已有视频提取镜头。在新机器上，从项目根目录运行一次：

```bash
.venv/bin/python scripts/install_integrations.py
```

安装脚本使用 Git 和 uv，把 [last30days v4.6.0](https://github.com/mvanhorn/last30days-skill/releases/tag/v4.6.0) 和 [AutoClip v1.6.0](https://github.com/zhouxiaoka/autoclip/releases/tag/v1.6.0) 放在 `.tools/` 内并核对固定提交。需要 Python 3.12+、FFmpeg 和 ffprobe。

**找社区线索。** 在 Video Studio 的“社区线索”中查询或刷新，已有项目也可以单独使用。新选题进入研究阶段时会自动查询。检索使用选题或原报道的公开标题，匿名查询 Hacker News 和 GitHub 近 30 天的匹配项。结果保存在该视频项目的 `research/last30days.json`。互动量供编辑判断受众兴趣，脚本引用事实仍需核实。可在 `config/settings.yaml` 的 `video.last30days` 下关闭检索或调整超时。

**选视频镜头。** 在 Video Studio 的素材库导入已剪好的 MP4，或点“从视频提取候选镜头”选择 MP4、MOV、MKV 或 WebM 文件。自动提取按硬切、转场划分镜头，每次默认最多取 6 段，每段最长 6 秒。在分镜里选中素材再重新渲染，视频以原速静音播放，过短的片段在该镜头内循环。若要按访谈内容选精彩段落，可以先在 AutoClip 完成语义选段，再导入它的导出文件。

命令行也支持同一素材库。例如，先将 `PROJECT_ID` 换成一个已有的普通视频项目 ID：

```bash
.venv/bin/python -m src.video.autoclip scan PROJECT_ID "/path/to/发布会.mp4" --max-clips 3 --clip-seconds 5
.venv/bin/python -m src.video.autoclip import PROJECT_ID "/path/to/访谈.mp4" --start 32 --duration 5 --title "谈到产品变化"
.venv/bin/python -m src.video.autoclip import-manifest PROJECT_ID "/path/to/autoclip-outputs.json"
```

清单可以来自 AutoClip 的 `autoclip outputs <id>` 等本地导出，清单引用的视频文件需在本机可读。重复导入同一源文件的相同区间会复用已有素材。

### Directed 流程（导演方案 → 专门的 composition）

自动 pipeline 让模型在通用组件里挑画面，容易做成“截图加大字”。对质量要求高的视频，改用 directed 流程：
先写 `creative_direction.md`（开场方案、视觉概念、逐镜头分镜），再为这条视频写一个专门的 Remotion composition。
镜头时间仍然全部来自真实配音。

在 Video Studio 中，只改画面时点“沿用配音重渲染导演版”。修改 `shots.json` 的旁白后，点“重新配音并渲染导演版”。两项操作都会使用该项目指定的 Remotion 模板。

```bash
.venv/bin/python -m src.video.directed build apple-agent-permissions-v2               # 配音 + 对时 + 渲染 + QC
.venv/bin/python -m src.video.directed build apple-agent-permissions-v2 --skip-voice  # 只改了画面
```

- 分镜和旁白在项目目录的 `shots.json`；画面代码在 `video/src/v2/`（虚拟摄影机、触达地图、证据快切等可复用部件在 `kit.tsx` / `map.tsx`）。
- 真实操作录屏用 `src/video/capture.py`：只录某个窗口所在的区域，不接管鼠标，不需要“辅助功能”权限。
  系统设置靠系统自带的面板链接跳转；终端演示把脚本交给 Terminal.app 运行。**它不会结束 Terminal 进程**，演示窗口录完后需要手动关。
- Agent 演示用 `scripts/agent_demo.py`：让 Codex 在只有示例文件的沙盒文件夹里完成一个真实任务，实时打印它的每个动作并记录事件。
- 录屏素材在项目的 `capture/`（原始）和 `assets/`（裁掉标题栏和侧边栏之后）。

## 增删数据源

改 `config/sources.yaml` 即可。新的来源类型：在 `src/fetchers/` 写一个
`BaseFetcher` 子类，用 `@register("类型名")` 装饰，并在 `src/fetchers/__init__.py` 里导入。

## 去重规则

- `content_hash` = sha1(来源 + 规范化 URL)，没有 URL 时退回规范化标题。同一来源内唯一。
- 重复抓到的条目不丢弃，而是更新 `engagement_score` / `last_seen_at` / `seen_count`。
- `url_hash` 只看规范化 URL，用来识别"不同来源指向同一篇文章"。

# 面向 AI 岗位采集与简历匹配的招聘数据 Agent 系统

这个项目基于 `boss-zhipin-scraper` 的 Chrome CDP 岗位采集能力，但项目核心不是“网页自动点击”，而是把岗位数据变成可用于求职决策的结构化系统：**采集 → 详情合并 → 去重 → 归一化 → 入库 → JD 结构化 → 技能分析 → 简历匹配 → 最终报告**，一条命令跑通。

## 项目定位

- 外部 `boss-zhipin-scraper` 只是**采集引擎**，通过 `app/integrations/boss_zhipin` 适配层接入，主项目不依赖它的内部实现。
- 主项目负责领域建模、持久化、结构化分析、AI 简历匹配和报告生成。
- AI 只负责“单个岗位的结构化匹配分析”，**排序、格式化和最终报告由系统代码稳定生成**，不依赖 AI 自由发挥。

## 首次运行前：启动 Chrome CDP

真实采集依赖一个开启远程调试的专用 Chrome（不复用主浏览器 Profile）。**首次运行前必须先启动它并登录 BOSS**，否则采集会因连不上 `127.0.0.1:9222` 而失败（Windows 报 `WinError 10061`）。

```powershell
# 1. 启动专用 Chrome CDP（首次会打开窗口，请在其中登录 zhipin.com）
python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --setup-chrome --cdp-port 9222

# 2. 确认环境和登录状态
python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --check --cdp-port 9222
```

`--check` 全部通过后再运行下面的主入口。如果采集步骤报 `WinError 10061` 或 `127.0.0.1:9222`，说明 CDP 没起来，回到这一节先跑 `--setup-chrome`。

## 一键运行（主入口）

```powershell
python scripts/run_full_job_agent.py `
  --resume-file private/resume.pdf `
  --keyword "AI Agent" `
  --cities 上海,深圳,广州 `
  --pages 1 `
  --scraper-root external/boss-zhipin-scraper `
  --output-dir data/reports `
  --max-jobs 30 `
  --include-detail
```

`run_full_job_agent.py` 会依次完成：逐城市采集 → 详情合并 → 跨城市去重 → 归一化 → 入库 → JD 结构化 → 技能分析 → 读取简历 → 简历-岗位匹配 → 生成最终报告，并把每一步的成功/失败写入运行轨迹。产物统一以 `run_id` 前缀写入 `--output-dir`：

- `{run_id}_job_overview.csv`：推荐投递总览表（含公司、薪资、公司规模、融资阶段、行业、岗位链接）。
- `{run_id}_structured_jobs.json`：每个岗位的结构化 JD。
- `{run_id}_skill_analysis.json`：高频技能画像。
- `{run_id}_match_results.json`：结构化匹配结果（可全局排序、可入库）。
- `{run_id}_final_report.md`：系统生成的最终报告。
- `{run_id}_steps.jsonl`：运行轨迹，逐步记录状态、耗时、条目数和产物路径。

详情采集由一对开关控制：默认 `--include-detail`（采集详情 JD 并合并回岗位，让 JD 进入结构化和匹配链路），传 `--no-detail` 则只采列表页、跳过详情。失败时报告会明确指出卡在哪一步（`failed_step`）。

> 提示：BOSS 详情页有频率限制，每条约 20-30 秒。工作流会在去重和 `--title-contains` 过滤后，只对前 `--max-jobs` 条岗位抓详情，因此 `--max-jobs` 是控制总耗时的主要开关。

## 目录结构

```text
app/
  collectors/            # 采集适配器 (BossZhipinCollector)
  integrations/boss_zhipin/  # 外部 scraper 集成：命令构建 + 详情合并/去重
  core/                  # 配置边界（后续 FastAPI 化预留）
  db/                    # SQLAlchemy models + session
  repositories/          # job / run(+step) / match 三个仓储
  schemas/               # Pydantic: collect/job/jd/match/report/run/workflow
  services/              # 领域服务 + job_agent_workflow 编排
external/
  boss-zhipin-scraper/   # 外部采集引擎（gitignore，不提交）
scripts/                 # run_full_job_agent.py 为主，其余为调试工具
data/                    # 运行产物占位（真实内容不提交）
```

## 技术路线

```text
专用 Chrome 登录态
  -> Chrome DevTools Protocol
  -> CollectionSafetyPolicy 采集前安全检查
  -> BossZhipinCollector 调用 external/boss-zhipin-scraper（可选详情 JD）
  -> merge_boss_list_and_detail_jobs 把详情 JD/地址/技能/福利合并回列表岗位
  -> dedupe_raw_jobs 跨城市去重
  -> RawJobPost 保存原始字段（公司规模、融资阶段、行业、福利、岗位链接等一等字段）
  -> JobNormalizer 统一岗位字段 + salary 解析
  -> SQLAlchemy Repository 持久化岗位、技能、AgentRun、AgentStep、JobMatch
  -> JDStructurer 结构化职责、要求、技能和风险点
  -> SkillAnalyzer 统计高频技能、类别分布和技能组合
  -> ResumeJobMatcher 让 AI 输出结构化 JobMatchResult 并全局排序
  -> ReportGenerator 由系统代码生成 CSV 总览 + Markdown 最终报告
```

`run_full_job_agent_workflow()` 是把上面每一步串起来的编排层，采集器和 AI Provider 都通过工厂注入，因此可以用 fixture 完整跑通而不触发真实 subprocess 或网络。

## 为什么不是 browser-use 主线

`browser-use` 适合做“让 Agent 操作浏览器”的通用自动化演示；本项目的目标是构建招聘数据分析系统。对 BOSS 岗位这类场景，直接通过 CDP 复用专用浏览器登录态并读取结构化接口输出，比模拟点击、滚动、解析 DOM 更稳定，也更适合作为数据工程链路。

## 合规边界

- 仅用于个人求职分析和学习研究。
- 低频采集，不做大规模数据抓取。
- 不自动投递，不自动发送消息。
- 不采集与岗位无关的个人隐私。
- 不公开再分发原始岗位数据。
- 尊重平台规则和网站使用条款。
- 默认使用专用 Chrome Profile，不复用主浏览器敏感登录态。

## 外部采集引擎

外部 `boss-zhipin-scraper` 放在 `external/boss-zhipin-scraper`，**不提交到 Git**（见 `.gitignore` 与 `external/README.md`）。用 `BOSS_SCRAPER_ROOT` 或 `--scraper-root` 指向本地 scraper 根目录即可；适配层只依赖它的 `scripts/boss_cdp_raw.py` 命令行接口，不耦合内部实现。

## 采集安全检查

真实采集前先做请求级安全检查：

```powershell
python scripts/check_collection_safety.py --keyword "AI Agent" --city 上海 --pages 2
```

默认策略：

- 单次最多 `3` 页。
- 默认专用 Profile 为 `~/.boss-zhipin-scraper/chrome-profile`。
- 禁止复用主浏览器 Profile。
- 禁止 `--copy-login-state`。
- 禁止自动投递和自动发送消息。

## 开发调试工具（次要入口）

日常主入口是 `scripts/run_full_job_agent.py`。下面这些脚本保留下来用于分步调试，不再是主流程：

- `scripts/collect_boss_jobs.py`：只做采集，验证 CDP / scraper 是否可用。默认只采列表页（详情每条约 30s），需要详情时加 `--include-detail`。
- `scripts/run_job_pipeline.py`：从已导出 JSON 跑离线 Pipeline（归一化 + 结构化 + 技能分析）。
- `scripts/analyze_resume_jobs.py`：从已导出 JSON 做 AI 简历-岗位匹配（输出 Markdown）。
- `scripts/resume_full_job_agent.py`：断点续跑。当某次 run 已完成到 `skill_analysis`、只在 `resume_matching` 失败（例如 AI 中转断连）时，复用同一个 `run_id` 直接从匹配步骤继续，不重新采集：

  ```powershell
  python scripts/resume_full_job_agent.py `
    --run-id <失败的 run_id> `
    --resume-file private/resume.pdf `
    --output-dir data/reports `
    --database-url sqlite:///data/db/job_agent.db `
    --batch-size 3
  ```

  它读取 `data/reports/{run_id}_structured_jobs.json` 和 `_skill_analysis.json`，从 SQLite 恢复岗位元信息，续跑后写出 `_match_results.json`、`_job_overview.csv`、`_final_report.md`。AI 断连时会提示降低 `--batch-size`、提高 `AI_MATCHER_TIMEOUT_SECONDS` 或检查中转服务。

- `scripts/export_public_snapshot.py`：导出可公开的干净快照（只含源码、测试、文档和占位文件），绝不包含 `.env`、真实简历、`data/**` 真实数据、数据库、缓存或外部 scraper 源码：

  ```powershell
  python scripts/export_public_snapshot.py --dest ../job-agent-matcher-public
  ```

### 单独采集

```powershell
python scripts/collect_boss_jobs.py `
  --keyword "AI Agent" `
  --city 上海 `
  --pages 1 `
  --scraper-root external/boss-zhipin-scraper
```

注意：这个命令会尝试调用真实 `boss-zhipin-scraper`。运行前需要先使用专用 Chrome Profile 完成登录，并确认 CDP 端口可用（见上文“首次运行前：启动 Chrome CDP”）。这个调试脚本默认 **只采列表页**（`--no-detail`），因为详情页每个约 30 秒，快速验证采集是否正常时不该顺带爬详情；需要详情 JD 时显式加 `--include-detail`。主入口 `run_full_job_agent.py` 则默认在过滤并按 `--max-jobs` 截断后，只为入选岗位抓详情。

Windows 下已在 adapter 内处理 UTF-8 输出和绝对输出路径；`--scraper-root` 可以传真实 scraper 根目录，也可以传下载后多套了一层的外层目录。

常用采集参数直接在命令里改，不需要改源码：

- `--keyword`：岗位关键词，例如 `AI Agent`、`RAG 工程师`、`大模型应用开发`。
- `--city`：采集城市，例如 `上海`、`北京`、`深圳`、`杭州`。
- `--cities`：多个城市，逗号分隔，例如 `上海,北京,深圳`。传了 `--cities` 时会忽略单城市 `--city`。
- `--pages`：采集页数。项目安全策略默认单次最多 3 页，建议先从 1 页开始验证。
- `--output-dir`：原始岗位 JSON 输出目录，默认是 `data/raw_jobs`，该目录真实内容不会提交到 GitHub。

示例：

```powershell
python scripts/collect_boss_jobs.py `
  --keyword "RAG 工程师" `
  --city 北京 `
  --pages 2 `
  --scraper-root external/boss-zhipin-scraper
```

多城市示例：

```powershell
python scripts/collect_boss_jobs.py `
  --keyword "AI Agent" `
  --cities 上海,北京,深圳 `
  --pages 1 `
  --scraper-root external/boss-zhipin-scraper
```

多城市采集会逐个城市执行，每个城市生成独立的原始 JSON 和 run 记录；`--pages` 是每个城市的页数。

## 数据库建模

项目使用 SQLite + SQLAlchemy 建立最小可解释的数据模型：

- `job_posts`：保存归一化后的岗位主表，使用 `(platform, source_job_id)` 做唯一约束，保证重复导入不会产生重复岗位。除基础字段外，还提升了公司规模、融资阶段、行业、公司链接、Boss、福利、地址、薪资区间等岗位元信息为一等字段。
- `job_skills`：保存岗位技能关键词，和岗位一对多关联，便于后续做技能统计和简历匹配。
- `agent_runs`：保存一次任务的整体执行轨迹（状态、耗时、命令、错误信息和输出路径）。
- `agent_steps`：保存一次 Workflow 内部每个步骤（采集、详情合并、归一化、入库、JD 结构化、技能分析、简历匹配、报告生成）的状态、耗时、条数和产物路径，失败时能定位到具体步骤。
- `job_matches`：保存结构化简历-岗位匹配结果（匹配度、推荐等级、匹配证据、短板、简历建议和岗位准备重点），支持全局排序和后续 Web 展示。

默认数据库地址为 `sqlite:///data/db/job_agent.db`，也可以通过 `JOB_AGENT_DATABASE_URL` 或 `--database-url` 覆盖。

> 注意：本次重构给 `job_posts` 增加了新列并新增了 `agent_steps`、`job_matches` 两张表。`Base.metadata.create_all` 只新建缺失的表，不会给旧表补列。如果你有旧的本地 `job_agent.db`，请先删除它让系统重建（岗位数据可从原始 JSON 重新入库）。

## JD 结构化

规则版 `JDStructurer` 先用稳定可测试的方式把 JD 原文转成结构化对象：

- `responsibilities`：岗位职责。
- `requirements`：经验、学历和能力要求。
- `skills`：技能名称、类别、证据片段和是否必需。
- `risk_points`：后续岗位评估或简历匹配需要注意的风险点。
- `summary` / `confidence`：岗位摘要和结构化置信度。

当前实现不依赖真实 LLM，后续可以让 LLM 输出同一个 `StructuredJD` Schema，再由 Pydantic 校验。

## 技能分析

`SkillAnalyzer` 基于 `StructuredJD.skills` 生成岗位技能画像：

- `top_skills`：技能出现次数、岗位覆盖数和覆盖率。
- `category_distribution`：AI、backend、data、devops 等类别分布。
- `common_skill_pairs`：常见技能组合，例如 Python + RAG。
- `required_skill_names`：后续简历匹配优先关注的技能清单。
- `recommendations`：面向求职准备的技能补齐建议。

SkillAnalyzer 不重新解析 JD 原文，而是复用 JDStructurer 的结构化结果，因此未来接 LLM 解析时统计层不用改。

## 端到端 Pipeline

离线 Pipeline 主入口推荐优先用 fixture 或已导出的 JSON 做可复现验证：

```powershell
python scripts/run_job_pipeline.py tests/fixtures/sample_boss_jobs.json `
  --database-url sqlite:///data/db/job_agent.db `
  --output-dir data/reports
```

Pipeline 会生成三类产物：

- `*_structured_jds.json`：每个岗位的职责、要求、技能、风险点和摘要。
- `*_skill_analysis.json`：高频技能、技能类别、技能组合和建议。
- `*_pipeline_report.md`：适合人工复盘和后续简历修改的 Markdown 报告。

真实采集和离线分析保持分层：真实采集必须先经过 `CollectionSafetyPolicy`，而 Pipeline 默认只处理已经导出的 JSON，因此更适合自动化测试和本地演示。

## AI 简历-岗位匹配分析

系统不单独实现规则版 `ResumeParser`。简历是自由文本，项目经历和技能证据高度依赖上下文，因此直接让 AI 模型读取“私有简历文本 + 结构化岗位画像”更适合生成求职匹配报告。

真实调用前通过环境变量配置 OpenAI-compatible 接口：

```powershell
$env:AI_MATCHER_API_KEY="your-api-key"
$env:AI_MATCHER_BASE_URL="https://your-compatible-endpoint/v1"
$env:AI_MATCHER_MODEL="your-model-name"
$env:AI_MATCHER_TIMEOUT_SECONDS="180"
```

也可以写到项目根目录 `.env`，脚本会自动读取：

```text
AI_MATCHER_API_KEY=your-api-key
AI_MATCHER_BASE_URL=https://your-compatible-endpoint/v1
AI_MATCHER_MODEL=your-model-name
AI_MATCHER_TIMEOUT_SECONDS=180
AI_MATCHER_RETRY_COUNT=2
AI_MATCHER_RETRY_BACKOFF_SECONDS=2
```

如果 `.env` 和 PowerShell `$env:` 同时存在，当前进程里的 `$env:` 优先。

`AI_MATCHER_TIMEOUT_SECONDS` 用于较慢模型或中转服务；`AI_MATCHER_MAX_TOKENS` 是可选项，只有确认服务兼容时再配置。

运行方式：

```powershell
python scripts/analyze_resume_jobs.py `
  --resume-file private/resume.pdf `
  --jobs data/raw_jobs/my_jobs.json `
  --output data/reports/resume_job_ai_analysis.md `
  --max-jobs 20
```

如果多城市或多关键词采集生成了多个 JSON，可以一次性传给 `--jobs`：

```powershell
python scripts/analyze_resume_jobs.py `
  --resume-file private/resume.pdf `
  --jobs data/raw_jobs/shanghai.json data/raw_jobs/beijing.json data/raw_jobs/shenzhen.json `
  --output data/reports/resume_job_ai_analysis.md `
  --max-jobs 50
```

也可以传目录或通配符，脚本会合并多个 JSON，并按 `(platform, source_job_id)` 去重：

```powershell
python scripts/analyze_resume_jobs.py `
  --resume-file private/resume.pdf `
  --jobs "data/raw_jobs/*.json" `
  --output data/reports/resume_job_ai_analysis.md `
  --max-jobs 50 `
  --batch-size 10
```

`--batch-size` 会把岗位分批发送给模型，适合中转服务不稳定或岗位数量较多时使用。比如 `--max-jobs 50 --batch-size 10` 会拆成 5 次模型调用，最终写入一个 Markdown 报告。

注意：`--resume-file` 支持 `.pdf`、`.txt` 和 `.md`。`private/`、`resumes/`、`data/raw_jobs/` 和 `data/reports/` 的真实内容默认不提交到 GitHub，避免泄露简历、岗位原文、Cookie 或密钥。

## 本地验证

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/normalize_boss_export.py tests/fixtures/sample_boss_jobs.json --output data/processed_jobs/sample_normalized.json
python scripts/check_collection_safety.py --keyword "AI Agent" --city 上海 --pages 2
python scripts/import_boss_export.py tests/fixtures/sample_boss_jobs.json --database-url sqlite:///data/db/job_agent.db
python scripts/structure_jd_export.py tests/fixtures/sample_boss_jobs.json --output data/processed_jobs/sample_structured_jds.json
python scripts/analyze_skills_export.py tests/fixtures/sample_boss_jobs.json --output data/reports/sample_skill_analysis.json
python scripts/run_job_pipeline.py tests/fixtures/sample_boss_jobs.json --database-url sqlite:///data/db/job_agent.db --output-dir data/reports
# Real AI call requires AI_MATCHER_API_KEY or OPENAI_API_KEY.
python scripts/analyze_resume_jobs.py --resume-file private/resume.pdf --jobs tests/fixtures/sample_boss_jobs.json --output data/reports/resume_job_ai_analysis.md
# Evaluate a real export and its matching collection run without mixing history.
python scripts/evaluate_job_agent.py --jobs data/raw_jobs/<real-export>.json --run-log data/runs/agent_runs.jsonl --output data/reports/evaluation.json
```

评估口径和最近一次真实采集结果见 [`docs/evaluation.md`](docs/evaluation.md)。脚本会对缺少人工技能金标准或真实匹配结果的指标输出 `null`，避免使用不可验证的占位数字。

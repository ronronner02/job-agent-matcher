# Design Decision: Offline Pipeline Flow

## 背景

采集适配、岗位归一化、SQLite 入库、JD 结构化和技能分析原本分散在多个脚本中。离线 Pipeline 将它们串成可复现的流水线，让一个导出的岗位 JSON 可以稳定产出数据库记录、结构化 JD、技能画像和 Markdown 报告。

## 决策

新增 `run_offline_job_pipeline` 作为端到端服务层，固定执行：

1. `BossZhipinCollector.collect` 读取外部导出的原始岗位 JSON。
2. `normalize_boss_jobs` 转成项目内统一 `NormalizedJobPost`。
3. `upsert_normalized_jobs` 可选写入 SQLite，依赖 `(platform, source_job_id)` 去重。
4. `structure_jds` 把岗位描述转成职责、要求、技能、风险点和摘要。
5. `analyze_skills` 生成高频技能、类别分布、技能组合和学习建议。
6. 输出结构化 JD JSON、技能分析 JSON 和面向人工复盘的 Markdown 报告。

## 为什么先做离线 Pipeline

- 真实采集涉及登录态、平台规则和频率控制，不适合作为默认验证入口。
- 离线 JSON 更容易写自动化测试，能保证每次改代码后结果可复现。
- 后续无论接真实采集、FastAPI、定时任务还是简历匹配，都可以复用同一个服务层。

## 边界

- Pipeline 不负责启动 Chrome，也不绕过 `CollectionSafetyPolicy`。
- Pipeline 不保存 Cookie、Chrome Profile 或原始平台数据到公开仓库。
- Pipeline 输出目录默认在 `data/reports`，该目录中的生成文件不提交到 GitHub。

## 设计收益

系统拆分为“采集边界”和“离线分析流水线”两层。采集层负责合规、低频地获取岗位导出；Pipeline 层只处理输入 JSON，因此可测试、可复现，也方便在 CI 或本地运行。这种分层避免浏览器自动化和业务分析耦合，并让简历匹配、报告生成和评估复用同一套中间结果。

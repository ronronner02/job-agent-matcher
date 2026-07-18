# 端到端 Job Agent Workflow 设计

## 背景

重构前，采集、离线 Pipeline 和 AI 简历匹配分散在多个脚本里，用户需要手动串联多条命令，中间产物也不统一。岗位元信息（公司规模、融资阶段、行业、福利、岗位链接、地址）只存在原始 `raw_payload` 里，报告和 AI Prompt 都拿不到。

## 目标

一条命令完成：采集 → 详情合并 → 去重 → 归一化 → 入库 → JD 结构化 → 技能分析 → 简历匹配 → 报告生成，并且：

1. 岗位元信息成为 `RawJobPost` / `NormalizedJobPost` 的一等字段。
2. 详情 JD 能进入结构化和匹配链路（可配置 `--include-detail`）。
3. AI 输出结构化 `JobMatchResult`（JSON），系统负责全局排序、入库和报告格式化。
4. 每一步都有可观测的运行轨迹（`AgentStep`），失败时能定位到具体步骤。

## 关键设计

### 采集引擎与主项目的边界

外部 `boss-zhipin-scraper` 收敛到 `external/boss-zhipin-scraper`（gitignore）。`app/integrations/boss_zhipin` 只负责构建命令行和合并/去重，`BossZhipinCollector` 作为适配器把导出 JSON 转成 `RawJobPost`。主项目不依赖 scraper 内部实现，只依赖其 CLI。

### 详情合并

`merge_boss_list_and_detail_jobs` 按三级优先级匹配（id / url / 公司+标题+地点），把详情页的 `jd_text`、`address`、`skills`、`welfare`、`detail_url` 合并回列表岗位，冲突时保留更完整的值，同时把详情原始 payload 挂到 `raw_payload["detail_raw_payload"]`。详情缺失时列表岗位不丢弃。

### AI 只做分析，系统负责排序和报告

`ResumeJobMatcher` 让模型对每个岗位输出 JSON（`match_score` / `recommendation_level` / `matched_evidence` / `gaps` / `resume_suggestions` / `interview_focus`），用 Pydantic 校验。分批调用时，各批结果先汇总，再做**全局排序**并重新分配 `rank`，避免“每批内部排序后直接拼接”导致的错误顺序。`ReportGenerator` 用系统代码生成 CSV 总览和 Markdown 报告，AI 不参与格式化。

### 运行轨迹

`_StepTracker` 给每一步计时、记录成功/失败，写入 `{run_id}_steps.jsonl`；开启持久化时同步写 `agent_steps` 表。JSONL 面向单次运行的可读排查，DB 面向跨运行查询，二者字段一致。任一步失败抛 `WorkflowError`，结果里带上 `failed_step`。

### 可测试性

采集器和 AI Provider 通过工厂注入，测试用 fixture + 假 Provider 完整跑通工作流，不触发真实 subprocess 或网络。

# 任务评估

本项目的评估脚本是 `scripts/evaluate_job_agent.py`。它读取真实 BOSS JSON 导出和追加式运行日志，按导出文件关联对应的采集记录，避免历史任务污染当前结果：

```powershell
python scripts/evaluate_job_agent.py `
  --jobs data/raw_jobs/<real-export>.json `
  --details data/raw_jobs/<real-details>.json `
  --run-log data/runs/agent_runs.jsonl `
  --output data/reports/evaluation.json `
  --markdown-output data/reports/evaluation.md
```

## 指标口径

| 指标 | 口径 |
| --- | --- |
| 岗位采集成功率 | `boss_collect` 任务中 `status=success` 的任务数 / 采集任务总数。 |
| 字段完整率 | `source_job_id`、`title`、`company`、`location`、`salary`、`tags`、`job_url` 共 7 个列表页字段中非空字段数 / 应有字段总数。JD 正文属于详情页字段，不计入列表页快速采集的完整率。 |
| 详情 JD 完整率 | 在提供 `--details` 时，详情记录中 `source_job_id` 和 `jd_text` 同时非空的字段比例。 |
| 技能标签准确率 | 对 `--skill-gold` 独立参考技能集合计算 micro-F1，同时输出 precision 和 recall。本次 30 条评估使用只读取职位描述区的独立 JD 文本标签规则，不读取 `JDStructurer` 输出。没有参考标注时返回 `null`。 |
| 匹配解释有效率 | 检查每个测试岗位是否有完整的 `matched_evidence`、`gaps`、`resume_suggestions` 和 `interview_focus`，这是结构有效性，不等同于语义正确性。匹配子集测试使用 `--match-job-ids` 指定分母。没有真实匹配结果时返回 `null`。 |
| 平均任务耗时 | 当前评估范围内 `boss_collect` 运行记录的 `duration_ms` 平均值。 |

## 2026-07-18 真实采集结果

本次使用 BOSS 直聘专用 Chrome CDP 登录态，以关键词 `AI Agent`、城市上海、1 页、列表页模式采集，得到 30 条岗位。当前运行日志只关联这 1 次采集任务：

| 指标 | 实测结果 | 说明 |
| --- | ---: | --- |
| 岗位采集成功率 | 100% | 1 / 1 次采集任务成功，不能表述为 30 / 30 次任务。 |
| 列表页字段完整率 | 100% | 30 条岗位 × 7 个字段全部非空。 |
| 详情 JD 完整率 | 100% | 30 / 30 条岗位均成功获取 JD 正文。 |
| 技能标签准确率 | 86.72% micro-F1 | 30 条详情 JD 独立参考标签；precision 86.34%，recall 87.11%。 |
| 匹配解释有效率 | 100% | 30 / 30 条匹配结果均覆盖岗位 ID，并包含匹配证据、差距、简历建议和岗位准备重点；这是结构有效性指标，不代表人工语义正确率。 |
| 平均采集耗时 | 20.996 秒 | 1 次采集任务的实测耗时。 |

本次 30 条岗位全部抓取详情，30 条均返回 JD 正文。使用独立的 JD 职位描述区标签规则建立 30 条参考标签后，规则版 `JDStructurer` 的技能标签 micro-F1 为 86.72%，precision 为 86.34%，recall 为 87.11%。参考标签只读取当前岗位职位描述区，不读取 `JDStructurer` 的预测结果、列表页 `skills` 字段或页面推荐岗位区。

使用同一批 30 条岗位调用真实 OpenAI-compatible 模型，模型返回了 30 条结构化匹配结果；四类解释字段均非空，因此匹配解释结构有效率为 100%。分母通过 `--match-job-ids` 显式指定为这 30 条岗位。

这批数据足以支持简历中的“30 条真实岗位采集、详情解析、技能识别与匹配评估集”结论，但采集运行日志只有 1 次真实采集任务，因此不能表述成“30 次独立采集任务”。后续扩大采集任务次数时，评估脚本会复用同一口径；输入缺失时保留 `null`，不会把失败请求转换为 0%。

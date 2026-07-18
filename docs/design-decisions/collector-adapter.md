# Design Decision: JobCollectorAdapter

## 决策

本项目不直接把 `boss-zhipin-scraper` 的脚本逻辑复制进业务代码，而是通过 `BossZhipinCollector` 做采集适配层。适配层统一输入 `CollectionRequest`，统一输出 `BossCollectionResult`，其中包含 `raw_jobs` 和 `AgentRun`。

## 为什么需要 Adapter

`boss-zhipin-scraper` 是一个外部采集工具，它的边界是命令行参数、JSON 文件和进程退出码。招聘数据 Agent 需要的是稳定的业务接口：

```text
CollectionRequest
  -> safety check
  -> external scraper command
  -> raw JSON file
  -> List[RawJobPost]
  -> AgentRun
```

Adapter 的价值是把外部工具的不稳定细节挡在边界外。后续如果支持其他招聘网站，或者 `boss-zhipin-scraper` 的输出字段变化，下游的 JD 结构化、技能分析、简历匹配不需要跟着重写。

## 实现范围

已经完成：

- 构造 `boss_cdp_raw.py` 命令。
- 调用前执行 `CollectionSafetyPolicy`。
- 默认使用 `--no-detail`，只采集岗位列表。
- 将输出 JSON 转为 `RawJobPost`。
- 记录 `AgentRun`，包含状态、错误、耗时、命令和 raw 输出路径。
- 将 run 追加写入 `data/runs/agent_runs.jsonl`。

适配器不负责：

- 数据库持久化。
- JD 结构化和技能分析。
- 简历匹配和报告生成。

## 错误处理

Adapter 会把三类错误统一落到 `AgentRun.status = failed`：

- 安全检查不通过，例如页数过高、使用主浏览器 Profile、复制登录态。
- 外部脚本返回非 0 退出码，例如 CDP 未启动或未登录。
- 输出文件不存在或 JSON 无法读取。

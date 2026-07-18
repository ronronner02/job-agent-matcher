# Design Decision: Database Modeling

## 决策

项目引入 SQLite + SQLAlchemy，把岗位数据从文件流转升级为可查询、可去重、可追踪的数据库模型。

## 表设计

- `job_posts`：岗位主表，保存平台、来源岗位 ID、关键词、城市、标题、公司、地点、薪资、经验、学历、JD、链接和原始 payload。
- `job_skills`：岗位技能表，从归一化结果中拆出技能关键词，支持后续技能统计和匹配。
- `agent_runs`：执行记录表，保存采集/导入任务的状态、耗时、命令、输出路径和错误信息。

## 为什么这样建模

`job_posts` 使用 `(platform, source_job_id)` 唯一约束，解决重复导入问题；`job_skills` 单独拆表，是为了让技能分析不依赖 JSON 字段扫描；`agent_runs` 独立保存执行轨迹，方便解释可观测性和问题排查。

## 当前边界

当前只做最小可用持久化，不引入复杂迁移系统、向量数据库或用户账户体系。现有 upsert 适合单用户 CLI/本地演示场景；如果后续进入并发服务，需要升级为数据库原生 upsert 或增加任务锁。JD 结构化、技能分析和简历匹配可以继续复用这层 Repository。

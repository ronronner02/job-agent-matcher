# Design Decision: JD Structuring

## 决策

项目引入 `StructuredJD` Pydantic Schema 和规则版 `JDStructurer`，先把 JD 原文解析成职责、要求、技能标签、风险点、摘要和置信度。当前实现不依赖真实 LLM，保证测试稳定；后续可以用 LLM 替换解析实现，但保持 Schema 和下游接口不变。

## 为什么先做规则版

JD 结构化最终会接 LLM，但如果一开始就依赖大模型，测试会不稳定，成本也更高。规则版先解决三个基础问题：

- 明确结构化输出格式。
- 让样例数据可以稳定跑通。
- 给后续 LLM 输出提供校验 Schema。

## Schema 设计

- `StructuredJD`：保存岗位 ID、岗位标题、职责、要求、技能、风险点、摘要和置信度。
- `SkillRequirement`：保存技能名称、技能类别、证据片段和是否必需。
- `SkillCategory`：把技能分为语言、后端、AI、数据、DevOps、工作流等类别。

## 当前边界

当前解析器依赖技能词典、句子切分和关键词规则，适合稳定测试和演示，不适合替代最终 LLM 解析。后续接 LLM 时，LLM 只负责生成 `StructuredJD` 兼容 JSON，Pydantic 负责校验，规则版可以作为 fallback。

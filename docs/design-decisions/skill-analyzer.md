# Design Decision: Skill Analyzer

## 决策

`SkillAnalyzer` 基于 `StructuredJD.skills` 做岗位技能画像统计。它不重新解析 JD 原文，而是聚合结构化后的技能结果，输出高频技能、技能类别分布、常见技能组合、核心技能清单和学习建议。

## 为什么放在 JDStructurer 后面

`JDStructurer` 负责从自然语言 JD 中提取结构化技能；`SkillAnalyzer` 负责统计和解释这些技能。拆开后，后续无论 JD 结构化来自规则版还是 LLM 版，技能统计逻辑都可以复用。

## 输出设计

- `top_skills`：统计技能出现次数、覆盖岗位数和覆盖率。
- `category_distribution`：统计 AI、backend、data、devops 等类别分布。
- `common_skill_pairs`：统计岗位中常见技能组合，例如 Python + RAG。
- `required_skill_names`：输出后续简历匹配优先关注的技能名。
- `recommendations`：把统计结果转成求职准备建议。

## 当前边界

当前统计基于样本岗位集合，不代表全市场结论。接入真实采集数据后，可以用同一套分析逻辑生成技能画像和求职报告。

# AI Resume-Job Analysis

## 背景

项目原计划在岗位画像之后实现规则版 `ResumeParser`，把简历拆成技能、项目、教育和关键词。但简历是高自由度长文本，规则解析容易漏掉上下文，也容易把“项目经历”和“技能证据”割裂开。

## 决策

跳过单独的规则版 `ResumeParser`，改为让 AI 模型直接读取：

- 私有简历文本。
- Pipeline 产出的 `StructuredJD` 岗位样本。

系统通过 `AIResumeJobAnalyzer` 构造受约束 Prompt，要求模型输出中文 Markdown 报告，包括总体匹配、匹配优势、主要差距、简历改写建议和岗位准备重点。

## 为什么仍然需要结构化 JD

LLM 直接读所有原始岗位文本会带来输入冗余和不可控问题。项目仍然先用 `JDStructurer` 把岗位压缩成职责、要求、技能和风险点，再交给 LLM 分析。这样模型看到的是高信噪比岗位画像，输出更稳定，也更容易解释。

## Provider 边界

`AIResumeJobAnalyzer` 只依赖最小接口 `generate(prompt)`。真实调用由 `OpenAICompatibleProvider` 完成，支持环境变量：

- `AI_MATCHER_API_KEY` 或 `OPENAI_API_KEY`
- `AI_MATCHER_BASE_URL` 或 `OPENAI_BASE_URL`
- `AI_MATCHER_MODEL` 或 `OPENAI_MODEL`
- `AI_MATCHER_TIMEOUT_SECONDS`：慢模型或中转服务的请求超时秒数。
- `AI_MATCHER_MAX_TOKENS`：可选输出长度限制。部分 OpenAI-compatible 服务不支持该参数，不配置即可。

公开仓库不保存 Key、Base URL、简历原文、Cookie 或真实岗位数据。

## 运行方式

```powershell
python scripts/analyze_resume_jobs.py `
  --resume-file private/resume.pdf `
  --jobs data/raw_jobs/my_jobs.json `
  --output data/reports/resume_job_ai_analysis.md `
  --max-jobs 20
```

`--resume-file` 支持 `.pdf`、`.txt` 和 `.md`。PDF 会先用 `pypdf` 提取文本，再交给 AI 分析；如果 PDF 是扫描图片版，需要先做 OCR，否则无法提取有效文字。

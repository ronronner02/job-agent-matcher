from __future__ import annotations

from typing import Protocol

from app.schemas.jd import StructuredJD


class TextGenerationProvider(Protocol):
    """Minimal interface for any LLM provider used by resume-job analysis."""

    def generate(self, prompt: str) -> str:
        """Return model-generated text for the given prompt."""


def analyze_resume_against_jobs(
    resume_text: str,
    structured_jds: list[StructuredJD],
    provider: TextGenerationProvider,
    *,
    max_jobs: int = 20,
) -> str:
    """Ask an AI model to compare one resume with collected structured jobs."""

    cleaned_resume = resume_text.strip()
    if not cleaned_resume:
        raise ValueError("resume_text cannot be blank")
    if not structured_jds:
        raise ValueError("structured_jds cannot be empty")
    if max_jobs <= 0:
        raise ValueError("max_jobs must be positive")

    prompt = build_resume_job_analysis_prompt(cleaned_resume, structured_jds[:max_jobs])
    result = provider.generate(prompt).strip()
    if not result:
        raise ValueError("AI provider returned an empty analysis")
    return result


def build_resume_job_analysis_prompt(
    resume_text: str,
    structured_jds: list[StructuredJD],
) -> str:
    """Build a grounded prompt from private resume text and structured jobs."""

    job_blocks = "\n\n".join(_format_job_for_prompt(index, jd) for index, jd in enumerate(structured_jds, 1))
    return f"""你是一个严谨的 AI 求职匹配分析助手。请只基于下面给出的简历和岗位信息分析，不要编造经历、学历、项目或技能。

输出一份中文 Markdown 报告，必须包含以下部分：
1. 总体匹配结论：用 3-5 句话说明候选人与岗位样本的匹配度。
2. 建议投递顺序：必须用 Markdown 表格按匹配度从高到低排序所有岗位，列包含：排名、岗位ID、岗位标题、匹配度百分比、推荐等级、匹配理由、主要短板、投递建议。
3. 匹配优势：列出简历中已经能支撑岗位要求的证据。
4. 主要差距：列出岗位高频要求中简历证据不足的地方。
5. 简历改写建议：给出可以直接改进简历项目描述的建议，但不能虚构经历。
6. 面试准备重点：按优先级列出需要准备的技术讲法。

要求：
- 必须引用岗位中的技能、职责或风险点作为依据。
- 投递顺序必须覆盖输入的每一个岗位，不能只推荐前几名。
- 匹配度必须是 0-100 的整数；推荐等级只能是“优先投递”“可以投递”“谨慎投递”。
- 排名必须严格按匹配度从高到低排列；如果分数相同，优先选择短板更少的岗位。
- 如果简历没有证据，明确写“简历中暂无证据”。
- 不要输出任何 API、密钥、Cookie 或隐私建议。

## 简历文本

{resume_text}

## 岗位样本

{job_blocks}
"""


def _format_job_for_prompt(index: int, jd: StructuredJD) -> str:
    skills = "、".join(skill.name for skill in jd.skills) or "未识别到明确技能"
    responsibilities = "；".join(jd.responsibilities[:3]) or "无明确职责"
    requirements = "；".join(jd.requirements[:3]) or "无明确要求"
    risk_points = "；".join(jd.risk_points[:3]) or "无明确风险点"
    return (
        f"### 岗位 {index}: {jd.job_title}\n"
        f"- 岗位ID: {jd.source_job_id}\n"
        f"- 摘要: {jd.summary}\n"
        f"- 技能: {skills}\n"
        f"- 职责: {responsibilities}\n"
        f"- 要求: {requirements}\n"
        f"- 风险点: {risk_points}"
    )

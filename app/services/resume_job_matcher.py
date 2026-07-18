from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.schemas.jd import StructuredJD
from app.schemas.job import NormalizedJobPost
from app.schemas.match import JobMatchReport, JobMatchResult


class TextGenerationProvider(Protocol):
    """Minimal interface for any LLM provider used by resume-job matching."""

    def generate(self, prompt: str) -> str:
        """Return model-generated text for the given prompt."""


_LEVEL_ORDER = {"优先投递": 0, "可以投递": 1, "谨慎投递": 2}


@dataclass(frozen=True)
class JobMatchContext:
    """A job paired with its structured JD, everything the matcher needs."""

    job: NormalizedJobPost
    jd: StructuredJD


def build_match_contexts(
    jobs: list[NormalizedJobPost],
    structured_jds: list[StructuredJD],
) -> list[JobMatchContext]:
    """Pair normalized jobs with their structured JDs by source_job_id."""

    jd_by_id = {jd.source_job_id: jd for jd in structured_jds}
    contexts: list[JobMatchContext] = []
    for job in jobs:
        jd = jd_by_id.get(job.source_job_id)
        if jd is not None:
            contexts.append(JobMatchContext(job=job, jd=jd))
    return contexts


def match_resume_against_jobs(
    resume_text: str,
    contexts: list[JobMatchContext],
    provider: TextGenerationProvider,
    *,
    run_id: str,
    max_jobs: int = 20,
    batch_size: int = 0,
) -> JobMatchReport:
    """Produce a globally-ranked structured match report.

    The model is asked to return JSON. Results from every batch are collected,
    validated with Pydantic, then sorted globally by score (ties broken by
    recommendation level then fewer gaps). Ranks are assigned after the global
    sort so batching never leaks into the final ordering.
    """

    cleaned_resume = resume_text.strip()
    if not cleaned_resume:
        raise ValueError("resume_text cannot be blank")
    if not contexts:
        raise ValueError("contexts cannot be empty")
    if max_jobs <= 0:
        raise ValueError("max_jobs must be positive")

    selected = contexts[:max_jobs]
    batches = _split_batches(selected, batch_size)

    results: list[JobMatchResult] = []
    seen_ids: set[str] = set()
    valid_ids = {ctx.job.source_job_id for ctx in selected}
    for batch in batches:
        raw = provider.generate(build_match_prompt(cleaned_resume, batch)).strip()
        for result in parse_match_results(raw):
            if result.source_job_id in valid_ids and result.source_job_id not in seen_ids:
                seen_ids.add(result.source_job_id)
                results.append(result)

    ranked = rank_match_results(results)
    return JobMatchReport(run_id=run_id, total_jobs=len(selected), results=ranked)


def rank_match_results(results: list[JobMatchResult]) -> list[JobMatchResult]:
    """Global sort by score desc, then recommendation level, then fewer gaps."""

    ordered = sorted(
        results,
        key=lambda r: (
            -r.match_score,
            _LEVEL_ORDER.get(r.recommendation_level, 9),
            len(r.gaps),
        ),
    )
    return [result.model_copy(update={"rank": index}) for index, result in enumerate(ordered, start=1)]


def parse_match_results(raw: str) -> list[JobMatchResult]:
    """Parse JSON (possibly fenced) into JobMatchResult, tolerating noise."""

    payload = _extract_json(raw)
    if payload is None:
        return []

    items: list[object]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        candidate = payload.get("results") or payload.get("matches") or payload.get("jobs")
        items = candidate if isinstance(candidate, list) else [payload]
    else:
        return []

    results: list[JobMatchResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            results.append(JobMatchResult.model_validate(item))
        except Exception:
            continue
    return results


def build_match_prompt(resume_text: str, contexts: list[JobMatchContext]) -> str:
    """Build a grounded prompt asking for a strict JSON match array."""

    job_blocks = "\n\n".join(
        _format_job_for_prompt(index, ctx) for index, ctx in enumerate(contexts, 1)
    )
    return f"""你是一个严谨的 AI 求职匹配分析助手。请只基于下面给出的简历和岗位信息分析，不要编造经历、学历、项目或技能。

请为每一个岗位输出一条匹配结果，并且只输出一个 JSON 数组，不要输出任何多余文字或 Markdown。
数组中每个对象必须包含这些字段：
- source_job_id: 字符串，必须与岗位信息中的“岗位ID”完全一致。
- match_score: 0-100 的整数匹配度。
- recommendation_level: 只能是 "优先投递"、"可以投递" 或 "谨慎投递"。
- matched_evidence: 字符串数组，简历中能支撑该岗位要求的证据。
- gaps: 字符串数组，岗位要求中简历证据不足的地方；没有证据时写“简历中暂无证据”。
- resume_suggestions: 字符串数组，可直接改进简历的建议，但不能虚构经历。
- interview_focus: 字符串数组，针对该岗位需要准备的面试重点。

要求：
- 必须覆盖输入的每一个岗位，不能只返回前几个。
- 匹配理由要引用岗位的技能、职责、要求或风险点。
- 不要输出任何 API、密钥、Cookie 或隐私建议。

## 简历文本

{resume_text}

## 岗位样本

{job_blocks}
"""


def _format_job_for_prompt(index: int, ctx: JobMatchContext) -> str:
    job = ctx.job
    jd = ctx.jd
    skills = "、".join(skill.name for skill in jd.skills) or "未识别到明确技能"
    responsibilities = "；".join(jd.responsibilities[:3]) or "无明确职责"
    requirements = "；".join(jd.requirements[:3]) or "无明确要求"
    risk_points = "；".join(jd.risk_points[:3]) or "无明确风险点"
    welfare = "、".join(job.welfare) or "未提供"
    return (
        f"### 岗位 {index}: {job.job_title}\n"
        f"- 岗位ID: {job.source_job_id}\n"
        f"- 公司: {job.company}\n"
        f"- 地点: {job.location}\n"
        f"- 地址: {job.address or '未提供'}\n"
        f"- 薪资: {job.salary or '未提供'}\n"
        f"- 经验: {job.experience_required or '未提供'}\n"
        f"- 学历: {job.education_required or '未提供'}\n"
        f"- 公司规模: {job.company_scale or '未提供'}\n"
        f"- 融资阶段: {job.company_stage or '未提供'}\n"
        f"- 行业: {job.company_industry or '未提供'}\n"
        f"- 福利: {welfare}\n"
        f"- 岗位链接: {job.job_url or job.detail_url or '未提供'}\n"
        f"- JD摘要: {jd.summary}\n"
        f"- 技能: {skills}\n"
        f"- 职责: {responsibilities}\n"
        f"- 要求: {requirements}\n"
        f"- 风险点: {risk_points}"
    )


def _split_batches(
    contexts: list[JobMatchContext],
    batch_size: int,
) -> list[list[JobMatchContext]]:
    if batch_size <= 0 or batch_size >= len(contexts):
        return [contexts]
    return [contexts[i : i + batch_size] for i in range(0, len(contexts), batch_size)]


def _extract_json(raw: str) -> object | None:
    text = raw.strip()
    if not text:
        return None

    # Strip Markdown code fences if the model wrapped the JSON.
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the first balanced array/object substring.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None

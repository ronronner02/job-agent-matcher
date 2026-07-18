from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.collectors.boss_zhipin_collector import BossCollectionResult, BossZhipinCollector
from app.db.session import session_scope
from app.integrations.boss_zhipin.detail_merge import (
    dedupe_raw_jobs,
    merge_boss_list_and_detail_jobs,
)
from app.schemas.collect import CollectionRequest
from app.schemas.job import NormalizedJobPost, RawJobPost
from app.schemas.match import JobMatchReport
from app.schemas.run import AgentRun, AgentStep
from app.schemas.workflow import (
    FullJobAgentRequest,
    FullJobAgentResult,
    WorkflowArtifacts,
)
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.repositories.job_repository import upsert_normalized_jobs
from app.repositories.match_repository import save_match_report
from app.repositories.run_repository import save_agent_run, save_agent_steps
from app.services.report_generator import build_final_report, build_overview_csv
from app.services.resume_job_matcher import (
    TextGenerationProvider,
    build_match_contexts,
    match_resume_against_jobs,
)
from app.services.resume_reader import read_resume_text
from app.services.skill_analyzer import analyze_skills


# Injected so tests can avoid subprocess/network. Defaults use the real thing.
CollectorFactory = Callable[[FullJobAgentRequest], BossZhipinCollector]
ProviderFactory = Callable[[], TextGenerationProvider]
ResumeReader = Callable[[str], str]


STEP_ORDER = [
    "resume_reading",
    "collection",
    "detail_merge",
    "normalization",
    "persistence",
    "jd_structuring",
    "skill_analysis",
    "resume_matching",
    "report_generation",
]


class WorkflowError(Exception):
    """Raised when a workflow step fails; carries the step name for reporting."""

    def __init__(self, step_name: str, message: str) -> None:
        super().__init__(message)
        self.step_name = step_name
        self.message = message


class _StepTracker:
    """Times each step, records success/failure, and keeps a consistent trace.

    Steps are appended to an in-memory list that is later written to JSONL and,
    when persistence is on, to the ``agent_steps`` table. A failed step raises
    ``WorkflowError`` so the workflow can stop and report exactly where.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.steps: list[AgentStep] = []
        self._order = 0

    def run(self, name: str, fn: Callable[[], "_StepOutcome"]) -> object:
        self._order += 1
        step = AgentStep(run_id=self.run_id, name=name, order_index=self._order, status="running")
        start = time.perf_counter()
        try:
            outcome = fn()
        except WorkflowError:
            raise
        except Exception as exc:  # convert any failure into a tracked step
            elapsed = _elapsed_ms(start)
            self.steps.append(step.finish_failed(error_message=str(exc), duration_ms=elapsed))
            raise WorkflowError(name, str(exc)) from exc

        elapsed = _elapsed_ms(start)
        self.steps.append(
            step.finish_success(
                detail=outcome.detail,
                item_count=outcome.item_count,
                duration_ms=elapsed,
                artifact_path=outcome.artifact_path,
            )
        )
        return outcome.value


class _StepOutcome:
    """Return value plus step metadata produced by a single step body."""

    def __init__(
        self,
        value: object,
        *,
        detail: str | None = None,
        item_count: int | None = None,
        artifact_path: str | None = None,
    ) -> None:
        self.value = value
        self.detail = detail
        self.item_count = item_count
        self.artifact_path = artifact_path


def run_full_job_agent_workflow(
    request: FullJobAgentRequest,
    *,
    collector_factory: CollectorFactory | None = None,
    provider_factory: ProviderFactory | None = None,
    resume_reader: ResumeReader = read_resume_text,
) -> FullJobAgentResult:
    """Run the whole job agent end to end and return a summary.

    Steps: collection -> detail_merge -> normalization -> persistence ->
    jd_structuring -> skill_analysis -> resume_matching -> report_generation.
    Every step is timed and recorded; if one fails, the run stops and the
    result names the failed step. All artifacts are written under ``output_dir``
    with the run id as a filename prefix.
    """

    run_id = uuid4().hex
    tracker = _StepTracker(run_id)
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = WorkflowArtifacts()

    collector_factory = collector_factory or _default_collector_factory
    provider_factory = provider_factory or _default_provider_factory

    result = FullJobAgentResult(
        run_id=run_id,
        status="running",
        keyword=request.keyword,
        cities=list(request.cities),
    )

    try:
        # 0. resume_reading — read the resume up front so a bad path or empty
        # file fails fast with its own step name (not mislabelled as collection).
        def _read_resume() -> _StepOutcome:
            text = resume_reader(request.resume_file)
            if not text.strip():
                raise RuntimeError(f"resume file is empty: {request.resume_file}")
            return _StepOutcome(text, detail=f"简历 {len(text)} 字", item_count=1)

        resume_text: str = tracker.run("resume_reading", _read_resume)  # type: ignore[assignment]

        collector = collector_factory(request)

        # 1. collection (per city, LIST ONLY — no detail pages yet)
        def _collect() -> _StepOutcome:
            collect_results = _collect_all_cities(collector, request)
            raw_jobs = [job for cr in collect_results for job in cr.raw_jobs]
            failures = [cr.run for cr in collect_results if cr.run.status != "success"]
            if not raw_jobs and failures:
                message = "; ".join(r.error_message or "collection failed" for r in failures)
                raise RuntimeError(_augment_cdp_error(message))
            detail = f"{len(request.cities)} 城市, {len(raw_jobs)} 条原始岗位"
            return _StepOutcome(raw_jobs, detail=detail, item_count=len(raw_jobs))

        raw_jobs: list[RawJobPost] = tracker.run("collection", _collect)  # type: ignore[assignment]
        result.raw_job_count = len(raw_jobs)

        # 2. detail_merge: dedupe -> title-filter -> CAP to max_jobs -> fetch
        # details for survivors only, then merge. Fetching details after filtering
        # and capping is the whole point: BOSS rate-limits each detail page to
        # ~30s, and its keyword search is fuzzy (a search for "AI Agent实习生" also
        # returns UE实习生, 产品实习生, ...). Only jobs that will actually be ranked
        # (contexts[:max_jobs]) get a detail fetch, so runtime is bounded by
        # max_jobs, not by how many jobs BOSS happened to return.
        def _dedupe() -> _StepOutcome:
            unique = dedupe_raw_jobs(raw_jobs)
            filtered = _filter_by_title(unique, request.title_filters)
            detail = f"去重后 {len(unique)} 条"
            if request.title_filters:
                detail += f", 标题过滤后 {len(filtered)} 条"

            # Cap BEFORE detail fetch. max_jobs bounds the final AI ranking, so
            # fetching JDs for jobs past that cap is wasted ~30s-per-page work.
            # max_details, when set, caps even tighter.
            cap = request.max_jobs
            if request.max_details is not None:
                cap = min(cap, request.max_details)
            capped = filtered[:cap]
            if len(capped) < len(filtered):
                detail += f", 取前 {len(capped)} 条抓取详情"

            merged = capped
            if request.include_detail and capped:
                detail_jobs = collector.fetch_details_for_jobs(
                    capped,
                    keyword=request.keyword,
                    cdp_port=request.cdp_port,
                    max_details=len(capped),
                )
                if detail_jobs:
                    merged = merge_boss_list_and_detail_jobs(capped, detail_jobs)
                    detail += f", 抓取详情 {len(detail_jobs)} 条"
            return _StepOutcome(merged, detail=detail, item_count=len(merged))

        unique_jobs: list[RawJobPost] = tracker.run("detail_merge", _dedupe)  # type: ignore[assignment]
        result.unique_job_count = len(unique_jobs)

        # 3. normalization
        def _normalize() -> _StepOutcome:
            normalized = normalize_boss_jobs(unique_jobs)
            return _StepOutcome(normalized, item_count=len(normalized))

        normalized_jobs: list[NormalizedJobPost] = tracker.run("normalization", _normalize)  # type: ignore[assignment]

        # 4. persistence
        def _persist() -> _StepOutcome:
            if not request.persist:
                return _StepOutcome(0, detail="persist=False, 跳过入库", item_count=0)
            with session_scope(request.database_url) as session:
                saved = upsert_normalized_jobs(session, normalized_jobs)
                count = len(saved)
            return _StepOutcome(count, item_count=count)

        saved_count: int = tracker.run("persistence", _persist)  # type: ignore[assignment]
        result.saved_job_count = saved_count

        # 5. jd_structuring
        structured_path = output_dir / f"{run_id}_structured_jobs.json"

        def _structure() -> _StepOutcome:
            structured = structure_jds(normalized_jobs)
            _write_json(structured_path, [jd.model_dump(mode="json") for jd in structured])
            return _StepOutcome(
                structured, item_count=len(structured), artifact_path=str(structured_path)
            )

        structured_jds = tracker.run("jd_structuring", _structure)
        result.structured_jd_count = len(structured_jds)  # type: ignore[arg-type]
        artifacts.structured_jobs_json = str(structured_path)

        # 6. skill_analysis
        skill_path = output_dir / f"{run_id}_skill_analysis.json"

        def _skills() -> _StepOutcome:
            report = analyze_skills(structured_jds)  # type: ignore[arg-type]
            _write_json(skill_path, report.model_dump(mode="json"))
            return _StepOutcome(report, artifact_path=str(skill_path))

        skill_report = tracker.run("skill_analysis", _skills)
        artifacts.skill_analysis_json = str(skill_path)

        # 7. resume_matching
        match_path = output_dir / f"{run_id}_match_results.json"

        def _match() -> _StepOutcome:
            contexts = build_match_contexts(normalized_jobs, structured_jds)  # type: ignore[arg-type]
            if not contexts:
                raise RuntimeError("no job/JD pairs to match")
            provider = provider_factory()
            report = match_resume_against_jobs(
                resume_text,
                contexts,
                provider,
                run_id=run_id,
                max_jobs=request.max_jobs,
                batch_size=request.batch_size,
            )
            if request.persist:
                with session_scope(request.database_url) as session:
                    save_match_report(session, report)
            _write_json(match_path, report.model_dump(mode="json"))
            return _StepOutcome(
                report, item_count=len(report.results), artifact_path=str(match_path)
            )

        match_report: JobMatchReport = tracker.run("resume_matching", _match)  # type: ignore[assignment]
        result.matched_job_count = len(match_report.results)
        artifacts.match_results_json = str(match_path)

        # 8. report_generation
        overview_path = output_dir / f"{run_id}_job_overview.csv"
        report_path = output_dir / f"{run_id}_final_report.md"

        def _report() -> _StepOutcome:
            jobs_by_id = {job.source_job_id: job for job in normalized_jobs}
            final = build_final_report(match_report, jobs_by_id, skill_report)  # type: ignore[arg-type]
            overview_path.write_text(build_overview_csv(final.overview), encoding="utf-8-sig")
            report_path.write_text(final.markdown, encoding="utf-8")
            return _StepOutcome(
                final, item_count=final.priority_jobs, artifact_path=str(report_path)
            )

        final_report = tracker.run("report_generation", _report)
        result.priority_job_count = final_report.priority_jobs  # type: ignore[attr-defined]
        artifacts.job_overview_csv = str(overview_path)
        artifacts.final_report_md = str(report_path)

        result.status = "success"
    except WorkflowError as exc:
        result.status = "failed"
        result.failed_step = exc.step_name
        result.error_message = exc.message

    # Always write the step trace and persist the run + steps, even on failure.
    steps_path = output_dir / f"{run_id}_steps.jsonl"
    _write_steps_jsonl(steps_path, tracker.steps)
    artifacts.steps_jsonl = str(steps_path)
    result.artifacts = artifacts

    if request.persist:
        _persist_run_trace(request, result, tracker.steps)

    return result


CDP_HINT = (
    "Chrome CDP 未启动，请先运行 --setup-chrome 并登录 BOSS：\n"
    "  python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --setup-chrome --cdp-port 9222\n"
    "  python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --check --cdp-port 9222"
)

_CDP_ERROR_MARKERS = ("127.0.0.1:9222", "WinError 10061", "/json/version")


def _augment_cdp_error(message: str) -> str:
    """Append a friendly CDP hint when the error looks like Chrome isn't up."""

    if any(marker in message for marker in _CDP_ERROR_MARKERS):
        return f"{message}\n\n{CDP_HINT}"
    return message


def _filter_by_title(jobs: list[RawJobPost], terms: list[str]) -> list[RawJobPost]:
    """Keep jobs whose title contains at least one term (case-insensitive).

    Returns the input unchanged when no terms are given, so filtering is fully
    opt-in and never silently drops everything.
    """

    if not terms:
        return jobs
    lowered = [term.lower() for term in terms if term.strip()]
    if not lowered:
        return jobs
    kept: list[RawJobPost] = []
    for job in jobs:
        title = (job.title or "").lower()
        if any(term in title for term in lowered):
            kept.append(job)
    return kept


def _collect_all_cities(
    collector: BossZhipinCollector,
    request: FullJobAgentRequest,
) -> list[BossCollectionResult]:
    results: list[BossCollectionResult] = []
    for city in request.cities:
        # List-only here: details are fetched later, after dedupe + title filter,
        # for survivors only (see the detail_merge step).
        collect_request = CollectionRequest(
            keyword=request.keyword,
            city=city,
            pages=request.pages,
            cdp_port=request.cdp_port,
            include_detail=False,
        )
        results.append(collector.collect_from_request(collect_request))
    return results


def _persist_run_trace(
    request: FullJobAgentRequest,
    result: FullJobAgentResult,
    steps: list[AgentStep],
) -> None:
    run = AgentRun(
        id=result.run_id,
        task_type="full_job_agent",
        keyword=request.keyword,
        city=",".join(request.cities),
        status="success" if result.status == "success" else "failed",
        total_jobs=result.unique_job_count,
        success_count=result.matched_job_count,
        error_message=result.error_message,
        raw_output_path=result.artifacts.final_report_md,
    )
    run = run.model_copy(update={"finished_at": run.started_at})
    with session_scope(request.database_url) as session:
        save_agent_run(session, run)
        save_agent_steps(session, steps)


def _default_collector_factory(request: FullJobAgentRequest) -> BossZhipinCollector:
    return BossZhipinCollector(scraper_root=request.scraper_root)


def _default_provider_factory() -> TextGenerationProvider:
    from app.services.llm_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider.from_env()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_steps_jsonl(path: Path, steps: list[AgentStep]) -> None:
    lines = [json.dumps(step.model_dump(mode="json"), ensure_ascii=False) for step in steps]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)

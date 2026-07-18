from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.integrations.boss_zhipin.detail_merge import merge_boss_list_and_detail_jobs
from app.schemas.collect import CollectionRequest
from app.schemas.job import RawJobPost
from app.schemas.run import AgentRun
from app.services.collection_safety import CollectionSafetyPolicy, validate_collection_request


CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class BossCollectionResult:
    raw_jobs: list[RawJobPost]
    run: AgentRun


class BossZhipinCollector:
    """Adapter for JSON exported by boss-zhipin-scraper.

    The real CDP script remains an external data source. This adapter is the
    first line of our own project: it converts exported rows into RawJobPost.
    """

    def __init__(
        self,
        export_path: str | Path | None = None,
        *,
        scraper_root: str | Path | None = None,
        output_dir: str | Path | None = None,
        run_log_path: str | Path | None = None,
        runner: CommandRunner | None = None,
    ):
        self.export_path = Path(export_path) if export_path else None
        root_value = scraper_root if scraper_root is not None else os.environ.get("BOSS_SCRAPER_ROOT")
        self.scraper_root = _resolve_scraper_root(Path(root_value).expanduser()) if root_value else None
        self.output_dir = Path(output_dir or os.environ.get("BOSS_RAW_OUTPUT_DIR", "data/raw_jobs"))
        self.run_log_path = Path(
            run_log_path or os.environ.get("BOSS_RUN_LOG_PATH", "data/runs/agent_runs.jsonl")
        )
        self.runner = runner or _default_runner

    def collect(self) -> list[RawJobPost]:
        if not self.export_path:
            raise ValueError("export_path is required when reading an existing export")
        payload = self._load_json()
        keyword = payload.get("keyword") if isinstance(payload, dict) else None
        city = payload.get("city") if isinstance(payload, dict) else None
        rows = self._extract_job_rows(payload)
        return [self._to_raw_job(row, keyword=keyword, city=city) for row in rows]

    def collect_details(self, detail_path: str | Path) -> list[RawJobPost]:
        """Read a scraper detail export (list of detail records) into raw jobs."""

        path = Path(detail_path)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        rows = self._extract_job_rows(payload)
        return [self._to_raw_job(row, keyword=None, city=None) for row in rows]

    def collect_from_request(
        self,
        request: CollectionRequest,
        *,
        policy: CollectionSafetyPolicy | None = None,
        output_path: str | Path | None = None,
    ) -> BossCollectionResult:
        start = time.perf_counter()
        output = (Path(output_path) if output_path else self._default_output_path(request)).resolve()
        command: list[str] = []
        run = AgentRun(
            task_type="boss_collect",
            keyword=request.keyword,
            city=request.city,
            status="running",
            raw_output_path=str(output),
        )

        safety = validate_collection_request(request, policy)
        if not safety.allowed:
            return self._finish_failed(
                run,
                "; ".join(safety.reasons),
                start,
            )

        try:
            command = self.build_command(request, output)
            run = run.model_copy(update={"command": command})
            output.parent.mkdir(parents=True, exist_ok=True)
            completed = self.runner(command, self.scraper_root)
            if completed.returncode != 0:
                message = _completed_error(completed)
                return self._finish_failed(run, message, start)
            if not output.exists():
                message = _completed_error(completed)
                return self._finish_failed(
                    run,
                    f"collector finished without creating output file: {output}; {message}",
                    start,
                )

            raw_jobs = BossZhipinCollector(output).collect()
            if request.include_detail:
                detail_path = self.detail_output_path(request, output)
                detail_jobs = self.collect_details(detail_path)
                if detail_jobs:
                    raw_jobs = merge_boss_list_and_detail_jobs(raw_jobs, detail_jobs)
            finished = run.finish_success(
                total_jobs=len(raw_jobs),
                duration_ms=_elapsed_ms(start),
            )
            self._append_run_log(finished)
            return BossCollectionResult(raw_jobs=raw_jobs, run=finished)
        except Exception as exc:
            if command:
                run = run.model_copy(update={"command": command})
            return self._finish_failed(run, str(exc), start)

    def build_command(
        self,
        request: CollectionRequest,
        output_path: str | Path,
    ) -> list[str]:
        script_path = self._scraper_script_path()
        if not script_path.exists():
            raise FileNotFoundError(f"boss-zhipin scraper script not found: {script_path}")

        command = [
            sys.executable,
            str(script_path),
            "--keyword",
            request.keyword,
            "--city",
            request.city,
            "--pages",
            str(request.pages),
            "--format",
            "json",
            "--output",
            str(output_path),
            "--cdp-port",
            str(request.cdp_port),
        ]

        if request.include_detail:
            command.extend(["--detail", "--detail-output", str(self.detail_output_path(request, output_path))])
            if request.max_details is not None:
                command.extend(["--max-details", str(request.max_details)])
        else:
            command.append("--no-detail")

        return command

    def detail_output_path(
        self,
        request: CollectionRequest,
        output_path: str | Path,
    ) -> Path:
        if request.detail_output_path:
            return Path(request.detail_output_path)
        output = Path(output_path)
        return output.with_name(f"{output.stem}_details{output.suffix}")

    def build_detail_command(
        self,
        list_path: str | Path,
        detail_path: str | Path,
        *,
        cdp_port: int,
        max_details: int | None = None,
    ) -> list[str]:
        """Build a command that fetches details for a pre-filtered list file.

        Uses the scraper's ``--input`` mode: it reads jobs from ``list_path``
        (no re-scraping the search results) and only fetches detail pages for
        those jobs. This is what lets us fetch details *after* dedupe and title
        filtering, instead of paying ~30s per detail page for jobs we discard.
        """

        script_path = self._scraper_script_path()
        if not script_path.exists():
            raise FileNotFoundError(f"boss-zhipin scraper script not found: {script_path}")

        command = [
            sys.executable,
            str(script_path),
            "--input",
            str(list_path),
            "--detail",
            "--detail-output",
            str(detail_path),
            "--cdp-port",
            str(cdp_port),
            "--format",
            "json",
        ]
        if max_details is not None:
            command.extend(["--max-details", str(max_details)])
        return command

    def fetch_details_for_jobs(
        self,
        jobs: list[RawJobPost],
        *,
        keyword: str,
        city: str = "",
        cdp_port: int = 9222,
        max_details: int | None = None,
    ) -> list[RawJobPost]:
        """Fetch detail-page JD only for the given (already filtered) jobs.

        Writes the jobs' original payloads to a temporary list file, runs the
        scraper in ``--input`` mode, and reads back the detail export. Returns an
        empty list (never raises for an empty input) when there is nothing to do.
        """

        if not jobs or self.scraper_root is None:
            return []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        list_path = (self.output_dir / f"filtered_{_safe_slug(keyword)}_{timestamp}.json").resolve()
        detail_path = list_path.with_name(f"{list_path.stem}_details.json")

        payload = {
            "keyword": keyword,
            "city": city,
            "total": len(jobs),
            "jobs": [dict(job.raw_payload) for job in jobs if job.raw_payload],
        }
        if not payload["jobs"]:
            return []

        list_path.parent.mkdir(parents=True, exist_ok=True)
        list_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        command = self.build_detail_command(
            list_path, detail_path, cdp_port=cdp_port, max_details=max_details
        )
        completed = self.runner(command, self.scraper_root)
        if completed.returncode != 0:
            raise RuntimeError(_completed_error(completed))
        return self.collect_details(detail_path)

    def _load_json(self) -> Any:
        if not self.export_path:
            raise ValueError("export_path is required")
        with self.export_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _scraper_script_path(self) -> Path:
        if self.scraper_root is None:
            raise ValueError("scraper_root is required or BOSS_SCRAPER_ROOT must be set")
        # scraper_root is already absolute (see resolve_boss_scraper_root); the
        # script path must stay absolute because the runner uses cwd=scraper_root,
        # otherwise a relative path would be re-joined and duplicated.
        return (self.scraper_root / SCRAPER_SCRIPT_RELPATH).resolve()

    def _default_output_path(self, request: CollectionRequest) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        keyword = _safe_slug(request.keyword)
        city = _safe_slug(request.city)
        return self.output_dir / f"boss_jobs_{keyword}_{city}_{timestamp}.json"

    def _finish_failed(
        self,
        run: AgentRun,
        error_message: str,
        start: float,
    ) -> BossCollectionResult:
        finished = run.finish_failed(
            error_message=error_message,
            duration_ms=_elapsed_ms(start),
        )
        self._append_run_log(finished)
        return BossCollectionResult(raw_jobs=[], run=finished)

    def _append_run_log(self, run: AgentRun) -> None:
        self.run_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.run_log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(run.model_dump(mode="json"), ensure_ascii=False) + "\n")

    @staticmethod
    def _extract_job_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            jobs = payload.get("jobs", [])
            if isinstance(jobs, list):
                return [row for row in jobs if isinstance(row, dict)]
            return []
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    @staticmethod
    def _to_raw_job(
        row: dict[str, Any],
        *,
        keyword: str | None,
        city: str | None,
    ) -> RawJobPost:
        job_url = _first_text(row, "job_link", "job_url", "url", "link")
        return RawJobPost(
            keyword=keyword,
            city=city,
            source_job_id=_first_text(row, "job_id", "encrypt_job_id", "security_id"),
            title=_first_text(row, "title", "job_name", "jobName"),
            company=_first_text(row, "company", "company_name", "brandName", "boss_name"),
            location=_first_text(row, "location", "areaDistrict", "cityName"),
            address=_first_text(row, "address", "work_address", "workAddress", "detail_address"),
            salary=_first_text(row, "salary", "salaryDesc"),
            tags=_first_text(row, "tags", "tags_list", "job_labels", "jobLabels"),
            skills=_skill_values(row),
            job_url=job_url,
            detail_url=_first_text(row, "detail_url", "job_link", "job_url", "link"),
            jd_text=_first_text(row, "jd_text", "jd", "description", "job_description"),
            company_scale=_first_text(row, "company_scale", "scale", "brandScaleName", "companyScale"),
            company_stage=_first_text(row, "company_stage", "stage", "brandStageName", "financeStage"),
            company_industry=_first_text(
                row, "company_industry", "industry", "brandIndustry", "industryName"
            ),
            company_link=_first_text(row, "company_link", "companyUrl", "brand_link"),
            boss_name=_first_text(row, "boss_name", "bossName", "hrName"),
            boss_title=_first_text(row, "boss_title", "bossTitle", "hrTitle"),
            welfare=_first_text(row, "welfare", "welfareList", "brandWelfare"),
            raw_payload=row,
        )


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _skill_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("skills", "skills_text", "skillLabels", "job_labels", "jobLabels"):
        values.extend(_split_skill_value(row.get(key)))

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        normalized = cleaned.lower()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            deduped.append(cleaned)
    return deduped


def _split_skill_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(",", "|").split("|") if item.strip()]
    return [str(value).strip()]


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _default_runner(
    command: list[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the scraper, streaming its output live so long runs show progress.

    ``capture_output=True`` used to hide all scraper progress until the process
    exited, which made a slow-but-working detail crawl look frozen. We now stream
    each line to stderr as it arrives while still buffering it for error
    reporting, and enforce a timeout so a stuck detail page cannot hang forever.

    The timeout (seconds) comes from ``BOSS_COLLECT_TIMEOUT_SECONDS`` (default
    1800). On timeout the process is killed and a non-zero result is returned so
    the caller records a clear failure instead of blocking.
    """

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    timeout_seconds = _int_env("BOSS_COLLECT_TIMEOUT_SECONDS", 1800)

    start = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    lines: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            lines.append(line)
            sys.stderr.write(line)
            sys.stderr.flush()
            if timeout_seconds and (time.perf_counter() - start) > timeout_seconds:
                process.kill()
                process.wait()
                lines.append(f"\n[TIMEOUT] collector exceeded {timeout_seconds}s and was killed\n")
                return subprocess.CompletedProcess(command, 124, stdout="".join(lines), stderr="")
        returncode = process.wait()
    except Exception:
        process.kill()
        raise

    return subprocess.CompletedProcess(command, returncode, stdout="".join(lines), stderr="")


def _completed_error(completed: subprocess.CompletedProcess[str]) -> str:
    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()
    message = stderr or stdout or f"collector exited with code {completed.returncode}"
    return message[-2000:]


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


SCRAPER_SCRIPT_RELPATH = Path("scripts") / "boss_cdp_raw.py"


def resolve_boss_scraper_root(root: Path) -> Path:
    """Resolve the real boss-zhipin-scraper root to an ABSOLUTE path.

    ``root`` is always the scraper's true root (the directory that directly
    contains ``scripts/boss_cdp_raw.py``). We accept three shapes:

      1. A direct root:   ``<root>/scripts/boss_cdp_raw.py`` exists.
      2. The project root ``.`` or any parent that contains the scraper one
         level down (e.g. ``external/boss-zhipin-scraper``).
      3. A one-level download wrapper (``<root>/<inner>/scripts/...``).

    The result is always absolute so it can be used both as ``cwd`` and to build
    an absolute script path — never re-joined against ``cwd`` again. If nothing
    matches, raise with every candidate path we checked.
    """

    resolved = root.expanduser().resolve()
    checked: list[Path] = []

    # 1. Direct root.
    direct = resolved / SCRAPER_SCRIPT_RELPATH
    checked.append(direct)
    if direct.exists():
        return resolved

    # 2. Known layout: <root>/external/boss-zhipin-scraper/scripts/...
    #    Lets callers pass the project root (or ".") without knowing the layout.
    conventional = resolved / "external" / "boss-zhipin-scraper" / SCRAPER_SCRIPT_RELPATH
    checked.append(conventional)
    if conventional.exists():
        return (resolved / "external" / "boss-zhipin-scraper").resolve()

    # 3. Any single one-level nested match (download wrapper, etc.).
    nested_matches = sorted(resolved.glob(f"*/{SCRAPER_SCRIPT_RELPATH.as_posix()}"))
    checked.append(resolved / "*" / SCRAPER_SCRIPT_RELPATH)
    if len(nested_matches) == 1:
        return nested_matches[0].parents[1].resolve()

    joined = "\n".join(f"  - {path}" for path in checked)
    raise FileNotFoundError(
        "boss-zhipin scraper script not found. Checked these candidate paths:\n"
        f"{joined}\n"
        f"Pass --scraper-root pointing at the directory that contains "
        f"'{SCRAPER_SCRIPT_RELPATH.as_posix()}' (or the project root)."
    )


# Backwards-compatible alias for the previous private name.
_resolve_scraper_root = resolve_boss_scraper_root


def _safe_slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isascii() and ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if cleaned:
        return cleaned
    digest = hashlib.sha1(value.strip().encode("utf-8")).hexdigest()[:8]
    return f"text-{digest}"

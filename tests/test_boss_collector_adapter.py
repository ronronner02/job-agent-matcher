import json
import subprocess
from pathlib import Path

import pytest

from app.collectors.boss_zhipin_collector import (
    BossZhipinCollector,
    resolve_boss_scraper_root,
)
from app.schemas.collect import CollectionRequest
from app.schemas.job import RawJobPost


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def test_collector_reads_boss_export_into_raw_jobs() -> None:
    raw_jobs = BossZhipinCollector(FIXTURE).collect()

    assert len(raw_jobs) == 3
    assert raw_jobs[0].keyword == "AI Agent"
    assert raw_jobs[0].city == "上海"
    assert raw_jobs[0].source_job_id == "sample-ai-agent-001"
    assert raw_jobs[0].skills == ["Python", "FastAPI", "LangGraph", "RAG"]
    assert raw_jobs[0].raw_payload["company"] == "示例智能科技"


def test_collector_maps_current_scraper_field_names(tmp_path: Path) -> None:
    export_path = tmp_path / "boss_jobs.json"
    export_path.write_text(
        json.dumps(
            {
                "keyword": "AI Agent",
                "city": "上海",
                "jobs": [
                    {
                        "job_id": "current-001",
                        "title": "AI 应用工程师",
                        "boss_name": "示例公司",
                        "location": "上海",
                        "salary": "20-35K",
                        "tags": "1-3年 | 本科",
                        "job_labels": "Python | RAG | FastAPI",
                        "skills": "Python | LangGraph",
                        "job_link": "https://www.zhipin.com/job_detail/current-001.html",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    raw_jobs = BossZhipinCollector(export_path).collect()

    assert raw_jobs[0].company == "示例公司"
    assert raw_jobs[0].tags == "1-3年 | 本科"
    assert raw_jobs[0].skills == ["Python", "LangGraph", "RAG", "FastAPI"]


def test_build_command_includes_detail_by_default(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    collector = BossZhipinCollector(scraper_root=scraper_root)
    request = CollectionRequest(keyword="AI Agent", city="上海", pages=2)
    output_path = tmp_path / "raw" / "jobs.json"

    command = collector.build_command(request, output_path)

    assert command[1].endswith("boss_cdp_raw.py")
    assert "--keyword" in command
    assert command[command.index("--keyword") + 1] == "AI Agent"
    assert "--city" in command
    assert command[command.index("--city") + 1] == "上海"
    assert "--pages" in command
    assert command[command.index("--pages") + 1] == "2"
    assert "--output" in command
    assert command[command.index("--output") + 1] == str(output_path)
    assert "--detail" in command
    assert "--detail-output" in command
    assert command[command.index("--detail-output") + 1].endswith("jobs_details.json")
    assert "--no-detail" not in command
    assert "--copy-login-state" not in command


def test_build_command_can_disable_detail_and_cap_details(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    collector = BossZhipinCollector(scraper_root=scraper_root)
    output_path = tmp_path / "raw" / "jobs.json"

    no_detail = collector.build_command(
        CollectionRequest(keyword="AI Agent", city="上海", pages=1, include_detail=False),
        output_path,
    )
    assert "--no-detail" in no_detail
    assert "--detail" not in no_detail

    capped = collector.build_command(
        CollectionRequest(keyword="AI Agent", city="上海", pages=1, max_details=5),
        output_path,
    )
    assert "--max-details" in capped
    assert capped[capped.index("--max-details") + 1] == "5"


def test_build_command_accepts_one_level_wrapped_scraper_root(tmp_path: Path) -> None:
    wrapper_root = tmp_path / "download-wrapper"
    scraper_root = _fake_scraper_root(wrapper_root)
    collector = BossZhipinCollector(scraper_root=wrapper_root)
    request = CollectionRequest(keyword="AI Agent", city="上海", pages=1)

    command = collector.build_command(request, tmp_path / "jobs.json")

    assert Path(command[1]) == scraper_root / "scripts" / "boss_cdp_raw.py"


def test_scraper_root_pointing_at_real_root_is_not_duplicated(tmp_path: Path) -> None:
    # Passing the true scraper root must NOT re-append its own path segment.
    scraper_root = _fake_scraper_root(tmp_path)
    collector = BossZhipinCollector(scraper_root=scraper_root)
    request = CollectionRequest(keyword="AI Agent", city="上海", pages=1)

    command = collector.build_command(request, tmp_path / "jobs.json")
    script_path = Path(command[1])

    assert script_path == (scraper_root / "scripts" / "boss_cdp_raw.py").resolve()
    assert script_path.is_absolute()
    # The 'boss-zhipin-scraper' segment must appear exactly once, not twice.
    assert script_path.as_posix().count("boss-zhipin-scraper") == 1


def test_scraper_root_project_root_finds_external_scraper(tmp_path: Path) -> None:
    # --scraper-root . (project root) should find external/boss-zhipin-scraper.
    scraper_root = tmp_path / "external" / "boss-zhipin-scraper"
    scripts_dir = scraper_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "boss_cdp_raw.py").write_text("# fake scraper\n", encoding="utf-8")

    collector = BossZhipinCollector(scraper_root=tmp_path)
    request = CollectionRequest(keyword="AI Agent", city="上海", pages=1)

    command = collector.build_command(request, tmp_path / "jobs.json")
    script_path = Path(command[1])

    assert script_path == (scraper_root / "scripts" / "boss_cdp_raw.py").resolve()
    assert script_path.as_posix().count("boss-zhipin-scraper") == 1


def test_missing_scraper_script_error_lists_checked_paths(tmp_path: Path) -> None:
    empty_root = tmp_path / "nowhere"
    empty_root.mkdir()

    with pytest.raises(FileNotFoundError) as excinfo:
        BossZhipinCollector(scraper_root=empty_root)

    message = str(excinfo.value)
    assert "Checked these candidate paths" in message
    assert "scripts/boss_cdp_raw.py" in message
    # The direct-root candidate must be one of the listed paths.
    assert "nowhere" in message


def test_collect_from_request_runs_external_scraper_and_records_success(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    output_dir = tmp_path / "raw"
    run_log_path = tmp_path / "runs" / "agent_runs.jsonl"

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output_path = Path(command[command.index("--output") + 1])
        assert output_path.is_absolute()
        output_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        output_dir=output_dir,
        run_log_path=run_log_path,
        runner=fake_runner,
    )

    result = collector.collect_from_request(CollectionRequest(keyword="AI Agent", pages=1))

    assert result.run.status == "success"
    assert result.run.total_jobs == 3
    assert result.run.success_count == 3
    assert Path(result.run.raw_output_path or "").name.isascii()
    assert len(result.raw_jobs) == 3
    assert run_log_path.exists()
    logged = json.loads(run_log_path.read_text(encoding="utf-8").splitlines()[0])
    assert logged["status"] == "success"
    assert logged["total_jobs"] == 3


def test_fetch_details_for_jobs_runs_input_mode_for_survivors_only(tmp_path: Path) -> None:
    # Two-phase: after filtering, details are fetched via --input for the given
    # jobs only, so we never pay the ~30s/detail cost for discarded jobs.
    scraper_root = _fake_scraper_root(tmp_path)
    output_dir = tmp_path / "raw"

    detail_records = [
        {
            "job_id": "keep-1",
            "title": "AI Agent 应用工程师",
            "company": "示例公司",
            "job_link": "https://www.zhipin.com/job_detail/keep-1.html",
            "jd": "负责 Agent 应用开发，熟悉 RAG 与 LangGraph。",
            "tags_list": "3-5年 | 本科",
            "skill_tags": ["Python", "RAG"],
        }
    ]

    commands: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        detail_out = Path(command[command.index("--detail-output") + 1])
        detail_out.parent.mkdir(parents=True, exist_ok=True)
        detail_out.write_text(json.dumps(detail_records, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        output_dir=output_dir,
        runner=fake_runner,
    )

    survivor = RawJobPost(
        source_job_id="keep-1",
        title="AI Agent 应用工程师",
        raw_payload={"job_id": "keep-1", "job_link": "https://www.zhipin.com/job_detail/keep-1.html"},
    )

    details = collector.fetch_details_for_jobs(
        [survivor], keyword="AI Agent", cdp_port=9222, max_details=5
    )

    assert len(commands) == 1
    command = commands[0]
    assert "--input" in command  # input mode, not a fresh search
    assert "--detail" in command
    assert command[command.index("--max-details") + 1] == "5"
    assert len(details) == 1
    assert details[0].jd_text and "Agent" in details[0].jd_text


def test_fetch_details_for_jobs_returns_empty_for_no_jobs(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    calls: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(scraper_root=scraper_root, runner=fake_runner)

    assert collector.fetch_details_for_jobs([], keyword="AI Agent") == []
    assert calls == []  # never launches the scraper for an empty list


def test_collect_from_request_records_runner_failure(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    run_log_path = tmp_path / "runs" / "agent_runs.jsonl"

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="CDP not ready")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        run_log_path=run_log_path,
        runner=fake_runner,
    )

    result = collector.collect_from_request(CollectionRequest(keyword="AI Agent", pages=1))

    assert result.run.status == "failed"
    assert result.raw_jobs == []
    assert result.run.error_message == "CDP not ready"
    logged = json.loads(run_log_path.read_text(encoding="utf-8").splitlines()[0])
    assert logged["status"] == "failed"
    assert logged["error_message"] == "CDP not ready"


def test_collect_from_request_rejects_unsafe_request_before_runner(tmp_path: Path) -> None:
    scraper_root = _fake_scraper_root(tmp_path)
    calls: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        run_log_path=tmp_path / "runs" / "agent_runs.jsonl",
        runner=fake_runner,
    )

    result = collector.collect_from_request(CollectionRequest(keyword="AI Agent", pages=4))

    assert result.run.status == "failed"
    assert "low-frequency limit" in (result.run.error_message or "")
    assert calls == []


def _fake_scraper_root(tmp_path: Path) -> Path:
    scraper_root = tmp_path / "boss-zhipin-scraper"
    scripts_dir = scraper_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "boss_cdp_raw.py").write_text("# fake scraper\n", encoding="utf-8")
    return scraper_root

import subprocess
from pathlib import Path

import pytest

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from scripts.collect_boss_jobs import collect_for_cities, parse_cities


def test_parse_cities_supports_chinese_and_ascii_commas() -> None:
    assert parse_cities("上海,北京，深圳,上海") == ["上海", "北京", "深圳"]


def test_parse_cities_rejects_blank_value() -> None:
    with pytest.raises(ValueError, match="at least one city"):
        parse_cities(" , ， ")


def test_collect_for_cities_runs_once_per_city(tmp_path: Path) -> None:
    scraper_root = tmp_path / "boss-zhipin-scraper"
    scripts_dir = scraper_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "boss_cdp_raw.py").write_text("# fake scraper\n", encoding="utf-8")
    output_dir = tmp_path / "raw"
    calls: list[tuple[str, list[str]]] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        city = command[command.index("--city") + 1]
        calls.append((city, command))
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            '{"keyword":"AI Agent","city":"%s","jobs":[]}' % city,
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        output_dir=output_dir,
        run_log_path=tmp_path / "runs" / "agent_runs.jsonl",
        runner=fake_runner,
    )

    results = collect_for_cities(
        collector,
        keyword="AI Agent",
        cities=["上海", "北京", "深圳"],
        pages=1,
        cdp_port=9222,
    )

    assert [city for city, _ in calls] == ["上海", "北京", "深圳"]
    assert [result.run.status for result in results] == ["success", "success", "success"]
    # Debug collection defaults to list-only so a quick check does not crawl details.
    for _, command in calls:
        assert "--no-detail" in command


def test_collect_for_cities_can_opt_into_detail(tmp_path: Path) -> None:
    scraper_root = tmp_path / "boss-zhipin-scraper"
    scripts_dir = scraper_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "boss_cdp_raw.py").write_text("# fake scraper\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text('{"keyword":"AI Agent","city":"上海","jobs":[]}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    collector = BossZhipinCollector(
        scraper_root=scraper_root,
        output_dir=tmp_path / "raw",
        run_log_path=tmp_path / "runs" / "agent_runs.jsonl",
        runner=fake_runner,
    )

    collect_for_cities(
        collector,
        keyword="AI Agent",
        cities=["上海"],
        pages=1,
        cdp_port=9222,
        include_detail=True,
    )

    assert "--detail" in calls[0]
    assert "--no-detail" not in calls[0]

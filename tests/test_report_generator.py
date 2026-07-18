from __future__ import annotations

from app.schemas.job import NormalizedJobPost
from app.schemas.match import JobMatchReport, JobMatchResult
from app.services.report_generator import build_final_report, build_overview_csv


def _job(source_job_id: str, **overrides: object) -> NormalizedJobPost:
    base: dict[str, object] = dict(
        platform="boss_zhipin",
        source_job_id=source_job_id,
        keyword="AI Agent",
        city="上海",
        job_title="AI Agent 应用工程师",
        company="示例智能科技",
        location="上海·浦东",
        address="上海市浦东新区张江路 100 号",
        salary="30-50K·15薪",
        company_scale="100-499人",
        company_stage="B轮",
        company_industry="人工智能",
        welfare=["五险一金", "股票期权"],
        job_url="https://www.zhipin.com/job_detail/sample.html",
    )
    base.update(overrides)
    return NormalizedJobPost(**base)


def _report() -> tuple[JobMatchReport, dict[str, NormalizedJobPost]]:
    jobs = {
        "job-1": _job("job-1"),
        "job-2": _job(
            "job-2",
            company="次要公司",
            job_title="大模型工程师",
            job_url="https://www.zhipin.com/job_detail/job-2.html",
        ),
    }
    report = JobMatchReport(
        run_id="run-x",
        total_jobs=2,
        results=[
            JobMatchResult(
                source_job_id="job-1",
                rank=1,
                match_score=92,
                recommendation_level="优先投递",
                matched_evidence=["做过 RAG 检索项目"],
                gaps=["缺少 LangGraph 实战"],
                resume_suggestions=["补充 Agent 项目量化指标"],
                interview_focus=["讲清 RAG 评估方式"],
            ),
            JobMatchResult(
                source_job_id="job-2",
                rank=2,
                match_score=70,
                recommendation_level="可以投递",
                gaps=["缺少大模型微调经验"],
            ),
        ],
    )
    return report, jobs


def test_final_report_includes_company_salary_link_address() -> None:
    report, jobs = _report()

    final = build_final_report(report, jobs)

    assert final.run_id == "run-x"
    assert final.matched_jobs == 2
    assert final.priority_jobs == 1

    md = final.markdown
    # Overview table + job card carry the real metadata.
    assert "示例智能科技" in md
    assert "30-50K·15薪" in md
    assert "上海市浦东新区张江路 100 号" in md  # address only appears in the job card
    assert "https://www.zhipin.com/job_detail/sample.html" in md
    assert "人工智能" in md
    assert "B轮" in md
    # Section skeleton is system-generated, not AI free-form.
    assert "## 一、总体匹配结论" in md
    assert "## 二、推荐投递总览" in md
    assert "## 七、投递策略" in md


def test_overview_rows_are_globally_ordered_by_rank() -> None:
    report, jobs = _report()

    final = build_final_report(report, jobs)

    assert [row.rank for row in final.overview] == [1, 2]
    assert final.overview[0].company == "示例智能科技"
    assert final.overview[0].match_score == 92


def test_overview_csv_has_chinese_headers_and_rows() -> None:
    report, jobs = _report()
    final = build_final_report(report, jobs)

    csv_text = build_overview_csv(final.overview)

    header = csv_text.splitlines()[0]
    assert "公司" in header
    assert "薪资" in header
    assert "岗位链接" in header
    assert "示例智能科技" in csv_text


def test_missing_job_metadata_renders_placeholder_not_crash() -> None:
    report, _ = _report()
    # No metadata for either job id -> rows still render with 未提供.
    final = build_final_report(report, {})

    assert final.matched_jobs == 2
    assert "未提供" in final.markdown
    row = final.overview[0]
    assert row.company == "未提供"
    assert row.match_score == 92  # score still comes from the match result

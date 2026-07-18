from pathlib import Path

import pytest

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.services.ai_resume_job_analyzer import (
    analyze_resume_against_jobs,
    build_resume_job_analysis_prompt,
)
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.llm_provider import _extract_chat_content
from app.services.llm_provider import OpenAICompatibleProvider


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


class FakeProvider:
    def __init__(self, response: str = "# 匹配报告\n\n候选人与 AI Agent 岗位较匹配。") -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _structured_jds():
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    return structure_jds(normalized_jobs)


def test_build_resume_job_analysis_prompt_contains_grounding_inputs() -> None:
    prompt = build_resume_job_analysis_prompt(
        "熟悉 Python、RAG、FastAPI，做过知识库项目。",
        _structured_jds()[:1],
    )

    assert "不要编造经历" in prompt
    assert "熟悉 Python" in prompt
    assert "AI Agent 应用工程师" in prompt
    assert "LangGraph" in prompt
    assert "简历中暂无证据" in prompt
    assert "建议投递顺序" in prompt
    assert "按匹配度从高到低排序所有岗位" in prompt
    assert "优先投递" in prompt


def test_analyze_resume_against_jobs_calls_provider_with_limited_jobs() -> None:
    provider = FakeProvider()
    result = analyze_resume_against_jobs(
        "做过 Python 后端和 RAG 检索项目。",
        _structured_jds(),
        provider,
        max_jobs=2,
    )

    assert result.startswith("# 匹配报告")
    assert len(provider.prompts) == 1
    assert "岗位 1" in provider.prompts[0]
    assert "岗位 2" in provider.prompts[0]
    assert "岗位 3" not in provider.prompts[0]


def test_analyze_resume_against_jobs_rejects_blank_resume() -> None:
    with pytest.raises(ValueError, match="resume_text"):
        analyze_resume_against_jobs("  ", _structured_jds(), FakeProvider())


def test_extract_chat_content_reads_openai_compatible_response() -> None:
    content = _extract_chat_content({"choices": [{"message": {"content": "ok"}}]})

    assert content == "ok"


def test_extract_chat_content_rejects_unexpected_response() -> None:
    with pytest.raises(RuntimeError, match="choices"):
        _extract_chat_content({"message": "missing choices"})


def test_openai_compatible_provider_reads_runtime_limits_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MATCHER_API_KEY", "test-key")
    monkeypatch.setenv("AI_MATCHER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AI_MATCHER_MODEL", "test-model")
    monkeypatch.setenv("AI_MATCHER_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("AI_MATCHER_MAX_TOKENS", "900")
    monkeypatch.setenv("AI_MATCHER_RETRY_COUNT", "3")
    monkeypatch.setenv("AI_MATCHER_RETRY_BACKOFF_SECONDS", "0.5")

    provider = OpenAICompatibleProvider.from_env()

    assert provider.api_key == "test-key"
    assert provider.base_url == "https://example.test/v1"
    assert provider.model == "test-model"
    assert provider.timeout_seconds == 180
    assert provider.max_tokens == 900
    assert provider.retry_count == 3
    assert provider.retry_backoff_seconds == 0.5


def test_openai_compatible_provider_omits_max_tokens_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MATCHER_API_KEY", "test-key")
    monkeypatch.delenv("AI_MATCHER_MAX_TOKENS", raising=False)

    provider = OpenAICompatibleProvider.from_env()

    assert provider.max_tokens is None


def test_openai_compatible_provider_reads_dotenv_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_MATCHER_API_KEY", raising=False)
    monkeypatch.delenv("AI_MATCHER_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MATCHER_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AI_MATCHER_API_KEY=dotenv-key",
                "AI_MATCHER_BASE_URL=https://dotenv.example/v1",
                "AI_MATCHER_MODEL=dotenv-model",
                "AI_MATCHER_TIMEOUT_SECONDS=120",
            ]
        ),
        encoding="utf-8",
    )

    provider = OpenAICompatibleProvider.from_env(env_file)

    assert provider.api_key == "dotenv-key"
    assert provider.base_url == "https://dotenv.example/v1"
    assert provider.model == "dotenv-model"
    assert provider.timeout_seconds == 120


def test_openai_compatible_provider_prefers_process_env_over_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_MATCHER_API_KEY", "process-key")
    env_file = tmp_path / ".env"
    env_file.write_text("AI_MATCHER_API_KEY=dotenv-key", encoding="utf-8")

    provider = OpenAICompatibleProvider.from_env(env_file)

    assert provider.api_key == "process-key"

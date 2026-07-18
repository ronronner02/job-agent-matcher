from __future__ import annotations

from app.schemas.job import NormalizedJobPost, RawJobPost
from app.services.salary_parser import parse_salary


EDUCATION_KEYWORDS = ("博士", "硕士", "本科", "大专", "高中", "中专", "学历不限")
EXPERIENCE_KEYWORDS = ("经验不限", "应届", "在校", "年")


def normalize_boss_job(raw: RawJobPost) -> NormalizedJobPost:
    """Convert a BOSS raw job row into the project's stable job schema."""

    experience, education = split_experience_and_education(raw.tags)
    company = raw.company or raw.boss_name or "unknown"
    salary = clean_optional(raw.salary)
    parsed_salary = parse_salary(salary)
    return NormalizedJobPost(
        platform=raw.platform,
        source_job_id=raw.source_job_id or fallback_job_id(raw),
        keyword=raw.keyword or "unknown",
        city=raw.city or "unknown",
        job_title=raw.title or "unknown",
        company=company,
        location=raw.location or "unknown",
        address=clean_optional(raw.address),
        salary=salary,
        salary_min=parsed_salary.salary_min,
        salary_max=parsed_salary.salary_max,
        salary_unit=parsed_salary.salary_unit,
        experience_required=experience,
        education_required=education,
        jd_text=clean_optional(raw.jd_text),
        job_url=clean_optional(raw.job_url),
        detail_url=clean_optional(raw.detail_url),
        company_scale=clean_optional(raw.company_scale),
        company_stage=clean_optional(raw.company_stage),
        company_industry=clean_optional(raw.company_industry),
        company_link=clean_optional(raw.company_link),
        boss_name=clean_optional(raw.boss_name),
        boss_title=clean_optional(raw.boss_title),
        welfare=split_welfare(raw.welfare),
        skill_keywords=raw.skills,
        raw_payload=raw.raw_payload,
    )


def normalize_boss_jobs(raw_jobs: list[RawJobPost]) -> list[NormalizedJobPost]:
    return [normalize_boss_job(raw_job) for raw_job in raw_jobs]


def split_experience_and_education(tags: str | None) -> tuple[str | None, str | None]:
    if not tags:
        return None, None

    parts = [part.strip() for part in tags.replace("/", "|").split("|") if part.strip()]
    experience = next((part for part in parts if looks_like_experience(part)), None)
    education = next((part for part in parts if looks_like_education(part)), None)
    return experience, education


def looks_like_experience(value: str) -> bool:
    return any(keyword in value for keyword in EXPERIENCE_KEYWORDS)


def looks_like_education(value: str) -> bool:
    return any(keyword in value for keyword in EDUCATION_KEYWORDS)


def split_welfare(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace("，", "|").replace(",", "|").split("|")]
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            result.append(part)
    return result


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def fallback_job_id(raw: RawJobPost) -> str:
    if raw.job_url:
        return raw.job_url.rstrip("/").split("/")[-1].replace(".html", "")
    if raw.title and raw.company:
        return f"{raw.company}:{raw.title}"
    return "unknown"

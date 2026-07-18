from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import JobPost, JobSkill
from app.schemas.job import NormalizedJobPost


def upsert_normalized_job(session: Session, job: NormalizedJobPost) -> JobPost:
    existing = session.scalar(
        select(JobPost)
        .where(JobPost.platform == job.platform)
        .where(JobPost.source_job_id == job.source_job_id)
        .options(selectinload(JobPost.skills))
    )

    if existing is None:
        existing = JobPost(platform=job.platform, source_job_id=job.source_job_id)
        existing.created_at = job.created_at
        session.add(existing)

    _apply_job_fields(existing, job)
    return existing


def upsert_normalized_jobs(session: Session, jobs: list[NormalizedJobPost]) -> list[JobPost]:
    saved: list[JobPost] = []
    seen: dict[tuple[str, str], JobPost] = {}
    for job in jobs:
        key = (job.platform, job.source_job_id)
        if key in seen:
            existing = seen[key]
            _apply_job_fields(existing, job)
        else:
            existing = upsert_normalized_job(session, job)
            seen[key] = existing
        saved.append(existing)
    session.flush()
    return saved


def list_jobs(session: Session, *, keyword: str | None = None, city: str | None = None) -> list[JobPost]:
    stmt: Select[tuple[JobPost]] = select(JobPost).options(selectinload(JobPost.skills))
    if keyword:
        stmt = stmt.where(JobPost.keyword == keyword)
    if city:
        stmt = stmt.where(JobPost.city == city)
    return list(session.scalars(stmt.order_by(JobPost.id)))


def get_jobs_by_source_ids(
    session: Session,
    source_job_ids: list[str],
    *,
    platform: str = "boss_zhipin",
) -> dict[str, NormalizedJobPost]:
    """Rebuild NormalizedJobPost objects from persisted rows, keyed by id.

    Used by the resume/continuation flow to recover job metadata without
    re-collecting. Only ids that exist are returned; missing ids are skipped.
    """

    if not source_job_ids:
        return {}
    stmt = (
        select(JobPost)
        .where(JobPost.platform == platform)
        .where(JobPost.source_job_id.in_(source_job_ids))
        .options(selectinload(JobPost.skills))
    )
    return {row.source_job_id: job_post_to_normalized(row) for row in session.scalars(stmt)}


def job_post_to_normalized(job_post: JobPost) -> NormalizedJobPost:
    """Convert a persisted JobPost row back into a NormalizedJobPost."""

    return NormalizedJobPost(
        platform=job_post.platform,  # type: ignore[arg-type]
        source_job_id=job_post.source_job_id,
        keyword=job_post.keyword,
        city=job_post.city,
        job_title=job_post.job_title,
        company=job_post.company,
        location=job_post.location,
        address=job_post.address,
        salary=job_post.salary,
        salary_min=job_post.salary_min,
        salary_max=job_post.salary_max,
        salary_unit=job_post.salary_unit,  # type: ignore[arg-type]
        experience_required=job_post.experience_required,
        education_required=job_post.education_required,
        jd_text=job_post.jd_text,
        job_url=job_post.job_url,
        detail_url=job_post.detail_url,
        company_scale=job_post.company_scale,
        company_stage=job_post.company_stage,
        company_industry=job_post.company_industry,
        company_link=job_post.company_link,
        boss_name=job_post.boss_name,
        boss_title=job_post.boss_title,
        welfare=list(job_post.welfare or []),
        skill_keywords=[skill.skill for skill in job_post.skills],
        raw_payload=dict(job_post.raw_payload or {}),
        created_at=job_post.created_at,
    )


def _apply_job_fields(job_post: JobPost, job: NormalizedJobPost) -> None:
    job_post.keyword = job.keyword
    job_post.city = job.city
    job_post.job_title = job.job_title
    job_post.company = job.company
    job_post.location = job.location
    job_post.address = job.address
    job_post.salary = job.salary
    job_post.salary_min = job.salary_min
    job_post.salary_max = job.salary_max
    job_post.salary_unit = job.salary_unit
    job_post.experience_required = job.experience_required
    job_post.education_required = job.education_required
    job_post.jd_text = job.jd_text
    job_post.job_url = job.job_url
    job_post.detail_url = job.detail_url
    job_post.company_scale = job.company_scale
    job_post.company_stage = job.company_stage
    job_post.company_industry = job.company_industry
    job_post.company_link = job.company_link
    job_post.boss_name = job.boss_name
    job_post.boss_title = job.boss_title
    job_post.welfare = list(job.welfare)
    job_post.raw_payload = job.raw_payload
    _sync_skills(job_post, job.skill_keywords)


def _sync_skills(job_post: JobPost, skills: list[str]) -> None:
    desired: dict[str, str] = {}
    for skill in skills:
        cleaned = skill.strip()
        if cleaned:
            desired.setdefault(cleaned.lower(), cleaned)

    existing_by_key = {skill.skill.lower(): skill for skill in job_post.skills}
    job_post.skills[:] = [
        skill for skill in job_post.skills if skill.skill.lower() in desired
    ]

    for key, skill in desired.items():
        if key not in existing_by_key:
            job_post.skills.append(JobSkill(skill=skill, source="normalized"))

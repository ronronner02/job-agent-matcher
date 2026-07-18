from __future__ import annotations

from app.schemas.job import RawJobPost


def merge_boss_list_and_detail_jobs(
    list_jobs: list[RawJobPost],
    detail_jobs: list[RawJobPost],
) -> list[RawJobPost]:
    """Merge detail-page JD data back into the list-page raw jobs.

    The list export gives company / salary / metadata for every job; the detail
    export adds JD text, address, richer skills and welfare, but only for the
    jobs whose detail page was actually visited (``--max-details`` may cap it).

    Matching order:
      1. source_job_id / job_id / encrypt_job_id
      2. job_url / detail_url / job_link
      3. company + title + location

    List jobs without a matching detail are kept untouched. When a field is set
    on both sides, the more complete detail value wins, but the original
    ``raw_payload`` is preserved and the detail payload is attached separately.
    """

    detail_by_id: dict[str, RawJobPost] = {}
    detail_by_url: dict[str, RawJobPost] = {}
    detail_by_composite: dict[tuple[str, str, str], RawJobPost] = {}

    for detail in detail_jobs:
        for key in _id_keys(detail):
            detail_by_id.setdefault(key, detail)
        for key in _url_keys(detail):
            detail_by_url.setdefault(key, detail)
        composite = _composite_key(detail)
        if composite is not None:
            detail_by_composite.setdefault(composite, detail)

    merged: list[RawJobPost] = []
    for job in list_jobs:
        detail = _find_detail(job, detail_by_id, detail_by_url, detail_by_composite)
        if detail is None:
            merged.append(job)
        else:
            merged.append(_apply_detail(job, detail))
    return merged


def dedupe_raw_jobs(raw_jobs: list[RawJobPost]) -> list[RawJobPost]:
    """Drop duplicate jobs collected across cities/pages, keeping the richest.

    Each job gets a single canonical key: its id if present, else its url, else
    the company+title+location composite. Using one key per job (id first) means
    two jobs with different ids never merge just because they share a
    company+title+location. Multi-city collection frequently returns the same
    nationwide posting under several city queries, so this runs before
    normalization to avoid analysing and ranking the same job twice. On a
    collision the first job is kept but its longer JD/address/skills/welfare
    fields are filled in from the duplicate.
    """

    by_key: dict[str, int] = {}
    unique: list[RawJobPost] = []
    for job in raw_jobs:
        key = _canonical_key(job)
        if key is None:
            unique.append(job)
            continue
        if key in by_key:
            index = by_key[key]
            unique[index] = _apply_detail(unique[index], job)
            continue
        by_key[key] = len(unique)
        unique.append(job)
    return unique


def _canonical_key(job: RawJobPost) -> str | None:
    id_keys = _id_keys(job)
    if id_keys:
        return id_keys[0]
    url_keys = _url_keys(job)
    if url_keys:
        return url_keys[0]
    composite = _composite_key(job)
    if composite is not None:
        return "composite:" + "|".join(composite)
    return None


def _find_detail(
    job: RawJobPost,
    detail_by_id: dict[str, RawJobPost],
    detail_by_url: dict[str, RawJobPost],
    detail_by_composite: dict[tuple[str, str, str], RawJobPost],
) -> RawJobPost | None:
    for key in _id_keys(job):
        if key in detail_by_id:
            return detail_by_id[key]
    for key in _url_keys(job):
        if key in detail_by_url:
            return detail_by_url[key]
    composite = _composite_key(job)
    if composite is not None and composite in detail_by_composite:
        return detail_by_composite[composite]
    return None


def _apply_detail(job: RawJobPost, detail: RawJobPost) -> RawJobPost:
    updates: dict[str, object] = {}

    # Prefer the more complete detail value for these fields.
    for field in ("jd_text", "address", "welfare", "detail_url"):
        merged_value = _prefer_longer(getattr(job, field), getattr(detail, field))
        if merged_value != getattr(job, field):
            updates[field] = merged_value

    merged_skills = _merge_skills(job.skills, detail.skills)
    if merged_skills != job.skills:
        updates["skills"] = merged_skills

    # Keep the list raw_payload, expose the detail payload alongside it.
    detail_payload = detail.raw_payload or {}
    if detail_payload:
        raw_payload = dict(job.raw_payload)
        raw_payload["detail_raw_payload"] = detail_payload
        updates["raw_payload"] = raw_payload

    if not updates:
        return job
    return job.model_copy(update=updates)


def _id_keys(job: RawJobPost) -> list[str]:
    keys: list[str] = []
    if job.source_job_id:
        keys.append(f"id:{job.source_job_id.strip()}")
    payload = job.raw_payload or {}
    for name in ("job_id", "encrypt_job_id"):
        value = payload.get(name)
        if value:
            keys.append(f"id:{str(value).strip()}")
    return keys


def _url_keys(job: RawJobPost) -> list[str]:
    keys: list[str] = []
    for url in (job.job_url, job.detail_url):
        if url:
            keys.append(f"url:{url.strip().rstrip('/')}")
    payload = job.raw_payload or {}
    for name in ("job_link", "link", "job_url"):
        value = payload.get(name)
        if value:
            keys.append(f"url:{str(value).strip().rstrip('/')}")
    return keys


def _composite_key(job: RawJobPost) -> tuple[str, str, str] | None:
    company = (job.company or "").strip().lower()
    title = (job.title or "").strip().lower()
    location = (job.location or "").strip().lower()
    if company and title and location:
        return (company, title, location)
    return None


def _prefer_longer(existing: object, incoming: object) -> object:
    if not incoming:
        return existing
    if not existing:
        return incoming
    if isinstance(existing, str) and isinstance(incoming, str):
        return incoming if len(incoming.strip()) > len(existing.strip()) else existing
    return existing


def _merge_skills(list_skills: list[str], detail_skills: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for skill in [*list_skills, *detail_skills]:
        cleaned = skill.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            merged.append(cleaned)
    return merged

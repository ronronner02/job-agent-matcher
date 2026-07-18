from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.job import SalaryUnit


@dataclass(frozen=True)
class ParsedSalary:
    """Structured salary extracted from a BOSS salary string.

    The original string is always preserved by the caller; parsing failures
    return ``None`` fields instead of raising, so a weird format never blocks
    the pipeline.
    """

    salary_min: int | None = None
    salary_max: int | None = None
    salary_unit: SalaryUnit | None = None


# "25-45K", "30-50k", "24-30K·15薪"
_K_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~到]\s*(\d+(?:\.\d+)?)\s*[kK]")
# single "30K"
_K_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK]")
# "300-350元/天", "8000-12000元/月"
_YUAN_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~到]\s*(\d+(?:\.\d+)?)\s*元?\s*/?\s*([天日时小时月年周])")
_YUAN_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*元\s*/?\s*([天日时小时月年周])")

_UNIT_MAP: dict[str, SalaryUnit] = {
    "天": "day",
    "日": "day",
    "时": "hour",
    "小时": "hour",
    "月": "month",
    "年": "year",
    "周": "day",
}


def parse_salary(salary: str | None) -> ParsedSalary:
    """Best-effort parse of a BOSS salary label into min/max/unit."""

    if not salary:
        return ParsedSalary()

    text = salary.strip()
    if not text:
        return ParsedSalary()

    # Thousand-per-month "K" notation is the common BOSS full-time format.
    match = _K_RANGE.search(text)
    if match:
        low = _to_thousands(match.group(1))
        high = _to_thousands(match.group(2))
        return ParsedSalary(salary_min=low, salary_max=high, salary_unit="month")

    # Yuan-per-period, typical for internships ("300-350元/天").
    match = _YUAN_RANGE.search(text)
    if match:
        low = _to_int(match.group(1))
        high = _to_int(match.group(2))
        unit = _UNIT_MAP.get(match.group(3))
        return ParsedSalary(salary_min=low, salary_max=high, salary_unit=unit)

    match = _YUAN_SINGLE.search(text)
    if match:
        value = _to_int(match.group(1))
        unit = _UNIT_MAP.get(match.group(2))
        return ParsedSalary(salary_min=value, salary_max=value, salary_unit=unit)

    match = _K_SINGLE.search(text)
    if match:
        value = _to_thousands(match.group(1))
        return ParsedSalary(salary_min=value, salary_max=value, salary_unit="month")

    return ParsedSalary()


def _to_thousands(value: str) -> int:
    return int(round(float(value) * 1000))


def _to_int(value: str) -> int:
    return int(round(float(value)))

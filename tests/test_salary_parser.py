from app.services.salary_parser import parse_salary


def test_parse_k_range_monthly() -> None:
    result = parse_salary("25-45K·14薪")
    assert result.salary_min == 25000
    assert result.salary_max == 45000
    assert result.salary_unit == "month"


def test_parse_k_range_without_extra_month() -> None:
    result = parse_salary("30-50K")
    assert result.salary_min == 30000
    assert result.salary_max == 50000
    assert result.salary_unit == "month"


def test_parse_yuan_per_day_internship() -> None:
    result = parse_salary("300-350元/天")
    assert result.salary_min == 300
    assert result.salary_max == 350
    assert result.salary_unit == "day"


def test_parse_single_k_value() -> None:
    result = parse_salary("20K")
    assert result.salary_min == 20000
    assert result.salary_max == 20000
    assert result.salary_unit == "month"


def test_parse_returns_empty_for_unparseable_text() -> None:
    result = parse_salary("面议")
    assert result.salary_min is None
    assert result.salary_max is None
    assert result.salary_unit is None


def test_parse_handles_none_and_blank() -> None:
    assert parse_salary(None).salary_min is None
    assert parse_salary("   ").salary_max is None

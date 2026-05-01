from shortlist.sources._comp import parse_comp_from_text


def test_dollar_k_range():
    assert parse_comp_from_text("$200k - $240k") == (200000, 240000)


def test_dollar_full_range():
    assert parse_comp_from_text("$200,000 to $240,000") == (200000, 240000)


def test_capital_k_no_dollar_on_right():
    assert parse_comp_from_text("$200K-240K") == (200000, 240000)


def test_em_dash_range():
    assert parse_comp_from_text("Compensation: $180k–220k base") == (180000, 220000)


def test_hourly_slash_hr():
    assert parse_comp_from_text("$45/hr") == (45, 45)


def test_hourly_range_per_hour():
    assert parse_comp_from_text("$45-75 per hour") == (45, 75)


def test_single_amount_with_keyword():
    assert parse_comp_from_text("Salary: $180,000") == (180000, 180000)


def test_eur_keyword():
    assert parse_comp_from_text("Salary 150-180k EUR base") == (150000, 180000)


def test_returns_none_when_no_money():
    assert parse_comp_from_text("Just a job description with no comp.") == (None, None)


def test_returns_none_for_empty():
    assert parse_comp_from_text("") == (None, None)


def test_rejects_revenue_context():
    assert parse_comp_from_text("We are a $50M ARR company growing 30% YoY") == (None, None)


def test_rejects_employee_count():
    assert parse_comp_from_text("Join our team of 500 employees building") == (None, None)


def test_rejects_funding_round():
    assert parse_comp_from_text("$15M Series A round closed") == (None, None)


def test_picks_comp_over_funding_when_both_present():
    text = "We raised $20M Series B last year. Salary range $200k-240k."
    lo, hi = parse_comp_from_text(text)
    assert lo == 200000
    assert hi == 240000


def test_swaps_inverted_range():
    assert parse_comp_from_text("$240k-200k") == (200000, 240000)


def test_clamps_implausibly_low_salary():
    assert parse_comp_from_text("Years experience: 1-5") == (None, None)


def test_bare_numbers_treated_as_thousands():
    assert parse_comp_from_text("Salary 150-180 USD base") == (150000, 180000)

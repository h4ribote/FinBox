"""Calendar tests (doc 03 3.1.1 example table)."""
import pytest

from finbox.core.time import Calendar


def test_decompose_table():
    cal = Calendar(turns_per_month=4)
    assert cal.decompose(0) == (1, 1, 1)
    assert cal.decompose(3) == (1, 1, 4)
    assert cal.decompose(4) == (1, 2, 1)
    assert cal.decompose(47) == (1, 12, 4)
    assert cal.decompose(48) == (2, 1, 1)
    assert cal.decompose(122) == (3, 7, 3)


def test_label():
    cal = Calendar()
    assert cal.label(0) == "Y1-M01-T1"
    assert cal.label(122) == "Y3-M07-T3"


def test_to_tick_roundtrip():
    cal = Calendar()
    for tick in (0, 3, 4, 47, 48, 122, 1000):
        assert cal.to_tick(*cal.decompose(tick)) == tick


def test_turns_per_year():
    assert Calendar(4).turns_per_year == 48
    assert Calendar(8).turns_per_year == 96


def test_boundaries():
    cal = Calendar(4)
    assert cal.is_month_end(3) and not cal.is_month_end(2)
    assert cal.is_quarter_end(11) and not cal.is_quarter_end(7)
    assert cal.is_year_end(47) and not cal.is_year_end(11)
    # year end is also month and quarter end
    assert cal.is_month_end(47) and cal.is_quarter_end(47)


def test_negative_tick_rejected():
    with pytest.raises(ValueError):
        Calendar().decompose(-1)

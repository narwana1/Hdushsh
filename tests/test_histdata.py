import pandas as pd

from nqgc.data.histdata import to_utc


def test_to_utc_normal_summer_winter_and_dst_gap_weeks():
    raw = pd.DatetimeIndex([
        # 2024-03-17 is a US-DST / EU-standard week: feed is stamped one hour early
        "2024-03-17 17:00", "2024-03-18 08:30",
        # normal summer week (EDT): Sunday 18:00 NY = 22:00 UTC
        "2024-06-02 18:00", "2024-06-03 09:30",
        # winter week (EST): Sunday 18:00 NY = 23:00 UTC
        "2024-12-01 18:00", "2024-12-02 09:30",
    ])
    utc = to_utc(raw)
    assert list(utc.strftime("%Y-%m-%d %H:%M")) == [
        "2024-03-17 22:00", "2024-03-18 13:30",
        "2024-06-02 22:00", "2024-06-03 13:30",
        "2024-12-01 23:00", "2024-12-02 14:30",
    ]


def test_to_utc_gap_weeks_before_2019_are_not_shifted():
    raw = pd.DatetimeIndex(["2015-03-08 18:00", "2015-03-09 09:30"])  # 2015 gap week, feed was correct
    assert list(to_utc(raw).strftime("%H:%M")) == ["22:00", "13:30"]


def test_to_utc_rejects_unsorted_input():
    import pytest

    with pytest.raises(ValueError):
        to_utc(pd.DatetimeIndex(["2024-06-03 09:30", "2024-06-02 18:00"]))

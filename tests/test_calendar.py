"""Tests for UMelb Freebies calendar builder."""

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from build_calendar import (
    build_ics, deduplicate, filter_date_range, filter_free,
    _make_uid, _parse_time_list_format, FreeEvent, MEL,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=MEL)


def _event(name="Free Lunch", url="https://umsu.unimelb.edu.au/ents/event/1/",
           start=None, end=None, description="Free food for students", source="free_food"):
    if start is None:
        start = datetime(2026, 9, 16, 12, 0, tzinfo=MEL)
    if end is None:
        end = datetime(2026, 9, 16, 13, 0, tzinfo=MEL)
    return {
        "source": source, "name": name, "url": url,
        "start": start, "end": end,
        "location": "Parkville", "description": description,
        "organisation": "UMSU", "fetched_at": NOW,
    }


def test_stable_uid():
    e1 = _event()
    e2 = _event()
    uid1 = _make_uid(FreeEvent(source=e1["source"], name=e1["name"], url=e1["url"], start=e1["start"], end=e1["end"]))
    uid2 = _make_uid(FreeEvent(source=e2["source"], name=e2["name"], url=e2["url"], start=e2["start"], end=e2["end"]))
    assert uid1 == uid2


def test_deduplicate():
    e1 = _event()
    e2 = _event()
    result = deduplicate([e1, e2])
    assert len(result) == 1


def test_deduplicate_different_dates():
    e1 = _event()
    e2 = _event(start=datetime(2026, 9, 17, 12, 0, tzinfo=MEL), end=datetime(2026, 9, 17, 13, 0, tzinfo=MEL))
    result = deduplicate([e1, e2])
    assert len(result) == 2


def test_paid_excluded():
    e = _event(description="Cost: $5 entry")
    result = filter_free([e])
    assert len(result) == 0


def test_free_food_included():
    e = _event(description="Free pizza for all students")
    result = filter_free([e])
    assert len(result) == 1


def test_free_benefit_included():
    e = _event(name="Free Gift Giveaway", description="Free merchandise for students", source="free")
    result = filter_free([e])
    assert len(result) == 1


def test_free_workshop_excluded():
    e = _event(name="Free Workshop", description="Learn new skills", source="free")
    result = filter_free([e])
    assert len(result) == 0


def test_past_excluded():
    e = _event(start=datetime(2026, 9, 10, 12, 0, tzinfo=MEL), end=datetime(2026, 9, 10, 13, 0, tzinfo=MEL))
    result = filter_date_range([e], NOW)
    assert len(result) == 0


def test_future_within_14_days():
    e = _event(start=datetime(2026, 9, 25, 12, 0, tzinfo=MEL), end=datetime(2026, 9, 25, 13, 0, tzinfo=MEL))
    result = filter_date_range([e], NOW)
    assert len(result) == 1


def test_beyond_14_days_excluded():
    e = _event(start=datetime(2026, 10, 1, 12, 0, tzinfo=MEL), end=datetime(2026, 10, 1, 13, 0, tzinfo=MEL))
    result = filter_date_range([e], NOW)
    assert len(result) == 0


def test_melbourne_timezone():
    e = _event(start=datetime(2026, 9, 16, 9, 30, tzinfo=MEL), end=datetime(2026, 9, 16, 10, 30, tzinfo=MEL))
    result = filter_date_range([e], NOW)
    assert len(result) == 1
    assert result[0]["start"].tzinfo is not None


def test_ics_generated():
    e = _event()
    ics = build_ics([e], NOW)
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics


def test_ics_required_fields():
    e = _event()
    ics = build_ics([e], NOW)
    for field in ["UID:", "DTSTAMP:", "DTSTART", "DTEND", "SUMMARY:", "LOCATION:", "DESCRIPTION:", "URL:", "STATUS:", "CATEGORIES:"]:
        assert field in ics, f"Missing {field} in ICS"


def test_ics_event_url():
    e = _event()
    ics = build_ics([e], NOW)
    assert e["url"] in ics


def test_parse_time_range():
    base = datetime(2026, 9, 16, tzinfo=MEL)
    start, end = _parse_time_list_format("noon - 2:30pm", base)
    assert start.hour == 12 and start.minute == 0
    assert end.hour == 14 and end.minute == 30


def test_parse_time_pm():
    base = datetime(2026, 9, 16, tzinfo=MEL)
    start, end = _parse_time_list_format("1pm - 4pm", base)
    assert start.hour == 13
    assert end.hour == 16

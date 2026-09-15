"""UMelb Freebies: Fetch UMSU free events and generate an ICS calendar."""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("umelb-freebies")

MEL = ZoneInfo("Australia/Melbourne")
BASE = "https://umsu.unimelb.edu.au"
SOURCES = {
    "free_food": "/ents/eventlist/free-food/",
    "free": "/ents/eventlist/free/",
    "all_events": "/things-to-do/events/",
}

FREE_FOOD_KEYWORDS = [
    "free breakfast", "free brunch", "free lunch", "free bbq", "free pizza",
    "free food", "free meal", "free coffee", "free drinks", "free snacks",
    "free ice cream", "free food pack", "免费食品", "免费早餐", "免费午餐",
    "免费 bbq", "免费 pizza", "免费咖啡", "免费饮料", "免费零食",
]

FREE_BENEFIT_KEYWORDS = [
    "free gift", "free merchandise", "free book", "free stationery",
    "free workshop", "free movie", "free game", "free cultural",
    "free social", "免费礼品", "免费 merchandise", "免费生活用品",
    "免费书籍", "免费学习用品", "免费 workshop", "免费电影", "免费游戏",
]

PAID_INDICATORS = [
    "$", "cost:", "price:", "ticket", "fee", "payment", "paid",
    "purchase", "buy tickets", "book now", "register and pay",
]

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

DATE_HEADER_RE = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)"
)
TIME_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)|(?:midnight|noon))\s*[-–—]\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)|(?:midnight|noon))",
    re.IGNORECASE,
)
SINGLE_TIME_RE = re.compile(r"(\d{1,2}(?::\d{2})?)\s*(am|pm)", re.IGNORECASE)


@dataclass
class FreeEvent:
    """A free event at UMSU."""
    source: str
    name: str
    url: str
    start: datetime
    end: datetime
    location: str = ""
    description: str = ""
    organisation: str = ""
    is_free_food: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(MEL))


def _make_uid(event: FreeEvent) -> str:
    key = f"{event.source}|{event.url}|{event.start.isoformat()}|{event.name}"
    return hashlib.sha256(key.encode()).hexdigest()[:32] + "@umelb-freebies"


def _parse_time_token(value: str, ampm: str) -> tuple[int, int]:
    if ampm.lower() == "midnight":
        return (0, 0)
    if ampm.lower() == "noon":
        return (12, 0)
    parts = value.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if ampm.lower() == "pm" and hour != 12:
        hour += 12
    elif ampm.lower() == "am" and hour == 12:
        hour = 0
    return (hour, minute)


def _parse_date_header(text: str, year: int) -> Optional[datetime]:
    match = DATE_HEADER_RE.search(text)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2).lower()
    month = MONTH_NAMES.get(month_name)
    if month is None:
        return None
    return datetime(year, month, day, tzinfo=MEL)


def _parse_time_token_str(value: str) -> tuple[int, int]:
    value = value.strip().lower()
    if value == "midnight":
        return (0, 0)
    if value == "noon":
        return (12, 0)
    hm = re.match(r"(\d{1,2})(?::(\d{2}))?", value)
    if not hm:
        return (9, 0)
    h = int(hm.group(1))
    m = int(hm.group(2) or 0)
    if "pm" in value and h != 12:
        h += 12
    elif "am" in value and h == 12:
        h = 0
    return (h, m)


def _parse_time_range(text: str, base_date: datetime) -> Optional[tuple[datetime, datetime]]:
    match = TIME_RANGE_RE.search(text)
    if not match:
        return None
    start_h, start_m = _parse_time_token_str(match.group(1))
    end_h, end_m = _parse_time_token_str(match.group(2))
    start = base_date.replace(hour=start_h, minute=start_m)
    end = base_date.replace(hour=end_h, minute=end_m)
    if end <= start:
        end += timedelta(days=1)
    return (start, end)


def _parse_time_list_format(text: str, base_date: datetime) -> Optional[tuple[datetime, datetime]]:
    """Parse formats like 'noon - 2:30pm', '1pm - 4pm', or '15th September midnight - 18th September midnight'."""
    text = text.strip()

    # Try to match a full date range like "15th September midnight - 18th September midnight"
    date_range_match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(midnight|noon|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
        r"\s*[-\u2013\u2014]\s*"
        r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+)?(midnight|noon|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        text,
        re.IGNORECASE,
    )
    if date_range_match:
        year = base_date.year
        day1 = int(date_range_match.group(1))
        month1 = MONTH_NAMES.get(date_range_match.group(2).lower(), base_date.month)
        time1 = date_range_match.group(3)
        day2 = int(date_range_match.group(4)) if date_range_match.group(4) else day1
        month2 = MONTH_NAMES.get(date_range_match.group(5).lower(), month1) if date_range_match.group(5) else month1
        time2 = date_range_match.group(6)

        def _hm(s):
            s = s.strip().lower()
            if s == "midnight":
                return (0, 0)
            if s == "noon":
                return (12, 0)
            m2 = re.match(r"(\d{1,2})(?::(\d{2}))?", s)
            h = int(m2.group(1)) if m2 else 9
            mn = int(m2.group(2) or 0) if m2 else 0
            if "pm" in s and h != 12:
                h += 12
            elif "am" in s and h == 12:
                h = 0
            return (h, mn)

        h1, m1 = _hm(time1)
        h2, m2 = _hm(time2)
        start = datetime(year, month1, day1, h1, m1, tzinfo=MEL)
        end = datetime(year, month2, day2, h2, m2, tzinfo=MEL)
        if end <= start:
            end += timedelta(days=1)
        return (start, end)

    match = TIME_RANGE_RE.search(text)
    if match:
        return _parse_time_range(text, base_date)
    match = SINGLE_TIME_RE.search(text)
    if match:
        h, m = _parse_time_token(match.group(1), match.group(2))
        start = base_date.replace(hour=h, minute=m)
        return (start, start + timedelta(hours=1))
    return (base_date.replace(hour=9), base_date.replace(hour=17))


def _parse_detail_date(text: str) -> Optional[tuple[datetime, datetime]]:
    """Parse detail page date format like '16/09/2026–16/09/2026'."""
    text = text.strip()
    pattern = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
    dates = pattern.findall(text)
    if len(dates) >= 1:
        d1 = datetime(int(dates[0][2]), int(dates[0][1]), int(dates[0][0]), tzinfo=MEL)
        if len(dates) >= 2:
            d2 = datetime(int(dates[1][2]), int(dates[1][1]), int(dates[1][0]), tzinfo=MEL)
        else:
            d2 = d1
        return (d1, d2)
    return None


def _parse_detail_time(text: str, base_date: datetime) -> Optional[tuple[datetime, datetime]]:
    """Parse detail page time format like '9:30 AM–10:30 AM'."""
    text = text.strip()
    pattern = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
    times = pattern.findall(text)
    if len(times) >= 1:
        h1 = int(times[0][0]); m1 = int(times[0][1])
        if times[0][2].upper() == "PM" and h1 != 12: h1 += 12
        elif times[0][2].upper() == "AM" and h1 == 12: h1 = 0
        if len(times) >= 2:
            h2 = int(times[1][0]); m2 = int(times[1][1])
            if times[1][2].upper() == "PM" and h2 != 12: h2 += 12
            elif times[1][2].upper() == "AM" and h2 == 12: h2 = 0
        else:
            h2, m2 = h1 + 1, m1
        start = base_date.replace(hour=h1, minute=m1)
        end = base_date.replace(hour=h2, minute=m2)
        if end <= start:
            end += timedelta(days=1)
        return (start, end)
    return None


def _fetch_page(session: requests.Session, path: str) -> Optional[str]:
    url = urljoin(BASE, path)
    try:
        resp = session.get(url, timeout=30, headers={"User-Agent": "UMelbFreebies/1.0"})
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


def _resolve_url(href: str) -> str:
    return urljoin(BASE, href)


def _is_paid(event_text: str) -> bool:
    lower = event_text.lower()
    for indicator in PAID_INDICATORS:
        if indicator in lower:
            return True
    return False


def _is_free_food(name: str, description: str, tags: list[str]) -> bool:
    if "free food" in tags:
        return True
    text = f"{name} {description}".lower()
    return any(kw in text for kw in FREE_FOOD_KEYWORDS)


def _is_free_benefit(name: str, description: str, tags: list[str]) -> bool:
    if "free" in tags:
        return True
    text = f"{name} {description}".lower()
    return any(kw in text for kw in FREE_BENEFIT_KEYWORDS)


def parse_eventlist_page(html: str, source: str, year: int) -> list[dict]:
    """Parse an /ents/eventlist/ page with date headers."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    current_date: Optional[datetime] = None

    for element in soup.find_all(True):
        if element.name == "h4" and element.find_parent("div", id="events"):
            parsed_date = _parse_date_header(element.get_text(), year)
            if parsed_date:
                current_date = parsed_date
            continue
        if element.name != "div" or "event_item" not in (element.get("class") or []):
            continue
        if current_date is None:
            continue

        name_el = element.find("a", class_="msl_event_name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        url = _resolve_url(href)

        time_el = element.find("dd", class_="msl_event_time")
        time_text = time_el.get_text(strip=True) if time_el else ""
        loc_el = element.find("dd", class_="msl_event_location")
        location = loc_el.get_text(strip=True) if loc_el else ""
        desc_el = element.find("dd", class_="msl_event_description")
        description = desc_el.get_text(strip=True) if desc_el else ""
        org_el = element.find("span", class_="msl_event_organisation")
        organisation = org_el.get_text(strip=True) if org_el else ""

        times = _parse_time_list_format(time_text, current_date)
        if times is None:
            continue
        start, end = times

        events.append({
            "source": source,
            "name": name,
            "url": url,
            "start": start,
            "end": end,
            "location": location,
            "description": description,
            "organisation": organisation,
        })

    return events


def parse_all_events_page(html: str, source: str) -> list[dict]:
    """Parse the main /things-to-do/events/ page filtering by free tags."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    seen_date_text: Optional[str] = None

    for item in soup.find_all("div", class_="event_item"):
        tags = [
            a.get_text(strip=True).lower()
            for a in item.find_all("a", class_=lambda c: c and "msl_event_types" not in (c or ""))
            if a.find_parent("dd", class_="msl_event_types")
        ]
        if not tags:
            types_dd = item.find("dd", class_="msl_event_types")
            if types_dd:
                tags = [a.get_text(strip=True).lower() for a in types_dd.find_all("a")]

        is_free = "free" in tags or "free food" in tags
        if not is_free:
            continue

        name_el = item.find("a", class_="msl_event_name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        url = _resolve_url(href)

        time_el = item.find("dd", class_="msl_event_time")
        time_text = time_el.get_text(strip=True) if time_el else ""
        loc_el = item.find("dd", class_="msl_event_location")
        location = loc_el.get_text(strip=True) if loc_el else ""
        desc_el = item.find("dd", class_="msl_event_description")
        description = desc_el.get_text(strip=True) if desc_el else ""
        org_el = item.find("span", class_="msl_event_organisation")
        organisation = org_el.get_text(strip=True) if org_el else ""

        # Parse time like "15th September midnight - 18th September midnight" or "17th September 7pm - 9:30pm"
        start, end = _parse_main_page_time(time_text)
        if start is None:
            continue

        events.append({
            "source": source,
            "name": name,
            "url": url,
            "start": start,
            "end": end,
            "location": location,
            "description": description,
            "organisation": organisation,
        })

    return events


def _parse_main_page_time(text: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse main events page time format like '15th September midnight - 18th September midnight'."""
    text = text.strip()
    # Pattern: "15th September midnight - 18th September midnight"
    pattern = re.compile(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(midnight|noon|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
        r"\s*[-–—]\s*"
        r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+)?(midnight|noon|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return (None, None)

    year = datetime.now(MEL).year
    day1 = int(match.group(1))
    month1 = MONTH_NAMES.get(match.group(2).lower(), 1)
    time1 = match.group(3)
    day2 = int(match.group(4)) if match.group(4) else day1
    month2 = MONTH_NAMES.get(match.group(5).lower(), month1) if match.group(5) else month1
    time2 = match.group(6)

    def _time_to_hm(t: str) -> tuple[int, int]:
        t = t.strip().lower()
        if t == "midnight":
            return (0, 0)
        if t == "noon":
            return (12, 0)
        hm = re.match(r"(\d{1,2})(?::(\d{2}))?", t)
        if not hm:
            return (9, 0)
        h = int(hm.group(1)); m = int(hm.group(2) or 0)
        if "pm" in t and h != 12: h += 12
        elif "am" in t and h == 12: h = 0
        return (h, m)

    h1, m1 = _time_to_hm(time1)
    h2, m2 = _time_to_hm(time2)
    start = datetime(year, month1, day1, h1, m1, tzinfo=MEL)
    end = datetime(year, month2, day2, h2, m2, tzinfo=MEL)
    if end <= start:
        end += timedelta(days=1)
    return (start, end)


def deduplicate(events: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    result: list[dict] = []
    for e in events:
        key = (e["url"], e["start"].isoformat(), e["name"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(e)
    return result


def filter_free(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    for e in events:
        combined = f"{e['name']} {e['description']}"
        if _is_paid(combined):
            continue
        if not (_is_free_food(e["name"], e["description"], []) or
                _is_free_benefit(e["name"], e["description"], [])):
            # For eventlist pages, all events are already tagged as free
            if e["source"] in ("free_food", "free"):
                pass
            else:
                continue
        result.append(e)
    return result


def filter_date_range(events: list[dict], now: datetime, days: int = 14) -> list[dict]:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today_start + timedelta(days=days + 1)
    return [e for e in events if e["start"] >= today_start and e["start"] < cutoff]


def build_ics(events: list[dict], now: datetime) -> str:
    now_utc = now.astimezone(ZoneInfo("UTC"))
    dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UMelb Freebies//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:🍔 UMelb Freebies",
        "X-WR-TIMEZONE:Australia/Melbourne",
    ]

    for e in events:
        uid = _make_uid(FreeEvent(
            source=e["source"], name=e["name"], url=e["url"],
            start=e["start"], end=e["end"],
        ))
        start_fmt = e["start"].strftime("%Y%m%dT%H%M%S")
        end_fmt = e["end"].strftime("%Y%m%dT%H%M%S")

        desc_parts = []
        if e["description"]:
            desc_parts.append(e["description"])
        desc_parts.append(f"Source: {e['source']}")
        desc_parts.append(f"URL: {e['url']}")
        desc_parts.append(f"Fetched: {now.strftime('%Y-%m-%d %H:%M %Z')}")
        description = "\\n".join(desc_parts)

        summary = e["name"]
        if e["organisation"]:
            summary = f"{e['name']} ({e['organisation']})"

        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;TZID=Australia/Melbourne:{start_fmt}",
            f"DTEND;TZID=Australia/Melbourne:{end_fmt}",
            f"SUMMARY:{esc(summary)}",
            f"LOCATION:{esc(e['location'])}" if e["location"] else "LOCATION:",
            f"DESCRIPTION:{esc(description)}",
            f"URL:{e['url']}",
            "STATUS:CONFIRMED",
            f"CATEGORIES:{e['source'].upper().replace('_', ' ')}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def run() -> str:
    now = datetime.now(MEL)
    year = now.year
    session = requests.Session()
    all_raw: list[dict] = []
    statuses: list[str] = []

    for name, path in SOURCES.items():
        html = _fetch_page(session, path)
        if html is None:
            statuses.append(f"{name}: FAILED")
            continue
        if name in ("free_food", "free"):
            parsed = parse_eventlist_page(html, name, year)
        else:
            parsed = parse_all_events_page(html, name)
        statuses.append(f"{name}: OK — {len(parsed)} events")
        all_raw.extend(parsed)

    for status in statuses:
        logger.info(status)
    if all(s.endswith("FAILED") for s in statuses):
        logger.warning("WARNING: all sources failed")

    deduped = deduplicate(all_raw)
    free = filter_free(deduped)
    in_range = filter_date_range(free, now)

    logger.info("After dedup: %d, free: %d, in range: %d", len(deduped), len(free), len(in_range))

    return build_ics(in_range, now)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    output = Path("docs/freebies.ics")
    ics = run()
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as f:
        f.write(ics)
    logger.info("Wrote %s (%d bytes)", output, len(ics))


if __name__ == "__main__":
    main()

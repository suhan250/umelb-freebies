import re
from pathlib import Path

ics = Path("docs/freebies.ics").read_text(encoding="utf-8")
events = re.findall(r"BEGIN:VEVENT\r\n(.*?)END:VEVENT", ics, re.DOTALL)

print(f"Total events: {len(events)}\n")
for i, ev in enumerate(events):
    summary = re.search(r"SUMMARY:(.*)", ev)
    dtstart = re.search(r"DTSTART;TZID=Australia/Melbourne:(\d{8}T\d{6})", ev)
    dtend = re.search(r"DTEND;TZID=Australia/Melbourne:(\d{8}T\d{6})", ev)
    url = re.search(r"URL:(.*)", ev)

    s = summary.group(1).strip() if summary else "?"
    ds = dtstart.group(1) if dtstart else "?"
    de = dtend.group(1) if dtend else "?"
    u = url.group(1).strip() if url else "?"

    # Format datetime for readability
    d1 = f"{ds[4:6]}/{ds[6:8]} {ds[9:11]}:{ds[11:13]}"
    d2 = f"{de[4:6]}/{de[6:8]} {de[9:11]}:{de[11:13]}"

    print(f"{i+1:2d}. {s}")
    print(f"    Start: {d1} | End: {d2}")
    print(f"    URL: {u}")
    print()

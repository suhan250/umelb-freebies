import re, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ics = Path("docs/freebies.ics").read_text(encoding="utf-8").replace("\r\n", "\n")
events = re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", ics, re.DOTALL)
urls = []
for ev in events:
    m = re.search(r"URL:(.*)", ev)
    if m:
        url = m.group(1).strip()
        urls.append(url)

print(f"Total events: {len(events)}, URLs found: {len(urls)}\n")
for i, u in enumerate(set(urls)):
    print(f"  {u}")

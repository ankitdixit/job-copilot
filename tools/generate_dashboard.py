#!/usr/bin/env python3
"""generate_dashboard.py — pipeline.md + tasks.md → HTML dashboard.

Extracted from the personal vault_update.py orchestrator so it can be used standalone
without any personal configuration or hardcoded company data.

Usage:
    python3 tools/generate_dashboard.py --pipeline pipeline.md --tasks tasks.md
    python3 tools/generate_dashboard.py --pipeline pipeline.md --tasks tasks.md --output dashboard/schedule.html

Pipeline format expected (markdown table):
    | Company | Stage | Role | Next Action | Date | Contact | Comp |
    |---------|-------|------|-------------|------|---------|------|
    | ...     | ...   | ...  | ...         | ...  | ...     | ...  |

Stage values (case-insensitive): applied, screening, interviewing, final round, offer, rejected

Tasks format expected (from tasks.md):
    - [ ] (P0) [fixed: YYYY-MM-DD HH:MM] #stream Task description
    - [x] Task description  ← done, skipped
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STAGE_ORDER = ["Applied", "Screening", "Interviewing", "Final Round", "Offer"]
STAGE_COLOURS = {
    "Applied": "#4a6fa5",
    "Screening": "#6b8e6b",
    "Interviewing": "#e8a838",
    "Final Round": "#c0804a",
    "Offer": "#5bba6f",
    "Rejected": "#7a4a4a",
}


def parse_pipeline(md: str) -> list[dict]:
    rows = []
    lines = md.splitlines()
    headers: list[str] = []

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r"[-:]+", c) for c in cells if c):
            continue
        if not headers:
            headers = [h.lower().replace(" ", "_") for h in cells]
            continue
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells)))

    return rows


def parse_upcoming_tasks(md: str) -> list[dict]:
    upcoming = []
    pattern = re.compile(
        r"- \[ \] \((P\d)\) \[fixed: (\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)\] (#\w+) (.+)"
    )
    for line in md.splitlines():
        m = pattern.match(line.strip())
        if m:
            priority, date_str, stream, description = m.groups()
            date_str = date_str.replace(" ", "T")
            if len(date_str) == 10:
                date_str += "T00:00"
            upcoming.append(
                {
                    "priority": priority,
                    "date": date_str,
                    "stream": stream,
                    "description": description.strip(),
                }
            )
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def stage_board_html(rows: list[dict]) -> str:
    buckets: dict[str, list[dict]] = {s: [] for s in STAGE_ORDER}
    buckets["Rejected"] = []

    for r in rows:
        stage_raw = r.get("stage", "").strip()
        stage = stage_raw.title()
        if stage in buckets:
            buckets[stage].append(r)
        else:
            buckets["Applied"].append(r)

    cols = []
    for stage in STAGE_ORDER + ["Rejected"]:
        colour = STAGE_COLOURS.get(stage, "#555")
        cards = "".join(
            f'<div class="card">'
            f'<strong>{r.get("company", "?")}</strong><br>'
            f'<small>{r.get("role", r.get("next_action", ""))[:60]}</small>'
            f"</div>"
            for r in buckets[stage]
        )
        count = len(buckets[stage])
        cols.append(
            f'<div class="col">'
            f'<div class="col-header" style="background:{colour}">{stage} <span class="badge">{count}</span></div>'
            f"{cards}"
            f"</div>"
        )

    return '<div class="board">' + "".join(cols) + "</div>"


def upcoming_table_html(tasks: list[dict]) -> str:
    if not tasks:
        return "<p>No upcoming fixed events found.</p>"

    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    rows_html = ""
    for t in tasks[:20]:
        past = t["date"] < now
        cls = ' class="past"' if past else ""
        rows_html += (
            f"<tr{cls}>"
            f"<td>{t['date']}</td>"
            f"<td>{t['priority']}</td>"
            f"<td>{t['stream']}</td>"
            f"<td>{t['description'][:100]}</td>"
            f"</tr>"
        )

    return (
        '<table class="upcoming">'
        "<thead><tr><th>When</th><th>P</th><th>Stream</th><th>Task</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


def pipeline_table_html(rows: list[dict]) -> str:
    if not rows:
        return "<p>No pipeline entries found.</p>"

    headers = list(rows[0].keys()) if rows else []
    thead = "<tr>" + "".join(f"<th>{h.replace('_',' ').title()}</th>" for h in headers) + "</tr>"
    tbody = ""
    for r in rows:
        stage = r.get("stage", "").strip().title()
        colour = STAGE_COLOURS.get(stage, "")
        style = f' style="border-left: 4px solid {colour}"' if colour else ""
        tbody += f"<tr{style}>" + "".join(f"<td>{r.get(h,'')}</td>" for h in headers) + "</tr>"

    return (
        '<table class="pipeline">'
        f"<thead>{thead}</thead>"
        f"<tbody>{tbody}</tbody>"
        "</table>"
    )


def generate_html(pipeline_rows: list[dict], tasks: list[dict], generated_at: str) -> str:
    board = stage_board_html(pipeline_rows)
    upcoming = upcoming_table_html(tasks)
    table = pipeline_table_html(pipeline_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Search Dashboard</title>
<style>
  :root {{
    --bg: #1e1e2e; --surface: #2a2a3e; --text: #cdd6f4; --muted: #6c7086;
    --border: #45475a;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; font-size: 14px; padding: 20px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1rem; color: var(--muted); margin: 24px 0 10px; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-bottom: 20px; }}

  /* Stage board */
  .board {{ display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }}
  .col {{ min-width: 160px; flex: 1; background: var(--surface); border-radius: 8px; overflow: hidden; }}
  .col-header {{ padding: 8px 10px; font-weight: 600; font-size: 12px; display: flex; justify-content: space-between; }}
  .badge {{ background: rgba(0,0,0,0.25); border-radius: 10px; padding: 1px 7px; }}
  .card {{ padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }}
  .card small {{ color: var(--muted); }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }}
  th {{ text-align: left; padding: 6px 8px; background: var(--surface); color: var(--muted); border-bottom: 1px solid var(--border); }}
  td {{ padding: 5px 8px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: var(--surface); }}
  tr.past td {{ opacity: 0.5; }}
  .upcoming {{ margin-bottom: 20px; }}
  .pipeline {{ margin-bottom: 30px; }}
</style>
</head>
<body>
<h1>Job Search Dashboard</h1>
<p class="meta">Generated: {generated_at}</p>

<h2>Stage Board</h2>
{board}

<h2>Upcoming (fixed dates)</h2>
{upcoming}

<h2>Full Pipeline</h2>
{table}

</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML job-search dashboard from markdown files")
    parser.add_argument("--pipeline", required=True, help="Path to pipeline.md (markdown table)")
    parser.add_argument("--tasks", default=None, help="Path to tasks.md (optional)")
    parser.add_argument("--output", default="-", help="Output HTML file path (default: stdout)")
    args = parser.parse_args()

    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"Error: pipeline file not found: {pipeline_path}", file=sys.stderr)
        sys.exit(1)

    pipeline_md = pipeline_path.read_text()
    tasks_md = Path(args.tasks).read_text() if args.tasks and Path(args.tasks).exists() else ""

    rows = parse_pipeline(pipeline_md)
    tasks = parse_upcoming_tasks(tasks_md)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = generate_html(rows, tasks, generated_at)

    if args.output == "-":
        print(html)
    else:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"Dashboard written to {out} ({len(rows)} pipeline entries, {len(tasks)} upcoming tasks)")


if __name__ == "__main__":
    main()

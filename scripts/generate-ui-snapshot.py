#!/usr/bin/env python3
"""Generate a static HTML snapshot of the Band A dashboard UI."""

import html
import json
import urllib.request
from datetime import datetime
from pathlib import Path

API = "http://127.0.0.1:8000/api/v1"
OUT = Path(__file__).resolve().parent.parent / "frontend" / "band-a-ui-snapshot.html"

DEMO_STEPS = [
    ("1", "Zoho happy path", "Zoho tab → New Lead → Band A (once)",
     "Creates a brand-new lead ID and enters Band A.", "Pipeline shows Ingress → Admission → Run → Dispatch → Queue"),
    ("2", "Teams same pipeline", "Teams tab → Ask Teams to Qualify Lead",
     "A salesperson asks manually — same Band A path.", "New run created through identical pipeline stages"),
    ("3", "Scheduler sweep", "Scheduler tab → Run Scheduler Now",
     "Pending leads are picked up automatically.", "Multiple runs created"),
    ("4", "Invalid auth", "Test Admission Controls → Invalid Auth",
     "Bad identity is rejected before a run exists.", "rejected: true, run_created: false"),
    ("5", "Duplicate event", "Test Admission Controls → Duplicate Event",
     "Same event_id returns the existing run safely.", "duplicate: true, same run_id both times"),
    ("5b", "Resend webhook (active run)", "Worker OFF → Send Webhook twice for same lead",
     "Rejection while first run is still active.", "Rejected banner; active_run_blocked"),
    ("6", "Queue backlog", "Worker OFF → create leads → Worker ON",
     "Band A finishes at the queue; Band B drains when available.", "Pending count rises then drains"),
    ("7", "Multi-tenant", "Switch to company-b → qualify LEAD-10007",
     "Each tenant has isolated quota.", "Run created for company-b lead"),
    ("8", "Reset demo", "Header → Reset Demo",
     "Restore clean seed state.", "Metrics and tables return to initial seed data"),
]

STAGES = [
    ("INGRESS", "01 Ingress Edge", "Accepts the arrival, validates the envelope, stores the raw event."),
    ("ADMISSION", "02 Admission Control", "Decides whether this request may proceed."),
    ("RUN_MANAGER", "03 Run Manager", "Turns the admitted request into a trackable run."),
    ("DISPATCHER", "04 Dispatcher", "Chooses how the run should proceed."),
    ("MESSAGE_TRANSPORT", "05 Message Transport", "Durably carries async work to another process."),
]


def fetch(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=5) as r:
        return json.loads(r.read())


def badge(status: str) -> str:
    colors = {
        "ADMITTED": "badge-own",
        "QUEUED": "badge-blue",
        "HANDED_OFF": "badge-ink",
        "REJECTED": "badge-invariant",
        "FAILED": "badge-invariant",
        "SUSPENDED": "badge-yellow",
        "DISPATCHED": "badge-own",
        "QUALIFICATION_IN_PROGRESS": "badge-blue",
        "PENDING_QUALIFICATION": "badge-own",
        "NEW": "badge-gray",
    }
    cls = colors.get(status, "badge-gray")
    return f'<span class="badge {cls}">{html.escape(status)}</span>'


def fmt_time(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        return ts


def strip_html(text: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    for a, b in [("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")]:
        text = text.replace(a, b)
    return text.strip()


def pipeline_html(events: list) -> str:
    by_stage = {}
    for e in events:
        by_stage.setdefault(e["stage"], []).append(e)

    cards = []
    done = 0
    for sid, label, desc in STAGES:
        evs = by_stage.get(sid, [])
        if evs:
            status = "failed" if any(x["status"] == "FAILED" for x in evs) else "done"
            if status == "done":
                done += 1
        else:
            status = "pending"
        actions = "".join(
            f'<div class="stage-action {"fail" if e["status"]=="FAILED" else "ok"}">✓ {html.escape(e["action"].replace("_"," "))}</div>'
            for e in evs
        )
        cards.append(f"""
        <div class="stage-card stage-{status}">
          <div class="stage-num">{html.escape(label.split()[0])}</div>
          <div class="stage-title">{html.escape(label[3:])}</div>
          <p class="stage-desc">{html.escape(desc)}</p>
          <div class="stage-actions">{actions}</div>
        </div>""")

    band_b = any(e.get("stage") == "BAND_B" and e.get("action") == "handed_off" for e in events)
    band_b_cls = "band-b-done" if band_b else "band-b-wait"
    band_b_msg = "Handed off. Band A does not reason about lead quality." if band_b else "Waiting for async handoff via Message Transport…"

    return f"""
    <div class="pipeline-grid">{''.join(cards)}</div>
    <div class="band-b {band_b_cls}">
      <div class="band-b-title">BAND B — Reasoning &amp; Action</div>
      <p>{html.escape(band_b_msg)}</p>
    </div>"""


def timeline_html(events: list) -> str:
    if not events:
        return '<p class="muted">No events yet.</p>'
    rows = []
    for e in events:
        st = "fail" if e["status"] == "FAILED" else "ok"
        msg = f' — {html.escape(e["message"])}' if e.get("message") else ""
        rows.append(f"""
        <div class="timeline-row">
          <span class="timeline-time">{fmt_time(e["timestamp"])}</span>
          <span class="timeline-stage {st}">{html.escape(e["stage"])}</span>
          <span>{html.escape(e["action"].replace("_"," "))}</span>
          <span class="muted truncate">{msg}</span>
        </div>""")
    return f'<div class="timeline">{"".join(rows)}</div>'


def demo_guide_html() -> str:
    steps = []
    for sid, title, action, say, expect in DEMO_STEPS:
        steps.append(f"""
        <li class="demo-step">
          <label class="demo-step-label">
            <input type="checkbox" disabled />
            <div>
              <div class="demo-step-title">{html.escape(sid)}. {html.escape(title)}</div>
              <div><span class="mono own">Click:</span> {html.escape(action)}</div>
              <div class="muted"><span class="mono">Say:</span> {html.escape(say)}</div>
              <div class="muted"><span class="mono">Expect:</span> {html.escape(expect)}</div>
            </div>
          </label>
        </li>""")
    return f"""
    <section class="demo-guide">
      <div class="demo-guide-header">
        <div><span class="demo-guide-title">Demo Guide</span><span class="demo-guide-count">0/{len(DEMO_STEPS)} steps complete</span></div>
        <span class="mono own">Hide</span>
      </div>
      <div class="demo-guide-body">
        <p class="muted">Follow these steps to demo Band A to a reviewer. Check off each step as you go.</p>
        <ol class="demo-steps">{''.join(steps)}</ol>
        <button type="button" class="btn-outline-sm" disabled>Reset checklist</button>
      </div>
    </section>"""


def main():
    try:
        leads = fetch("/leads?tenant_id=company-a")
        runs = fetch("/runs?tenant_id=company-a")
        metrics = fetch("/metrics/summary")
        queue = fetch("/queue/status")
        active_run_id = runs[0]["run_id"] if runs else "RUN-2026-000007"
        active_run = fetch(f"/runs/{active_run_id}")
        events = fetch(f"/runs/{active_run_id}/events")
        mail = fetch(f"/runs/{active_run_id}/inbound-mail")
    except Exception as exc:
        raise SystemExit(f"Could not fetch live API data ({exc}). Start backend on :8000 first.") from exc

    plain_body = strip_html(mail.get("mail_body", ""))
    lead_rows = []
    for l in leads:
        active = l.get("active_run_id")
        active_cell = (
            f'<span class="link">{html.escape(active)}</span>' if active else "—"
        )
        budget = f"₹{(l['budget']/100000):.1f}L" if l.get("budget") else "₹0.0L"
        lead_rows.append(f"""
        <tr>
          <td class="mono">{html.escape(l['lead_id'])}</td>
          <td>{html.escape(l['company_name'])}</td>
          <td>{html.escape(l['industry'])}</td>
          <td>{budget}</td>
          <td>{badge(l['status'])}</td>
          <td class="mono-xs">{active_cell}</td>
        </tr>""")

    run_options = "".join(
        f'<option selected>{html.escape(r["run_id"])} ({html.escape(r["source"])})</option>'
        if r["run_id"] == active_run_id
        else f'<option>{html.escape(r["run_id"])} ({html.escape(r["source"])})</option>'
        for r in runs[:12]
    )

    lead_options = "".join(
        f'<option>{html.escape(l["lead_id"])} — {html.escape(l["company_name"])}'
        + (f' (active: {l["active_run_id"]})' if l.get("active_run_id") else "")
        + "</option>"
        for l in leads[:8]
    )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Band A — Sales Lead Qualification (UI Snapshot)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --paper: #F4F6F5; --ink: #17211E; --ink-soft: #4A5551; --own: #0C6B58;
      --own-tint: #E3F0EC; --invariant: #AE4326; --invariant-tint: #F7E9E3; --hairline: #C9D1CE;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font-family: "IBM Plex Sans", system-ui, sans-serif; -webkit-font-smoothing: antialiased; }}
    .font-display {{ font-family: "Space Grotesk", sans-serif; }}
    .mono {{ font-family: "IBM Plex Mono", monospace; }}
    .muted {{ color: var(--ink-soft); }}
    .own {{ color: var(--own); }}
    .wrap {{ max-width: 72rem; margin: 0 auto; padding: 2rem 1.5rem; }}
    .page-nav {{ display: flex; gap: .5rem; margin-bottom: 1.5rem; }}
    .page-nav button {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; padding: .5rem 1rem; border-radius: .375rem; border: 1px solid var(--hairline); background: #fff; cursor: pointer; }}
    .page-nav button.active {{ background: var(--own); color: #fff; border-color: var(--own); }}
    .page {{ display: none; }}
    .page.active {{ display: block; }}
    header {{ border-bottom: 2px solid var(--ink); padding-bottom: 1.5rem; margin-bottom: 1.5rem; }}
    h1 {{ font-family: "Space Grotesk", sans-serif; font-size: 1.875rem; font-weight: 700; margin: .5rem 0; }}
    .card {{ background: #fff; border: 1px solid var(--hairline); border-radius: .375rem; padding: 1rem; }}
    .grid-6 {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: .75rem; margin-bottom: 2rem; }}
    .metric {{ text-align: center; }}
    .metric-val {{ font-family: "Space Grotesk", sans-serif; font-size: 1.5rem; font-weight: 700; }}
    .metric-label {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--ink-soft); }}
    .grid-main {{ display: grid; grid-template-columns: 1fr 2fr; gap: 1rem; margin-bottom: 2rem; }}
    .tabs {{ display: flex; gap: .5rem; margin-bottom: 1rem; }}
    .tab {{ padding: .25rem .75rem; border-radius: .25rem; font-family: "IBM Plex Mono", monospace; font-size: .875rem; text-transform: capitalize; border: 1px solid var(--hairline); background: #fff; }}
    .tab.active {{ background: var(--own); color: #fff; border-color: var(--own); }}
    .btn {{ width: 100%; padding: .5rem; border-radius: .25rem; font-weight: 500; font-size: .875rem; border: none; cursor: default; }}
    .btn-primary {{ background: var(--own); color: #fff; }}
    .btn-secondary {{ background: #fff; color: var(--own); border: 1px solid var(--own); }}
    .btn-danger {{ background: #fff; color: var(--invariant); border: 1px solid var(--invariant); }}
    .btn-outline-sm {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; border: 1px solid var(--hairline); background: #fff; padding: .25rem .75rem; border-radius: .25rem; color: var(--ink-soft); }}
    select, input[type=text] {{ width: 100%; border: 1px solid var(--hairline); border-radius: .25rem; padding: .25rem .5rem; font-size: .875rem; margin: .5rem 0; }}
    .badge {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; padding: .125rem .5rem; border-radius: 9999px; display: inline-block; }}
    .badge-own {{ background: var(--own-tint); color: var(--own); }}
    .badge-blue {{ background: #eff6ff; color: #1e40af; }}
    .badge-ink {{ background: var(--ink); color: #fff; }}
    .badge-invariant {{ background: var(--invariant-tint); color: var(--invariant); }}
    .badge-yellow {{ background: #fefce8; color: #854d0e; }}
    .badge-gray {{ background: #f3f4f6; color: #374151; }}
    .banner {{ border: 1px solid var(--own); background: var(--own-tint); color: var(--own); padding: .75rem 1rem; border-radius: .375rem; margin-bottom: 1rem; font-family: "IBM Plex Mono", monospace; font-size: .875rem; }}
    .demo-guide {{ background: #fff; border: 2px solid var(--own); border-radius: .375rem; margin-bottom: 2rem; overflow: hidden; }}
    .demo-guide-header {{ display: flex; justify-content: space-between; padding: .75rem 1rem; background: var(--own-tint); }}
    .demo-guide-title {{ font-family: "Space Grotesk", sans-serif; font-weight: 600; color: var(--own); }}
    .demo-guide-count {{ margin-left: .75rem; font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--ink-soft); }}
    .demo-guide-body {{ padding: 1rem; }}
    .demo-steps {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .75rem; }}
    .demo-step {{ border: 1px solid var(--hairline); border-radius: .375rem; padding: .75rem; }}
    .demo-step-label {{ display: flex; gap: .75rem; font-size: .875rem; }}
    .demo-step-title {{ font-family: "Space Grotesk", sans-serif; font-weight: 600; margin-bottom: .25rem; }}
    .pipeline-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: .75rem; margin-bottom: 1.5rem; }}
    .stage-card {{ border-radius: .375rem; border: 2px solid var(--hairline); padding: .75rem; background: #fff; opacity: .85; }}
    .stage-done {{ border-color: var(--own); background: var(--own-tint); opacity: 1; }}
    .stage-failed {{ border-color: var(--invariant); background: var(--invariant-tint); }}
    .stage-num {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--own); font-weight: 600; }}
    .stage-title {{ font-family: "Space Grotesk", sans-serif; font-weight: 600; font-size: .875rem; margin-top: .25rem; }}
    .stage-desc {{ font-size: .75rem; color: var(--ink-soft); margin: .5rem 0; }}
    .stage-action {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; }}
    .stage-action.ok {{ color: var(--own); }}
    .stage-action.fail {{ color: var(--invariant); }}
    .band-b {{ margin-top: 1rem; border-radius: .375rem; border: 2px dashed var(--hairline); padding: 1rem; text-align: center; background: #fff; }}
    .band-b-done {{ border-style: solid; border-color: var(--own); background: var(--ink); color: #fff; }}
    .band-b-done p {{ color: var(--own-tint); }}
    .band-b-title {{ font-family: "Space Grotesk", sans-serif; font-weight: 600; }}
    .timeline {{ max-height: 16rem; overflow-y: auto; }}
    .timeline-row {{ display: flex; gap: .75rem; font-size: .875rem; border-bottom: 1px solid var(--hairline); padding-bottom: .5rem; margin-bottom: .5rem; flex-wrap: wrap; }}
    .timeline-time {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--ink-soft); white-space: nowrap; }}
    .timeline-stage {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; text-transform: uppercase; }}
    .timeline-stage.ok {{ color: var(--own); }}
    .timeline-stage.fail {{ color: var(--invariant); font-weight: 600; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 2rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
    th {{ text-align: left; font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--ink-soft); border-bottom: 1px solid var(--hairline); padding: .5rem 0; }}
    td {{ border-bottom: 1px solid var(--hairline); padding: .5rem 0; }}
    tr:hover {{ background: rgba(244,246,245,.5); }}
    .mono {{ font-family: "IBM Plex Mono", monospace; }}
    .mono-xs {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; }}
    .link {{ color: var(--own); text-decoration: underline; }}
    .mail-dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: .5rem 1.5rem; font-family: "IBM Plex Mono", monospace; font-size: .875rem; margin-bottom: 1rem; }}
    .mail-dl dt {{ font-size: .75rem; color: var(--ink-soft); text-transform: uppercase; }}
    .mail-body {{ border: 1px solid var(--hairline); border-radius: .375rem; background: var(--paper); padding: .75rem; max-height: 18rem; overflow-y: auto; font-size: .875rem; white-space: pre-wrap; }}
    .view-tabs {{ display: flex; gap: .25rem; }}
    .view-tab {{ padding: .25rem .5rem; font-family: "IBM Plex Mono", monospace; font-size: .75rem; border-radius: .25rem; border: 1px solid var(--hairline); background: var(--own); color: #fff; }}
    .view-tab.inactive {{ background: #fff; color: var(--ink); }}
    .section-title {{ font-family: "Space Grotesk", sans-serif; font-weight: 600; margin: 0 0 .75rem; }}
    .watch-run {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .75rem; margin-bottom: 1rem; }}
    .header-row {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; margin-top: 1rem; }}
    .snapshot-note {{ font-family: "IBM Plex Mono", monospace; font-size: .75rem; color: var(--ink-soft); background: #fff; border: 1px dashed var(--hairline); padding: .75rem 1rem; border-radius: .375rem; margin-bottom: 1.5rem; }}
    @media (max-width: 900px) {{
      .grid-6 {{ grid-template-columns: repeat(3, 1fr); }}
      .grid-main, .grid-2, .pipeline-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="snapshot-note">Static UI snapshot generated {html.escape(generated)} from live API data. Interactive app: <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a></div>

    <nav class="page-nav">
      <button type="button" class="active" onclick="showPage('dashboard')">Dashboard</button>
      <button type="button" onclick="showPage('run-detail')">Run Detail — {html.escape(active_run_id)}</button>
    </nav>

    <!-- DASHBOARD -->
    <div id="page-dashboard" class="page active">
      <header>
        <div class="mono muted" style="font-size:.75rem;letter-spacing:.1em;text-transform:uppercase">Agentic Systems Lab · Local Emulator</div>
        <h1>Sales Lead Qualification — <span class="own">Band A</span> Runtime</h1>
        <p class="muted">Local emulator of Entry &amp; Control. No Azure, no real Zoho/Teams.</p>
        <div class="header-row">
          <label class="mono" style="font-size:.875rem">Tenant: <select style="width:auto;display:inline-block"><option>company-a</option><option>company-b</option></select></label>
          <button type="button" class="btn btn-danger" style="width:auto;padding:.25rem 1rem;font-size:.875rem">Reset Demo</button>
        </div>
      </header>

      <div class="banner">New email received → {html.escape(active_run_id)}</div>

      {demo_guide_html()}

      <div class="grid-6">
        <div class="card metric"><div class="metric-val">{metrics['total_leads']}</div><div class="metric-label">Leads</div></div>
        <div class="card metric"><div class="metric-val">{metrics['active_runs']}</div><div class="metric-label">Active Runs</div></div>
        <div class="card metric"><div class="metric-val">{metrics['queued_messages']}</div><div class="metric-label">Queued</div></div>
        <div class="card metric"><div class="metric-val">{metrics['completed_handoffs']}</div><div class="metric-label">Handoffs</div></div>
        <div class="card metric"><div class="metric-val">{metrics['rejected_requests']}</div><div class="metric-label">Rejected</div></div>
        <div class="card metric"><div class="metric-val">{metrics['failed_runs']}</div><div class="metric-label">Failed</div></div>
      </div>

      <section class="grid-main">
        <div class="card">
          <h2 class="section-title">Entry Points</h2>
          <div class="tabs">
            <span class="tab active">zoho</span>
            <span class="tab">teams</span>
            <span class="tab">scheduler</span>
          </div>
          <p class="muted" style="font-size:.75rem">Zoho Simulator — Local</p>
          <p class="muted" style="font-size:.75rem"><span class="mono own">New Lead → Band A</span> creates a <strong>new lead ID every click</strong>.</p>
          <button type="button" class="btn btn-primary" style="margin-top:.5rem">New Lead → Band A</button>
          <select>{lead_options}</select>
          <p class="mono own" style="font-size:.75rem">Active run: {html.escape(active_run_id)} — resending should reject</p>
          <button type="button" class="btn btn-secondary">Send Webhook — {html.escape(leads[0]['lead_id'] if leads else 'LEAD-10001')}</button>
        </div>

        <div class="card">
          <div class="watch-run">
            <h2 class="section-title" style="margin:0">Band A Pipeline</h2>
            <label class="mono" style="font-size:.75rem">Watch run: <select style="width:auto;max-width:220px">{run_options}</select></label>
          </div>
          {pipeline_html(events)}
        </div>
      </section>

      <section class="card" style="margin-bottom:2rem">
        <h2 class="section-title">Watch Run</h2>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;font-family:'IBM Plex Mono',monospace;font-size:.875rem">
          <div>Run ID: <span class="link">{html.escape(active_run['run_id'])}</span></div>
          <div>Source: {html.escape(active_run['source'])}</div>
          <div>Lead: {html.escape(active_run['lead_id'])}</div>
          <div>State: {badge(active_run['state'])}</div>
        </div>
      </section>

      <section class="card" style="margin-bottom:2rem">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem;flex-wrap:wrap;gap:.5rem">
          <h2 class="section-title" style="margin:0">Received Email (Zoho Webhook)</h2>
          <div class="view-tabs">
            <span class="view-tab">plain</span>
            <span class="view-tab inactive">html</span>
            <span class="view-tab inactive">raw</span>
          </div>
        </div>
        <dl class="mail-dl">
          <div><dt>From</dt><dd>{html.escape(mail.get('mail_from','—'))}</dd></div>
          <div><dt>To</dt><dd>{html.escape(mail.get('mail_to','—'))}</dd></div>
          <div style="grid-column:1/-1"><dt>Subject</dt><dd>{html.escape(mail.get('mail_subject','—'))}</dd></div>
          <div><dt>Message ID</dt><dd style="font-size:.75rem">{html.escape(mail.get('mail_message_id','—'))}</dd></div>
          <div><dt>Received</dt><dd>{html.escape(mail.get('received_at','—'))}</dd></div>
        </dl>
        <div class="mail-body">{html.escape(plain_body)}</div>
      </section>

      <section class="grid-2">
        <div class="card">
          <h2 class="section-title">Event Timeline</h2>
          {timeline_html(events)}
        </div>
        <div class="card">
          <h2 class="section-title">Queue</h2>
          <p class="mono" style="font-size:.875rem;margin-bottom:.75rem">Pending: {queue['pending']} · Processing: {queue['processing']} · Worker: {'ON' if queue['worker_running'] else 'OFF'}</p>
          <div style="display:flex;gap:.5rem">
            <button type="button" class="btn btn-secondary" style="width:auto;font-size:.75rem;padding:.25rem .75rem">Worker ON</button>
            <button type="button" class="btn btn-secondary" style="width:auto;font-size:.75rem;padding:.25rem .75rem">Worker OFF</button>
          </div>
        </div>
      </section>

      <section class="card" style="margin-bottom:2rem">
        <h2 class="section-title">Test Admission Controls</h2>
        <div style="display:flex;flex-wrap:wrap;gap:.5rem">
          <button type="button" class="btn btn-danger" style="width:auto;font-size:.875rem;padding:.25rem .75rem">Invalid Auth</button>
          <button type="button" class="btn btn-danger" style="width:auto;font-size:.875rem;padding:.25rem .75rem">Wrong Tenant</button>
          <button type="button" class="btn btn-danger" style="width:auto;font-size:.875rem;padding:.25rem .75rem">Duplicate Event</button>
          <button type="button" class="btn btn-danger" style="width:auto;font-size:.875rem;padding:.25rem .75rem">Quota Exceeded</button>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Leads</h2>
        <table>
          <thead><tr><th>Lead ID</th><th>Company</th><th>Industry</th><th>Budget</th><th>Status</th><th>Active Run</th></tr></thead>
          <tbody>{''.join(lead_rows)}</tbody>
        </table>
      </section>
    </div>

    <!-- RUN DETAIL -->
    <div id="page-run-detail" class="page">
      <a href="#" class="link mono" style="font-size:.875rem" onclick="showPage('dashboard');return false">← Dashboard</a>
      <h1 class="font-display" style="font-size:1.5rem;margin-top:1rem">Run Detail</h1>

      <div class="card" style="margin-top:1rem;display:grid;grid-template-columns:1fr 1fr;gap:1rem;font-family:'IBM Plex Mono',monospace;font-size:.875rem">
        <div>Run ID: {html.escape(active_run['run_id'])}</div>
        <div>Lead ID: {html.escape(active_run['lead_id'])}</div>
        <div>Tenant: {html.escape(active_run['tenant_id'])}</div>
        <div>Source: {html.escape(active_run['source'])}</div>
        <div>Trigger: {html.escape(active_run['trigger_type'])}</div>
        <div>Owner: {html.escape(active_run['owner'])}</div>
        <div>State: {badge(active_run['state'])}</div>
        <div>Correlation: {html.escape(active_run['correlation_id'])}</div>
        <div>Created: {html.escape(active_run['created_at'])}</div>
      </div>

      <section class="card" style="margin-top:1.5rem">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
          <h2 class="section-title" style="margin:0">Received Email (Zoho Webhook)</h2>
          <div class="view-tabs"><span class="view-tab">plain</span><span class="view-tab inactive">html</span><span class="view-tab inactive">raw</span></div>
        </div>
        <dl class="mail-dl">
          <div><dt>From</dt><dd>{html.escape(mail.get('mail_from','—'))}</dd></div>
          <div><dt>To</dt><dd>{html.escape(mail.get('mail_to','—'))}</dd></div>
          <div style="grid-column:1/-1"><dt>Subject</dt><dd>{html.escape(mail.get('mail_subject','—'))}</dd></div>
        </dl>
        <div class="mail-body">{html.escape(plain_body)}</div>
      </section>

      <section class="card" style="margin-top:1.5rem">
        <h2 class="section-title">Event Timeline</h2>
        {timeline_html(events)}
      </section>
    </div>
  </div>

  <script>
    function showPage(id) {{
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.page-nav button').forEach(b => b.classList.remove('active'));
      document.getElementById('page-' + id).classList.add('active');
      event.target.classList.add('active');
    }}
  </script>
</body>
</html>"""

    OUT.write_text(doc, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

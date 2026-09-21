# Build Assignment 01 — Slice 01 · Entry & Control

**Agentic Systems Lab · Giant Leap Systems**
**Issued:** 24 August 2026 · **Duration:** one week · **Teams:** Vertex · Bedrock · Foundry

---

## Ground rules

**Cloud, not agent platform.** Band A has no agent in it, so Vertex / Bedrock / Foundry are not involved this week. You are building on **GCP, AWS and Azure** — edge, queue, store, identity.

**Containers, not serverless.** All five components deploy as one service. Execution ceilings on functions would force async for a platform reason rather than a design reason, and that contaminates the comparison.

**One cloud per pair, for the whole programme.** No rotation. You are becoming your cloud's house expert, which raises the stakes on two things: the Friday defense is *teaching*, not a status report — the other four leave able to reason about your cloud without having built on it — and the binding table is what someone reads when they land in an unfamiliar environment.

**Swap drill, half a day, end of the week.** Stand up **one** component — the run manager — on a cloud that isn't yours. Not a rebuild; just enough to prove the design survives the move. If it doesn't, that is the most valuable finding of the week: the design was cloud-shaped and nobody noticed.

---

## The assignment

Build **Slice 01 — Entry & Control** on your platform, for three entry points, ending in a stub.

This is the one slice that maps exactly onto a band. Everything after it cuts across several bands at once, because the reasoning loop cannot be built without the Trust gate and the record beneath it.

All five components. Working code. **No agent, no model call, nothing that reads the request.**

If you find yourself writing a prompt this week, stop — you have left the assignment.

---

## The three entry points

Each teaches something the others don't. Build all three; they share components 02–05.

| | Entry point | What it forces you to solve |
|---|---|---|
| **E1** | **Email** — to a shared test address | Sender verification (SPF/DKIM/DMARC). Mail providers retry, so arrival dedupe is real, not theoretical. Nobody is waiting. |
| **E2** | **Web UI — conversational** | Someone *is* waiting. The run **continues** rather than being created. Conversation identity must be resolved and owned. |
| **E3** | **Scheduler** — a timed trigger | **Nobody sent anything.** Who is the principal when a cron fires? There is no input to hash, so the dedupe key must be minted from the schedule occurrence. |

E3 is deliberately cheap — roughly twenty lines — and included because it breaks the assumption that a request has a human sender.

---

## What each component must do

**01 · Ingress edge.** Three adapters, one shared downstream path. Verify the source, store the raw arrival, acknowledge fast. E2 additionally needs a streaming channel back to the browser — treat that as an outbound pipe, not part of ingress.

**02 · Admission control.** One module serving all three adapters — not three copies. Authenticate the caller. Resolve the tenant. Deduplicate the arrival. Admit a budget (token, tool-call, wall-clock and money ceilings). **Rejections never become runs** and go to telemetry, not the run store.

**03 · Run manager.** Create the run with identity, owner, tenant, budget and state. Suspend and resume must both work even though nothing pauses this week — build them, prove them with a forced kill. E2 resolves to an **existing** run instead of creating one.

**04 · Dispatcher.** One question, answered from the arrival channel alone: *is anyone waiting?* E2 → sync. E1 and E3 → async. **The choice is written to the run record.** Async runs are durable by default; if your platform's durable execution isn't wired yet, note it as a deviation and carry on — nothing pauses this week.

**05 · Message transport.** Async only. Queue for work distribution. Set up a dead-letter path even though nothing will use it yet.

---

## The handoff stub — identical across all three teams

Do not improvise this. Comparability depends on it.

```
handoff(run) -> void
    logs: run_id, tenant, principal, budget, route, arrival_source
    returns immediately
```

That's the whole stub. Anything more and you have started slice 02.

---

## Acceptance tests

Your build is done when all eight pass. **Write the tests before the code.**

| ID | Test |
|---|---|
| **AC-1** | Same arrival delivered twice → exactly one run |
| **AC-2** | Spoofed or unauthenticated sender → rejected, no run created, recorded in telemetry |
| **AC-3** | Every run carries identity, tenant, owner and a budget ceiling from the moment of creation |
| **AC-4** | The dispatch choice is readable from the run record afterwards |
| **AC-5** | **E2:** a second message on the same conversation continues the existing run — it does not create a new one |
| **AC-6** | **E2:** refresh the browser mid-run and nothing is lost — no state lives in the client |
| **AC-7** | **E3:** firing the same schedule occurrence twice → one run |
| **AC-8** | Kill the process after run creation; the run is still there, in the right state, on restart |

AC-2 and AC-6 are the two I expect at least one team to fail on first attempt. Failing them is a finding — log it, don't hide it.

---

## Binding table — rows 01–05 only

Five rows, not twenty. Fill them **after** building, not before.

| # | Component | Platform primitive | Managed / self-hosted | Gap vs. spine | Deviation ID |
|---|---|---|---|---|---|
| 01 | Ingress edge | | | | |
| 02 | Admission control | | | | |
| 03 | Run manager | | | | |
| 04 | Dispatcher | | | | |
| 05 | Message transport | | | | |

Where the platform offers nothing and you built it yourself, write `NONE — built in-house`. **Those are the most valuable rows in the table.**

Open a `DEV-` entry the same day you hit a constraint, before writing the workaround. The deviations *are* the comparison — unlogged, the week produces three working systems and zero findings.

---

## Non-goals

- **No agent, no model, no prompt.** Nothing this week reads the request.
- No retrieval, no memory, no tools.
- No production hardening, no scale work, no UI beyond what E2 needs.
- No component invented or omitted. All five exist — thin is fine, absent is not.

---

## Friday defense — 20 minutes per pair

Demo the three entry points and the eight tests. Then defend three binding rows: **the one you're least sure about, the one that forced the biggest workaround, and the one where your platform is clearly strongest.**

Then, in ten minutes, **teach your cloud** to the other two pairs: what it gives you free, what it makes you build, and what would bite someone landing on it cold.

**The test for whether the week worked:** can someone say *"Bedrock forces us to build this in-house and Vertex doesn't"* — with a logged deviation behind it? If nobody can say a sentence like that, the week produced code and no findings.

---

## Reference

`asl_band_a_diagram.html` — the five components and the flow. **This is the only reference for this assignment.**

This is slice 01 of seven. The rest of the architecture exists but is not yet released — you will get each slice as you reach it. Don't design ahead of what you've been given.

**Components are revisited, never finished.** Later slices come back and thicken what you build here. That is not rework.

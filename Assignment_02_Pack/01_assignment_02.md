# Build Assignment 02

## Build an agent that reviews supplier invoices

**Agentic Systems Lab · Giant Leap Systems**
**Two weeks · Teams: GCP · AWS · Azure**
**Before you start:** Assignment 01 must be finished and demoed.

---

## Where you are

**Assignment 01** built the front door: work arrives, gets checked, becomes a run with an owner and a budget, and gets routed. That stays. Everything you build now sits behind it.

**This assignment** adds the agent. It reads and explains. It changes nothing.

**Assignment 03** will let it change things — and most of that work will be underneath the agent, not in it.

See `asl_build_journey_map.md` for the whole journey.

**The one move this time:** the agent decides its own next step.

---

## What you are building

A supplier invoice arrives. Your agent works out what is wrong with it and explains why.

It reads the invoice, then checks it against what was ordered, what actually arrived, the supplier's commercial terms, what has been invoiced before, and the company's policy. Then it writes up its findings.

**It changes nothing.** It posts nothing, sends nothing, approves nothing. Read-only, this time.

All three teams build the same thing. That is deliberate: if you build different things, we cannot tell whether a difference between your systems came from the cloud or from you.

---

## Why this needs an agent at all

Most invoice checking doesn't. If you can write the rule, write the rule.

But some of it is genuinely a judgment call:

- The price is 3% over the PO. Is that an exception, or within tolerance for this supplier?
- The quantity doesn't match. Short delivery, or a partial invoice against a standing order?
- Two policies could apply. Which one governs?
- No PO reference at all. Unauthorised purchase, or a category that doesn't need one?

Give the same invoice to two experienced AP analysts and they will check things in a different order, and both be right.

**That is the bar.** If your agent always does the same steps in the same order, you have built a script with a model in it — fine software, but not what this assignment is for.

**Your test:** take two similar invoices. Could your agent reasonably investigate them in a different order and be correct both times? If not, go back.

---

## The rules for this build

**One agent.** No second agent, no delegation, no manager-and-specialists. That comes later.

**Read only.** Nothing your agent does changes anything in the world.

**It finishes in one go.** Nothing waits for a human, nothing pauses for days. Also later.

**The agent decides its own next step.** This is the important one. You give it a goal and a set of tools; it works out what to call and in what order. **You do not write that sequence.**

**Write it as a loop, not a flowchart.** A `while` loop: ask the model what to do, do it, feed the result back, repeat until it says it's done or you hit a limit. That's the whole shape.

⚠ Don't reach for a graph or workflow framework this week. The moment you draw boxes and arrows, you have decided the order — and the model is just filling in your boxes. That's exactly what this assignment is trying to avoid, and it's hard to catch in review because the code looks sophisticated. Graphs arrive in Assignment 04, where you'll want them for a reason.

**Use your own cloud's agent SDK.** ADK on Vertex, the Bedrock SDK or Strands on AWS, Agent Framework on Azure. **No LangChain, no LangGraph, no other cross-cloud framework.**

Not because they're bad — because if all three teams use the same framework, all three build the same thing and we learn nothing about the clouds. That's the point of running three teams. Hand-rolling the loop against the raw model API is a perfectly good answer; just write down that you did.

---

## First job: decide what is *not* the agent's work

Before writing any agent code, split the problem.

Pulling line items off a document is extraction. Looking up a PO by number is a database call. **Neither needs a model.** Both are tools the agent calls, not steps in its reasoning — which is why extraction is already a tool, provided to you, rather than something you build.

The split you have to get right is what's left: which parts of *judging* the invoice belong in the loop, and which are still just lookups dressed up.

What's left — the parts that need judgment — is what the agent actually does.

Getting this split right is the first real design decision, and you'll defend it at the demo. **Doing less with the agent is usually the better answer.**

### The extractor is not certain, and that is on purpose

`extract_invoice` returns structured data **plus a confidence score per field**. Roughly one field in eight comes back below 0.90 — which is what real document extraction does, and pretending otherwise teaches the wrong habit.

A low-confidence field may well be correct. **Deciding what to do about it is the agent's job.** Cross-check the figure against the PO, or say plainly in the finding that a number is uncertain — both defensible. Silently treating a 0.61-confidence total as fact is not.

This is judgment, not plumbing. Don't wrap it in a rule.

---

## How it connects to what you built last time

Assignment 01 ended with a stub — `handoff(run)` — that logged the run and returned.

Now it calls your agent instead. Everything you built stays: the run still has an identity, an owner, a tenant and a budget, and your agent works inside all of it.

### How an invoice actually arrives

**The email arrives. The agent never sees it.**

1. An email lands with the invoice attached as a PDF. Real email — the front door you built last time.
2. Your **ingress edge** stores the raw email and its attachment exactly as they came. It parses nothing.
3. Your **admission control** verifies the sender and resolves them to a supplier. Your tenant resolution stops being decorative and starts deciding which supplier's data this run may ever touch.
4. Your **run manager** creates the run carrying a **document reference** to the stored attachment — not its contents.
5. Your **agent** receives the run and calls `extract_invoice(document_ref)`, which returns structured data.

**Extraction happens inside that tool**, which is exactly where the assignment says it belongs. Your agent never touches the raw document, and nobody spends three days on attachment handling.

⚠ Don't shortcut this by handing the agent an invoice id directly. The supplier's identity comes from the **verified sender**, and that is what makes last assignment's work load-bearing rather than ceremonial.

### The same agent, from chat

An AP analyst opens the web UI and types *"what's wrong with invoice INV-04766?"*

**Same agent. Same tools. Same reasoning.** The only difference is that someone is waiting for the answer.

You built both doors last time. This is where that pays off — and it is a real test of whether you built them properly.

**If your agent can tell which door the run came through, something has leaked.** It shouldn't be able to. Whether anyone is waiting was decided at the front door and is none of the agent's business.

---

## The pieces you'll build

Roughly in the order a run moves through them.

**Context** — decide what the agent sees *this turn*. Not everything, every time. The result of the last tool call becomes part of the next turn's context.

**The agent** — model, instructions, and the loop.

**A tool registry** — a list of what the agent is allowed to call. Seven read-only tools, no more:

| Tool | Reads from |
|---|---|
| `extract_invoice(document_ref)` | Extraction service |
| `get_purchase_order(po_number)` | ERP |
| `get_goods_receipt(po_number)` | ERP |
| `get_vendor(supplier_id)` | ERP |
| `get_ap_history(supplier_id)` | ERP |
| `search_policy(query)` | Policy store |
| `get_policy(policy_id)` | Policy store |

If it isn't on the list, the agent can't reach it.

⚠ **Three things about this list are deliberate.**

**The goods receipt is separate from the PO.** Real accounts payable matches on three documents — what was ordered, what arrived, what was invoiced. Without the receipt you cannot tell a short delivery from a partial invoice.

**Policy is search-then-fetch, not lookup.** You don't know the policy id in advance. You search for what might apply and read what comes back — and sometimes more than one policy applies. That is not a bug in the search.

**No tool does the reasoning for you.** There is no `check_variance()` or `validate_invoice()`. If you find yourself wanting one, that is the agent's job you are trying to move into a tool.

**Connectors** — the code that actually calls those systems.

**A policy check** — before any tool call runs, something *other than the agent* decides whether it's allowed. Not a line in the prompt. Separate code.

**Credentials** — tools get short-lived, narrowly-scoped credentials, handed out only along the path that already recorded what the agent intends to do. No long-lived keys in environment variables.

**Three systems, three credentials.** The ERP, the extraction service and the policy store each take their own token, and none accepts another's. That is not an inconvenience we could have designed away — it is the point. Your broker mints the right one for the tool being called, scoped to that call.

**The journal** — write down every turn: what the agent saw, what it decided, what it called, what came back. Keep it simple for now; we build on it next time.

You are building thin versions of all of these. Assignment 03 comes back and deepens several. **That is not rework — that's the plan.**

---

## What the agent produces

A **finding** — written for an AP analyst, not for a machine.

We are not giving you a schema. But three teams producing three unrecognisable output shapes makes the demos useless, so every finding must contain these, however you format them:

- **The verdict.** Clean, or an exception. If an exception, what kind.
- **What it checked**, and what came back. An unstated check did not happen, as far as anyone reading is concerned.
- **Which policy it applied**, by id — and where two could apply, which it chose and why.
- **The reasoning.** Two or three sentences a human could disagree with.
- **Anything it was unsure of**, including low-confidence extracted fields.

⚠ Case 10 has six lines, four of them clean. A finding that reports "exception" without saying which line and why is not a finding.

**Write it for the analyst who has to act on it**, not for your test harness.

---

## When you're done

Your build passes when all ten hold:

1. Show two runs where the agent investigated in a different order, and both were right.
2. The agent **cannot** call a tool that isn't in the registry — *cannot*, not *doesn't*.
3. Every turn is written to the journal: what it saw, decided, called, got back.
4. The loop stops on any of three limits — number of turns, money spent, time elapsed. Test each separately.
5. No connector gets a credential except through the path that recorded the intent first.
6. Context is rebuilt each turn. The last result is there; stale material isn't just piling up.
7. The policy check runs independently of the agent's reasoning — and you can show it blocking something.
8. You can replay a finished run from the journal with no model calls and no cost.
9. The **same agent** handles the same invoice arriving by email and asked about in chat — same code path, no branch on where it came from.
10. When the extractor returns a low-confidence field, the agent does something about it — cross-checks it, or says so in the finding. It does not silently treat it as fact.

**Expect to fail 5 and 7 on the first attempt.** Both pass every functional test while being wrong. A credential in an environment variable works perfectly and fails 5. A guardrail in the prompt reads fine and fails 7.

---

## Three things that must be impossible, not just untested

There's a difference between "it didn't happen" and "it can't happen." Show us the second.

- The agent **cannot** reach a tool outside the registry — because of how it's wired, not because you told it not to.
- The agent **cannot** get a long-lived credential.
- The loop **cannot** run forever, on any of the three limits.

A rule in the prompt is a request. Show the constraint.

**And one inventory.** List everything your agent's sandbox can actually reach — not just the seven tools, but every cache, bucket, database, queue and shared file it could touch if it tried. **Your real tool surface is everything reachable, not everything registered.** The risk is near zero this week because nothing writes. The habit is the point, and it is much harder to retrofit in assignment 03.

---

## What we're giving you

Everything is in `06_invoice_review_data/`. Read its `README.md` first. Don't build any of it yourself — it's shared, so all three teams test against identical behaviour.

- **Twelve invoices**, arriving as email with SPF/DKIM/DMARC results — and the same twelve as chat queries
- **Two mock systems**: an ERP (purchase orders, goods receipts, vendor master, AP history) and a policy store (four policies, written as prose). Plus the extraction service.
- **`CASES.md`** — what each case forces the agent to do. **Not an answer key.** Knowing what a case tests doesn't tell you what the agent should conclude.

`python mock_systems.py` puts it on port 8080. Or read it as a specification and reimplement it on your platform — it's about 250 lines and deliberately boring.

⚠ **Four of the twelve cases have no single correct verdict.** Two experienced analysts would differ. You are graded on **the evidence you gathered and the reasoning you stated** — did you check the supplier's terms before judging the variance, did you look at history before calling a short delivery. An agent that reaches a defensible conclusion for stated reasons passes. One that reaches the "expected" conclusion having checked nothing does not.

⚠ All three teams share these. Treat them as a live environment, not a scratchpad — your test setup has the same reach as a real one, and "it's only testing" is how most agent incidents start.

---

## The comparison table

After you build — not before — fill in your cloud's rows for the pieces above.

Where your platform gave you something, name it. Where it gave you nothing and you wrote it yourself, write **"nothing — built it ourselves."** Those are the most useful rows in the whole table.

Record what your SDK gave you for the loop and what you had to write. Everyone is building the same loop, so the only thing that varies is how much each cloud hands you — which is exactly what we're trying to find out.

When you hit a wall, write down what the platform wouldn't do **before** you write the workaround. Afterwards you'll rationalise it.

---

## Not this week

- Nothing that changes the world — no writes, posts, emails, approvals
- No waiting for humans, no pausing for days
- No second agent, no delegation
- No graphs, state machines or workflow frameworks
- No LangChain, LangGraph or other cross-cloud framework
- No serious retrieval or search — keep context simple, that comes later
- Leave the scheduler alone. A nightly sweep means many runs from one trigger, and that is assignment 05
- Don't skip a piece, and don't add one

---

## The demo — 30 minutes

Show two runs that went different ways and were both right — one arriving by email, one asked in chat. Show the policy check blocking something. Show a replay.

Then talk us through four things:

1. **What you decided was not the agent's job**, and why it became a tool
2. **What your agent actually judges** — the part a rule couldn't handle
3. **Your hardest row in the comparison table**
4. **One thing that's impossible in your build**, and why — not that it didn't happen, but that it can't

Then ten minutes teaching the other two teams your cloud's agent SDK. They won't have used it, and one day they might have to.

---

## Reference

`asl_build_journey_map.md` — the whole journey, and where this sits on it
`asl_band_a_diagram.html` — what you built last time
`asl_band_b_diagram.html` — the loop you're building now
`06_invoice_review_data/README.md` — the data, the systems, and how to run them
`06_invoice_review_data/CASES.md` — what each of the twelve cases forces

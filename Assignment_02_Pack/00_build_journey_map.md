# The Build Journey

**Agentic Systems Lab · Giant Leap Systems**
**Read this once at kickoff. Keep it. Each assignment tells you where you are on it.**

---

## What you are doing over the next few months

You are building **one system, six times over** — except only the first four times does it survive.

Each build adds one thing. Not a new project each time: the same system, growing. What you write in assignment 02 is still running in assignment 05, with more around it.

Then two short spikes at the end, on the same foundation, to see two shapes you would otherwise never build.

---

## The plumbing you build once

Assignment 01 built the front door: how work arrives, gets checked, becomes a run with an owner and a budget, and gets routed.

**That barely changes for the rest of the programme.** A simple agent and a complicated one arrive the same way. You built it once; it serves everything after.

What changes from here is what happens *after* the front door — and the interesting part is that it is not only the agent that changes. Making an agent that can *do* things rather than only *read* things is mostly work in the layers underneath it: recording what it did, stopping it doing the same thing twice, deciding what it is allowed to do at all.

⚠ **That surprises people.** "Build a better agent" usually means "build better machinery around the agent." Watch for it.

---

## The growth path — four builds, cumulative

### 02 · An agent that reads and explains
Supplier invoices arrive. The agent works out what is wrong with them and writes up its findings. It changes nothing.

**The move:** the agent decides its own next step. You give it tools and a goal; it works out the order.
**Where the work is:** the reasoning loop, and the first thin versions of everything around it.

### 03 · An agent that changes things
The same agent now posts its findings to the accounting system.

**The move:** read-only → makes changes.
**Where the work is:** almost entirely underneath the agent. What happens when the call succeeds but the process dies before recording it? What stops a retry creating the same entry twice? The agent barely changes. This is the assignment that surprises everyone.

### 04 · An agent a human has to approve
Some corrections need a finance manager's sign-off. The system stops, waits — possibly for days — and continues when approval arrives.

**The move:** everything runs start to finish → the run can pause and come back.
**Where the work is:** the run has to genuinely stop existing and be rebuilt later. Nothing held in memory. This is where you will want the structure you were told not to build in assignment 02, and now you will know why.

### 05 · A team of agents
One agent got too broad. Now a manager agent delegates to specialists — extraction, policy, tax — and pulls their answers together.

**The move:** one agent → several, with one in charge.
**Where the work is:** back in the agent layer, and in how agents talk to each other. Everything underneath is already built.

---

## Then two spikes — three or four days each

**These are throwaway. You will delete them, and that is fine.**

You are not building a system. You are seeing a shape, on the foundation you already have, and answering one question about our architecture.

### 06 · Agents that argue
Same specialists, but no manager. They deliberate as peers and a human decides between them.

**The question:** does our foundation actually support this, or does something break?

### 07 · A system that never stops
The same system, running continuously and unattended, reacting to events as they arrive rather than to requests.

**The question:** same one.

⚠ **Do not over-engineer these.** No production polish, no new data, no new front door. If you find yourself rebuilding assignment 01, stop — that is itself the finding.

---

## What we are actually testing

Every assignment claims the same underlying architecture holds. The spikes are where that claim gets tested against shapes it was not designed around.

**If changing the kind of agentic system means rebuilding the plumbing, our architecture is wrong** — and we want to know that from you, in week eighteen, rather than from a client.

Write down what breaks. That is the deliverable.

---

## Rules that hold for every assignment

**All three teams build the same thing.** If you build different things, we cannot tell whether a difference between your systems came from the cloud or from you.

**Use your own cloud's SDK.** No cross-cloud frameworks. The whole point of three teams is finding out what each cloud gives you; a portable framework on top hides exactly that.

**Nothing is finished.** Assignment 02 builds a thin journal; 03 comes back and deepens it; 04 deepens it again. Revisiting is the plan, not rework.

**Don't build ahead.** Each assignment names what it defers. Building assignment 04's structure during assignment 02 is the most common way to get 02 wrong.

**Write down what your platform wouldn't do — before you write the workaround.** Afterwards you will rationalise it.

---

## A note on names

The industry has names for the six shapes above, and so do we. They are in a separate document you will read later.

We have left them out here on purpose. **The names are only useful once you have built the thing** — before that they are labels for something you have not seen, and they make the shapes sound more different from each other than they actually are.

Build first. Names after.

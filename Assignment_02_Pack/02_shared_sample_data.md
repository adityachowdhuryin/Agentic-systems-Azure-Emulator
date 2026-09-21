# Shared Sample Data — invoice review

**Agentic Systems Lab · Giant Leap Systems**
**Built once, centrally. All three teams read identical bytes.**

---

## Why this is central and not per-team

Three teams building three data sets means three different behaviours, and every difference between their systems becomes unattributable. The data is the one thing that must be byte-identical.

**And the data decides whether the assignment works.** If the invoices all match their POs cleanly, nothing requires judgment, and all three teams will correctly build a validation script — the exact thing the assignment tells them not to build. **The awkward cases are the assignment.**

---

## Two systems, not five sources

Real accounts payable does not have five flat files. It has an **ERP** and a **document/policy
store**, and they behave differently — which is precisely the lesson.

| What | Where it really lives | Access pattern |
|---|---|---|
| Purchase orders | ERP | Structured, exact lookup by key |
| **Goods receipts** | ERP, same instance | Structured — the third leg of the three-way match |
| Vendor master — terms, tolerances, hold status | ERP, same instance | Structured |
| Prior invoices | ERP, AP subledger | Structured query |
| **Policy** | SharePoint / Confluence / a PDF manual | **Unstructured prose. Searched, not looked up** |

Four of the five are one system, one credential, one access pattern. Policy is somewhere
else entirely, is prose, and is retrieved by search. **That asymmetry is why policy
interpretation is the judgment and everything else is a lookup.**

⚠ **The goods receipt was missing from the first draft of this spec.** Without it, case 05
is unanswerable — you cannot distinguish a short delivery from a partial invoice. Real AP
matches on three documents, and so does this.

## Built and shipped

`06_invoice_review_data/` contains the working data set and the two mock systems:

```
erp/purchase_orders  goods_receipts  vendor_master  ap_history
policy_store/        four policy documents, as prose
inbound/emails       twelve arrivals with SPF/DKIM/DMARC results
inbound/documents    the invoice payloads the extraction service reads
inbound/chat_queries.json
expected/            what each case forces — not an answer key
mock_systems.py      ERP + extraction + policy store + (assignment 03) accounting
```

`python mock_systems.py` on port 8080, or read it as a spec and reimplement it.

**Credentials are scoped per system.** The ERP token does not open the policy store. That
is not decoration — it is what the credential broker exists to do, and it is verified.

## The five sources

**Invoices arrive as PDF, because they do** — but extraction is a *provided tool*, not something teams build. They call `/extraction/invoice` and get structured data back. Realism without three days of attachment handling.

🔍 **And the extractor returns per-field confidence**, as every real document-processing product does. Roughly one field in eight comes back below 0.90. A low-confidence field may still be correct — **deciding what to do about it is the agent's problem.** Re-read the document, cross-check against the PO, or state the uncertainty in the finding: all defensible. Ignoring it is not. That turns OCR from toil into judgment.

| Source | Format | Why |
|---|---|---|
| `invoices/` | JSON | What arrived |
| `purchase_orders/` | JSON | What was agreed |
| `suppliers/` | JSON | Terms, tolerances, status |
| `policies/` | **Markdown prose** | Deliberately not structured — see below |
| `invoice_history/` | JSON | Prior invoices per supplier |

⚠ **Policies must be prose, not config.** If tolerance is a number in a JSON field, applying it is a lookup and the agent is redundant. Written as policy text — *"variances up to 5% may be accepted where the supplier has no open disputes and the category is not capital equipment"* — reading it is interpretation. **That is where the judgment lives.** Make them short, real-sounding, and slightly ambiguous at the edges, the way actual policies are.

Write at least two policies that could both plausibly apply to the same invoice.

---

## The cases

Twelve is enough. Each names what it forces the agent to do.

| # | Case | Forces |
|---|---|---|
| 01 | Clean — matches the PO exactly | A baseline. Correct answer: no exception. Watch for agents that invent one |
| 02 | Price 3% over, supplier terms allow 5% | Must fetch supplier terms; the invoice alone looks wrong |
| 03 | Price 12% over, outside tolerance | Straightforward exception |
| 04 | Price 4% over, two policies apply — general 5%, supplier-specific 2% | **Must decide which governs.** No lookup answers this |
| 05 | Quantity 80 against a PO for 100 | Short delivery or partial invoice? Only the history distinguishes them |
| 06 | Quantity 110 against a PO for 100 | Over-delivery — accepted or an error? |
| 07 | No PO reference, category permits direct spend | Unauthorised, or fine? Needs the policy |
| 08 | No PO reference, category does not permit it | Same shape, opposite answer |
| 09 | Same invoice number as one three weeks ago | Only visible from history |
| 10 | Six lines: four clean, one 15% over, one short | Per-line reasoning, then a composite judgment about the whole invoice |
| 11 | Supplier terms expired last month | The terms record is itself the exception |
| 12 | Priced per case on the PO, invoiced per unit | Numbers look wildly wrong until the units are noticed |

**Case 04 is the one that matters most.** It is the case where two competent analysts genuinely disagree — and if it isn't in the data, nothing in the set requires an agent.

**Include case 01.** An agent that manufactures exceptions from a clean invoice has failed, and without a clean case nobody finds out.

---

## The five read tools

The simulated systems expose exactly these, all read-only:

- `get_invoice(invoice_id)`
- `get_purchase_order(po_number)`
- `get_supplier_terms(supplier_id)`
- `get_policy(policy_id)` and `list_policies(category)`
- `get_invoice_history(supplier_id, months)`

**Nothing else.** Any tool that would do the reasoning for the agent — `check_variance()`, `validate_invoice()` — defeats the assignment.

⚠ Note `list_policies` returns more than one for some categories. **That is deliberate**, and it is how case 04 becomes a real decision rather than a lookup.

---

## How the awkward cases get graded

Cases 04, 05, 07 and 10 have no single correct verdict. Two experienced analysts would differ.

**So grade the evidence, not the verdict.** The test is whether the agent found the relevant facts and said why — did it fetch the supplier terms before judging the variance, did it look at history before calling a short delivery, did it notice both policies applied and say which it chose and why.

An agent that reaches a defensible conclusion for stated reasons passes. One that reaches the "expected" conclusion having checked nothing fails.

🔍 That is a rough version of what assignment 06 does properly. Rough is fine for now — the point is that graders never mark on the verdict alone, or teams will tune toward the answer key instead of building an agent.

---

## How the data reaches the teams

**Invoices arrive as email.** Each of the twelve cases is a sample email with a JSON attachment, sent to the shared test address. Supplier identity comes from the verified sender, not from a field inside the file — that is what makes assignment 01's admission control load-bearing.

Provide per-team aliases on the test address, or three teams will race for the same inbox and duplicate-arrival tests become untestable.

**The other four sources are served by the simulated systems**, behind the five read tools. Teams never read these files directly; their tools do.

**Also send each case as a chat query** — *"what's wrong with invoice 5611?"* — so the same case can be exercised through both doors. That is what pass criterion 9 checks.

🔍 **Optional, costs about a day:** make one of the twelve a PDF instead of JSON. It teaches that extraction belongs behind a tool rather than in the agent — a lesson worth having, but not worth three days of attachment handling. Add it only if the teams are ahead.

---

## Also needed

**A simulated accounting system**, write-capable, from assignment 03 onward. It needs its **own record of what was written**, independent of anything the teams build — otherwise nobody can detect a write that happened but was never recorded, and that is the entire lesson of assignment 03.

**Fault injection**, from assignment 03: a call that times out after succeeding, a duplicate delivery, an intermittently unavailable service. Without these, the machinery of assignment 03 is untestable and teams will believe it works.

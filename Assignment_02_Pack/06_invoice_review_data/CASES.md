# The twelve cases

| Case | Supplier | What it forces |
|---|---|---|
| 01 | SUP-1001 | Clean invoice. Correct answer: no exception. Catches agents that invent one. |
| 02 | SUP-1001 | Price 3% over. Invoice alone looks wrong; the vendor master says 5% is fine. |
| 03 | SUP-1001 | Price 12% over. Straightforward exception. |
| 04 | SUP-1002 | **Price 4% over. POL-AP-001 allows 5%; the supplier's negotiated agreement says 2%.** No lookup resolves this. |
| 05 | SUP-1001 | Invoiced 80 of 100, receipt confirms 80. Short delivery or partial invoice? Only AP history distinguishes them. |
| 06 | SUP-1001 | Invoiced 110 against a PO for 100, receipt confirms 110. Within the 10% over-delivery tolerance. |
| 07 | SUP-1004 | No PO. Professional Services, AUD 860 — under the AUD 1,000 threshold. Permitted. |
| 08 | SUP-1005 | No PO. Raw Materials — never permitted, whatever the value. Same shape as 07, opposite answer. |
| 09 | SUP-1001 | Invoice number INV-01417 already paid on 2026-09-01. Only visible in AP history. |
| 10 | SUP-1002 | Six lines: four clean, one 15% over, one short-delivered. Per-line reasoning, then a judgment about the invoice as a whole. |
| 11 | SUP-1003 | Commercial agreement lapsed 2026-08-31. The vendor record is itself the exception. |
| 12 | SUP-1002 | PO priced per case of 12; invoice priced per unit. Totals look wildly wrong until units are noticed. |

**Case 04 is the one that matters.** It is the case where two competent analysts genuinely
disagree. Without it, nothing in the set requires an agent rather than a rule.

**Case 01 matters nearly as much.** An agent that manufactures an exception from a clean
invoice has failed, and without a clean case nobody finds out.

**Cases 04, 05, 07 and 10 have no single right verdict.** Grade the evidence, not the answer.

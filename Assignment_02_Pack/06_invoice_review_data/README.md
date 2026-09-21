# Invoice review — shared sample data

Built once, centrally. All three teams read identical bytes.

## Two systems, not five sources

Real AP does not have five flat files. It has an ERP and a document/policy store, and
they behave differently — which is the point.

    erp/                  structured, exact lookup by key, one credential
      purchase_orders/    what was agreed
      goods_receipts/     what actually arrived  (the third leg of the three-way match)
      vendor_master/      terms, tolerances, agreement validity, hold status
      ap_history/         prior invoices per supplier

    policy_store/         prose. Searched, not looked up. A different credential.

    inbound/
      emails/             twelve arrivals, with SPF/DKIM/DMARC results
      documents/          what the extraction service reads. NOT for the agent —
                          the agent calls extract_invoice(document_ref)
      chat_queries.json   the same twelve, asked through the chat door

    expected/             what each case forces the agent to do. NOT an answer key.

    mock_systems.py       the two systems, plus extraction, plus (for assignment 03)
                          the accounting system

## Running it

    pip install fastapi uvicorn
    python mock_systems.py        # http://localhost:8080

Or read it as a specification and reimplement it on your own platform. It is about
250 lines and deliberately boring.

## What the tools look like

    GET  /erp/purchase-orders/{po_number}          x-credential: erp-scoped-token
    GET  /erp/goods-receipts?po_number=            x-credential: erp-scoped-token
    GET  /erp/vendors/{supplier_id}                x-credential: erp-scoped-token
    GET  /erp/ap-history/{supplier_id}             x-credential: erp-scoped-token
    GET  /extraction/invoice?document_ref=         x-credential: extract-scoped-token
    GET  /policy/search?q=                         x-credential: policy-scoped-token
    GET  /policy/{policy_id}                       x-credential: policy-scoped-token

Note the credentials are **different per system**. One token does not open everything.
That is not decoration — it is the point of the credential broker you are building.

## The extraction service returns confidence

Real document extraction is not certain, and pretending otherwise teaches the wrong
habit. `/extraction/invoice` returns per-field confidence. Roughly one field in eight
comes back below 0.90.

A low-confidence field may still be correct. **Deciding what to do about it is the
agent's problem** — re-read the document, cross-check against the PO, or say plainly
in the finding that a number is uncertain. All three are defensible. Ignoring it is not.

## Policy search returns more than one result

`/policy/search` will sometimes return two policies that both plausibly apply. This is
deliberate and it is not a bug in the search. Real policy is like this. Choosing which
governs, and saying why, is the judgment the assignment is about.

## Assignment 03 only

    POST /accounting/corrections     x-credential: accounting-scoped-token
                                     idempotency-key: <required>
    GET  /accounting/corrections?invoice_number=     the reconciliation probe
    POST /_admin/faults?on=true      turn on timeouts-after-success

The accounting system keeps its **own** ledger, independent of anything you build.
That is how we find out whether something happened that you never recorded.

Turn the faults on early. Two weeks against a system that always answers correctly
will convince you everything works.

## Grading

Four of the twelve cases have no single correct verdict — two experienced analysts
would differ. **Graders mark the evidence gathered and the reasoning stated, not the
verdict.** An agent that reaches a defensible conclusion for stated reasons passes.
One that reaches the expected conclusion having checked nothing does not.

`expected/` describes what each case forces. It is not an answer key, and teams should
have it — knowing what a case is testing does not tell you what the agent should decide.

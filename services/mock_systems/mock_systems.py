"""
Mock systems of record for the ASL invoice-review assignments.

Two systems, deliberately different in shape — because that is how it is in reality.

  ERP           structured, exact lookup by key, one credential
  Policy store  unstructured prose, searched not looked up, different credential

Run:  python mock_systems.py           -> http://localhost:8080
Deps: fastapi uvicorn   (or read it as a spec and reimplement on your platform)
"""
import json, os, glob, random, hashlib
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse

ROOT = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="ASL Mock Systems of Record")

def load(p):
    with open(os.path.join(ROOT, p)) as f: return json.load(f)

def need(token, expected, system):
    # Scoped credentials: the ERP and the policy store do NOT share one.
    if token != expected:
        raise HTTPException(401, f"{system}: invalid or wrongly-scoped credential")

# ─────────────────────────── ERP ───────────────────────────
ERP_TOKEN = "erp-scoped-token"

@app.get("/erp/purchase-orders/{po_number}")
def get_purchase_order(po_number: str, x_credential: str = Header(None)):
    need(x_credential, ERP_TOKEN, "ERP")
    try: return load(f"erp/purchase_orders/{po_number}.json")
    except FileNotFoundError: raise HTTPException(404, "purchase order not found")

@app.get("/erp/goods-receipts")
def get_goods_receipt(po_number: str, x_credential: str = Header(None)):
    need(x_credential, ERP_TOKEN, "ERP")
    hits = [load(p.replace(ROOT + os.sep, "")) for p in glob.glob(f"{ROOT}/erp/goods_receipts/*.json")]
    hits = [h for h in hits if h["po_number"] == po_number]
    if not hits: raise HTTPException(404, "no goods receipt for this purchase order")
    return {"receipts": hits}

@app.get("/erp/vendors/{supplier_id}")
def get_vendor(supplier_id: str, x_credential: str = Header(None)):
    need(x_credential, ERP_TOKEN, "ERP")
    try: return load(f"erp/vendor_master/{supplier_id}.json")
    except FileNotFoundError: raise HTTPException(404, "supplier not found")

@app.get("/erp/ap-history/{supplier_id}")
def get_ap_history(supplier_id: str, months: int = 12, x_credential: str = Header(None)):
    need(x_credential, ERP_TOKEN, "ERP")
    try: return load(f"erp/ap_history/{supplier_id}.json")
    except FileNotFoundError: return {"supplier_id": supplier_id, "invoices": []}

# ──────────────────── Document extraction ────────────────────
# Realistic IDP behaviour: structured output WITH per-field confidence.
# Some fields come back uncertain. The agent must decide whether to trust them.
EXTRACT_TOKEN = "extract-scoped-token"

def _conf(doc_ref, field):
    h = int(hashlib.sha256(f"{doc_ref}:{field}".encode()).hexdigest(), 16)
    r = (h % 1000) / 1000.0
    return 0.55 + r * 0.20 if r < 0.12 else 0.93 + r * 0.07   # ~12% of fields are shaky

@app.get("/extraction/invoice")
def extract_invoice(document_ref: str, x_credential: str = Header(None)):
    need(x_credential, EXTRACT_TOKEN, "Extraction service")
    matches = glob.glob(f"{ROOT}/inbound/documents/*{document_ref}*.json")
    if not matches: raise HTTPException(404, "document not found")
    inv = load(matches[0].replace(ROOT + os.sep, ""))
    out = {"document_ref": document_ref, "extracted": inv, "field_confidence": {}}
    for k in ("invoice_number", "supplier_id", "invoice_date", "po_reference", "total_amount"):
        out["field_confidence"][k] = round(_conf(document_ref, k), 3)
    for line in inv["lines"]:
        for k in ("item_code", "quantity", "unit_price"):
            out["field_confidence"][f"line_{line['line_no']}.{k}"] = round(
                _conf(document_ref, f"{line['line_no']}{k}"), 3)
    out["note"] = ("Confidence below 0.90 means the extractor is unsure of that field. "
                   "It may still be correct. Deciding what to do about it is your problem.")
    return out

# ───────────────────────── Policy store ─────────────────────────
# Different system, different credential, prose not records, search not lookup.
POLICY_TOKEN = "policy-scoped-token"

def _policies():
    out = []
    for p in sorted(glob.glob(f"{ROOT}/policy_store/*.md")):
        text = open(p).read()
        pid = text.split("policy_id:")[1].split("\n")[0].strip()
        title = text.split("title:")[1].split("\n")[0].strip()
        out.append({"policy_id": pid, "title": title, "path": os.path.basename(p), "text": text})
    return out

@app.get("/policy/search")
def search_policy(q: str, x_credential: str = Header(None)):
    need(x_credential, POLICY_TOKEN, "Policy store")
    terms = [t for t in q.lower().split() if len(t) > 3]
    scored = []
    for p in _policies():
        body = p["text"].lower()
        score = sum(body.count(t) for t in terms)
        if score: scored.append({"policy_id": p["policy_id"], "title": p["title"], "score": score})
    scored.sort(key=lambda x: -x["score"])
    # NOTE: more than one policy can legitimately match. That is deliberate.
    return {"query": q, "results": scored}

@app.get("/policy/{policy_id}")
def get_policy(policy_id: str, x_credential: str = Header(None)):
    need(x_credential, POLICY_TOKEN, "Policy store")
    for p in _policies():
        if p["policy_id"] == policy_id:
            return {"policy_id": p["policy_id"], "title": p["title"], "text": p["text"]}
    raise HTTPException(404, "policy not found")

# ───────────────── Accounting system — assignment 03 only ─────────────────
# Keeps its OWN record of what was written, independent of anything you build.
# That is how we detect a write that happened but was never recorded.
LEDGER = os.path.join(ROOT, "_accounting_system_ledger.jsonl")
ACCT_TOKEN = "accounting-scoped-token"
FAULTS = {"enabled": False}

@app.post("/accounting/corrections")
def post_correction(payload: dict, idempotency_key: str = Header(None),
                    x_credential: str = Header(None)):
    need(x_credential, ACCT_TOKEN, "Accounting system")
    if not idempotency_key:
        raise HTTPException(400, "idempotency key required for effectful operations")
    seen = {}
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            r = json.loads(line); seen[r["idempotency_key"]] = r
    body_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    if idempotency_key in seen:
        prior = seen[idempotency_key]
        if prior["body_hash"] != body_hash:
            raise HTTPException(409, "idempotency key reused with different content — "
                                     "this is a collision, not a duplicate")
        return {"status": "already_applied", "entry_id": prior["entry_id"], "replayed": True}
    entry = {"entry_id": f"CE-{random.randint(100000,999999)}",
             "idempotency_key": idempotency_key, "body_hash": body_hash, "payload": payload}
    with open(LEDGER, "a") as f: f.write(json.dumps(entry) + "\n")
    if FAULTS["enabled"] and random.random() < 0.30:
        # The effect landed. The caller will never hear about it.
        raise HTTPException(504, "gateway timeout")
    return {"status": "applied", "entry_id": entry["entry_id"]}

@app.get("/accounting/corrections")
def list_corrections(invoice_number: str = None, x_credential: str = Header(None)):
    """The reconciliation probe. Ask before you retry."""
    need(x_credential, ACCT_TOKEN, "Accounting system")
    rows = []
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            r = json.loads(line)
            if invoice_number is None or r["payload"].get("invoice_number") == invoice_number:
                rows.append({"entry_id": r["entry_id"], "idempotency_key": r["idempotency_key"],
                             "payload": r["payload"]})
    return {"corrections": rows}

@app.post("/_admin/faults")
def set_faults(on: bool):
    FAULTS["enabled"] = on
    return {"faults_enabled": on}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

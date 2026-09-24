"""Run Assignment 02 mock systems on port 8090 (8080 reserved for webhook bridge)."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "Assignment_02_Pack" / "06_invoice_review_data"
UPLOADS = REPO / "data" / "invoice_uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("INVOICE_UPLOADS_DIR", str(UPLOADS))
os.chdir(PACK)
sys.path.insert(0, str(PACK))

# Patch port by importing after rewriting __main__
import mock_systems as ms
import uvicorn

if __name__ == "__main__":
    print(f"Serving mock systems from {PACK} on http://127.0.0.1:8090")
    print(f"Live invoice uploads: {UPLOADS}")
    uvicorn.run(ms.app, host="0.0.0.0", port=8090)

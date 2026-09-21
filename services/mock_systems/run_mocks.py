"""Run Assignment 02 mock systems on port 8090 (8080 reserved for webhook bridge)."""
import os
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "Assignment_02_Pack" / "06_invoice_review_data"
os.chdir(PACK)
sys.path.insert(0, str(PACK))

# Patch port by importing after rewriting __main__
import mock_systems as ms
import uvicorn

if __name__ == "__main__":
    print(f"Serving mock systems from {PACK} on http://127.0.0.1:8090")
    uvicorn.run(ms.app, host="0.0.0.0", port=8090)

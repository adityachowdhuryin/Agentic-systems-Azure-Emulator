"""Container entry for mocks — pack already at /app/pack."""
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mocks")

PACK = Path(os.environ.get("MOCK_PACK_DIR", "/app/pack"))
UPLOADS = Path(os.environ.get("INVOICE_UPLOADS_DIR", "/app/data/invoice_uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("INVOICE_UPLOADS_DIR", str(UPLOADS))
os.chdir(PACK)
sys.path.insert(0, str(PACK))

import mock_systems as ms  # noqa: E402
import uvicorn

if __name__ == "__main__":
    logger.info(
        "Mocks starting broker_secret_fingerprint=%s (must match bandb)",
        ms.broker_secret_fingerprint(),
    )
    uvicorn.run(ms.app, host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))

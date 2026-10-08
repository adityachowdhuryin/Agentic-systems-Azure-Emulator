"""Document store for live invoice JSON — local disk or Azure Blob."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from app.config import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_UPLOADS = REPO_ROOT / "data" / "invoice_uploads"


class DocumentStore(Protocol):
    def put_json(self, document_ref: str, payload: dict[str, Any]) -> str: ...
    def get_json(self, document_ref: str) -> dict[str, Any] | None: ...


class LocalDocumentStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(
            os.getenv("INVOICE_UPLOADS_DIR") or settings.invoice_uploads_dir or str(DEFAULT_UPLOADS)
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(self, document_ref: str, payload: dict[str, Any]) -> str:
        path = self.root / f"{document_ref}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def get_json(self, document_ref: str) -> dict[str, Any] | None:
        path = self.root / f"{document_ref}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class BlobDocumentStore:
    def __init__(self):
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
        from azure.storage.blob import BlobServiceClient

        account = (
            os.environ.get("AZURE_STORAGE_ACCOUNT") or settings.azure_storage_account
        )
        if not account:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT required for blob document store")
        # Prefer the user-assigned MI pinned on ACA (AZURE_CLIENT_ID).
        client_id = os.environ.get("AZURE_CLIENT_ID")
        if client_id:
            cred = ManagedIdentityCredential(client_id=client_id)
        else:
            cred = DefaultAzureCredential()
        url = f"https://{account}.blob.core.windows.net"
        self._client = BlobServiceClient(url, credential=cred)
        self._container = (
            os.environ.get("AZURE_BLOB_CONTAINER")
            or settings.azure_blob_container
            or "documents"
        )
        try:
            self._client.create_container(self._container)
        except Exception:
            pass

    def put_json(self, document_ref: str, payload: dict[str, Any]) -> str:
        blob = self._client.get_blob_client(self._container, f"{document_ref}.json")
        data = json.dumps(payload, indent=2).encode("utf-8")
        blob.upload_blob(data, overwrite=True)
        return blob.url

    def get_json(self, document_ref: str) -> dict[str, Any] | None:
        blob = self._client.get_blob_client(self._container, f"{document_ref}.json")
        try:
            raw = blob.download_blob().readall()
        except Exception:
            return None
        return json.loads(raw.decode("utf-8"))


def get_document_store() -> DocumentStore:
    # Prefer live ACA env over import-time settings default (local).
    backend = (
        os.environ.get("DOCUMENT_STORE_BACKEND")
        or settings.document_store_backend
        or "local"
    ).lower()
    if backend == "blob":
        return BlobDocumentStore()
    return LocalDocumentStore()

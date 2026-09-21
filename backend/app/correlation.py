import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    cid = correlation_id_var.get()
    if not cid:
        cid = f"CORR-{uuid.uuid4().hex[:12].upper()}"
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    correlation_id_var.set(cid)


def new_correlation_id() -> str:
    cid = f"CORR-{uuid.uuid4().hex[:12].upper()}"
    correlation_id_var.set(cid)
    return cid

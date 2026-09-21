import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import (
    Finding,
    JournalTurn,
    Lead,
    InboundEvent,
    QueueMessage,
    Run,
    RuntimeEvent,
    init_db,
)
from app.repositories.base import LeadRepository
from app.schemas import LeadCreate

# Real inbound channels — preserved on reset only when NOT sample-player
EXTERNAL_LEAD_SOURCES = frozenset({"Zoho Mail", "Teams"})

SAMPLE_ORIGIN = "sample_player"
_SAMPLE_ID_PREFIXES: frozenset[str] | None = None


def _seed_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "data" / "seed_leads.json"


def _samples_root() -> Path:
    return Path(__file__).resolve().parents[3] / "samples"


def _sample_id_prefixes() -> frozenset[str]:
    global _SAMPLE_ID_PREFIXES
    if _SAMPLE_ID_PREFIXES is not None:
        return _SAMPLE_ID_PREFIXES
    prefixes: set[str] = set()
    root = _samples_root()
    for channel in ("teams", "zoho"):
        folder = root / channel
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sid = str(data.get("id") or path.stem)
            except (OSError, json.JSONDecodeError):
                sid = path.stem
            if sid:
                prefixes.add(sid)
    _SAMPLE_ID_PREFIXES = frozenset(prefixes)
    return _SAMPLE_ID_PREFIXES


def seed_database(db: Session) -> None:
    """Load stub seed leads. Used by tests only — not called on app startup or reset."""
    seed_path = _seed_path()
    with open(seed_path) as f:
        leads_data = json.load(f)

    repo = LeadRepository(db)
    for item in leads_data:
        if repo.get_by_lead_id(item["lead_id"]):
            continue
        repo.create(LeadCreate(**item))

    db.commit()


def _parse_inbound_blob(payload_json: str | None) -> tuple[dict, dict]:
    if not payload_json:
        return {}, {}
    try:
        stored = json.loads(payload_json)
    except json.JSONDecodeError:
        return {}, {}
    if not isinstance(stored, dict):
        return {}, {}
    inner = stored.get("payload") if isinstance(stored.get("payload"), dict) else {}
    return stored, inner


def _looks_like_sample_id(value: str) -> bool:
    if not value:
        return False
    for prefix in _sample_id_prefixes():
        if value == prefix or value.startswith(f"{prefix}-"):
            return True
    # event_id form: teams-teams-horizon-crm-xxxx / zoho-mail-zoho-nordic-billing-xxxx
    for prefix in _sample_id_prefixes():
        if prefix in value:
            return True
    return False


def _email_is_sample_domain(email: str) -> bool:
    """True for fictional *mail* domains used by sample/demo Zoho paths.

    Do NOT treat @teams.local as sample — live Teams bot leads use that suffix.
    Teams samples are detected via demo_origin / sample-ingress / sample-conv-*.
    """
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].lower().strip(">")
    # .example = fictional Zoho/sample mail; exclude teams.local (live bot identity)
    return domain.endswith(".example")


def is_sample_player_inbound(stored: dict, inner: dict, *, event_id: str = "") -> bool:
    """True if inbound payload was produced by the Scheduler sample player."""
    if inner.get("demo_origin") == SAMPLE_ORIGIN or stored.get("demo_origin") == SAMPLE_ORIGIN:
        return True
    if (inner.get("teams_channel") or "") == "sample-ingress":
        return True
    conv = str(inner.get("conversation_id") or "")
    if conv.startswith("sample-conv-"):
        return True
    for key in ("mail_message_id", "activity_id", "message_id"):
        if _looks_like_sample_id(str(inner.get(key) or "")):
            return True
    if _looks_like_sample_id(event_id) or _looks_like_sample_id(str(stored.get("event_id") or "")):
        return True
    mail_from = str(inner.get("mail_from") or inner.get("email") or "")
    if _email_is_sample_domain(mail_from):
        return True
    # Angle-addr: Name <user@domain.example>
    m = re.search(r"<([^>]+)>", mail_from)
    if m and _email_is_sample_domain(m.group(1)):
        return True
    return False


def is_sample_player_lead(db: Session, lead: Lead) -> bool:
    """A Teams/Zoho Mail lead created via sample ingress (not live bot/mail)."""
    if lead.source not in EXTERNAL_LEAD_SOURCES:
        return False

    # Scheduler admission demos use fixed LEAD-DEMO-* IDs
    if (lead.lead_id or "").startswith("LEAD-DEMO-"):
        return True

    # Fictional sample / demo mail domains are never live Zoho
    if lead.source == "Zoho Mail" and _email_is_sample_domain(lead.email or ""):
        return True

    runs = db.query(Run).filter(Run.lead_id == lead.lead_id).all()
    if not runs:
        if lead.source == "Teams" and (lead.email or "").endswith("@teams.local"):
            # Live Teams also uses @teams.local — require inbound markers when possible
            return False
        return False

    for run in runs:
        inbound = (
            db.query(InboundEvent).filter(InboundEvent.event_id == run.inbound_event_id).first()
            if run.inbound_event_id
            else None
        )
        if not inbound:
            continue
        stored, inner = _parse_inbound_blob(inbound.payload_json)
        if is_sample_player_inbound(stored, inner, event_id=inbound.event_id):
            return True
    return False


def reset_demo(db: Session) -> None:
    """
    Clear simulator / stub / sample-player data while preserving real live
    Zoho Mail and Teams bot leads, runs, inbound events, queue messages, and
    runtime events. Does not re-seed stub leads.
    """
    candidates = (
        db.query(Lead).filter(Lead.source.in_(list(EXTERNAL_LEAD_SOURCES))).all()
    )
    preserve_lead_ids = {
        lead.lead_id for lead in candidates if not is_sample_player_lead(db, lead)
    }

    preserve_runs = (
        db.query(Run.run_id, Run.inbound_event_id)
        .filter(Run.lead_id.in_(preserve_lead_ids))
        .all()
        if preserve_lead_ids
        else []
    )
    preserve_run_ids = {row[0] for row in preserve_runs}
    preserve_inbound_ids = {row[1] for row in preserve_runs if row[1]}

    if preserve_run_ids:
        db.query(RuntimeEvent).filter(
            (RuntimeEvent.run_id.is_(None)) | (~RuntimeEvent.run_id.in_(preserve_run_ids))
        ).delete(synchronize_session=False)
        db.query(QueueMessage).filter(~QueueMessage.run_id.in_(preserve_run_ids)).delete(
            synchronize_session=False
        )
        db.query(JournalTurn).filter(~JournalTurn.run_id.in_(preserve_run_ids)).delete(
            synchronize_session=False
        )
        db.query(Finding).filter(~Finding.run_id.in_(preserve_run_ids)).delete(
            synchronize_session=False
        )
        db.query(Run).filter(~Run.run_id.in_(preserve_run_ids)).delete(synchronize_session=False)
    else:
        db.query(RuntimeEvent).delete()
        db.query(QueueMessage).delete()
        db.query(JournalTurn).delete()
        db.query(Finding).delete()
        db.query(Run).delete()

    if preserve_inbound_ids:
        db.query(InboundEvent).filter(~InboundEvent.event_id.in_(preserve_inbound_ids)).delete(
            synchronize_session=False
        )
    else:
        db.query(InboundEvent).delete()

    if preserve_lead_ids:
        db.query(Lead).filter(~Lead.lead_id.in_(preserve_lead_ids)).delete(synchronize_session=False)
    else:
        db.query(Lead).delete()

    db.commit()


def init_and_seed() -> None:
    init_db()
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

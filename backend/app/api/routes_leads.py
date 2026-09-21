from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.base import LeadRepository
from app.schemas import LeadCreate, LeadResponse

router = APIRouter(prefix="/api/v1", tags=["leads"])


@router.get("/leads", response_model=list[LeadResponse])
def list_leads(tenant_id: str | None = None, db: Session = Depends(get_db)):
    repo = LeadRepository(db)
    result = []
    for lead in repo.list_leads(tenant_id):
        active = repo.get_active_run_for_lead(lead.lead_id)
        latest = repo.get_latest_run_for_lead(lead.lead_id)
        item = LeadResponse.model_validate(lead)
        item.active_run_id = active.run_id if active else None
        item.latest_run_id = latest.run_id if latest else None
        result.append(item)
    return result


@router.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    repo = LeadRepository(db)
    lead = repo.get_by_lead_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    active = repo.get_active_run_for_lead(lead_id)
    latest = repo.get_latest_run_for_lead(lead_id)
    item = LeadResponse.model_validate(lead)
    item.active_run_id = active.run_id if active else None
    item.latest_run_id = latest.run_id if latest else None
    return item


@router.post("/leads", response_model=LeadResponse)
def create_lead(data: LeadCreate, db: Session = Depends(get_db)):
    repo = LeadRepository(db)
    lead = repo.create(data)
    db.commit()
    return LeadResponse.model_validate(lead)

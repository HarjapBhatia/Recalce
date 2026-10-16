"""
app/api/routes/public.py

Public endpoints for the landing page.
Provides platform statistics and recent anonymized reconciliation events.
"""

import random

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.db.session import get_db
from app.models.organization import Organization
from app.models.reconciliation_result import ReconciliationResult
from app.models.reconciliation_batch import ReconciliationBatch

router = APIRouter(prefix="/public", tags=["public"])

@router.get("/platform-stats")
def get_platform_stats(db: Session = Depends(get_db)):
    """Return aggregated platform statistics for the landing page."""
    # Active tenants count
    active_tenants = db.scalar(
        select(func.count(Organization.id))
        .where(Organization.is_active == True)
    ) or 0

    # Total transactions processed (measured by total number of internal and bank records matched/unreconciled)
    total_transactions = db.scalar(
        select(func.count(ReconciliationResult.id))
    ) or 0

    # Match rate (percentage of MATCHED results out of total)
    matched_count = db.scalar(
        select(func.count(ReconciliationResult.id))
        .where(ReconciliationResult.status == 'MATCHED')
    ) or 0
    
    match_rate = 0.0
    if total_transactions > 0:
        match_rate = (matched_count / total_transactions) * 100.0

    # Average processing time
    # Average difference between processing_completed_at and processing_started_at in milliseconds
    avg_processing_interval = db.scalar(
        select(func.avg(ReconciliationBatch.processing_completed_at - ReconciliationBatch.processing_started_at))
        .where(ReconciliationBatch.processing_completed_at.is_not(None))
        .where(ReconciliationBatch.processing_started_at.is_not(None))
    )
    
    avg_processing_time_ms = 0
    if avg_processing_interval is not None:
        avg_processing_time_ms = int(avg_processing_interval.total_seconds() * 1000)

    return {
        "active_tenants": active_tenants,
        "total_transactions": total_transactions,
        "match_rate": round(match_rate, 1),
        "processing_time_ms": avg_processing_time_ms
    }

@router.get("/recent-events")
def get_recent_events(db: Session = Depends(get_db)):
    """Return a diverse, shuffled mix of recent reconciliation results for the terminal feed."""
    # Fetch some matched
    matched = db.execute(
        select(ReconciliationResult)
        .where(ReconciliationResult.status == 'MATCHED')
        .order_by(ReconciliationResult.created_at.desc())
        .limit(10)
    ).scalars().all()
    
    # Fetch some anomalies/under review
    review = db.execute(
        select(ReconciliationResult)
        .where(ReconciliationResult.status == 'UNDER_REVIEW')
        .order_by(ReconciliationResult.created_at.desc())
        .limit(5)
    ).scalars().all()
    
    # Fetch some unreconciled
    unreconciled = db.execute(
        select(ReconciliationResult)
        .where(ReconciliationResult.status == 'UNRECONCILED')
        .order_by(ReconciliationResult.created_at.desc())
        .limit(5)
    ).scalars().all()
    
    results = list(matched) + list(review) + list(unreconciled)
    
    # If the DB doesn't have a good mix yet, just pull whatever is latest to fill out to 20
    if len(results) < 20:
        extra = db.execute(
            select(ReconciliationResult)
            .order_by(ReconciliationResult.created_at.desc())
            .limit(20 - len(results))
        ).scalars().all()
        results.extend(extra)
        
    random.shuffle(results)
    
    events = []
    for r in results:
        match_type = r.match_type.value if r.match_type else "UNKNOWN"
        events.append({
            "id": str(r.id),
            "timestamp": r.created_at.isoformat(),
            "status": r.status.value,
            "match_type": match_type,
            "is_anomaly": r.is_anomaly
        })
        
    return events

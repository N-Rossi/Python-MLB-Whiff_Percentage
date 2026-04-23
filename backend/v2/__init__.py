"""
v2 API — endpoints built on the Phase 1 derived tables.

Legacy endpoints (first-pitch offspeed report) stay untouched in `backend.main`.
"""

from fastapi import APIRouter

from backend.v2.lookups import router as lookups_router
from backend.v2.sequences import router as sequences_router
from backend.v2.matchup import router as matchup_router

router = APIRouter(prefix="/api/v2", tags=["v2"])
router.include_router(lookups_router)
router.include_router(sequences_router)
router.include_router(matchup_router)

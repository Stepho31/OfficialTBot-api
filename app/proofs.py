from fastapi import APIRouter

router = APIRouter(prefix="/proofs", tags=["proofs"])

@router.get("/daily/latest")
def latest_daily():
    return {"date": None, "hash": None, "signature": None, "public_key": None, "ipfs_cid": None}

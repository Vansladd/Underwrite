from fastapi import APIRouter, HTTPException, Response, status

from app.services.storage import LocalStorage, StorageDep

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{key:path}")
async def get_document(key: str, storage: StorageDep) -> Response:
    # Dev-only: prod serves S3 presigned URLs directly and never reaches this route.
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        data = storage.read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND) from None
    return Response(content=data, media_type="application/pdf")

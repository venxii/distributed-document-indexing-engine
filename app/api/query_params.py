from fastapi import HTTPException


def normalize_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Search query cannot be blank")
    return normalized

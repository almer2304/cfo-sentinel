from fastapi import Header, HTTPException, status
from core.database import verify_session_token

async def get_current_user(
    authorization: str = Header(None)
) -> dict:
    """
    Middleware untuk verifikasi token dari header.
    Frontend kirim: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak ditemukan. Silakan login.",
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Format token tidak valid.",
        )

    token = parts[1]
    user = verify_session_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau sudah expired. "
                   "Silakan login kembali.",
        )

    return user

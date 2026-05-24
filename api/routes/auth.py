from fastapi import APIRouter, HTTPException, Depends, status
from api.models.request import LoginRequest, RegisterRequest
from api.models.response import TokenResponse, UserData, BaseResponse
from api.middleware.auth import get_current_user
from core.database import (
    create_user, verify_login,
    create_session_token, delete_session_token,
    get_user_stats,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login user dan return session token."""
    user = verify_login(request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah.",
        )

    token = create_session_token(user["id"])
    stats = get_user_stats(user["id"])

    return TokenResponse(
        success=True,
        token=token,
        user=UserData(
            id=user["id"],
            business_name=user["business_name"],
            email=user["email"],
            business_type=user["business_type"],
            total_sessions=stats.get("total_sessions", 0),
            avg_health_score=stats.get("avg_health", 0),
        ),
    )


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Daftar user baru."""
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password minimal 6 karakter.",
        )

    user = create_user(
        business_name=request.business_name,
        email=request.email,
        password=request.password,
        business_type=request.business_type,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email sudah terdaftar.",
        )

    token = create_session_token(user["id"])

    # Simpan saldo awal sebagai transaksi pertama jika > 0
    if request.initial_cash_balance > 0:
        from core.database_new import save_transaction_simple
        from core.database import get_connection
        
        # Simpan secara manual jurnal 'Modal Awal'
        tx = save_transaction_simple(
            user_id=user["id"],
            raw_input=f"Saldo Awal saat pendaftaran: Rp {request.initial_cash_balance:,.0f}",
            notes="Opening Balance (Auto-generated from Register)"
        )
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE transactions 
            SET amount = ?, type = 'income', category = 'Modal',
                debit_account = 'Kas', credit_account = 'Modal Pemilik',
                agent_classified = 1
            WHERE transaction_code = ?
        """, (request.initial_cash_balance, tx["transaction_code"]))
        conn.commit()
        conn.close()

    return TokenResponse(
        success=True,
        token=token,
        user=UserData(
            id=user["id"],
            business_name=user["business_name"],
            email=user["email"],
            business_type=user["business_type"],
            total_sessions=0,
            avg_health_score=0,
        ),
    )


@router.post("/logout", response_model=BaseResponse)
async def logout(
    current_user: dict = Depends(get_current_user)
):
    """Logout dan invalidate token."""
    delete_session_token(current_user["id"])
    return BaseResponse(success=True, message="Berhasil logout.")


@router.get("/me", response_model=UserData)
async def get_me(
    current_user: dict = Depends(get_current_user)
):
    """Ambil data user yang sedang login."""
    stats = get_user_stats(current_user["id"])
    return UserData(
        id=current_user["id"],
        business_name=current_user["business_name"],
        email=current_user["email"],
        business_type=current_user["business_type"],
        total_sessions=stats.get("total_sessions", 0),
        avg_health_score=stats.get("avg_health", 0),
    )

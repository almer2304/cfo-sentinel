"""
dashboard/auth.py
CFO Sentinel — Authentication UI Layer

Handles login/register forms and session management.
Uses st.query_params for persistent session tokens that survive browser refresh.
"""

import streamlit as st
from core.database import (
    create_user, verify_login, get_user_stats,
    create_session_token, verify_session_token,
    delete_session_token
)


def render_auth_page() -> bool:
    """
    Cek session dari query params terlebih dahulu.
    Jika ada token valid → auto login tanpa tampilkan form.
    Jika tidak ada → tampilkan form login.
    Return True jika sudah login.
    """
    # Cek apakah sudah login di session_state
    if st.session_state.get("logged_in"):
        return True

    # Coba auto-login dari token di query params
    params = st.query_params
    token = params.get("session_token", "")

    if token:
        user = verify_session_token(token)
        if user:
            # Auto login berhasil
            _set_session(user)
            return True
        else:
            # Token tidak valid — hapus dari URL
            st.query_params.clear()

    # Tidak ada token valid → tampilkan form login
    _render_login_register_form()
    return False


def _set_session(user: dict):
    """Set semua session state setelah login berhasil."""
    st.session_state["logged_in"]          = True
    st.session_state["user_id"]            = user["id"]
    st.session_state["user_name"]          = user["business_name"]
    st.session_state["user_email"]         = user["email"]
    st.session_state["user_business_type"] = user.get(
        "business_type", "general"
    )
    st.session_state["user"]               = user


def _render_login_register_form():
    """Render form login dan register."""
    # Header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align:center; padding:2rem 0 1rem'>
            <div style='font-size:56px'>🛡️</div>
            <h1 style='color:#dc2626;margin:0'>CFO Sentinel</h1>
            <p style='color:#9ca3af;margin:0'>
                AI Financial Advisor untuk UMKM Indonesia
            </p>
        </div>
        """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 Masuk", "✨ Daftar Gratis"])

    with tab_login:
        st.markdown("### Selamat Datang Kembali!")
        with st.form("form_login", clear_on_submit=False):
            email    = st.text_input("Email",
                         placeholder="email@bisniskamu.com")
            password = st.text_input("Password",
                         type="password", placeholder="••••••••")
            submit   = st.form_submit_button(
                "🔑 Masuk",
                use_container_width=True,
                type="primary"
            )

        if submit:
            if not email or not password:
                st.error("Email dan password wajib diisi.")
            else:
                with st.spinner("Memverifikasi..."):
                    user = verify_login(email, password)
                if user:
                    _set_session(user)
                    # Simpan token ke URL
                    token = create_session_token(user["id"])
                    st.query_params["session_token"] = token
                    st.success(
                        f"Selamat datang, **{user['business_name']}**!"
                    )
                    st.rerun()
                else:
                    st.error("Email atau password salah.")

        st.caption(
            "Demo: email **demo@cfosentinel.id** "
            "/ password **demo1234**"
        )

    with tab_register:
        BUSINESS_TYPES = {
            "kuliner": "🍜 Kuliner",
            "fashion": "👗 Fashion",
            "jasa":    "🛠️ Jasa",
            "retail":  "🛒 Retail",
            "general": "🏢 Lainnya",
        }

        st.markdown("### Mulai Gratis Sekarang!")
        with st.form("form_register", clear_on_submit=False):
            business_name = st.text_input(
                "Nama Bisnis *",
                placeholder="Contoh: Warung Makan Bu Sari"
            )
            business_type = st.selectbox(
                "Jenis Bisnis *",
                options=list(BUSINESS_TYPES.keys()),
                format_func=lambda x: BUSINESS_TYPES[x]
            )
            email = st.text_input(
                "Email *",
                placeholder="email@bisniskamu.com"
            )
            col1, col2 = st.columns(2)
            with col1:
                password = st.text_input(
                    "Password *", type="password",
                    placeholder="Min. 6 karakter"
                )
            with col2:
                confirm = st.text_input(
                    "Ulangi Password *", type="password"
                )
            agree = st.checkbox(
                "Saya mengerti analisis ini bersifat estimasi."
            )
            submit = st.form_submit_button(
                "✨ Daftar Gratis",
                use_container_width=True,
                type="primary"
            )

        if submit:
            errors = []
            if not business_name:
                errors.append("Nama bisnis wajib diisi.")
            if not email or "@" not in email:
                errors.append("Email tidak valid.")
            if len(password) < 6:
                errors.append("Password minimal 6 karakter.")
            if password != confirm:
                errors.append("Password tidak cocok.")
            if not agree:
                errors.append("Centang persetujuan dulu.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                with st.spinner("Membuat akun..."):
                    user = create_user(
                        business_name=business_name,
                        email=email,
                        password=password,
                        business_type=business_type,
                    )
                if user:
                    _set_session(user)
                    token = create_session_token(user["id"])
                    st.query_params["session_token"] = token
                    st.success(
                        f"Akun **{business_name}** berhasil dibuat!"
                    )
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Email sudah terdaftar.")


def render_user_sidebar(user: dict):
    """Render user info and logout button in sidebar."""
    user_id = user.get("id") or st.session_state.get("user_id")
    name    = user.get("business_name") or \
              st.session_state.get("user_name", "User")

    st.sidebar.markdown(f"**👤 {name}**")

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        # Hapus token dari database
        if user_id:
            delete_session_token(user_id)
        # Hapus query params
        st.query_params.clear()
        # Hapus session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# Keep backward compatibility — alias for old function name
def render_user_greeting():
    """Render greeting di sidebar (backward compatible wrapper)."""
    user = st.session_state.get("user", {})
    if not user:
        user = {
            "id": st.session_state.get("user_id"),
            "business_name": st.session_state.get("user_name", "User"),
        }
    render_user_sidebar(user)

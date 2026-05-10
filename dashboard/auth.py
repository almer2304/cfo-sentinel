"""
dashboard/auth.py
CFO Sentinel — Authentication UI Layer

Handles login/register forms and session management.
"""

import streamlit as st
from core.database import create_user, verify_login, get_user_stats


def render_auth_page():
    """Render halaman login/register. Return True jika sudah logged in."""
    if st.session_state.get("logged_in"):
        return True

    st.markdown(
        """
        <div style="text-align:center; margin-bottom:2rem;">
            <h1>🛡️ CFO Sentinel</h1>
            <p style="color:#888;">AI-Powered Financial Advisor untuk UMKM</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["🔑 Login", "📝 Daftar Baru"])

    with tab_login:
        _render_login()

    with tab_register:
        _render_register()

    return False


def _render_login():
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", placeholder="email@bisnis.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(
            "🔑 Masuk", use_container_width=True, type="primary"
        )

    if submitted:
        if not email or not password:
            st.warning("Isi email dan password.")
            return
        user = verify_login(email, password)
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user["id"]
            st.session_state["user_name"] = user["business_name"]
            st.session_state["user_email"] = user["email"]
            st.session_state["user_business_type"] = user.get(
                "business_type", "general"
            )
            st.success(f"Selamat datang, {user['business_name']}! 🎉")
            st.rerun()
        else:
            st.error("❌ Email atau password salah.")


def _render_register():
    with st.form("register_form", clear_on_submit=False):
        biz_name = st.text_input(
            "Nama Bisnis", placeholder="Warung Makan Barokah"
        )
        email = st.text_input(
            "Email", placeholder="email@bisnis.com", key="reg_email"
        )
        password = st.text_input(
            "Password", type="password", key="reg_pass",
            help="Minimal 6 karakter"
        )
        password2 = st.text_input(
            "Ulangi Password", type="password", key="reg_pass2"
        )
        biz_type = st.selectbox(
            "Jenis Bisnis",
            ["general", "kuliner", "fashion", "jasa", "retail"],
            format_func=lambda x: {
                "general": "Umum", "kuliner": "Kuliner / F&B",
                "fashion": "Fashion", "jasa": "Jasa",
                "retail": "Retail",
            }.get(x, x),
        )
        submitted = st.form_submit_button(
            "📝 Daftar", use_container_width=True
        )

    if submitted:
        if not biz_name or not email or not password:
            st.warning("Semua field wajib diisi.")
            return
        if len(password) < 6:
            st.warning("Password minimal 6 karakter.")
            return
        if password != password2:
            st.warning("Password tidak cocok.")
            return

        user = create_user(biz_name, email, password, biz_type)
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user["id"]
            st.session_state["user_name"] = user["business_name"]
            st.session_state["user_email"] = user["email"]
            st.session_state["user_business_type"] = user.get(
                "business_type", "general"
            )
            st.success("✅ Akun berhasil dibuat! Selamat datang! 🎉")
            st.rerun()
        else:
            st.error("❌ Email sudah terdaftar. Silakan login.")


def render_user_greeting():
    """Render greeting di sidebar."""
    name = st.session_state.get("user_name", "User")
    user_id = st.session_state.get("user_id")
    st.sidebar.markdown(f"### 👋 Halo, **{name}**!")

    if user_id:
        stats = get_user_stats(user_id)
        if stats["total_sessions"] > 0:
            st.sidebar.caption(
                f"📊 Total analisis: {stats['total_sessions']} | "
                f"Avg Health: {stats['avg_health']}/100"
            )

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

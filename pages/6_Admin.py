import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import (verificar_login, barra_superior, solo_admin,
                  listar_usuarios, cambiar_rol, eliminar_usuario,
                  contar_por_rol, MAX_ADMINS, MAX_USUARIOS,
                  _guardar_usuarios, _cargar_usuarios, _hash)

st.set_page_config(page_title="Admin", page_icon="🔧", layout="wide")
verificar_login()
barra_superior()
solo_admin()

st.markdown("## 🔧 Panel de Administración")
st.caption("Gestión de usuarios del sistema. Solo visible para administradores.")
st.markdown("---")

usuarios = listar_usuarios()
n_admins, n_usuarios = contar_por_rol()

# ── Métricas ──────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Administradores", f"{n_admins} / {MAX_ADMINS}")
c2.metric("Usuarios", f"{n_usuarios} / {MAX_USUARIOS}")
c3.metric("Total cuentas", len(usuarios))

st.markdown("---")

# ── Tabla de usuarios ─────────────────────────────────────────────
st.markdown("### 👥 Usuarios registrados")

if not usuarios:
    st.info("No hay usuarios registrados aún.")
else:
    for uname, udata in usuarios.items():
        rol_actual = udata.get('rol', 'usuario')
        col_nom, col_rol, col_acc = st.columns([3, 2, 2])

        with col_nom:
            st.markdown(f"<div style='padding-top:8px;color:#f1f5f9;font-weight:500;'>"
                        f"👤 {udata.get('nombre','—')} <span style='color:#475569;font-size:.8rem;'>({uname})</span>"
                        f"</div>", unsafe_allow_html=True)

        with col_rol:
            nuevo_rol = st.selectbox(
                "Rol",
                ["admin", "usuario"],
                index=0 if rol_actual == "admin" else 1,
                key=f"rol_{uname}",
                label_visibility="collapsed",
            )
            if nuevo_rol != rol_actual:
                # Validar límites antes de cambiar
                n_a, n_u = contar_por_rol()
                puede = True
                if nuevo_rol == "admin" and n_a >= MAX_ADMINS:
                    st.error(f"Máximo {MAX_ADMINS} administradores.")
                    puede = False
                if nuevo_rol == "usuario" and n_u >= MAX_USUARIOS:
                    st.error(f"Máximo {MAX_USUARIOS} usuarios.")
                    puede = False
                if puede:
                    cambiar_rol(uname, nuevo_rol)
                    st.rerun()

        with col_acc:
            if st.button("🗑 Eliminar", key=f"del_{uname}"):
                eliminar_usuario(uname)
                st.rerun()

        st.divider()

# ── Crear usuario ─────────────────────────────────────────────────
st.markdown("### ➕ Crear usuario")

with st.expander("Nuevo usuario", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        nu_user = st.text_input("Usuario (login)", key="nu_user").strip().lower()
        nu_nombre = st.text_input("Nombre completo", key="nu_nombre").strip()
    with col2:
        nu_pwd = st.text_input("Contraseña", type="password", key="nu_pwd")
        nu_rol = st.selectbox("Rol", ["usuario", "admin"], key="nu_rol")

    if st.button("✅ Crear usuario", type="primary", key="btn_crear_usr"):
        if not nu_user or not nu_nombre or not nu_pwd:
            st.error("Completa todos los campos.")
        elif len(nu_pwd) < 6:
            st.error("La contraseña debe tener al menos 6 caracteres.")
        else:
            users = _cargar_usuarios()
            admin_users = st.secrets.get("usuarios", {})
            if nu_user in users or nu_user in admin_users:
                st.error("Ese usuario ya existe.")
            else:
                n_a, n_u = contar_por_rol()
                if nu_rol == "admin" and n_a >= MAX_ADMINS:
                    st.error(f"Máximo {MAX_ADMINS} administradores permitidos.")
                elif nu_rol == "usuario" and n_u >= MAX_USUARIOS:
                    st.error(f"Máximo {MAX_USUARIOS} usuarios permitidos.")
                else:
                    users[nu_user] = {
                        "nombre":   nu_nombre,
                        "password": _hash(nu_pwd),
                        "rol":      nu_rol,
                    }
                    _guardar_usuarios(users)
                    st.success(f"Usuario **{nu_nombre}** creado como **{nu_rol}**.")
                    st.rerun()

# ── Resumen de permisos ───────────────────────────────────────────
st.markdown("---")
st.markdown("### 📋 Resumen de permisos")
st.markdown("""
| Función | 👑 Admin | 👤 Usuario |
|---|---|---|
| Ver Inicio / Resumen | ✅ | ✅ |
| **Marcar pagos + recibos** | ✅ | ❌ |
| **Desmarcar pagos** | ✅ | ❌ |
| Ver Plan de Pagos | ✅ | ✅ |
| Cargar Plan de Pagos | ✅ | ✅ |
| Descargar Estado de Cuenta | ✅ | ✅ |
| Documentos adjuntos | ✅ | ✅ |
| Ver Reservas | ✅ | ✅ |
| **Agregar reservas** | ✅ | ❌ |
| **Eliminar reservas** | ✅ | ❌ |
| Descargar Reportes Excel | ✅ | ✅ |
| **Panel de Administración** | ✅ | ❌ |
""")

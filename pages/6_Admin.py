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
                    for k in ['nu_user', 'nu_nombre', 'nu_pwd']:
                        st.session_state.pop(k, None)
                    st.rerun()

# ── Llaves de la API ──────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🔑 Llaves para otras apps")
st.caption(
    "Otra aplicación usa la llave para subir PDF de contratos y anexos de pago. "
    "La llave completa se muestra una sola vez. Aquí solo queda el inicio, para reconocerla."
)

from api import claves as claves_api
from utils import _sb

if st.session_state.get("clave_nueva"):
    st.success("Copia esta llave ahora. No se vuelve a mostrar.")
    st.code(st.session_state["clave_nueva"], language=None)
    if st.button("Ya la copié", key="clave_copiada"):
        st.session_state.pop("clave_nueva", None)
        st.rerun()

with st.expander("Generar una llave", expanded=False):
    etiq = st.text_input("Nombre de la app que se va a conectar", key="etiq_clave").strip()
    if st.button("Generar llave", type="primary", key="btn_clave"):
        if not etiq:
            st.error("Ponle un nombre para saber de qué app es.")
        else:
            st.session_state["clave_nueva"] = claves_api.crear(
                _sb(), etiq, st.session_state.get("usuario", "")
            )
            st.rerun()

claves = claves_api.listar(_sb())
if not claves:
    st.info("Todavía no hay llaves.")
else:
    for c in claves:
        col_a, col_b = st.columns([4, 1])
        estado = "activa" if c.get("activa") else "revocada"
        with col_a:
            st.markdown(
                f"**{c.get('etiqueta', '—')}** · `{c.get('prefijo', '')}…` · {estado}"
            )
            st.caption(f"Último uso: {c.get('ultimo_uso') or 'nunca'}")
        with col_b:
            if c.get("activa") and st.button("Revocar", key=f"rev_{c['id']}"):
                claves_api.revocar(_sb(), c["id"])
                st.rerun()

with st.expander("Crear la tabla en Supabase (una vez)"):
    st.markdown(
        "Hoy las llaves se guardan en el bucket privado, archivo `sistema/api_claves.json`, "
        "porque la tabla `api_claves` todavía no está creada. Cuando pegues este SQL en "
        "Supabase → SQL Editor, la app pasa a usar la tabla sola. Las llaves ya creadas "
        "en el archivo no se copian: genera una nueva después de crear la tabla."
    )
    st.code(
        """CREATE TABLE IF NOT EXISTS api_claves (
    id          TEXT PRIMARY KEY,
    etiqueta    TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,
    prefijo     TEXT NOT NULL,
    activa      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_por  TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    ultimo_uso  TIMESTAMPTZ
);
ALTER TABLE api_claves DISABLE ROW LEVEL SECURITY;""",
        language="sql",
    )

# ── Resumen de permisos ───────────────────────────────────────────
st.markdown("---")
st.markdown("### 📋 Resumen de permisos")
st.markdown("""
| Función | 👑 Admin | 👤 Usuario |
|---|---|---|
| Ver Inicio / Resumen | ✅ | ✅ |
| **Marcar pagos** | ✅ | ❌ |
| **Desmarcar pagos** | ✅ | ❌ |
| Descargar recibos emitidos | ✅ | ✅ |
| Ver Plan de Pagos | ✅ | ✅ |
| Cargar Plan de Pagos | ✅ | ✅ |
| Descargar Estado de Cuenta | ✅ | ✅ |
| Documentos adjuntos | ✅ | ✅ |
| Ver Reservas | ✅ | ✅ |
| **Agregar reservas** | ✅ | ❌ |
| **Eliminar reservas** | ✅ | ❌ |
| Descargar Reportes Excel | ✅ | ✅ |
| **Panel de Administración** | ✅ | ❌ |
| **Llaves de la API** | ✅ | ❌ |
""")

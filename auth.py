import streamlit as st
import json
import hashlib
import base64
from pathlib import Path
import extra_streamlit_components as stx

_LOGOS = {
    "riviera_park_2":    "logo_b64.txt",
    "villas_del_bosque": "logo_villas_b64.txt",
}

def _logo_b64():
    pid  = st.session_state.get("proyecto", "riviera_park_2")
    fname = _LOGOS.get(pid, "logo_b64.txt")
    p = Path(__file__).parent / fname
    if p.exists():
        return p.read_text().strip()
    # fallback al logo por defecto
    p2 = Path(__file__).parent / "logo_b64.txt"
    return p2.read_text().strip() if p2.exists() else ""

_COOKIE_NAME = "rp2_session"
_COOKIE_DAYS = 30

def _cookie_manager():
    return stx.CookieManager(key="cm")

def _get_sb():
    from supabase import create_client
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["service_key"])

def _cargar_usuarios():
    try:
        rows = _get_sb().table('usuarios').select('*').execute().data
        return {r['username']: {'nombre': r['nombre'], 'password': r['password_hash'], 'rol': r['rol']} for r in rows}
    except Exception:
        return {}

def _guardar_usuarios(usuarios: dict):
    sb = _get_sb()
    for username, data in usuarios.items():
        existing = sb.table('usuarios').select('id').eq('username', username).execute().data
        if existing:
            sb.table('usuarios').update({
                'nombre': data['nombre'], 'password_hash': data['password'], 'rol': data.get('rol','usuario')
            }).eq('username', username).execute()
        else:
            sb.table('usuarios').insert({
                'username': username, 'nombre': data['nombre'],
                'password_hash': data['password'], 'rol': data.get('rol','usuario')
            }).execute()

def _hash(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def _verificar(usuario, password):
    # Supabase primero (permite cambio de contraseña)
    usuarios = _cargar_usuarios()
    if usuario in usuarios:
        u = usuarios[usuario]
        if u["password"] == _hash(password):
            return u["nombre"], u.get("rol", "usuario")
    # Fallback a secrets (usuarios hardcoded)
    admin = st.secrets.get("usuarios", {}).get(usuario)
    if admin and admin["password"] == password:
        return admin["nombre"], admin["rol"]
    return None, None

def _restaurar_desde_cookie():
    """Intenta recuperar sesión desde cookie. Retorna True si tuvo éxito."""
    if st.session_state.get("autenticado"):
        return True
    try:
        cm = _cookie_manager()
        valor = cm.get(_COOKIE_NAME)
        if valor and "|" in valor:
            usuario, nombre, rol = valor.split("|", 2)
            st.session_state.autenticado = True
            st.session_state.usuario     = usuario
            st.session_state.nombre      = nombre
            st.session_state.rol         = rol
            return True
    except Exception:
        pass
    return False

def _guardar_cookie(usuario, nombre, rol):
    try:
        cm = _cookie_manager()
        cm.set(_COOKIE_NAME, f"{usuario}|{nombre}|{rol}",
               max_age=_COOKIE_DAYS * 86400)
    except Exception:
        pass

def _borrar_cookie():
    try:
        cm = _cookie_manager()
        cm.delete(_COOKIE_NAME)
    except Exception:
        pass

def login():
    # Intentar restaurar sesión desde cookie antes de mostrar el formulario
    if _restaurar_desde_cookie():
        st.rerun()
        return

    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style='text-align:center; padding:60px 0 20px'>
        <div style='font-size:2.8rem; margin-bottom:8px;'>🏗</div>
        <h1 style='font-size:2rem; font-weight:800; letter-spacing:-.02em; margin:0;'>
            ConstruLab
        </h1>
        <p style='color:#64748b; font-size:1rem; margin-top:6px;'>
            Control de Abonos de Proyectos
        </p>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 1.2, 1])[1]
    with col:
        tab_in, tab_reg = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with tab_in:
            with st.form("login"):
                usuario  = st.text_input("Usuario").strip().lower()
                password = st.text_input("Contraseña", type="password")
                entrar   = st.form_submit_button("Entrar", use_container_width=True)
            if entrar:
                nombre, rol = _verificar(usuario, password)
                if nombre:
                    st.session_state.autenticado = True
                    st.session_state.usuario     = usuario
                    st.session_state.nombre      = nombre
                    st.session_state.rol         = rol
                    _guardar_cookie(usuario, nombre, rol)
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

        with tab_reg:
            with st.form("registro"):
                st.markdown("**Crea tu cuenta**")
                nuevo_usuario = st.text_input("Elige un usuario").strip().lower()
                nuevo_nombre  = st.text_input("Tu nombre completo").strip()
                nueva_pwd     = st.text_input("Contraseña", type="password")
                confirmar_pwd = st.text_input("Confirmar contraseña", type="password")
                registrar     = st.form_submit_button("Crear cuenta", use_container_width=True)

            if registrar:
                if not nuevo_usuario or not nuevo_nombre or not nueva_pwd:
                    st.error("Completa todos los campos.")
                elif nueva_pwd != confirmar_pwd:
                    st.error("Las contraseñas no coinciden.")
                elif len(nueva_pwd) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                else:
                    admin_users = st.secrets.get("usuarios", {})
                    existentes  = _cargar_usuarios()
                    if nuevo_usuario in admin_users or nuevo_usuario in existentes:
                        st.error("Ese usuario ya existe.")
                    else:
                        existentes[nuevo_usuario] = {
                            "nombre":   nuevo_nombre,
                            "password": _hash(nueva_pwd),
                            "rol":      "usuario"
                        }
                        _guardar_usuarios(existentes)
                        st.success(f"Cuenta creada. Ya puedes iniciar sesión, {nuevo_nombre}.")

# Proyectos disponibles: {id: nombre_display}
PROYECTOS = {
    "riviera_park_2":    "🏢 Riviera Park II — Fase 2",
    "villas_del_bosque": "🌳 Villas del Bosque",
}


def seleccionar_proyecto():
    """Pantalla de selección de proyecto tras el login."""
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style='text-align:center; padding:40px 0 30px'>
        <div style='font-size:2.4rem; margin-bottom:6px;'>🏗</div>
        <h1 style='font-size:1.8rem; font-weight:800; margin:0;'>ConstruLab</h1>
        <p style='color:#64748b; font-size:.95rem; margin-top:6px;'>
            Selecciona el proyecto al que deseas acceder
        </p>
    </div>
    <div style='text-align:center; color:#94a3b8; margin-bottom:20px;'>
        Bienvenido, <strong style='color:#f1f5f9;'>{st.session_state.get('nombre','')}</strong>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 1.2, 1])[1]
    with col:
        for pid, pnombre in PROYECTOS.items():
            if st.button(pnombre, use_container_width=True, key=f"proj_{pid}",
                         type="primary" if pid == "riviera_park_2" else "secondary"):
                st.session_state.proyecto = pid
                st.rerun()
        st.markdown("---")
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            cerrar_sesion()


MAX_ADMINS  = 4
MAX_USUARIOS = 4

def solo_admin():
    """Bloquea la página si el usuario no es admin."""
    if st.session_state.get('rol') != 'admin':
        st.error("🔒 Acceso restringido — solo administradores.")
        st.stop()

def contar_por_rol():
    """Retorna (n_admins, n_usuarios) de usuarios en usuarios.json."""
    users = _cargar_usuarios()
    admins   = sum(1 for u in users.values() if u.get('rol') == 'admin')
    usuarios = sum(1 for u in users.values() if u.get('rol') != 'admin')
    return admins, usuarios

def listar_usuarios():
    return _cargar_usuarios()

def cambiar_rol(username, nuevo_rol):
    users = _cargar_usuarios()
    if username in users:
        users[username]['rol'] = nuevo_rol
        _guardar_usuarios(users)

def eliminar_usuario(username):
    try:
        _get_sb().table('usuarios').delete().eq('username', username).execute()
    except Exception:
        pass

def verificar_login():
    if not _restaurar_desde_cookie():
        login()
        st.stop()
    # Autenticado pero sin proyecto seleccionado
    if not st.session_state.get('proyecto'):
        seleccionar_proyecto()
        st.stop()

def cerrar_sesion():
    _borrar_cookie()
    st.session_state.autenticado = False
    st.session_state.pop('proyecto', None)
    st.rerun()

def barra_superior():
    logo = _logo_b64()
    nome = st.session_state.get('nombre', '')

    st.markdown(f"""
    <style>
    /* ── Global background ───────────────────────────────── */
    .stApp {{ background: #0f1117; }}
    .main .block-container {{ padding-top: 1.5rem; max-width: 100%; }}

    /* ── Sidebar ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        background: #000000 !important;
        border-right: 1px solid #111;
        min-width: 220px !important;
    }}
    [data-testid="stSidebar"] * {{ color: #94a3b8 !important; }}

    /* ── Sidebar buttons ─────────────────────────────────── */
    [data-testid="stSidebar"] .stButton > button {{
        background: transparent !important;
        border: 1px solid #1e2c45 !important;
        color: #64748b !important;
        border-radius: 6px;
        font-size: .82rem;
        font-weight: 500;
        width: 100%;
        text-align: left !important;
        padding: 6px 12px !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: #1a2540 !important;
        color: #e2e8f0 !important;
        border-color: #2a3a55 !important;
    }}

    /* ── Logo + brand ────────────────────────────────────── */
    [data-testid="stSidebarNav"] {{
        padding-top: 160px !important;
        position: relative;
    }}
    [data-testid="stSidebarNav"]::before {{
        content: "";
        position: absolute;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        width: 140px;
        height: 140px;
        background: url("data:image/png;base64,{logo}") center/contain no-repeat;
        display: block;
    }}

    /* ── Nav section label ───────────────────────────────── */
    [data-testid="stSidebarNav"] li:first-child::before {{
        content: "PANEL DE CONTROL";
        display: block;
        font-size: .52rem;
        letter-spacing: .16em;
        color: #334155;
        padding: 0 14px 5px;
        font-weight: 700;
        text-transform: uppercase;
    }}

    /* ── Nav items ───────────────────────────────────────── */
    [data-testid="stSidebarNav"] ul {{ padding: 0 6px; list-style: none; }}
    [data-testid="stSidebarNav"] li {{ margin: 1px 0; }}
    [data-testid="stSidebarNav"] a {{
        border-radius: 6px;
        padding: 7px 14px !important;
        display: flex;
        align-items: center;
        transition: all .15s;
        border-left: 3px solid transparent;
    }}
    [data-testid="stSidebarNav"] a:hover {{
        background: #141f35 !important;
        border-left-color: #2a3a55;
    }}
    [data-testid="stSidebarNav"] a[aria-selected="true"] {{
        background: #141f35 !important;
        border-left-color: #3b82f6 !important;
    }}
    [data-testid="stSidebarNav"] span {{
        color: #64748b !important;
        font-size: .83rem;
        font-weight: 500;
    }}
    [data-testid="stSidebarNav"] a[aria-selected="true"] span {{
        color: #e2e8f0 !important;
    }}

    /* ── Main typography ─────────────────────────────────── */
    h1, h2, h3 {{ color: #f1f5f9 !important; letter-spacing: -.01em; }}

    /* ── Dataframe ───────────────────────────────────────── */
    [data-testid="stDataFrame"] > div {{
        border-radius: 8px;
        border: 1px solid #1e2a3a !important;
        overflow: hidden;
    }}

    /* ── Inputs / selects ────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] > div > div > input,
    [data-testid="stNumberInput"] > div > div > input,
    [data-testid="stDateInput"] > div > div > input {{
        background: #1e2536 !important;
        border: 1px solid #2a3a50 !important;
        border-radius: 6px !important;
        color: #e2e8f0 !important;
    }}

    /* ── Tabs ────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        background: #131929;
        border-radius: 8px;
        padding: 4px;
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 6px !important;
        color: #64748b !important;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        background: #1e2a3a !important;
        color: #f1f5f9 !important;
    }}

    /* ── Expanders ───────────────────────────────────────── */
    [data-testid="stExpander"] {{
        border: 1px solid #1e2a3a !important;
        border-radius: 8px !important;
        background: #131929 !important;
    }}

    /* ── Primary button ──────────────────────────────────── */
    .stButton > button[kind="primary"] {{
        background: #2563eb !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        color: #fff !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: #1d4ed8 !important;
    }}

    /* ── Download button ─────────────────────────────────── */
    .stDownloadButton > button {{
        background: #1e2536 !important;
        border: 1px solid #2a3a50 !important;
        border-radius: 6px !important;
        color: #93c5fd !important;
        font-weight: 500 !important;
    }}
    .stDownloadButton > button:hover {{
        background: #253347 !important;
        border-color: #3b82f6 !important;
    }}

    /* ── Toggle, divider, captions ───────────────────────── */
    [data-testid="stToggle"] label {{ color: #64748b !important; }}
    hr {{ border-color: #1e2a3a !important; }}
    [data-testid="stCaptionContainer"] {{ color: #475569 !important; }}

    /* ── Radio buttons ───────────────────────────────────── */
    [data-testid="stRadio"] > div {{ gap: 0.5rem; }}
    [data-testid="stRadio"] label {{
        background: #1e2536;
        border: 1px solid #2a3a50;
        border-radius: 6px;
        padding: 4px 14px;
        color: #64748b !important;
        cursor: pointer;
    }}
    [data-testid="stRadio"] label:has(input:checked) {{
        background: #1e3a5f !important;
        border-color: #3b82f6 !important;
        color: #93c5fd !important;
    }}

    /* ── Alert boxes ─────────────────────────────────────── */
    [data-testid="stAlert"] {{
        border-radius: 8px !important;
        border-left-width: 4px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    # ── Top bar ───────────────────────────────────────────────────────────
    proyecto_label = PROYECTOS.get(st.session_state.get('proyecto',''), 'Control CPP')
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#0d1f3c,#132040);
                color:#e2e8f0; padding:10px 20px; border-radius:8px;
                margin-bottom:16px; display:flex;
                justify-content:space-between; align-items:center;
                border:1px solid #1e2c45;
                box-shadow:0 2px 8px rgba(0,0,0,.5);'>
        <span style='font-weight:800; font-size:1rem; letter-spacing:.03em; color:#f1f5f9;'>
            {proyecto_label}
        </span>
        <span style='font-size:.8rem; color:#64748b;'>
            👤 {nome}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar bottom: user info + cerrar sesion + CONSTRULAB ────────────
    with st.sidebar:
        st.markdown("<div style='margin-top:8px;border-top:1px solid #1a2235;padding-top:10px;'></div>",
                    unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:.75rem;color:#475569;padding:0 4px 6px;'>👤 {nome}</div>",
                    unsafe_allow_html=True)
        if st.button("🔄 Cambiar proyecto", key="_cambiar_proy", use_container_width=True):
            st.session_state.pop('proyecto', None)
            st.rerun()
        if st.button("Cerrar sesión", key="_cerrar_sb", use_container_width=True):
            cerrar_sesion()
        st.markdown("""
        <div style='margin-top:auto;padding:16px 4px 4px;text-align:center;'>
            <span style='font-size:.65rem;font-weight:800;letter-spacing:.18em;
                         color:#273040;text-transform:uppercase;'>CONSTRULAB</span>
        </div>""", unsafe_allow_html=True)

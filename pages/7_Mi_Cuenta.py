import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, _hash, _get_sb, _verificar

st.set_page_config(page_title="Mi Cuenta", page_icon="👤", layout="wide")
verificar_login()
barra_superior()

st.markdown("## 👤 Mi Cuenta")
st.markdown("---")

usuario = st.session_state.get('usuario', '')
nombre  = st.session_state.get('nombre', '')

st.markdown(f"**Usuario:** `{usuario}`")
st.markdown(f"**Nombre:** {nombre}")
st.markdown(f"**Rol:** {st.session_state.get('rol', '')}")

st.markdown("---")
st.markdown("### 🔑 Cambiar contraseña")

with st.form("cambiar_pwd"):
    pwd_actual  = st.text_input("Contraseña actual", type="password")
    pwd_nueva   = st.text_input("Nueva contraseña", type="password")
    pwd_confirm = st.text_input("Confirmar nueva contraseña", type="password")
    guardar     = st.form_submit_button("Guardar nueva contraseña", type="primary")

if guardar:
    if not pwd_actual or not pwd_nueva or not pwd_confirm:
        st.error("Completa todos los campos.")
    elif pwd_nueva != pwd_confirm:
        st.error("Las contraseñas nuevas no coinciden.")
    elif len(pwd_nueva) < 6:
        st.error("La contraseña debe tener al menos 6 caracteres.")
    else:
        # Verificar contraseña actual
        nombre_ver, _ = _verificar(usuario, pwd_actual)
        if not nombre_ver:
            st.error("La contraseña actual es incorrecta.")
        else:
            # Upsert en Supabase con nueva contraseña hasheada
            sb = _get_sb()
            existing = sb.table('usuarios').select('id').eq('username', usuario).execute().data
            if existing:
                sb.table('usuarios').update({
                    'password_hash': _hash(pwd_nueva)
                }).eq('username', usuario).execute()
            else:
                # Era usuario de secrets, lo creamos en Supabase
                sb.table('usuarios').insert({
                    'username':      usuario,
                    'nombre':        nombre,
                    'password_hash': _hash(pwd_nueva),
                    'rol':           st.session_state.get('rol', 'usuario'),
                }).execute()
            st.success("¡Contraseña actualizada correctamente!")

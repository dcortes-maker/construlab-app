import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import (_proyecto_db, listar_buzon, aprobar_propuesta,
                   descartar_propuesta)
import pandas as pd

st.set_page_config(page_title="Buzón", page_icon="📥", layout="wide")
verificar_login()
barra_superior()

propuestas = listar_buzon(_proyecto_db())

st.markdown(f"## 📥 Buzón{f' · {len(propuestas)}' if propuestas else ''}")
st.caption("Clientes que aparecen en las carpetas de Drive pero todavía no están en la app. "
           "Nada entra solo: aquí se revisa y se aprueba.")

st.markdown("---")

if not propuestas:
    st.success("No hay nada pendiente. Todo lo que está en Drive ya está en la app.")
    st.stop()

ES_ADMIN = st.session_state.get('rol') == 'admin'
if not ES_ADMIN:
    st.info("Solo el administrador puede aprobar. Esto es lo que hay pendiente:")

con_plan = [p for p in propuestas if p.get('legible')]
sin_plan = [p for p in propuestas if not p.get('legible')]

c1, c2 = st.columns(2)
c1.metric("Listos para aprobar", len(con_plan),
          help="La app pudo leer su plan de pagos completo.")
c2.metric("Hay que cargarlos a mano", len(sin_plan),
          help="Su anexo es una foto escaneada, o solo hay contrato. No hay texto que leer.")

# ─── Los que se pueden aprobar de una ───────────────────────────────
if con_plan:
    st.markdown("### ✅ Listos para aprobar")
    for p in con_plan:
        with st.expander(f"**{p['unidad']}** — {p['nombre']} · {len(p['cuotas'])} cuotas · "
                         f"${p['total']:,.2f}"):
            st.caption(f"Leído de «{p['archivo']}» · {p['origen']}")

            df = pd.DataFrame([{
                'Cuota': c['num_cuota'],
                'Descripción': c['desc'],
                'Vence': c['fecha_venc'],
                'Monto': float(c['monto'] or 0),
            } for c in p['cuotas']])
            st.dataframe(df.style.format({'Monto': '${:,.2f}'}),
                         use_container_width=True, hide_index=True)
            st.markdown(f"**Total del plan: ${p['total']:,.2f}**")

            if ES_ADMIN:
                st.caption("Corrige el apartamento o el nombre si la app los leyó mal.")
                a, b = st.columns(2)
                u = a.text_input("Apartamento", value=p['unidad'], key=f"u_{p['id']}")
                n = b.text_input("Cliente", value=p['nombre'], key=f"n_{p['id']}")

                x, y = st.columns(2)
                if x.button("✅ Aprobar y crear el plan", type="primary", key=f"ok_{p['id']}"):
                    res = aprobar_propuesta(p['id'], u, n, st.session_state.get('nombre', ''))
                    if res['ok']:
                        st.success(f"Plan de {res['nombre']} creado en {res['unidad']} "
                                   f"({res['creadas']} cuotas).")
                        st.rerun()
                    else:
                        st.error(res['motivo'])
                if y.button("Descartar", key=f"no_{p['id']}"):
                    descartar_propuesta(p['id'], st.session_state.get('nombre', ''))
                    st.rerun()

# ─── Los que no se pueden leer ──────────────────────────────────────
if sin_plan:
    st.markdown("### ⚠️ Hay que cargarlos a mano")
    st.caption("De estos no hay plan que leer: o su anexo está escaneado como foto, "
               "o en Drive solo aparece el contrato. La app los detectó para que no se "
               "queden olvidados.")

    st.dataframe(
        pd.DataFrame([{
            'Apto': p['unidad'],
            'Cliente': p['nombre'],
            'Qué hay en Drive': 'Contrato' if p['tipo'] == 'contrato' else 'Anexo (escaneado)',
            'Archivo': p['archivo'],
        } for p in sin_plan]),
        use_container_width=True, hide_index=True,
    )

    if ES_ADMIN:
        with st.expander("Quitar uno de la lista"):
            st.caption("Úsalo cuando ya lo cargaste a mano, o si ese cliente no va.")
            op = {f"{p['unidad']} — {p['nombre']}": p['id'] for p in sin_plan}
            sel = st.selectbox("¿Cuál quitas?", list(op.keys()), key="quitar")
            if st.button("Quitar del buzón"):
                descartar_propuesta(op[sel], st.session_state.get('nombre', ''))
                st.rerun()

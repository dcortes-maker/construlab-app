import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import (_proyecto_db, listar_buzon, aprobar_propuesta,
                   descartar_propuesta)
import pandas as pd

st.set_page_config(page_title="Buzón", page_icon="📥", layout="wide")

# Las mismas opciones que al cargar un plan a mano, para que no se escriban
# descripciones distintas según por dónde entró el cliente.
DESCS = ["Reserva", "Separación",
         "I Pago", "II Pago", "III Pago", "IV Pago", "V Pago",
         "VI Pago", "VII Pago", "VIII Pago", "IX Pago", "X Pago",
         "XI Pago", "XII Pago", "XIII Pago", "XIV Pago", "XV Pago",
         "XVI Pago", "XVII Pago", "XVIII Pago", "XIX Pago", "XX Pago",
         "Abono inicial", "Gasto Legal", "Gasto Manejo", "Bonificación", "Otro"]
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
                '#': c['num_cuota'],
                'Descripción': c['desc'],
                'Fecha Venc.': pd.to_datetime(c['fecha_venc'], errors='coerce'),
                'Monto ($)': float(c['monto'] or 0),
            } for c in p['cuotas']])

            if not ES_ADMIN:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.markdown(f"**Total del plan: ${p['total']:,.2f}**")
                continue

            st.caption("Revisa que esté todo bien. Puedes corregir cualquier celda, "
                       "agregar filas o borrarlas antes de aceptar.")
            a, b = st.columns(2)
            u = a.text_input("Apartamento", value=p['unidad'], key=f"u_{p['id']}")
            n = b.text_input("Cliente", value=p['nombre'], key=f"n_{p['id']}")

            editado = st.data_editor(
                df, use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    '#': st.column_config.NumberColumn('#', min_value=1, step=1, width="small"),
                    'Descripción': st.column_config.SelectboxColumn('Descripción', options=DESCS,
                                                                    width="medium"),
                    'Fecha Venc.': st.column_config.DateColumn('Fecha Venc.', format="DD/MM/YYYY"),
                    'Monto ($)': st.column_config.NumberColumn('Monto ($)', min_value=0.01,
                                                               format="$%.2f"),
                },
                key=f"ed_{p['id']}",
            )

            filas = []
            for _, row in editado.iterrows():
                if pd.isna(row['Monto ($)']) or float(row['Monto ($)']) <= 0:
                    continue
                fv = row['Fecha Venc.']
                filas.append({
                    'num_cuota': int(row['#']) if pd.notna(row['#']) else 1,
                    'desc': row['Descripción'] or 'Abono inicial',
                    'fecha_venc': fv.date().isoformat() if pd.notna(fv) else None,
                    'monto': float(row['Monto ($)']),
                })

            total_ed = sum(f['monto'] for f in filas)
            st.markdown(f"**{len(filas)} cuotas · Total: ${total_ed:,.2f}**"
                        + (f"  ·  leído originalmente: ${p['total']:,.2f}"
                           if abs(total_ed - p['total']) > 0.01 else ""))

            x, y = st.columns(2)
            if x.button("✅ Aceptar y crear el plan", type="primary", key=f"ok_{p['id']}"):
                if not filas:
                    st.error("El plan quedó sin cuotas con monto.")
                else:
                    res = aprobar_propuesta(p['id'], u, n,
                                            st.session_state.get('nombre', ''), filas)
                    if res['ok']:
                        msg = (f"Plan de {res['nombre']} creado en {res['unidad']} "
                               f"({res['creadas']} cuotas).")
                        if res.get('reserva'):
                            msg += (f" Su reserva de ${res['reserva']['monto']:,.2f} "
                                    f"pasó al plan.")
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(res['motivo'])
            if y.button("Descartar", key=f"no_{p['id']}"):
                descartar_propuesta(p['id'], st.session_state.get('nombre', ''))
                st.rerun()

# ─── Los que no se pueden leer ──────────────────────────────────────
if sin_plan:
    st.markdown("### 📄 Con contrato, sin plan de pagos todavía")
    st.caption("Su documento está escaneado como foto, así que no hay cuotas que leer. "
               "Al aceptarlos quedan creados en la app con su contrato guardado y la "
               "alerta «Sin plan de pagos», para cargarles el plan después.")

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
        st.markdown("#### Aceptar uno")
        op = {f"{p['unidad']} — {p['nombre']}": p for p in sin_plan}
        sel = st.selectbox("¿A quién aceptas?", list(op.keys()), key="aceptar_sp")
        p = op[sel]

        a, b = st.columns(2)
        u = a.text_input("Apartamento", value=p['unidad'], key=f"su_{p['id']}")
        n = b.text_input("Cliente", value=p['nombre'], key=f"sn_{p['id']}")
        st.caption(f"Se creará **{u} — {n}** con su documento «{p['archivo']}» "
                   f"y la alerta de plan pendiente.")

        x, y = st.columns(2)
        if x.button("✅ Aceptar y crear en la app", type="primary", key=f"sok_{p['id']}"):
            res = aprobar_propuesta(p['id'], u, n, st.session_state.get('nombre', ''))
            if res['ok']:
                doc = f" Documento guardado como «{res['documento']}»." if res['documento'] else ""
                st.success(f"{res['nombre']} creado en {res['unidad']}, "
                           f"marcado sin plan de pagos.{doc}")
                st.rerun()
            else:
                st.error(res['motivo'])
        if y.button("Quitar del buzón", key=f"sno_{p['id']}",
                    help="Úsalo si ese cliente no va, o si ya lo cargaste a mano."):
            descartar_propuesta(p['id'], st.session_state.get('nombre', ''))
            st.rerun()

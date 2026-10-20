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
st.caption("Planes de pago que aparecieron en la carpeta de Drive de la app y "
           "todavía no están cargados. Nada entra solo: aquí se revisa y se aprueba.")

st.markdown("---")

if not propuestas:
    st.success("No hay nada pendiente.")
    st.caption("El robot revisa cada noche la carpeta «Riviera Par App de abonos». "
               "Si encuentra el anexo de un apartamento que no tiene su plan cargado, "
               "lo lee y lo deja aquí. Si el anexo está escaneado como foto no lo "
               "propone: hay que subirlo en PDF hecho desde Excel, o el Excel mismo.")
    st.stop()

ES_ADMIN = st.session_state.get('rol') == 'admin'
if not ES_ADMIN:
    st.info("Solo el administrador puede aprobar. Esto es lo que hay pendiente:")

for p in propuestas:
    titulo = f"**{p['unidad']}**"
    if p.get('nombre'):
        titulo += f" — {p['nombre']}"
    titulo += f" · {len(p['cuotas'])} cuotas · ${p['total']:,.2f}"

    with st.expander(titulo, expanded=len(propuestas) == 1):
        docs = ', '.join(f"«{i['archivo']}»" for i in (p.get('adjuntos') or {}).values())
        st.caption(f"{p['origen']} · {docs}")

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

        a, b = st.columns(2)
        u = a.text_input("Apartamento", value=p['unidad'], key=f"u_{p['id']}")
        n = b.text_input("Cliente", value=p.get('nombre', ''), key=f"n_{p['id']}",
                         placeholder="Escríbelo si el anexo no lo traía")

        st.caption("Revisa que esté todo bien. Puedes corregir cualquier celda, "
                   "agregar filas o borrarlas antes de aprobar.")
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

        x, y = st.columns([1, 4])
        if x.button("✅ Aprobar", type="primary", key=f"ok_{p['id']}",
                    use_container_width=True):
            if not filas:
                st.error("El plan quedó sin cuotas con monto.")
            elif not n.strip():
                st.error("Falta el nombre del cliente.")
            else:
                res = aprobar_propuesta(p['id'], u, n,
                                        st.session_state.get('nombre', ''), filas)
                if res['ok']:
                    msg = (f"Plan de {res['nombre']} creado en {res['unidad']} "
                           f"({res['creadas']} cuotas).")
                    if res.get('documento'):
                        msg += f" Documentos guardados: {', '.join(res['documento'])}."
                    mig = res.get('reserva') or {}
                    if mig.get('ambiguo'):
                        quienes = ', '.join(f"{z['nombre']} (${z['monto']:,.2f})"
                                            for z in mig['ambiguo'])
                        st.warning(f"{msg} Pero {res['unidad']} tiene más de una reserva "
                                   f"({quienes}) y no se pudo saber cuál es la suya. "
                                   f"Ninguna se tocó: revísalas en Reservas.")
                    else:
                        if mig.get('monto'):
                            msg += f" Su reserva de ${mig['monto']:,.2f} pasó al plan."
                        st.success(msg)
                    st.rerun()
                else:
                    st.error(res['motivo'])

        if y.button("Descartar", key=f"no_{p['id']}",
                    help="Si ese cliente no va, o si ya lo cargaste a mano."):
            descartar_propuesta(p['id'], st.session_state.get('nombre', ''))
            st.rerun()

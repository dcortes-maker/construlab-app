import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import (_proyecto_db, cargar_reservas, guardar_reserva, eliminar_reserva,
                   retirar_reserva)
from datetime import date
import pandas as pd

st.set_page_config(page_title="Reservas", page_icon="🔖", layout="wide")
verificar_login()
barra_superior()

st.markdown("## 🔖 Reservas sin CPP")
st.caption("Clientes que han reservado pero aún no tienen Contrato de Promesa de Pago.")

st.markdown("---")

reservas = cargar_reservas(_proyecto_db())

# ─── Tabla de reservas actuales ────────────────────────────────────
if reservas:
    df = pd.DataFrame([{
        'ID':       r['id'],
        'Cliente':  r['nombre'],
        'Lote / Apto': r['unidad'],
        'Monto ($)': r['monto'],
        'Fecha':    r['fecha'],
        'Notas':    r['notas'],
    } for r in reservas])

    total = df['Monto ($)'].sum()
    st.markdown(f"**{len(reservas)} cliente(s) en reserva** · Total: **${total:,.2f}**")

    def color_row(row):
        return ['color:#f1f5f9'] * len(row)

    st.dataframe(
        df.drop(columns=['ID']).style.apply(color_row, axis=1).format({'Monto ($)': '${:,.2f}'}),
        use_container_width=True,
        hide_index=True,
    )

    if st.session_state.get('rol') == 'admin':
        with st.expander("📤 Retirar del proyecto"):
            st.caption("El cliente sale de esta lista pero queda guardado en Clientes retirados, "
                       "con su abono y el estado de su devolución.")
            op_ret = {f"[{r['id']}] {r['nombre']} — {r['unidad']} — ${r['monto']:,.2f}": r
                      for r in reservas}
            sel_ret = st.selectbox("¿A quién retiras?", list(op_ret.keys()), key="sel_ret")
            r_sel = op_ret[sel_ret]

            motivo_ret = st.text_input("Motivo (opcional)", key="motivo_ret")
            devol_ret = st.radio(
                "¿Se le devuelve la reserva?",
                ["No aplica devolución", "Aplica devolución"],
                key="devol_ret",
                help="Si aplica, queda pendiente hasta que registres la transferencia "
                     "en la pantalla de Clientes retirados.",
            )

            if st.button("📤 Retirar del proyecto", type="primary"):
                res = retirar_reserva(r_sel['id'], motivo_ret,
                                      devol_ret == "Aplica devolución",
                                      st.session_state.get('nombre', ''))
                if res['ok']:
                    st.success(f"{res['nombre']} retirado del proyecto.")
                    st.rerun()
                else:
                    st.error(res['motivo'])

        with st.expander("🗑 Eliminar una reserva"):
            opciones = {f"[{r['id']}] {r['nombre']} — {r['unidad']}": r['id'] for r in reservas}
            sel_del = st.selectbox("Selecciona la reserva a eliminar", list(opciones.keys()))
            if st.button("Eliminar reserva", type="primary"):
                eliminar_reserva(opciones[sel_del])
                st.success("Reserva eliminada.")
                st.rerun()
else:
    st.info("No hay clientes en reserva registrados aún.")

st.markdown("---")

# ─── Agregar nueva reserva ─────────────────────────────────────────
if st.session_state.get('rol') == 'admin':
    st.markdown("### ➕ Agregar nueva reserva")
    c1, c2 = st.columns(2)
    with c1:
        nombre_r = st.text_input("Nombre del cliente", key="nom_r").strip().upper()
        unidad_r = st.text_input("Lote / Apartamento (ej: Lote 335, B4-6)", key="uni_r").strip().upper()
        notas_r  = st.text_input("Notas (opcional)", key="not_r").strip()
    with c2:
        monto_r  = st.number_input("Monto de la reserva ($)", min_value=0.01, value=500.00,
                                   step=0.01, format="%.2f", key="mnt_r")
        fecha_r  = st.date_input("Fecha de la reserva", value=date.today(),
                                 format="DD/MM/YYYY", key="fch_r")

    if st.button("✅ Guardar reserva", type="primary"):
        if not nombre_r or not unidad_r:
            st.error("Nombre y unidad son obligatorios.")
        else:
            guardar_reserva(nombre_r, unidad_r, monto_r, fecha_r, notas_r)
            for k in ['nom_r', 'uni_r', 'not_r', 'mnt_r', 'fch_r']:
                st.session_state.pop(k, None)
            st.success(f"Reserva de {nombre_r} guardada.")
            st.rerun()
else:
    st.info("Solo el administrador puede agregar o eliminar reservas.")


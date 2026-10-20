import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import (_proyecto_db, listar_retirados, marcar_devolucion_hecha,
                   reingresar_retirado, saldos_retiros)
from datetime import date
import pandas as pd

st.set_page_config(page_title="Clientes retirados", page_icon="📤", layout="wide")
verificar_login()
barra_superior()

st.markdown("## 📤 Clientes retirados")
st.caption("Quienes salieron del proyecto. Nada se borra: su plan y sus recibos quedan guardados, "
           "solo dejan de aparecer en las demás pantallas y su apartamento queda libre.")

st.markdown("---")

retirados = listar_retirados(_proyecto_db())

# Dos cosas distintas: si al cliente le toca devolución, y si el banco ya la hizo.
APLICA = {'no_aplica': 'No aplica', 'pendiente': 'Aplica', 'devuelta': 'Aplica'}
ESTADO = {'no_aplica': '—', 'pendiente': '⏳ Por hacer', 'devuelta': '✅ Hecha'}

if not retirados:
    st.info("No hay clientes retirados. Cuando retires a alguien desde Plan de Pagos "
            "o desde Reservas, aparecerá aquí.")
    st.stop()

pendientes = [r for r in retirados if r.get('devolucion') == 'pendiente']
saldos = saldos_retiros(_proyecto_db())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes retirados", len(retirados))
c2.metric("Queda en el proyecto", f"${saldos['retenido']:,.2f}",
          help="Abonos de quienes se fueron sin devolución. Este dinero sigue "
               "contando en el Total en Banco de Inicio.")
c3.metric("Por devolver", f"${saldos['por_devolver']:,.2f}",
          help="Ya salió del Total en Banco. Falta hacer la transferencia.")
c4.metric("Ya devuelto", f"${saldos['devuelto']:,.2f}")

st.markdown("---")

df = pd.DataFrame([{
    'Apto':      r['unidad'],
    'Cliente':   r['nombre'],
    'Tipo':      'Reserva' if r.get('tipo') == 'reserva' else 'CPP',
    'Retirado':  str(r.get('fecha_retiro') or '')[:10],
    'Abonado':   float(r.get('abonado') or 0),
    'Devolución': APLICA.get(r.get('devolucion'), ''),
    'Estado':    ESTADO.get(r.get('devolucion'), ''),
    'Devuelto el': str(r.get('devol_fecha') or '') [:10] or '—',
    'Motivo':    r.get('motivo') or '',
} for r in retirados])

st.dataframe(
    df.style.format({'Abonado': '${:,.2f}'}),
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")

# ─── Registrar una devolución ya hecha ─────────────────────────────
if pendientes:
    st.markdown("### 💸 Confirmar una devolución hecha")
    st.caption("Quien maneja el banco marca aquí una vez hecha la transferencia. "
               "Queda la confirmación con su monto y su fecha.")

    opciones = {
        f"{r['unidad']} — {r['nombre']} — ${float(r.get('abonado') or 0):,.2f}": r
        for r in pendientes
    }
    elegido = st.selectbox("¿A quién le devolviste?", list(opciones.keys()))
    r = opciones[elegido]

    c1, c2 = st.columns(2)
    with c1:
        monto = st.number_input("Monto devuelto ($)", min_value=0.0,
                                value=float(r.get('abonado') or 0),
                                step=0.01, format="%.2f")
    with c2:
        cuando = st.date_input("Fecha de la transferencia", value=date.today(),
                               format="DD/MM/YYYY")

    if st.button("✅ Devolución hecha", type="primary"):
        marcar_devolucion_hecha(r['id'], monto, cuando)
        st.success(f"Devolución de {r['nombre']} confirmada.")
        st.rerun()

    st.markdown("---")

# ─── Deshacer un retiro ────────────────────────────────────────────
with st.expander("↩️ Reingresar a un cliente (deshacer el retiro)"):
    st.caption("El cliente vuelve a aparecer en todas las pantallas con su plan tal como estaba. "
               "Úsalo solo si retiraste a alguien por error.")
    op2 = {f"{r['unidad']} — {r['nombre']}": r['id'] for r in retirados}
    sel = st.selectbox("¿A quién reingresas?", list(op2.keys()), key="reingreso")
    if st.button("Reingresar al proyecto"):
        res = reingresar_retirado(op2[sel])
        if res['ok']:
            st.success(f"{res['nombre']} reingresado al apartamento {res['unidad']}.")
            st.rerun()
        else:
            st.error(res['motivo'])

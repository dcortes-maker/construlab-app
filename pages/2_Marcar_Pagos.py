import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion, solo_admin
from utils import _proyecto_db, cargar_datos, marcar_pago, desmarcar_pago, generar_recibo, ajustar_monto_siguiente, siguiente_num_recibo, registrar_recibo, pdf_a_imagenes
from datetime import date
import base64

st.set_page_config(page_title="Marcar Pagos", page_icon="✅", layout="wide")
verificar_login()
barra_superior()
solo_admin()

datos = cargar_datos(_proyecto_db())
hoy   = datos['hoy']

st.markdown("## ✅ Marcar Pagos")

opciones_cli = [f"{u} — {n}" for u, n in datos['clientes']]
if not opciones_cli:
    st.info("Este proyecto aún no tiene clientes con plan de pagos.")
    st.stop()

sel = st.selectbox("Selecciona cliente", opciones_cli)
unidad = sel.split(" — ")[0]
nombre = sel.split(" — ")[1]

filas_cli = [f for f in datos['filas'] if f['unidad'] == unidad and 'bonif' not in f['desc'].lower()]
filas_cli.sort(key=lambda x: (x['fv'] or date(2099,1,1)))

tab1, tab2 = st.tabs(["📌 Marcar como Pagado", "↩️ Desmarcar Pago"])

with tab1:
    pendientes = [f for f in filas_cli if not f['fp'] and f['monto'] > 0]
    if not pendientes:
        st.success("Este cliente no tiene pagos pendientes.")
    else:
        st.markdown(f"**{len(pendientes)} cuota(s) pendiente(s)**")
        seleccionadas = []
        for f in pendientes:
            fv_txt = f['fv'].strftime('%d/%m/%Y') if f['fv'] else "Sin fecha"
            label  = f"[Fila {f['fila']}] {f['desc']}  —  ${f['monto']:,.2f}  (Vence: {fv_txt})"
            if st.checkbox(label, key=f"chk_{f['fila']}"):
                seleccionadas.append(f)

        fecha_pago = st.date_input("Fecha del pago", value=hoy, format="DD/MM/YYYY")
        forma_pago = st.radio("Forma de pago", ["Transferencia", "Efectivo", "Cheque"],
                              horizontal=True, key="forma_pago")

        # ── Monto real pagado ──────────────────────────────────────────
        total_sel = sum(f['monto'] for f in seleccionadas)
        st.markdown("---")
        col_m1, col_m2 = st.columns([1, 2])
        with col_m1:
            monto_real = st.number_input(
                "💵 Monto real recibido ($)",
                min_value=0.0,
                value=float(total_sel),
                step=0.01,
                format="%.2f",
                help="Por defecto es la suma de las cuotas seleccionadas. Si el cliente pagó más, el excedente se descuenta de la siguiente cuota pendiente.",
            )
        with col_m2:
            if len(seleccionadas) > 0 and monto_real > total_sel:
                excedente = monto_real - total_sel
                # Find next pending after selected
                filas_sel_nums = {f['fila'] for f in seleccionadas}
                siguiente = next(
                    (f for f in pendientes if f['fila'] not in filas_sel_nums),
                    None
                )
                if siguiente:
                    st.info(f"Excedente **${excedente:,.2f}** → se descontará de la cuota siguiente: "
                            f"_{siguiente['desc']}_ (${siguiente['monto']:,.2f} → **${max(0, siguiente['monto']-excedente):,.2f}**)")
                else:
                    st.info(f"Excedente **${excedente:,.2f}** — no hay cuota siguiente a descontar.")

        if st.button("✅ Marcar seleccionados como Pagados", type="primary",
                     disabled=len(seleccionadas) == 0):
            for f in seleccionadas:
                marcar_pago(f['fila'], fecha_pago, forma_pago)

            # Aplicar excedente a la siguiente cuota
            if monto_real > total_sel:
                excedente = monto_real - total_sel
                filas_sel_nums = {f['fila'] for f in seleccionadas}
                siguiente = next(
                    (f for f in pendientes if f['fila'] not in filas_sel_nums),
                    None
                )
                if siguiente and excedente > 0:
                    ajustar_monto_siguiente(siguiente['fila'], excedente)

            recibos_nuevos = []
            for f in seleccionadas:
                num = siguiente_num_recibo()
                registrar_recibo(num, f['fila'], unidad, nombre,
                                 f['desc'], f['monto'], fecha_pago)
                recibos_nuevos.append({'fila': f['fila'], 'desc': f['desc'],
                                       'monto': f['monto'], 'num': num})
            st.session_state['recibos_pendientes'] = recibos_nuevos
            st.session_state['recibo_monto_real'] = monto_real
            st.session_state['recibo_nombre'] = nombre
            st.session_state['recibo_unidad'] = unidad
            st.session_state['recibo_fecha']  = fecha_pago
            st.session_state['recibo_forma']  = forma_pago
            st.rerun()

    # Recibos — siempre visible, fuera del if/else de pendientes
    if (st.session_state.get('recibo_unidad') == unidad and
            st.session_state.get('recibos_pendientes')):
        st.success(f"{len(st.session_state['recibos_pendientes'])} pago(s) marcado(s) correctamente.")
        st.markdown("---")
        st.markdown("#### 🧾 Recibos generados")
        recs         = st.session_state['recibos_pendientes']
        r_nombre     = st.session_state['recibo_nombre']
        r_fecha      = st.session_state['recibo_fecha']
        r_forma      = st.session_state['recibo_forma']
        r_monto_real = st.session_state.get('recibo_monto_real')

        # Si hay un solo recibo y se pagó un monto real diferente, usarlo en el recibo
        monto_nominal = sum(r['monto'] for r in recs)
        for i, rec in enumerate(recs):
            # Distribute monto_real proportionally if multiple quotas; for single quota use directly
            if r_monto_real is not None and len(recs) == 1:
                monto_recibo = r_monto_real
            elif r_monto_real is not None and len(recs) > 1:
                # Proportional split
                monto_recibo = round(r_monto_real * (rec['monto'] / monto_nominal), 2) if monto_nominal else rec['monto']
            else:
                monto_recibo = rec['monto']

            pdf_bytes = generar_recibo(
                nombre=r_nombre,
                unidad=unidad,
                desc=rec['desc'],
                monto=monto_recibo,
                fecha_pago=r_fecha,
                num_recibo=rec.get('num', rec['fila']),
                forma_pago=r_forma,
            )
            fname = f"Recibo_{unidad}_{rec['desc'].replace(' ','_')}_{r_fecha.strftime('%Y%m%d')}.pdf"
            for pg in pdf_a_imagenes(pdf_bytes):
                st.image(pg, use_container_width=True)
            st.download_button(
                label=f"⬇️  Descargar recibo — {rec['desc']}  (${monto_recibo:,.2f})",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                key=f"dl_rec_{rec['fila']}",
            )
        if st.button("Cerrar recibos", key="clear_recs"):
            for k in ['recibos_pendientes','recibo_nombre','recibo_unidad','recibo_fecha','recibo_forma','recibo_monto_real']:
                st.session_state.pop(k, None)
            st.rerun()

with tab2:
    pagados = [f for f in filas_cli if f['fp'] and f['monto'] > 0]
    if not pagados:
        st.info("Este cliente no tiene pagos marcados.")
    else:
        st.markdown(f"**{len(pagados)} pago(s) registrado(s)**")
        seleccionadas2 = []
        for f in pagados:
            fv_txt = f['fv'].strftime('%d/%m/%Y') if f['fv'] else "—"
            fp_txt = f['fp'].strftime('%d/%m/%Y') if f['fp'] else "—"
            label  = f"[Fila {f['fila']}] {f['desc']}  —  ${f['monto']:,.2f}  (Pagado: {fp_txt})"
            if st.checkbox(label, key=f"des_{f['fila']}"):
                seleccionadas2.append(f)

        if st.button("↩️ Desmarcar seleccionados", type="secondary",
                     disabled=len(seleccionadas2) == 0):
            for f in seleccionadas2:
                desmarcar_pago(f['fila'])
            n = len(seleccionadas2)
            st.warning(f"{n} pago(s) desmarcado(s). Los cambios se reflejan al cambiar de cliente o recargar.")
            st.stop()


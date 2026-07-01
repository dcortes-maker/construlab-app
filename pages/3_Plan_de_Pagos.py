import streamlit as st
import sys; sys.path.insert(0, '..')
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import (_proyecto_db, cargar_datos, agregar_fila_plan, parsear_plan,
                   agregar_filas_plan_bulk, eliminar_plan, generar_estado_cuenta,
                   eliminar_filas_plan, actualizar_fila_plan, cargar_reservas,
                   listar_adjuntos, subir_adjunto, descargar_adjunto, eliminar_adjunto)
from datetime import date
import pandas as pd

st.set_page_config(page_title="Plan de Pagos", page_icon="📋", layout="wide")
verificar_login()
barra_superior()

datos = cargar_datos(_proyecto_db())
hoy   = datos['hoy']

st.markdown("## 📋 Plan de Pagos")

seccion = st.radio("", ["📄 Ver Plan", "📎 Cargar Plan de Pago", "📁 Documentos"],
                   horizontal=True, key="seccion_plan", label_visibility="collapsed")

st.markdown("---")

# ─── Ver plan ──────────────────────────────────────────────────
if seccion == "📄 Ver Plan":
    opciones_cli = ["Todos"] + [f"{u} — {n}" for u, n in datos['clientes']]
    sel = st.selectbox("Filtrar cliente", opciones_cli)

    filas = datos['filas']
    if sel != "Todos":
        unidad_f = sel.split(" — ")[0]
        filas = [f for f in filas if f['unidad'] == unidad_f]
    filas = [f for f in filas if 'bonif' not in f['desc'].lower()]
    filas = sorted(filas, key=lambda x: (x['unidad'], x['fv'] or date(2099,1,1)))

    # ── Modo edición (solo admin, solo un cliente) ──────────────
    modo_edicion = (st.session_state.get('rol') == 'admin' and
                    sel != "Todos" and
                    st.toggle("✏️ Editar plan", key="toggle_editar"))

    if modo_edicion:
        st.info("Edita directamente en la tabla. Marca las filas a eliminar con el checkbox.")
        DESCS_ED = ["Reserva","Separación",
                    "I Pago","II Pago","III Pago","IV Pago","V Pago",
                    "VI Pago","VII Pago","VIII Pago","IX Pago","X Pago",
                    "XI Pago","XII Pago","XIII Pago","XIV Pago","XV Pago",
                    "XVI Pago","XVII Pago","XVIII Pago","XIX Pago","XX Pago",
                    "Abono inicial","Gasto Legal","Gasto Manejo","Bonificación","Otro"]

        ed_data = pd.DataFrame([{
            'Eliminar':      False,
            'Fila':          f['fila'],
            'Descripción':   f['desc'],
            'F. Vencimiento': f['fv'],
            'Monto ($)':     f['monto'],
            'Estado':        '✅ Pagado' if f['fp'] else ('🔴 Atrasado' if f['fv'] and (f['fv'].year, f['fv'].month) < (hoy.year, hoy.month) else '🟡 Pendiente'),
        } for f in filas])

        editado = st.data_editor(
            ed_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Eliminar':      st.column_config.CheckboxColumn('🗑', width="small"),
                'Fila':          st.column_config.NumberColumn('Fila', disabled=True, width="small"),
                'Descripción':   st.column_config.SelectboxColumn('Descripción', options=DESCS_ED, width="medium"),
                'F. Vencimiento': st.column_config.DateColumn('F. Vencimiento', format="DD/MM/YYYY"),
                'Monto ($)':     st.column_config.NumberColumn('Monto ($)', min_value=0.01, format="$%.2f"),
                'Estado':        st.column_config.TextColumn('Estado', disabled=True, width="small"),
            },
            key="editor_plan"
        )

        col_g, col_e = st.columns([1, 1])
        with col_g:
            if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
                a_eliminar = editado[editado['Eliminar'] == True]['Fila'].tolist()
                if a_eliminar:
                    eliminar_filas_plan([int(f) for f in a_eliminar])
                # Actualizar filas no eliminadas
                for _, row in editado[editado['Eliminar'] != True].iterrows():
                    fila_orig = next((f for f in filas if f['fila'] == int(row['Fila'])), None)
                    if fila_orig:
                        nueva_desc  = row['Descripción'] or fila_orig['desc']
                        nueva_fecha = row['F. Vencimiento'] if pd.notna(row['F. Vencimiento']) else fila_orig['fv']
                        nuevo_monto = float(row['Monto ($)']) if pd.notna(row['Monto ($)']) else fila_orig['monto']
                        if (nueva_desc != fila_orig['desc'] or
                                nueva_fecha != fila_orig['fv'] or
                                nuevo_monto != fila_orig['monto']):
                            actualizar_fila_plan(int(row['Fila']), nueva_desc, nueva_fecha, nuevo_monto)
                st.success("Cambios guardados.")
                st.rerun()
        with col_e:
            st.caption(f"{len(editado[editado['Eliminar']==True])} fila(s) marcada(s) para eliminar")

    else:
        # Vista normal (solo lectura)
        rows = []
        for f in filas:
            rows.append({
                'Apto': f['unidad'],
                'Cliente': f['nombre'],
                'Descripción': f['desc'],
                'F. Vencimiento': f['fv'].strftime('%d/%m/%Y') if f['fv'] else '—',
                'Monto': f['monto'],
                'Estado': '✅ Pagado' if f['fp'] else ('🔴 Atrasado' if f['fv'] and (f['fv'].year, f['fv'].month) < (hoy.year, hoy.month) else '🟡 Pendiente'),
                'F. Pago': f['fp'].strftime('%d/%m/%Y') if f['fp'] else '—',
            })

        df = pd.DataFrame(rows)

        def color_estado(row):
            estilos = []
            for col in row.index:
                if '✅' in row['Estado']:
                    if col == 'Estado':
                        estilos.append('color:#4ade80; font-weight:600')
                    elif col in ('F. Pago', 'Monto'):
                        estilos.append('color:#4ade80')
                    else:
                        estilos.append('color:#64748b')
                elif '🔴' in row['Estado']:
                    if col == 'Estado':
                        estilos.append('color:#f87171; font-weight:600')
                    elif col == 'Monto':
                        estilos.append('color:#f87171')
                    else:
                        estilos.append('')
                else:
                    estilos.append('')
            return estilos

        st.dataframe(
            df.style.apply(color_estado, axis=1).format({'Monto': '${:,.2f}'}),
            use_container_width=True, hide_index=True, height=500
        )
        st.caption(f"{len(rows)} filas")

    # Botón estado de cuenta
    if sel != "Todos" and filas:
        unidad_ec = sel.split(" — ")[0]
        nombre_ec = sel.split(" — ")[1]

        if st.button("📄 Vista previa — Estado de Cuenta", key="btn_preview_ec"):
            st.session_state['mostrar_ec'] = unidad_ec

        if st.session_state.get('mostrar_ec') == unidad_ec:
            import base64
            pdf_ec = generar_estado_cuenta(unidad_ec, nombre_ec, filas)
            pdf_b64 = base64.b64encode(pdf_ec).decode()
            fname_ec = f"EstadoCuenta_{unidad_ec}_{date.today().strftime('%Y%m%d')}.pdf"
            col_dl, col_cl = st.columns([1, 4])
            with col_dl:
                st.download_button(
                    label="⬇️ Descargar Estado de Cuenta",
                    data=pdf_ec,
                    file_name=fname_ec,
                    mime="application/pdf",
                    key="dl_ec",
                )
            with col_cl:
                if st.button("✖ Cerrar vista previa", key="close_ec"):
                    st.session_state.pop('mostrar_ec', None)
                    st.rerun()

    # Eliminar plan completo (solo admin)
    if st.session_state.get('rol') == 'admin' and sel != "Todos":
        with st.expander("⚠ Eliminar plan completo de este cliente"):
            st.warning(f"Esto eliminará **todas** las cuotas de **{sel}**. No se puede deshacer.")
            if st.button("🗑 Eliminar plan completo", type="primary"):
                eliminar_plan(sel.split(" — ")[0])
                st.success("Plan eliminado.")
                st.rerun()

# ─── Adjuntar Documento ────────────────────────────────────────
if seccion == "📎 Cargar Plan de Pago":
    if 'plan_guardado' in st.session_state:
        st.success(st.session_state.pop('plan_guardado'))

    sin_plan = datos.get('sin_plan', set())

    st.markdown("#### 1. Selecciona el cliente")
    col1, col2 = st.columns(2)
    with col1:
        tipo = st.radio("Tipo", ["Cliente existente", "Cliente nuevo"], key="tipo_pdf")

    unidad_pdf = ""
    nombre_pdf = ""

    if tipo == "Cliente existente":
        clientes_all = list(datos['clientes'])
        unidades_con_plan = {u for u, _ in clientes_all}
        reservas_sin_plan = [
            (r['unidad'], r['nombre'])
            for r in cargar_reservas(_proyecto_db())
            if r['unidad'] not in unidades_con_plan
        ]
        clientes_all_ext = clientes_all + reservas_sin_plan
        unidades_reserva = {u for u, _ in reservas_sin_plan}

        def _lbl(u, n):
            if u in sin_plan:
                return f"⚠ {u} — {n}"
            if u in unidades_reserva:
                return f"🔖 {u} — {n}  (en reserva)"
            return f"{u} — {n}"

        opciones_all = [_lbl(u, n) for u, n in clientes_all_ext]
        with col1:
            sel2 = st.selectbox("Cliente", opciones_all, key="sel_pdf")
        idx_sel    = opciones_all.index(sel2)
        unidad_pdf = clientes_all_ext[idx_sel][0]
        nombre_pdf = clientes_all_ext[idx_sel][1]
        if unidad_pdf in sin_plan:
            st.warning(f"⚠ **{nombre_pdf}** no tiene plan completo. Carga el documento para completarlo.")
        elif unidad_pdf in unidades_reserva:
            st.info(f"🔖 **{nombre_pdf}** está en reserva. Al cargar el plan pasará a CPP.")
    else:
        with col1:
            nombre_pdf = st.text_input("Nombre del cliente", key="nom_pdf").strip().upper()
            unidad_pdf = st.text_input("Apartamento (ej: 3-B)", key="uni_pdf").strip().upper()

    st.markdown("#### 2. Sube el archivo del plan")
    st.caption("PDF, Excel (.xlsx, .xls)")
    archivo = st.file_uploader("Archivo", type=["pdf", "xlsx", "xls"], key="uploader_pdf",
                               label_visibility="collapsed")

    if archivo is not None:
        st.session_state['pdf_bytes'] = archivo.read()
        st.session_state['pdf_fname'] = archivo.name

    listo_para_leer = ('pdf_bytes' in st.session_state and
                       unidad_pdf and nombre_pdf and
                       'pdf_filas' not in st.session_state)

    if listo_para_leer:
        if st.button("📖 Leer archivo", type="secondary"):
            with st.spinner("Leyendo..."):
                try:
                    filas_leidas = parsear_plan(
                        st.session_state['pdf_bytes'],
                        st.session_state['pdf_fname']
                    )
                    st.session_state['pdf_filas']  = filas_leidas
                    st.session_state['pdf_unidad'] = unidad_pdf
                    st.session_state['pdf_nombre'] = nombre_pdf
                    st.session_state.pop('pdf_error', None)
                    st.rerun()
                except Exception as e:
                    st.session_state['pdf_error'] = str(e)
                    st.session_state.pop('pdf_filas', None)

    if st.session_state.get('pdf_error'):
        st.error(st.session_state['pdf_error'])

    if 'pdf_filas' in st.session_state:
        filas_leidas = st.session_state['pdf_filas']
        unidad_prev  = st.session_state.get('pdf_unidad', '')
        nombre_prev  = st.session_state.get('pdf_nombre', '')

        if not filas_leidas:
            st.error("No se encontraron cuotas. Verifica que el archivo sea el plan de pagos correcto.")
        else:
            st.markdown(f"#### 3. Revisa — **{nombre_prev}** | Apto {unidad_prev}")
            ya_tiene = [f for f in datos['filas'] if f['unidad'] == unidad_prev]
            if ya_tiene:
                st.warning(f"⚠ Este cliente ya tiene {len(ya_tiene)} cuota(s) registrada(s). Solo se agregarán las nuevas — no se duplicarán las existentes.")
            st.success(f"{len(filas_leidas)} cuotas encontradas · Total: ${sum(f['monto'] for f in filas_leidas):,.2f}")
            st.caption("Puedes editar, agregar o eliminar filas antes de guardar.")

            DESCS = ["Reserva","Separación",
                     "I Pago","II Pago","III Pago","IV Pago","V Pago",
                     "VI Pago","VII Pago","VIII Pago","IX Pago","X Pago",
                     "XI Pago","XII Pago","XIII Pago","XIV Pago","XV Pago",
                     "XVI Pago","XVII Pago","XVIII Pago","XIX Pago","XX Pago",
                     "Abono inicial","Gasto Legal","Gasto Manejo","Bonificación","Otro"]

            preview_df = pd.DataFrame([{
                '#':           f['num_cuota'],
                'Descripción': f['desc'],
                'Fecha Venc.': f['fecha_venc'],
                'Monto ($)':   f['monto'],
            } for f in filas_leidas])

            editado = st.data_editor(
                preview_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    '#':           st.column_config.NumberColumn('#', min_value=1, step=1, width="small"),
                    'Descripción': st.column_config.SelectboxColumn('Descripción', options=DESCS, width="medium"),
                    'Fecha Venc.': st.column_config.DateColumn('Fecha Venc.', format="DD/MM/YYYY"),
                    'Monto ($)':   st.column_config.NumberColumn('Monto ($)', min_value=0.01, format="$%.2f"),
                },
                key="preview_editor"
            )
            st.caption(f"Total: ${editado['Monto ($)'].fillna(0).sum():,.2f}")

            filas_a_guardar = []
            for _, row in editado.iterrows():
                if pd.isna(row['Monto ($)']) or float(row['Monto ($)']) <= 0: continue
                filas_a_guardar.append({
                    'num_cuota':  int(row['#']) if pd.notna(row['#']) else 1,
                    'desc':       row['Descripción'] or 'Abono inicial',
                    'fecha_venc': row['Fecha Venc.'] if pd.notna(row['Fecha Venc.']) else None,
                    'monto':      float(row['Monto ($)']),
                })

            col_a, col_b = st.columns([1, 4])
            with col_a:
                if st.button("✅ Guardar plan", type="primary", use_container_width=True):
                    agregar_filas_plan_bulk(unidad_prev, nombre_prev, filas_a_guardar)
                    fname_orig = st.session_state.get('pdf_fname', 'plan_de_pagos')
                    subir_adjunto(unidad_prev, f"Plan_de_Pagos_{fname_orig}",
                                  st.session_state['pdf_bytes'])
                    for k in ['pdf_filas','pdf_unidad','pdf_nombre','pdf_error','pdf_bytes','pdf_fname']:
                        st.session_state.pop(k, None)
                    st.session_state['plan_guardado'] = f"✅ Plan de {nombre_prev} guardado correctamente."
                    st.rerun()
            with col_b:
                if st.button("❌ Cancelar"):
                    for k in ['pdf_filas','pdf_unidad','pdf_nombre','pdf_error','pdf_bytes','pdf_fname']:
                        st.session_state.pop(k, None)
                    st.rerun()


# ─── Documentos adjuntos ───────────────────────────────────────────────────
if seccion == "📁 Documentos":
    import base64

    opciones_cli = [f"{u} — {n}" for u, n in datos['clientes']]
    sel_doc    = st.selectbox("Selecciona cliente", opciones_cli, key="sel_doc")
    unidad_doc = sel_doc.split(" — ")[0]
    nombre_doc = sel_doc.split(" — ")[1]

    st.markdown(f"#### 📁 Documentos de {nombre_doc} ({unidad_doc})")

    # ── Subir archivo ──────────────────────────────────────────────
    exp_key          = f"exp_adjunto_{unidad_doc}"
    expander_abierto = st.session_state.get(exp_key, False)

    with st.expander("➕ Subir nuevo documento", expanded=expander_abierto):
        st.session_state[exp_key] = True

        archivo_up = st.file_uploader(
            "Selecciona el archivo",
            type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls", "docx", "doc"],
            key=f"uploader_adjunto_{unidad_doc}",
        )
        nombre_custom = st.text_input("Nombre del archivo (opcional, sin extensión)",
                                      key=f"nom_adjunto_{unidad_doc}").strip()

        if archivo_up:
            if st.button("📤 Subir archivo", type="primary", key=f"btn_subir_adj_{unidad_doc}"):
                from pathlib import Path as _P
                ext          = _P(archivo_up.name).suffix
                nombre_final = (nombre_custom if nombre_custom else _P(archivo_up.name).stem) + ext
                ok = subir_adjunto(unidad_doc, nombre_final, archivo_up.read())
                if ok:
                    st.success(f"Archivo **{nombre_final}** subido correctamente.")
                    st.session_state[exp_key] = False
                    st.rerun()

        if st.button("✖ Cerrar", key=f"cerrar_exp_{unidad_doc}"):
            st.session_state[exp_key] = False
            st.rerun()

    # ── Lista de archivos ──────────────────────────────────────────
    archivos = listar_adjuntos(unidad_doc)

    if not archivos:
        st.markdown("<div style='color:#475569;padding:12px 0;'>Sin documentos guardados para este cliente.</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"**{len(archivos)} documento(s) adjunto(s)**")
        for arch in archivos:
            fname = arch['name']
            ext   = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            icono = {"pdf":"📄","jpg":"🖼","jpeg":"🖼","png":"🖼",
                     "xlsx":"📊","xls":"📊","docx":"📝","doc":"📝"}.get(ext, "📎")

            with st.expander(f"{icono} {fname}", expanded=False):
                try:
                    file_bytes = descargar_adjunto(unidad_doc, fname)
                except Exception as e:
                    st.error(f"No se pudo descargar: {e}")
                    continue

                if ext == "pdf":
                    pass  # solo descarga, sin iframe
                elif ext in ("jpg", "jpeg", "png"):
                    st.image(file_bytes, use_container_width=True)

                col_dl, col_del = st.columns([2, 1])
                with col_dl:
                    st.download_button(
                        label="⬇️ Descargar",
                        data=file_bytes,
                        file_name=fname,
                        mime="application/octet-stream",
                        key=f"dl_adj_{fname}",
                    )
                with col_del:
                    if st.button("🗑 Eliminar", key=f"del_adj_{fname}"):
                        eliminar_adjunto(unidad_doc, fname)
                        st.rerun()


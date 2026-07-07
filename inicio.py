import streamlit as st
from auth import verificar_login, barra_superior, cerrar_sesion
from utils import _proyecto_db, cargar_datos, cargar_reservas, clientes_con_contrato

st.set_page_config(
    page_title="Riviera Park II",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

verificar_login()

barra_superior()

datos = cargar_datos(_proyecto_db())
k = datos['kpis']
hoy = datos['hoy']

reservas = cargar_reservas(_proyecto_db())
total_reservado = sum(r['monto'] for r in reservas)

# ── Total en Banco (primero, es el resumen global) ────────────────
st.markdown(f"""
<div style='background:#1e2536; border-radius:10px; padding:16px 20px;
            border:1px solid #2a3550; border-left:4px solid #0ea5e9;
            box-shadow:0 2px 8px rgba(0,0,0,.3); margin-bottom:12px;
            display:flex; align-items:center; gap:40px;'>
    <div>
        <div style='font-size:.65rem;color:#64748b;letter-spacing:.08em;
                    text-transform:uppercase;margin-bottom:6px;'>TOTAL EN BANCO</div>
        <div style='font-size:1.8rem;font-weight:800;color:#38bdf8;
                    letter-spacing:-.02em;'>${k['abonado'] + total_reservado:,.2f}</div>
    </div>
    <div style='width:1px;background:#2a3550;height:40px;'></div>
    <div>
        <div style='font-size:.6rem;color:#64748b;text-transform:uppercase;
                    letter-spacing:.06em;margin-bottom:4px;'>Abonos CPP</div>
        <div style='font-size:1.1rem;font-weight:700;color:#4ade80;'>${k['abonado']:,.2f}</div>
    </div>
    <div style='width:1px;background:#2a3550;height:40px;'></div>
    <div>
        <div style='font-size:.6rem;color:#64748b;text-transform:uppercase;
                    letter-spacing:.06em;margin-bottom:4px;'>Reservas</div>
        <div style='font-size:1.1rem;font-weight:700;color:#f59e0b;'>${total_reservado:,.2f}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── KPIs CPP ─────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
def kpi(col, label, valor, color="#3b82f6", fmt="número"):
    v = f"${valor:,.2f}" if fmt == "dinero" else str(valor)
    col.markdown(f"""
    <div style='background:#1e2536; border-radius:10px; padding:16px 12px;
                text-align:left; margin-bottom:8px;
                box-shadow:0 2px 8px rgba(0,0,0,.3);
                border:1px solid #2a3550;
                border-left:4px solid {color};'>
        <div style='font-size:.65rem; color:#64748b; letter-spacing:.08em;
                    text-transform:uppercase; margin-bottom:6px;'>{label}</div>
        <div style='font-size:1.55rem; font-weight:800; color:#f1f5f9;
                    letter-spacing:-.02em;'>{v}</div>
    </div>""", unsafe_allow_html=True)

con_contrato = clientes_con_contrato(_proyecto_db())
kpi(c1, "Clientes CPP · Contratos", f"{k['clientes']} · 📄{len(con_contrato)}", "#3b82f6")
kpi(c2, "Total Cuotas",     k['total_cuotas'], "#6366f1")
kpi(c3, "Cuotas Pagadas",   k['pagadas'],      "#22c55e")
kpi(c4, "Cuotas Atrasadas", k['atrasadas'],    "#ef4444")
kpi(c5, "Total Abonado",    k['abonado'],      "#22c55e", "dinero")
kpi(c6, "Total Atrasado",   k['atrasado'],     "#ef4444", "dinero")

st.markdown("---")
st.markdown("### 📋 Clientes con CPP — Resumen de Pagos")

filas = []
for u, nom in datos['clientes']:
    d    = datos['dash'].get(u, {})
    sp   = u in datos['sin_plan']
    sep  = d.get('separacion', 0)
    gm   = d.get('gasto_manejo', 0)
    gl   = d.get('gasto_legal', 0)
    bon  = d.get('bonificacion', 0)
    abo  = d.get('abono', 0)
    tot  = sep + gm + gl + abo
    atr  = d.get('atrasado', 0)
    filas.append({
        'Apto': u,
        'Cliente': ('⚠ Sin plan de pagos — ' + nom) if sp else nom,
        'Contrato': '✓' if u in con_contrato else '✗',
        '# Cuotas': '—' if sp else d.get('n_cuotas', 0),
        'Total Plan': 0 if sp else d.get('total_plan', 0),
        'Separación': sep,
        'G. Manejo': gm,
        'G. Legal': gl,
        'Abono': abo,
        'Total Abonado': tot,
        'Atrasado': atr,
        '_sp': sp,
    })

import pandas as pd
df = pd.DataFrame(filas)

money_cols = ['Total Plan','Separación','G. Manejo','G. Legal','Abono','Total Abonado','Atrasado']

if df.empty:
    st.info("Este proyecto aún no tiene clientes ni planes de pago cargados.")
else:
    totales = {
        'Apto': '', 'Cliente': 'TOTAL',
        'Contrato': '',
        '# Cuotas': df['# Cuotas'].apply(lambda x: x if isinstance(x, int) else 0).sum(),
        'Total Plan':    df['Total Plan'].sum(),
        'Separación':    df['Separación'].sum(),
        'G. Manejo':     df['G. Manejo'].sum(),
        'G. Legal':      df['G. Legal'].sum(),
        'Abono':         df['Abono'].sum(),
        'Total Abonado': df['Total Abonado'].sum(),
        'Atrasado':      df['Atrasado'].sum(),
        '_sp': False,
    }
    df_total = pd.concat([df, pd.DataFrame([totales])], ignore_index=True)

    def color_row(row):
        es_total = row['Cliente'] == 'TOTAL'
        es_sp    = bool(row.get('_sp', False)) or str(row.get('Cliente','')).startswith('⚠')
        estilos = []
        for col in row.index:
            if col == '_sp':
                estilos.append('')
            elif es_total:
                estilos.append('background-color:#1e2a3a; color:#f1f5f9; font-weight:700; border-top:1px solid #3b82f6')
            elif col == 'Contrato':
                if row[col] == '✓':
                    estilos.append('color:#4ade80; font-weight:700; text-align:center')
                else:
                    estilos.append('color:#f87171; font-weight:700; text-align:center')
            elif es_sp:
                estilos.append('color:#f59e0b; font-weight:600')
            elif col == 'Atrasado' and row[col] > 0:
                estilos.append('color:#f87171; font-weight:600')
            elif col == 'Total Abonado' and row[col] > 0:
                estilos.append('color:#4ade80; font-weight:600')
            else:
                estilos.append('')
        return estilos

    fmt = {c: '${:,.2f}' for c in money_cols}
    st.dataframe(
        df_total.style.apply(color_row, axis=1).format(fmt),
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={'_sp': None},
    )

# ─── Sección reservas sin CPP ──────────────────────────────────────
if reservas:
    st.markdown("---")
    st.markdown("### 🔖 Clientes en Reserva (Sin CPP)")
    st.caption("Estas personas han pagado una reserva pero aún no tienen Contrato de Promesa de Pago.")

    df_res = pd.DataFrame([{
        'Lote / Apto': r['unidad'],
        'Cliente':     r['nombre'],
        'Monto ($)':   r['monto'],
        'Fecha':       r['fecha'],
        'Notas':       r['notas'],
    } for r in reservas])

    total_res = df_res['Monto ($)'].sum()
    cr1, cr2, cr3 = st.columns(3)
    kpi(cr1, "Clientes en Reserva", len(reservas), "#f59e0b")
    kpi(cr2, "Total Reservado",     total_res,     "#f59e0b", "dinero")
    cr3.empty()

    def color_res(row):
        estilos = []
        for col in row.index:
            if col == 'Cliente':
                estilos.append('color:#f1f5f9; font-weight:600')
            elif col == 'Monto ($)':
                estilos.append('color:#4ade80; font-weight:600')
            else:
                estilos.append('color:#94a3b8')
        return estilos

    st.dataframe(
        df_res.style.apply(color_res, axis=1).format({'Monto ($)': '${:,.2f}'}),
        use_container_width=True,
        hide_index=True,
    )


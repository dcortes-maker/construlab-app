"""
Capa de datos — Supabase (PostgreSQL + Storage)
"""
import streamlit as st
from supabase import create_client, Client
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
import io

_PROYECTOS_DB = {
    "riviera_park_2":    "riviera-park-2",
    "villas_del_bosque": "villas-del-bosque",
}
BUCKET = "adjuntos"

def _proyecto_db() -> str:
    pid = st.session_state.get("proyecto", "riviera_park_2")
    return _PROYECTOS_DB.get(pid, "riviera-park-2")
MES      = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
_excluir_matriz = ['separac', 'gasto', 'bonif', '⚠']


def _sb() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["service_key"])


def _a_fecha(v):
    if v is None: return None
    if isinstance(v, date) and not isinstance(v, datetime): return v
    if isinstance(v, datetime): return v.date()
    if isinstance(v, str):
        try: return date.fromisoformat(v[:10])
        except: return None
    return None


def _cat_marca(ref, desc):
    r = str(ref).lower()  if ref  else ''
    d = str(desc).lower() if desc else ''
    if r.startswith('separac'):          return 'separacion'
    if r.startswith('gasto manejo'):     return 'gasto_manejo'
    if r.startswith('gasto legal'):      return 'gasto_legal'
    if r.startswith('bonif'):            return 'bonificacion'
    if r.startswith('abono'):            return 'abono'
    if 'reserva' in d or 'separac' in d: return 'separacion'
    if 'gasto' in d and 'manejo' in d:  return 'gasto_manejo'
    if 'gasto' in d and 'legal'  in d:  return 'gasto_legal'
    if 'bonif' in d:                     return 'bonificacion'
    return 'abono'


@st.cache_data(ttl=15)
def cargar_datos(proyecto: str = ""):
    if not proyecto:
        proyecto = _proyecto_db()
    sb   = _sb()
    rows = sb.table('cuotas').select('*').eq('proyecto', proyecto).order('id').execute().data
    hoy  = date.today()

    vistos  = {}
    sin_plan = set()
    filas   = []

    for row in rows:
        u    = row['unidad']
        nom  = row['nombre']
        desc = row['descripcion'] or ''
        m    = row['monto']
        fv   = _a_fecha(row['fecha_venc'])
        fp   = _a_fecha(row['fecha_pago'])
        ref  = row.get('referencia')

        if u and nom and u not in vistos:
            vistos[u] = nom
            sin_plan.add(u)
        if u and '⚠' in desc:
            sin_plan.add(u)          # marcado explícitamente como sin plan
        elif u and row.get('num_cuota'):
            sin_plan.discard(u)      # tiene cuotas reales → sí tiene plan
        if u and m:
            filas.append({
                'fila':   row['id'],
                'unidad': u,
                'nombre': nom or vistos.get(u, ''),
                'desc':   desc,
                'fv':     fv,
                'monto':  float(m),
                'fp':     fp,
                'ref':    ref,
            })

    clientes = sorted(vistos.items())

    cuota_map = {}
    for f in filas:
        if not f['fv'] or 'bonif' in f['desc'].lower(): continue
        key = (f['unidad'], f['fv'].year, f['fv'].month)
        if key not in cuota_map:
            cuota_map[key] = {'monto': 0.0, 'pagado': True, 'fecha': f['fv']}
        cuota_map[key]['monto'] += f['monto']
        if not f['fp']:
            cuota_map[key]['pagado'] = False

    all_fechas = [f['fv'] for f in filas
                  if f['fv'] and not any(x in f['desc'].lower() for x in _excluir_matriz)]
    if all_fechas:
        f_min, f_max = min(all_fechas), max(all_fechas)
    else:
        f_min = f_max = date(hoy.year, hoy.month, 1)
    cols = []
    y, m = f_min.year, f_min.month
    while (y, m) <= (f_max.year, f_max.month):
        cols.append((y, m)); m += 1
        if m > 12: m = 1; y += 1

    cols_set      = set(cols)
    pagadas_cnt   = sum(1 for (u,y,m), v in cuota_map.items() if (y,m) in cols_set and v['pagado'])
    atrasadas_cnt = sum(1 for (u,y,m), v in cuota_map.items()
                        if (y,m) in cols_set and not v['pagado']
                        and (v['fecha'].year, v['fecha'].month) < (hoy.year, hoy.month))
    total_cuotas  = sum(1 for (u,y,m) in cuota_map if (y,m) in cols_set)

    dash = defaultdict(lambda: {
        'n_cuotas': 0, 'total_plan': 0.0, 'atrasado': 0.0,
        'separacion': 0.0, 'gasto_manejo': 0.0, 'gasto_legal': 0.0,
        'bonificacion': 0.0, 'abono': 0.0
    })
    for f in filas:
        u = f['unidad']
        if u in sin_plan: continue
        if 'bonif' in f['desc'].lower():
            if f['fp']: dash[u]['bonificacion'] += f['monto']
            continue
        dash[u]['n_cuotas']   += 1
        dash[u]['total_plan'] += f['monto']
        if f['fp']:
            cat = _cat_marca(f['ref'], f['desc'])
            dash[u][cat] += f['monto']
        elif f['fv'] and (f['fv'].year, f['fv'].month) < (hoy.year, hoy.month):
            dash[u]['atrasado'] += f['monto']
    for u in sin_plan:
        for f in filas:
            if f['unidad'] != u: continue
            d = f['desc'].lower()
            if f['fp'] and ('reserva' in d or 'separac' in d):
                dash[u]['separacion'] += f['monto']

    total_abonado  = sum(d['separacion']+d['gasto_manejo']+d['gasto_legal']+d['abono']
                         for d in dash.values())
    total_atrasado = sum(d['atrasado'] for d in dash.values())

    return {
        'clientes': clientes,
        'sin_plan': sin_plan,
        'filas':    filas,
        'cuota_map': cuota_map,
        'cols':     cols,
        'dash':     dict(dash),
        'hoy':      hoy,
        'kpis': {
            'clientes':     len(clientes),
            'total_cuotas': total_cuotas,
            'pagadas':      pagadas_cnt,
            'atrasadas':    atrasadas_cnt,
            'abonado':      total_abonado,
            'atrasado':     total_atrasado,
        }
    }


def marcar_pago(record_id: int, fecha_pago: date, forma_pago: str = 'Transferencia'):
    _sb().table('cuotas').update({
        'fecha_pago': fecha_pago.isoformat(),
        'forma_pago': forma_pago,
        'referencia': f"Pagado - {fecha_pago.strftime('%d/%m/%Y')}",
    }).eq('id', record_id).execute()
    cargar_datos.clear()


def desmarcar_pago(record_id: int):
    _sb().table('cuotas').update({
        'fecha_pago': None,
        'forma_pago': None,
        'referencia': None,
    }).eq('id', record_id).execute()
    anular_recibo(record_id)
    cargar_datos.clear()


def ajustar_monto_siguiente(record_id: int, excedente: float):
    sb  = _sb()
    row = sb.table('cuotas').select('monto').eq('id', record_id).execute().data
    if row:
        nuevo = max(0, float(row[0]['monto']) - excedente)
        sb.table('cuotas').update({'monto': round(nuevo, 2)}).eq('id', record_id).execute()
    cargar_datos.clear()


def agregar_filas_plan_bulk(unidad: str, nombre: str, filas: list):
    sb     = _sb()
    GASTOS = {'Gasto Manejo', 'Gasto Legal'}

    existing = sb.table('cuotas').select('num_cuota,descripcion').eq('proyecto', _proyecto_db()).eq('unidad', unidad).execute().data
    existentes = {(r['num_cuota'], (r['descripcion'] or '').strip() in GASTOS) for r in existing if r['num_cuota']}

    to_insert = []
    for f in filas:
        clave = (int(f['num_cuota']), str(f['desc']).strip() in GASTOS)
        if clave in existentes: continue
        rec = {
            'proyecto': _proyecto_db(), 'unidad': unidad, 'nombre': nombre,
            'num_cuota': f['num_cuota'], 'descripcion': f['desc'], 'monto': f['monto'],
        }
        if f.get('fecha_venc'):
            fv = f['fecha_venc']
            rec['fecha_venc'] = fv.isoformat() if hasattr(fv, 'isoformat') else str(fv)
        to_insert.append(rec)
        existentes.add(clave)

    if to_insert:
        for i in range(0, len(to_insert), 100):
            sb.table('cuotas').insert(to_insert[i:i+100]).execute()
    cargar_datos.clear()


def eliminar_filas_plan(record_ids: list):
    sb = _sb()
    for rid in record_ids:
        sb.table('cuotas').delete().eq('id', rid).execute()
    cargar_datos.clear()


def actualizar_fila_plan(record_id: int, desc: str, fecha_venc, monto: float):
    _sb().table('cuotas').update({
        'descripcion': desc,
        'fecha_venc':  fecha_venc.isoformat() if fecha_venc and hasattr(fecha_venc, 'isoformat') else None,
        'monto':       monto,
    }).eq('id', record_id).execute()
    cargar_datos.clear()


def eliminar_plan(unidad: str):
    _sb().table('cuotas').delete().eq('proyecto', _proyecto_db()).eq('unidad', unidad).execute()
    cargar_datos.clear()


def agregar_fila_plan(unidad: str, nombre: str, num_cuota, desc: str, fecha_venc, monto: float):
    rec = {
        'proyecto': _proyecto_db(), 'unidad': unidad, 'nombre': nombre,
        'num_cuota': num_cuota, 'descripcion': desc, 'monto': monto,
    }
    if fecha_venc:
        rec['fecha_venc'] = fecha_venc.isoformat() if hasattr(fecha_venc, 'isoformat') else str(fecha_venc)
    _sb().table('cuotas').insert(rec).execute()
    cargar_datos.clear()


# ─── Reservas ──────────────────────────────────────────────────────

@st.cache_data(ttl=15)
def cargar_reservas(proyecto: str = "") -> list:
    if not proyecto:
        proyecto = _proyecto_db()
    return _sb().table('reservas').select('*').eq('proyecto', proyecto).order('id').execute().data


def guardar_reserva(nombre: str, unidad: str, monto: float, fecha, notas: str = '') -> int:
    res = _sb().table('reservas').insert({
        'proyecto': _proyecto_db(),
        'nombre':   nombre.strip().upper(),
        'unidad':   unidad.strip().upper(),
        'monto':    float(monto),
        'fecha':    fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha),
        'notas':    notas.strip(),
    }).execute()
    return res.data[0]['id']


def eliminar_reserva(rid: int):
    _sb().table('reservas').delete().eq('id', rid).execute()


# ─── Adjuntos (Supabase Storage) ──────────────────────────────────

def _folder(unidad: str) -> str:
    return unidad.replace('/', '-').replace(' ', '_')


def _mime(filename: str) -> str:
    ext = filename.lower().rsplit('.', 1)[-1]
    return {
        'pdf':  'application/pdf',
        'png':  'image/png',
        'jpg':  'image/jpeg',
        'jpeg': 'image/jpeg',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls':  'application/vnd.ms-excel',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc':  'application/msword',
    }.get(ext, 'application/octet-stream')


def listar_adjuntos(unidad: str) -> list:
    try:
        folder = _folder(unidad)
        files  = _sb().storage.from_(BUCKET).list(folder)
        return [f for f in (files or []) if f.get('name') and not f['name'].startswith('.')]
    except Exception:
        return []


@st.cache_data(ttl=60)
def clientes_con_contrato(proyecto: str = "") -> set:
    """Unidades con un adjunto cuyo nombre contiene 'contrato' (en Plan de Pagos → Documentos)."""
    out = set()
    try:
        datos = cargar_datos(proyecto)
        for u, _ in datos['clientes']:
            for f in listar_adjuntos(u):
                if 'contrato' in f['name'].lower():
                    out.add(u)
                    break
    except Exception:
        pass
    return out


def subir_adjunto(unidad: str, filename: str, file_bytes: bytes) -> bool:
    sb     = _sb()
    folder = _folder(unidad)
    path   = f"{folder}/{filename}"
    try:
        sb.storage.from_(BUCKET).remove([path])
    except Exception:
        pass
    try:
        sb.storage.from_(BUCKET).upload(
            path, file_bytes,
            file_options={"content-type": _mime(filename), "upsert": "true"}
        )
        return True
    except Exception as e:
        st.error(f"Error al subir archivo: {e}")
        return False


def descargar_adjunto(unidad: str, filename: str) -> bytes:
    return _sb().storage.from_(BUCKET).download(f"{_folder(unidad)}/{filename}")


def eliminar_adjunto(unidad: str, filename: str):
    _sb().storage.from_(BUCKET).remove([f"{_folder(unidad)}/{filename}"])


# ─── Generación de PDFs ────────────────────────────────────────────

def pdf_a_imagenes(pdf_bytes: bytes, scale: float = 2.0) -> list:
    """Convierte cada página de un PDF a PNG (para vista previa en la nube)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_bytes)
    paginas = []
    for page in doc:
        img = page.render(scale=scale).to_pil()
        b = io.BytesIO()
        img.save(b, format='PNG')
        paginas.append(b.getvalue())
    return paginas

def siguiente_num_recibo() -> int:
    """Contador global consecutivo de recibos (inicia en 1020), guardado en Supabase."""
    sb = _sb()
    try:
        row = sb.table('contadores').select('valor').eq('nombre', 'recibo').execute().data
        if row:
            nuevo = row[0]['valor'] + 1
            sb.table('contadores').update({'valor': nuevo}).eq('nombre', 'recibo').execute()
        else:
            nuevo = 1020
            sb.table('contadores').insert({'nombre': 'recibo', 'valor': nuevo}).execute()
        return nuevo
    except Exception:
        return 1020


def registrar_recibo(num: int, cuota_id: int, unidad: str, nombre: str,
                     desc: str, monto: float, fecha_pago, forma: str = ''):
    """Guarda el recibo emitido en Supabase (para trazabilidad y anulación)."""
    try:
        _sb().table('recibos').insert({
            'num':      num,
            'cuota_id': cuota_id,
            'unidad':   unidad,
            'nombre':   nombre,
            'desc':     desc,
            'monto':    monto,
            'fecha':    fecha_pago.isoformat() if hasattr(fecha_pago, 'isoformat') else str(fecha_pago),
            'estado':   'emitido',
            'proyecto': _proyecto_db(),
            'forma':    forma,
        }).execute()
    except Exception:
        pass


def listar_recibos() -> list:
    """Recibos del proyecto actual, más recientes primero."""
    try:
        return _sb().table('recibos').select('*') \
                    .eq('proyecto', _proyecto_db()) \
                    .order('num', desc=True).execute().data or []
    except Exception:
        return []


def anular_recibo(cuota_id: int):
    """Marca como ANULADO el recibo emitido de una cuota desmarcada (el número no se reutiliza)."""
    try:
        _sb().table('recibos').update({'estado': 'anulado'}) \
             .eq('cuota_id', cuota_id).eq('estado', 'emitido').execute()
    except Exception:
        pass


def generar_recibo(nombre: str, unidad: str, desc: str, monto: float,
                   fecha_pago, num_recibo: int, forma_pago: str = 'Transferencia') -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib import colors

    buf = io.BytesIO()
    W, H = letter
    c = _canvas.Canvas(buf, pagesize=letter)

    LOGO   = str(Path(__file__).parent / "logo_recibo.png")
    MARCA  = str(Path(__file__).parent / "logo_recibo_marca.png")
    BLACK  = colors.black
    RED    = colors.HexColor('#C00000')

    # ── Logo superior izquierdo ────────────────────────────────────
    logo_w = 230
    logo_h = logo_w * 683 / 1024
    c.drawImage(LOGO, 75, H - 40 - logo_h, width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask='auto')

    # ── Datos de la empresa (centrado bajo el logo) ────────────────
    cx_emp = 75 + logo_w / 2
    c.setFillColor(BLACK); c.setFont("Helvetica", 10)
    c.drawCentredString(cx_emp, H - 183, "Riviera Park Development S.A.")
    c.drawCentredString(cx_emp, H - 199, "Las Mañanitas, Ciudad de Panamá")
    c.drawCentredString(cx_emp, H - 214, "+507 6975-4414 / 375-0404")
    c.drawCentredString(cx_emp, H - 230, "ventas@gterrabona.com")

    # ── Título ─────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 20)
    c.drawString(349, H - 150, "RECIBO DE PAGO")

    # ── Secciones CLIENTE / RECIBO ─────────────────────────────────
    c.setFont("Helvetica", 12)
    c.drawString(90, H - 283, "CLIENTE")
    c.drawString(306, H - 283, "RECIBO")

    fecha_str = fecha_pago.strftime('%-d/%-m/%Y') if hasattr(fecha_pago, 'strftime') else str(fecha_pago)
    metodo = {'transferencia': 'ACH', 'efectivo': 'Efectivo', 'cheque': 'Cheque'}.get(
        forma_pago.lower(), forma_pago)

    c.setFont("Helvetica", 12)
    c.drawString(90, H - 323, f"Nombre: {nombre}")

    y = H - 323
    c.drawString(306, y, "No.: ")
    c.setFillColor(RED); c.setFont("Helvetica-Bold", 12)
    c.drawString(306 + c.stringWidth("No.: ", "Helvetica", 12), y, str(num_recibo))
    c.setFillColor(BLACK); c.setFont("Helvetica", 12)
    y -= 19.5; c.drawString(306, y, f"Fecha: {fecha_str}")
    y -= 19.5; c.drawString(306, y, f"Método de pago: {metodo}")
    y -= 19.5; c.drawString(306, y, "Estado: Pagado")
    y -= 19.5; c.drawString(306, y, "Moneda: USD")

    # ── Tabla Descripción / Cantidad / Total ───────────────────────
    tx0, tx1, tx2, tx3 = 85, 343, 428, 559
    th_top = H - 443          # borde superior del header
    th_bot = H - 473          # borde inferior del header
    tr_bot = H - 501          # borde inferior de la fila de datos

    c.setLineWidth(1); c.setStrokeColor(BLACK)
    for yy in (th_top, th_bot, tr_bot):
        c.line(tx0, yy, tx3, yy)
    for xx in (tx0, tx1, tx2, tx3):
        c.line(xx, th_top, xx, tr_bot)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(tx0 + 5, th_top - 20, "Descripción")
    c.drawString(tx1 + 6, th_top - 20, "Cantidad")
    c.drawString(tx2 + 6, th_top - 20, "Total")

    c.setFont("Helvetica", 12)
    c.drawString(tx0 + 5, th_bot - 19, f"{desc} — Unidad {unidad}"[:48])
    c.drawString(tx1 + 6, th_bot - 19, "1")
    c.drawString(tx2 + 9, th_bot - 19, f"${monto:,.2f}")

    # ── Observaciones ──────────────────────────────────────────────
    c.setFont("Helvetica", 11)
    c.drawString(90, H - 564, "Observaciones:")
    c.drawString(90, H - 595, "_" * 42)

    # ── Marca de agua inferior derecha ─────────────────────────────
    wm_w = 354
    wm_h = wm_w * 683 / 1024
    c.drawImage(MARCA, 221, 20, width=wm_w, height=wm_h,
                preserveAspectRatio=True, mask='auto')

    c.save()
    buf.seek(0)
    return buf.read()


def generar_estado_cuenta(unidad: str, nombre: str, filas: list) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import cm, mm
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib import colors
    from datetime import date as _date

    buf = io.BytesIO()
    W, H = letter
    c = _canvas.Canvas(buf, pagesize=letter)

    TEAL     = colors.HexColor('#0D5C6E')
    TEAL_LT  = colors.HexColor('#E6F4F7')
    GREEN    = colors.HexColor('#1B5E20')
    GREEN_LT = colors.HexColor('#E8F5E9')
    RED      = colors.HexColor('#B71C1C')
    RED_LT   = colors.HexColor('#FFEBEE')
    GRAY     = colors.HexColor('#555555')
    LGRAY    = colors.HexColor('#F7F7F7')
    WHITE    = colors.white
    BLACK    = colors.black
    LOGO_PATH = str(Path(__file__).parent / "logo_recibo.png")

    hoy   = _date.today()
    M     = 1.8 * cm
    avail = W - 2*M

    filas_s      = sorted(filas, key=lambda x: (x['fv'] or _date(2099,1,1), x['desc']))
    total_plan   = sum(f['monto'] for f in filas_s)
    total_pagado = sum(f['monto'] for f in filas_s if f['fp'])
    saldo        = total_plan - total_pagado

    COLS = [0.9*cm, 5.8*cm, 3.4*cm, 3.2*cm, 4.1*cm]
    HDRS = ['#', 'DESCRIPCI\xd3N', 'F. VENCIMIENTO', 'MONTO', 'ESTADO']
    COLS[1] += avail - sum(COLS)

    def draw_header():
        hdr_h = 2.8*cm
        logo_w = 4.2*cm
        logo_h = logo_w * 683 / 1024
        c.drawImage(LOGO_PATH, M, H - M - logo_h - 0.1*cm,
                    width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
        c.setFillColor(BLACK); c.setFont("Helvetica-Bold", 15)
        c.drawRightString(W - M, H - M - 0.9*cm, "ESTADO DE CUENTA")
        c.setFillColor(GRAY); c.setFont("Helvetica", 9)
        c.drawRightString(W - M, H - M - 1.5*cm, "Riviera Park Development S.A.")
        c.drawRightString(W - M, H - M - 1.9*cm, f"Fecha: {hoy.strftime('%d/%m/%Y')}")
        c.setStrokeColor(TEAL); c.setLineWidth(1.5)
        c.line(M, H - M - hdr_h, W - M, H - M - hdr_h)
        return H - M - hdr_h

    def draw_table_header(y):
        c.setFillColor(TEAL)
        c.rect(M, y - 0.6*cm, avail, 0.6*cm, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 7.5)
        cx = M
        for hdr, cw in zip(HDRS, COLS):
            c.drawString(cx + 2*mm, y - 0.41*cm, hdr); cx += cw
        return y - 0.6*cm

    y = draw_header()
    y -= 0.3*cm
    c.setFillColor(TEAL_LT)
    c.rect(M, y - 1.3*cm, avail, 1.3*cm, fill=1, stroke=0)
    c.setFillColor(TEAL); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(M + 0.3*cm, y - 0.52*cm, "CLIENTE:")
    c.setFillColor(BLACK); c.setFont("Helvetica-Bold", 10)
    c.drawString(M + 2.2*cm, y - 0.52*cm, nombre.upper())
    c.setFillColor(TEAL); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(M + 0.3*cm, y - 1.03*cm, "UNIDAD:")
    c.setFillColor(BLACK); c.setFont("Helvetica", 10)
    c.drawString(M + 2.2*cm, y - 1.03*cm, unidad)
    y -= 1.3*cm

    y -= 0.4*cm
    bw3 = (avail - 0.4*cm) / 3

    def sum_box(x, label, val, bg, col):
        c.setFillColor(bg)
        c.roundRect(x, y - 1.5*cm, bw3, 1.5*cm, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(col); c.setLineWidth(0.5)
        c.roundRect(x, y - 1.5*cm, bw3, 1.5*cm, 3*mm, fill=0, stroke=1)
        c.setFillColor(GRAY); c.setFont("Helvetica", 7.5)
        c.drawCentredString(x + bw3/2, y - 0.55*cm, label)
        c.setFillColor(col); c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(x + bw3/2, y - 1.25*cm, f"$ {val:,.2f}")

    sum_box(M,                   "TOTAL DEL PLAN",  total_plan,   TEAL_LT, TEAL)
    sum_box(M + bw3 + 0.2*cm,   "TOTAL PAGADO",    total_pagado, GREEN_LT, GREEN)
    sum_box(M + 2*(bw3+0.2*cm), "SALDO PENDIENTE", saldo,
            RED_LT if saldo > 0 else GREEN_LT, RED if saldo > 0 else GREEN)
    y -= 1.5*cm

    y -= 0.4*cm
    y  = draw_table_header(y)
    RH = 0.55*cm

    for i, f in enumerate(filas_s):
        if y - RH < M + 1.5*cm:
            _draw_footer(c, M, avail, W, hoy)
            c.showPage()
            y = draw_header()
            y = draw_table_header(y)

        bg = (GREEN_LT if f['fp']
              else RED_LT if f['fv'] and (f['fv'].year, f['fv'].month) < (hoy.year, hoy.month)
              else (WHITE if i % 2 == 0 else LGRAY))
        c.setFillColor(bg)
        c.rect(M, y - RH, avail, RH, fill=1, stroke=0)

        fv_str = f['fv'].strftime('%d/%m/%Y') if f['fv'] else '—'
        if f['fp']:
            estado_txt, estado_col = f"Pag. {f['fp'].strftime('%d/%m/%Y')}", GREEN
        elif f['fv'] and (f['fv'].year, f['fv'].month) < (hoy.year, hoy.month):
            estado_txt, estado_col = 'ATRASADO', RED
        else:
            estado_txt, estado_col = 'Pendiente', GRAY

        c.setFillColor(BLACK); c.setFont("Helvetica", 7.5)
        cx = M
        for val, cw in zip([str(i+1), f['desc'], fv_str, f"$ {f['monto']:,.2f}"], COLS[:-1]):
            c.drawString(cx + 2*mm, y - 0.38*cm, val); cx += cw
        c.setFillColor(estado_col); c.setFont("Helvetica-Bold", 7)
        c.drawString(cx + 2*mm, y - 0.38*cm, estado_txt)

        c.setStrokeColor(colors.HexColor('#E0E0E0')); c.setLineWidth(0.3)
        c.line(M, y - RH, M + avail, y - RH)
        y -= RH

    c.setFillColor(TEAL_LT); c.setStrokeColor(TEAL); c.setLineWidth(1)
    c.rect(M, y - RH - 1*mm, avail, RH + 1*mm, fill=1, stroke=1)
    c.setFillColor(TEAL); c.setFont("Helvetica-Bold", 9)
    c.drawString(M + 0.3*cm, y - 0.38*cm, "TOTAL DEL PLAN")
    c.drawString(M + sum(COLS[:3]) + 2*mm, y - 0.38*cm, f"$ {total_plan:,.2f}")

    _draw_footer(c, M, avail, W, hoy)
    c.save()
    buf.seek(0)
    return buf.read()


def _draw_footer(c, M, avail, W, hoy):
    from reportlab.lib import colors
    TEAL = colors.HexColor('#0D5C6E')
    from reportlab.lib.units import cm, mm
    c.setFillColor(TEAL)
    c.rect(M, M, avail, 0.55*cm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica", 6.5)
    c.drawCentredString(W/2, M + 1.5*mm,
        f"Riviera Park Development, S.A.  —  Proyecto Riviera Park II  —  Generado el {hoy.strftime('%d/%m/%Y')}")


# ─── parsear_plan — sin cambios (procesa archivos subidos) ─────────

def parsear_plan(archivo_bytes, nombre_archivo: str, _debug=False) -> list:
    import re
    from datetime import date as date_cls

    MESES = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
              "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
              "jan":1,"apr":4,"aug":8,"dec":12}

    def _ultimo_dia(anio, mes):
        import calendar
        return calendar.monthrange(anio, mes)[1]

    def _parse_fecha(txt):
        if txt is None: return None
        if isinstance(txt, (date_cls, datetime)):
            d = txt.date() if isinstance(txt, datetime) else txt
            return d.replace(day=_ultimo_dia(d.year, d.month))
        txt = str(txt).strip().lower()
        m = re.search(r'([a-z]{3})[- ](\d{2,4})', txt)
        if m:
            mes = MESES.get(m.group(1))
            anio = int(m.group(2))
            if anio < 100: anio += 2000
            if mes: return date_cls(anio, mes, _ultimo_dia(anio, mes))
        m2 = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', txt)
        if m2:
            d2, mo, yr = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            if yr < 100: yr += 2000
            try: return date_cls(yr, mo, _ultimo_dia(yr, mo))
            except: pass
        return None

    def _parse_monto(txt):
        if txt is None: return None
        if isinstance(txt, (int, float)): return float(txt) if txt > 0 else None
        s = str(txt).strip().replace('$','').replace(' ','')
        if ',' in s and '.' in s: s = s.replace('.','').replace(',','.')
        elif ',' in s: s = s.replace(',','.')
        s = re.sub(r'[^\d.]', '', s)
        try:
            v = float(s); return v if v > 0 else None
        except: return None

    def _normalizar_desc(desc_raw):
        d = str(desc_raw).lower()
        if 'reserva' in d:                    return 'Reserva'
        if 'firma' in d or 'separac' in d:    return 'Separación'
        if 'gasto' in d and 'manejo' in d:    return 'Gasto Manejo'
        if 'gasto' in d and 'legal' in d:     return 'Gasto Legal'
        if 'bonif' in d:                      return 'Bonificación'
        return desc_raw.strip() or 'Abono inicial'

    def _procesar_filas(rows):
        col_num = col_fecha = col_ab = col_ex = col_desc = None
        resultado = []; en_tabla = False
        for row in rows:
            if not row: continue
            cells = [str(c).strip() if c is not None else '' for c in row]
            low   = [c.lower() for c in cells]
            if not en_tabla:
                if any('cuot' in c for c in low) and any('fech' in c for c in low):
                    col_num  = next((i for i,c in enumerate(low) if 'cuot' in c), None)
                    col_fecha= next((i for i,c in enumerate(low) if 'fech' in c), None)
                    col_ab   = next((i for i,c in enumerate(low) if 'abono' in c or 'inicial' in c), None)
                    col_ex   = next((i for i,c in enumerate(low) if 'gasto' in c or 'manejo' in c or 'legal' in c), None)
                    col_desc = next((i for i,c in enumerate(low) if 'observ' in c or 'concepto' in c or 'desc' in c), None)
                    en_tabla = True
                continue
            if col_num is None or col_num >= len(cells): continue
            num_raw = cells[col_num]
            if not re.match(r'^\d+$', num_raw): continue
            num = int(num_raw)
            fecha    = _parse_fecha(row[col_fecha] if col_fecha is not None and col_fecha < len(row) else None)
            monto_ab = _parse_monto(row[col_ab]   if col_ab   is not None and col_ab   < len(row) else None)
            monto_ex = _parse_monto(row[col_ex]   if col_ex   is not None and col_ex   < len(row) else None)
            desc_raw = cells[col_desc] if col_desc is not None and col_desc < len(cells) else ''
            if not desc_raw:
                for c in cells:
                    if c and not re.match(r'^[\d$.,/-]+$', c) and not re.match(r'^\d+$', c):
                        desc_raw = c; break
            desc    = _normalizar_desc(desc_raw)
            desc_ex = 'Gasto Legal' if col_ex is not None and 'legal' in (low[col_ex] if col_ex < len(low) else '') else 'Gasto Manejo'
            desc_ab = desc if 'gasto' not in desc.lower() else 'Abono inicial'
            if monto_ab and monto_ab > 0:
                resultado.append({'num_cuota': num, 'desc': desc_ab, 'fecha_venc': fecha, 'monto': monto_ab})
            if monto_ex and monto_ex > 0:
                resultado.append({'num_cuota': num, 'desc': desc_ex, 'fecha_venc': fecha, 'monto': monto_ex})
        return resultado

    ext = nombre_archivo.lower().rsplit('.', 1)[-1]

    if ext in ('xlsx', 'xls'):
        import openpyxl, pandas as pd
        wb_tmp = openpyxl.load_workbook(io.BytesIO(archivo_bytes), data_only=True)
        fls = []
        for sheet in wb_tmp.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row = list(row)
                if all(v is None or str(v).strip() == '' for v in row): continue
                fls.append(row)
        resultado = _procesar_filas(fls)
        if resultado: return resultado
        df_tmp = pd.read_excel(io.BytesIO(archivo_bytes), header=None)
        return _procesar_filas(df_tmp.values.tolist())

    import pdfplumber
    fls = []
    with pdfplumber.open(io.BytesIO(archivo_bytes)) as pdf:
        total_chars = sum(len(p.chars) for p in pdf.pages)
        if total_chars > 0:
            for page in pdf.pages:
                for tabla in page.extract_tables():
                    fls.extend(tabla)
            resultado = _procesar_filas(fls)
            if resultado: return resultado

    return []

#!/usr/bin/env python3
"""Busca en Drive clientes que todavía no están en la app.

Mira las carpetas que el equipo llena a mano —los contratos en `CPP/` y los
anexos en `ABONOS DE CLIENTES/Plan de pagos/`— y compara con lo que hay en la
app. De lo que falte deja una propuesta en el buzón.

No crea nada. Una propuesta es solo eso: alguien la aprueba desde la pantalla
Buzón y ahí sí se crea el plan. Esto es a propósito: la app lleva el dinero del
proyecto y un lector equivocado de madrugada no lo nota nadie.

La mitad de los anexos de Drive son fotos escaneadas y no tienen texto que leer.
Esos también se proponen, pero marcados para cargar a mano: lo valioso es que
nadie se entere tarde de que un cliente nunca entró a la app.

    python3 scripts/revisar_drive.py

Variables: las mismas del respaldo (SUPABASE_*, GOOGLE_SERVICE_ACCOUNT_JSON).
"""
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from supabase import create_client

import utils
from respaldo_documentos_drive import DRIVE_FOLDER_ID, _credenciales_supabase, _q

DIR_BUZON = "sistema/buzon"
CARPETAS = [
    ("CPP", "contrato"),
    ("ABONOS DE CLIENTES/Plan de pagos", "plan"),
]
DRIVE_LOCAL = Path(
    "/Users/daylincortes/Library/CloudStorage/"
    "GoogleDrive-dcortes@construlab.com.pa/"
    "Unidades compartidas/Construlab/Proyectos/"
    "1. PROYECTO RIVIERA PARK"
)


def _normalizar(unidad: str) -> str:
    """'3E' -> '3-E', 'PBA' -> 'PB-A'. Así se llaman en la app."""
    u = re.sub(r'[^A-Z0-9]', '', (unidad or '').upper())
    if not u:
        return ''
    if u.startswith('PB'):
        return f"PB-{u[2:]}" if len(u) > 2 else u
    return f"{u[0]}-{u[1:]}" if len(u) > 1 else u


def _del_nombre(archivo: str) -> tuple:
    """Saca unidad y cliente de '1A - Esteban Newsan.pdf' o 'Plan de pago 2G - Karol Saenz.pdf'."""
    n = re.sub(r'(?i)^plan de pagos?\s*', '', Path(archivo).stem).strip()
    m = re.match(r'([A-Za-z0-9]{1,4})\s*[-–]?\s+(.*)', n)
    if not m:
        return '', ''
    return _normalizar(m.group(1)), m.group(2).strip().upper()


class Drive:
    """Lee de Drive por la API, o de la carpeta sincronizada si no hay llave."""

    def __init__(self):
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        ruta = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not raw and ruta:
            raw = Path(ruta).read_text()
        self.service = None
        if raw:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            info = json.loads(raw)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive"])
            self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
            print(f"Drive por API. Cuenta {info.get('client_email','')}", flush=True)
        else:
            print("Drive por la carpeta local de esta Mac.", flush=True)

    def _hijos(self, pid):
        return self.service.files().list(
            q=f"'{pid}' in parents and trashed = false",
            fields="files(id, name, mimeType)", supportsAllDrives=True,
            includeItemsFromAllDrives=True, pageSize=1000,
        ).execute().get("files", [])

    def _id_de(self, ruta: str):
        pid = DRIVE_FOLDER_ID
        for tramo in ruta.split('/'):
            encontrado = next((h for h in self._hijos(pid) if h['name'] == tramo), None)
            if not encontrado:
                return None
            pid = encontrado['id']
        return pid

    def listar(self, ruta: str) -> list:
        if not self.service:
            carpeta = DRIVE_LOCAL / ruta
            if not carpeta.exists():
                return []
            return [p.name for p in sorted(carpeta.iterdir())
                    if p.is_file() and not p.name.startswith('.')]
        pid = self._id_de(ruta)
        if not pid:
            return []
        return sorted(h['name'] for h in self._hijos(pid)
                      if not h['mimeType'].endswith('folder'))

    def bajar(self, ruta: str, archivo: str) -> bytes:
        if not self.service:
            return (DRIVE_LOCAL / ruta / archivo).read_bytes()
        from googleapiclient.http import MediaIoBaseDownload
        pid = self._id_de(ruta)
        fid = next(h['id'] for h in self._hijos(pid) if h['name'] == archivo)
        buf = io.BytesIO()
        bajada = MediaIoBaseDownload(buf, self.service.files().get_media(
            fileId=fid, supportsAllDrives=True))
        hecho = False
        while not hecho:
            _, hecho = bajada.next_chunk()
        return buf.getvalue()


RUTA_INDICE = f"{DIR_BUZON}/_indice.json"


def _ya_propuesto() -> dict:
    """Qué archivos de Drive ya se propusieron, y si se pudieron leer.

    Un índice y no abrir las propuestas una por una: con catorce en el buzón eso
    eran catorce descargas cada noche, y una que tarde de más tumba la revisión
    entera. Aquí solo escribe el detector, que corre una vez al día.

    Guarda si el archivo era legible para poder volver a proponerlo si alguien
    reemplaza un anexo escaneado por uno hecho en Excel.
    """
    try:
        indice = utils._leer_doc(RUTA_INDICE)
    except Exception:
        indice = None
    datos = (indice or {}).get('archivos') or {}
    if isinstance(datos, list):          # formato viejo: solo nombres
        return {a: False for a in datos}
    return datos


def _guardar_indice(vistos: dict):
    utils._escribir_doc(RUTA_INDICE, {'archivos': vistos,
                                      'actualizado': datetime.now().isoformat(timespec='seconds')})


def main() -> int:
    url, key = _credenciales_supabase()
    sb = create_client(url, key)
    utils.configurar_cliente(sb)
    drive = Drive()

    proyecto = "riviera-park-2"
    datos_app = utils.cargar_datos(proyecto)
    sin_plan = {_normalizar(u) for u in datos_app['sin_plan']}
    # Quien fue retirado a propósito no "falta": sus papeles siguen en Drive y
    # sin esto el buzón propondría devolverlo al proyecto cada noche.
    retirados = {_normalizar(r['unidad']) for r in utils.listar_retirados(proyecto)}
    existen = {_normalizar(u) for u, _ in datos_app['clientes']} | retirados
    # Un cliente marcado «sin plan de pagos» sí interesa para los anexos: ya
    # está en la app pero le falta justo eso, y es lo que se viene a buscar.
    con_plan = (existen - sin_plan) | retirados

    ya = _ya_propuesto()
    nuevas = repetidas = 0

    for ruta, tipo in CARPETAS:
        for archivo in drive.listar(ruta):
            unidad, nombre = _del_nombre(archivo)
            if not unidad:
                continue
            if unidad in (con_plan if tipo == "plan" else existen):
                continue
            visto = archivo in ya
            # Un contrato ya avisado no se repite. Un anexo tampoco, salvo que
            # antes fuera un escaneo: ahí hay que volver a leerlo por si lo
            # reemplazaron por uno hecho en Excel, que sí trae cuotas.
            if visto and (ya[archivo] or tipo != "plan"):
                repetidas += 1
                continue

            ext = archivo.rsplit('.', 1)[-1].lower()
            datos = drive.bajar(ruta, archivo)
            cuotas = utils.parsear_plan(datos, archivo) or [] if (tipo == "plan" and ext == 'pdf') else []
            legible = bool(cuotas)

            if visto and not legible:
                repetidas += 1       # sigue escaneado: ya se avisó en su día
                continue

            pid = datetime.now().strftime('%Y%m%d%H%M%S') + re.sub(r'\W', '', unidad)
            # El documento se guarda junto a la propuesta, no en la carpeta del
            # cliente: hasta que alguien acepte, ese cliente no existe en la app.
            adjunto = f"{DIR_BUZON}/{pid}.{ext}"
            sb.storage.from_(utils.BUCKET).upload(
                adjunto, datos,
                file_options={"content-type": utils._mime(archivo),
                              "upsert": "true", "cache-control": "0"})

            propuesta = {
                'id': pid,
                'adjunto': adjunto,
                'proyecto': proyecto,
                'unidad': unidad,
                'nombre': nombre,
                'tipo': tipo,
                'archivo': archivo,
                'origen': f"Drive: {ruta}",
                'legible': legible,
                'cuotas': [{'num_cuota': c.get('num_cuota'), 'desc': c.get('desc'),
                            'fecha_venc': str(c.get('fecha_venc') or ''),
                            'monto': float(c.get('monto') or 0)} for c in cuotas],
                'total': round(sum(float(c.get('monto') or 0) for c in cuotas), 2),
                'estado': 'pendiente',
                'detectado': datetime.now().isoformat(timespec='seconds'),
            }
            utils._escribir_doc(f"{DIR_BUZON}/{pid}.json", propuesta)
            ya[archivo] = legible
            nuevas += 1
            marca = f"{len(cuotas)} cuotas" if legible else "hay que cargarlo a mano"
            print(f"  propuesta: {unidad} — {nombre} ({tipo}, {marca})", flush=True)

    if nuevas:
        _guardar_indice(ya)
    print(f"Revision lista. {nuevas} propuestas nuevas, {repetidas} ya estaban en el buzon.",
          flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        utils.configurar_cliente(None)

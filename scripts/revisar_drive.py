#!/usr/bin/env python3
"""Revisa la carpeta de Drive de la app y propone lo que falte en la app.

REGLA: la única carpeta que se lee es «Riviera Par App de abonos». Ahí dentro hay
una carpeta por apartamento, y el equipo deja en ella el contrato y el anexo de
pago. No se mira ninguna otra carpeta del proyecto.

De lo que encuentre para un apartamento que no está en la app —o que está pero
sin plan de pagos— deja una propuesta en el buzón. No crea nada: alguien la
aprueba desde la pantalla Buzón y ahí sí entra. Esto es a propósito, porque la
app lleva el dinero del proyecto y un lector equivocado de madrugada no lo nota
nadie.

Muchos de esos PDF son fotos escaneadas y no tienen texto que leer. Se proponen
igual, marcados para cargar a mano: lo valioso es que nadie se entere tarde de
que un cliente nunca entró a la app.

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
from respaldo_documentos_drive import (CARPETA_APP, DRIVE_FOLDER_ID,
                                       _credenciales_supabase, _q)

DIR_BUZON = "sistema/buzon"
RUTA_INDICE = f"{DIR_BUZON}/_indice.json"
DRIVE_LOCAL = Path(
    "/Users/daylincortes/Library/CloudStorage/"
    "GoogleDrive-dcortes@construlab.com.pa/"
    "Unidades compartidas/Construlab/Proyectos/"
    "1. PROYECTO RIVIERA PARK"
)


class Drive:
    """Lee la carpeta de una torre, por la API o por la carpeta sincronizada."""

    def __init__(self):
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        ruta = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not raw and ruta:
            raw = Path(ruta).read_text()
        self.service = None
        self.carpeta = CARPETA_APP
        self.ruta = None
        self.raiz = None
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

    def abrir(self, carpeta: str, raiz: str, ruta=None) -> bool:
        """Apunta a la carpeta de ese proyecto. False si no se puede abrir:
        o no existe, o al robot no le han compartido su carpeta raíz."""
        self.carpeta = carpeta
        self.ruta = ruta
        if not self.service:
            return self._local().exists()
        if not raiz:
            return False
        self.raiz = self._buscar(carpeta, raiz)
        return bool(self.raiz)

    def _hijos(self, pid):
        return self.service.files().list(
            q=f"'{pid}' in parents and trashed = false",
            fields="files(id, name, mimeType)", supportsAllDrives=True,
            includeItemsFromAllDrives=True, pageSize=1000,
        ).execute(num_retries=5).get("files", [])

    def _buscar(self, nombre, pid):
        return next((h['id'] for h in self._hijos(pid) if h['name'] == nombre), None)

    def _local(self) -> Path:
        return self.ruta or (DRIVE_LOCAL / self.carpeta)

    def apartamentos(self) -> list:
        """Rutas de las carpetas de cliente, relativas a la del proyecto.

        Villas agrupa sus lotes por fase, Riviera pone los apartamentos sueltos.
        Una carpeta que solo contiene carpetas es una agrupación y se baja un
        nivel; una que contiene archivos es la de un cliente.
        """
        if not self.service:
            raiz = self._local()
            if not raiz.exists():
                return []
            out = []
            for p in sorted(raiz.iterdir()):
                if not p.is_dir() or p.name.startswith('.'):
                    continue
                hijos = [x for x in p.iterdir() if not x.name.startswith('.')]
                if hijos and all(x.is_dir() for x in hijos):
                    out += [f"{p.name}/{q.name}" for q in sorted(hijos)]
                else:
                    out.append(p.name)
            return out
        if not self.raiz:
            return []
        out = []
        for h in sorted(self._hijos(self.raiz), key=lambda x: x['name']):
            if not h['mimeType'].endswith('folder'):
                continue
            dentro = self._hijos(h['id'])
            if dentro and all(x['mimeType'].endswith('folder') for x in dentro):
                out += [f"{h['name']}/{q['name']}"
                        for q in sorted(dentro, key=lambda x: x['name'])]
            else:
                out.append(h['name'])
        return out

    def _carpeta_de(self, ruta: str):
        pid = self.raiz
        for tramo in ruta.split('/'):
            pid = self._buscar(tramo, pid)
            if not pid:
                return None
        return pid

    def archivos(self, apto: str) -> list:
        if not self.service:
            return sorted(p.name for p in (self._local() / apto).iterdir()
                          if p.is_file() and not p.name.startswith('.'))
        pid = self._carpeta_de(apto)
        return sorted(h['name'] for h in self._hijos(pid)
                      if not h['mimeType'].endswith('folder')) if pid else []

    def bajar(self, apto: str, archivo: str) -> bytes:
        if not self.service:
            return (self._local() / apto / archivo).read_bytes()
        from googleapiclient.http import MediaIoBaseDownload
        fid = self._buscar(archivo, self._carpeta_de(apto))
        buf = io.BytesIO()
        bajada = MediaIoBaseDownload(buf, self.service.files().get_media(
            fileId=fid, supportsAllDrives=True))
        hecho = False
        while not hecho:
            _, hecho = bajada.next_chunk()
        return buf.getvalue()


def _extension(archivo: str) -> str:
    """Terminación del archivo, o 'pdf' si no trae una usable.

    En Drive muchos nombres llegan sin `.pdf` —«Anexo - SULEIDIS ITSEL MONTILLA
    RÍOS»— y partir por el punto devolvía el nombre entero como extensión, con
    espacios y tildes: el bucket rechaza esa ruta y la revisión se cae.
    """
    cola = archivo.rsplit('.', 1)[-1].lower() if '.' in archivo else ''
    return cola if re.fullmatch(r'[a-z0-9]{1,5}', cola) else 'pdf'


def _nombre_del_archivo(archivo: str) -> str:
    """«Anexo - SULEIDIS ITSEL MONTILLA RÍOS.pdf» -> «SULEIDIS ITSEL MONTILLA RÍOS».

    Muchos anexos no llevan el nombre del cliente dentro en un formato que se
    pueda leer, pero sí en el nombre del archivo. Es una propuesta: quien la
    aprueba lo ve y lo corrige si hace falta.
    """
    base = re.sub(r'\.[A-Za-z0-9]{1,5}$', '', archivo).strip()
    m = re.search(r'[-–]\s*(.+)$', base)
    cand = (m.group(1) if m else '').strip()
    # Solo letras y espacios: descarta códigos como «T.177185» o «1. CPP AC»
    return cand.upper() if re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ' ]{6,}", cand) else ''


def _normalizar(apto: str) -> str:
    """'8I' -> '8-I', 'PBA' -> 'PB-A'. Las carpetas de Drive no siempre traen
    el guion con el que la app nombra los apartamentos de Riviera.

    Un lote de Villas es solo un número —311— y ahí no hay nada que separar:
    con el guion quedaría '3-11', que es otro lote.
    """
    u = re.sub(r'[^A-Z0-9]', '', (apto or '').upper())
    if not u or u.isdigit():
        return u
    if u.startswith('PB'):
        return f"PB-{u[2:]}" if len(u) > 2 else u
    return f"{u[0]}-{u[1:]}" if len(u) > 1 else u


def _ya_propuesto() -> dict:
    """Qué archivos ya se propusieron, y si se pudieron leer.

    Un índice y no abrir las propuestas una por una: con catorce en el buzón eso
    eran catorce descargas cada noche, y una que tarde de más tumba la revisión.
    Guarda si el archivo era legible para poder volver a proponerlo si alguien
    reemplaza un anexo escaneado por uno hecho en Excel.
    """
    try:
        indice = utils._leer_doc(RUTA_INDICE)
    except Exception:
        indice = None
    datos = (indice or {}).get('archivos') or {}
    return {k: bool(v) for k, v in datos.items()} if isinstance(datos, dict) \
        else {a: False for a in datos}


def _guardar_indice(vistos: dict):
    utils._escribir_doc(RUTA_INDICE, {
        'archivos': vistos,
        'actualizado': datetime.now().isoformat(timespec='seconds')})


def main() -> int:
    url, key = _credenciales_supabase()
    sb = create_client(url, key)
    utils.configurar_cliente(sb)
    drive = Drive()

    total_nuevas = 0
    for pid, info in utils.PROYECTOS.items():
        if not drive.abrir(info['drive'], info['raiz'], utils.ruta_local(pid)):
            continue      # sin carpeta en Drive, o sin acceso todavía
        print(f"\n--- {utils.etiqueta_proyecto(pid)} · {info['drive']}", flush=True)
        total_nuevas += _revisar(sb, drive, info['db'])
    return 0


def _revisar(sb, drive, proyecto: str) -> int:
    d = utils.cargar_datos(proyecto)
    sin_plan = set(d['sin_plan'])
    # Quien fue retirado a propósito no "falta": sus papeles siguen en Drive y
    # sin esto el buzón propondría devolverlo al proyecto cada noche.
    retirados = {r['unidad'] for r in utils.listar_retirados(proyecto)}
    existen = {u for u, _ in d['clientes']} | retirados
    con_plan = (existen - sin_plan) | retirados

    ya = _ya_propuesto()
    nuevas = repetidas = ilegibles = 0

    for carpeta in drive.apartamentos():
        apto = _normalizar(carpeta.rsplit('/', 1)[-1])
        if not apto or apto in con_plan:
            continue          # ya está con su plan: no hay nada que proponer

        archivos = drive.archivos(carpeta)
        anexos = [a for a in archivos if utils.clasificar_documento(a) == 'anexo']
        if not anexos:
            continue

        # Sin anexo legible no se propone nada. Sirve igual un PDF que un Excel;
        # lo que no se puede leer es un PDF escaneado, que por dentro es una foto
        # y no trae cuotas. Proponerlo solo llena el buzón de cosas que nadie
        # puede aprobar.
        elegido = cuotas = datos = None
        for archivo in anexos:
            clave = f"{carpeta}/{archivo}"
            if ya.get(clave):
                continue      # ese anexo ya se propuso leído
            crudo = drive.bajar(carpeta, archivo)
            leidas = utils.parsear_plan(crudo, archivo) or []
            if leidas:
                elegido, cuotas, datos = archivo, leidas, crudo
                break
            ya[clave] = False
            ilegibles += 1

        if not elegido:
            repetidas += sum(1 for a in anexos if f"{carpeta}/{a}" in ya and ya[f"{carpeta}/{a}"])
            continue

        nombre = (utils.extraer_datos_cliente(datos, elegido) or {}).get('nombre', '')
        if not nombre:
            nombre = _nombre_del_archivo(elegido)
        contrato = next((a for a in archivos
                         if utils.clasificar_documento(a) == 'contrato'), None)

        pid = datetime.now().strftime('%Y%m%d%H%M%S') + re.sub(r'\W', '', apto)
        # Los documentos se guardan junto a la propuesta, no en la carpeta del
        # cliente: hasta que alguien acepte, ese cliente no existe en la app.
        adjuntos = {}
        for etiqueta, archivo, crudo in [('anexo', elegido, datos),
                                         ('contrato', contrato, None)]:
            if not archivo:
                continue
            crudo = crudo if crudo is not None else drive.bajar(carpeta, archivo)
            ruta = f"{DIR_BUZON}/{pid}_{etiqueta}.{_extension(archivo)}"
            sb.storage.from_(utils.BUCKET).upload(
                ruta, crudo,
                file_options={"content-type": utils._mime(archivo),
                              "upsert": "true", "cache-control": "0"})
            adjuntos[etiqueta] = {'ruta': ruta, 'archivo': archivo}

        utils._escribir_doc(f"{DIR_BUZON}/{pid}.json", {
            'id': pid,
            'proyecto': proyecto,
            'unidad': apto,
            'nombre': (nombre or '').strip().upper(),
            'carpeta': carpeta,
            'adjuntos': adjuntos,
            'archivo': elegido,
            'origen': f"Drive: {CARPETA_APP}/{carpeta}",
            'legible': True,
            'cuotas': [{'num_cuota': c.get('num_cuota'), 'desc': c.get('desc'),
                        'fecha_venc': str(c.get('fecha_venc') or ''),
                        'monto': float(c.get('monto') or 0)} for c in cuotas],
            'total': round(sum(float(c.get('monto') or 0) for c in cuotas), 2),
            'estado': 'pendiente',
            'detectado': datetime.now().isoformat(timespec='seconds'),
        })
        ya[f"{carpeta}/{elegido}"] = True
        _guardar_indice(ya)
        nuevas += 1
        con = f" + contrato «{contrato}»" if contrato else " (sin contrato en la carpeta)"
        print(f"  propuesta: {apto} — {len(cuotas)} cuotas, ${sum(float(c.get('monto') or 0) for c in cuotas):,.2f}"
              f" — «{elegido}»{con}", flush=True)

    _guardar_indice(ya)
    print(f"  {nuevas} propuestas nuevas, {repetidas} ya estaban en el buzon, "
          f"{ilegibles} anexos escaneados sin texto que leer.", flush=True)
    return nuevas


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        utils.configurar_cliente(None)

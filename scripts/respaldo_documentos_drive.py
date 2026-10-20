#!/usr/bin/env python3
"""Copia a Google Drive los PDF que alimentan y produce la app.

Fuente de verdad: Supabase Storage y la tabla recibos.
Destino: Construlab → Proyectos → 1. PROYECTO RIVIERA PARK → Riviera Par App de abonos.
Dentro, una carpeta por apartamento con su contrato, su anexo y sus recibos.

En Railway (y en cualquier servidor) usa la API de Drive con una cuenta de servicio.
En esta Mac, si no hay cuenta de servicio, escribe en la carpeta que sincroniza
Drive para escritorio.

    python3 scripts/respaldo_documentos_drive.py

Variables:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    GOOGLE_SERVICE_ACCOUNT_JSON   JSON de la cuenta de servicio, en una sola línea
    DRIVE_FOLDER_ID               carpeta del proyecto Riviera. Dentro se crea
                                  "Riviera Par App de abonos". Tiene valor por defecto.
"""
import io
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from supabase import create_client

import utils
from utils import BUCKET, clasificar_documento, obtener_pdf_recibo

# Id de "1. PROYECTO RIVIERA PARK" (Construlab → Proyectos). Ahí se crea la carpeta de la app.
CARPETA_APP = "Riviera Par App de abonos"
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "1ATTQPzvtDORoOqMLsMnSjDVdIatFVIF3")
DRIVE_LOCAL = Path(
    "/Users/daylincortes/Library/CloudStorage/"
    "GoogleDrive-dcortes@construlab.com.pa/"
    "Unidades compartidas/Construlab/Proyectos/"
    "1. PROYECTO RIVIERA PARK/Riviera Par App de abonos"
)
SALTAR = {"sistema", "recibos"}
LEEME = """# Riviera Par App de abonos

Esta carpeta la llena el respaldo de la app. Es el espejo de lo que está en Supabase.

Cada apartamento tiene su propia carpeta. Ahí están juntos:

- el contrato (el nombre contiene «contrato» o «cpp»)
- el anexo o plan de pagos
- los recibos emitidos. Si un recibo se anula, el archivo pasa a llevar `_ANULADO`

`CPP/` y `ABONOS DE CLIENTES/Plan de pagos/` se arman a mano. Esta copia no las toca.
La app es la fuente de verdad: borrar un archivo aquí no lo borra en ConstruLab.
"""


def _credenciales_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if url and key:
        return url, key
    raw = (ROOT / ".streamlit" / "secrets.toml").read_text()
    found = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', raw, re.M))
    return found["url"], found["service_key"]


def _fecha(valor):
    if hasattr(valor, "isoformat") and not isinstance(valor, str):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except Exception:
        return date.today()


def _listar_storage(sb, folder: str) -> list:
    return sb.storage.from_(BUCKET).list(folder, {"limit": 1000}) or []


def _q(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("'", "\\'")


class LocalDestino:
    """Escribe en la carpeta sincronizada de esta Mac."""

    def __init__(self):
        self.raiz = DRIVE_LOCAL

    def poner(self, tipo: str, unidad: str, fname: str, data: bytes) -> str:
        dest = self.raiz / utils._folder(unidad) / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size == len(data):
            return "igual"
        # Se escribe directo, sin pasar por un .tmp: Drive no deja renombrar sobre
        # un archivo que ya existe cuando el proceso lo lanza launchd de noche.
        dest.write_bytes(data)
        return "copiado"

    def anular_recibo(self, unidad: str, num: int) -> bool:
        carpeta = self.raiz / utils._folder(unidad)
        base = f"Recibo_{num}_{unidad.replace('/', '-')}"
        vivo = carpeta / f"{base}.pdf"
        muerto = carpeta / f"{base}_ANULADO.pdf"
        if vivo.exists() and not muerto.exists():
            vivo.rename(muerto)
            return True
        return False

    def asegurar_leeme(self):
        leeme = self.raiz / "LEEME.md"
        if not leeme.exists():
            leeme.write_text(LEEME, encoding="utf-8")


class DriveAPIDestino:
    """Sube por la API de Google Drive. Así Railway no necesita esta Mac."""

    def __init__(self, service, raiz_id: str):
        self.service = service
        self.raiz_id = raiz_id
        self._carpetas = {}

    def _buscar(self, nombre: str, parent_id: str, solo_carpeta: bool = False):
        tipo = " and mimeType = 'application/vnd.google-apps.folder'" if solo_carpeta else ""
        consulta = (
            f"name = '{_q(nombre)}' and '{parent_id}' in parents "
            f"and trashed = false{tipo}"
        )
        res = self.service.files().list(
            q=consulta,
            fields="files(id, name, size, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        ).execute(num_retries=5)
        files = res.get("files") or []
        return files[0] if files else None

    def _carpeta(self, nombre: str, parent_id: str) -> str:
        clave = (parent_id, nombre)
        if clave in self._carpetas:
            return self._carpetas[clave]
        ya = self._buscar(nombre, parent_id, solo_carpeta=True)
        if ya:
            self._carpetas[clave] = ya["id"]
            return ya["id"]
        creado = self.service.files().create(
            body={
                "name": nombre,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
            supportsAllDrives=True,
        ).execute(num_retries=5)
        self._carpetas[clave] = creado["id"]
        return creado["id"]

    def _dir(self, unidad: str) -> str:
        return self._carpeta(utils._folder(unidad), self.raiz_id)

    def poner(self, tipo: str, unidad: str, fname: str, data: bytes) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        parent = self._dir(unidad)
        # Los comprobantes pueden ser una foto del banco, no siempre un PDF.
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=utils._mime(fname), resumable=False)
        ya = self._buscar(fname, parent)
        if ya and int(ya.get("size") or 0) == len(data):
            return "igual"
        if ya:
            self.service.files().update(
                fileId=ya["id"],
                media_body=media,
                supportsAllDrives=True,
            ).execute(num_retries=5)
        else:
            self.service.files().create(
                body={"name": fname, "parents": [parent]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute(num_retries=5)
        return "copiado"

    def anular_recibo(self, unidad: str, num: int) -> bool:
        parent = self._dir(unidad)
        base = f"Recibo_{num}_{unidad.replace('/', '-')}"
        vivo = self._buscar(f"{base}.pdf", parent)
        muerto = self._buscar(f"{base}_ANULADO.pdf", parent)
        if vivo and not muerto:
            self.service.files().update(
                fileId=vivo["id"],
                body={"name": f"{base}_ANULADO.pdf"},
                supportsAllDrives=True,
            ).execute(num_retries=5)
            return True
        return False

    def asegurar_leeme(self):
        from googleapiclient.http import MediaIoBaseUpload

        if self._buscar("LEEME.md", self.raiz_id):
            return
        media = MediaIoBaseUpload(
            io.BytesIO(LEEME.encode("utf-8")),
            mimetype="text/markdown",
            resumable=False,
        )
        self.service.files().create(
            body={"name": "LEEME.md", "parents": [self.raiz_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute(num_retries=5)


def _destino():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    ruta = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not raw and ruta:
        raw = Path(ruta).read_text()
    if raw:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        print(
            f"Drive por API. Dentro de {DRIVE_FOLDER_ID} se usa '{CARPETA_APP}'. "
            f"Cuenta {info.get('client_email', '')}",
            flush=True,
        )
        destino = DriveAPIDestino(service, DRIVE_FOLDER_ID)
        destino.raiz_id = destino._carpeta(CARPETA_APP, DRIVE_FOLDER_ID)
        return destino
    if DRIVE_LOCAL.parent.exists():
        print("Drive por la carpeta local de esta Mac.", flush=True)
        return LocalDestino()
    print(
        "Falta GOOGLE_SERVICE_ACCOUNT_JSON. En Railway esa variable es obligatoria: "
        "el servidor no ve la carpeta de Drive de la Mac.",
        flush=True,
    )
    return None


def main() -> int:
    destino = _destino()
    if destino is None:
        return 1

    url, key = _credenciales_supabase()
    sb = create_client(url, key)
    utils.configurar_cliente(sb)

    copiados = {"contrato": 0, "anexo": 0, "recibo": 0, "comprobante": 0}
    iguales = {"contrato": 0, "anexo": 0, "recibo": 0, "comprobante": 0}
    omitidos = 0

    for item in _listar_storage(sb, ""):
        nombre = item.get("name") or ""
        if not nombre or nombre in SALTAR or item.get("metadata") is not None:
            continue
        for archivo in _listar_storage(sb, nombre):
            fname = archivo.get("name") or ""
            if not fname or fname.startswith(".") or archivo.get("metadata") is None:
                continue
            tipo = clasificar_documento(fname)
            if not tipo:
                omitidos += 1
                continue
            data = sb.storage.from_(BUCKET).download(f"{nombre}/{fname}")
            resultado = destino.poner(tipo, nombre, fname, data)
            if resultado == "copiado":
                copiados[tipo] += 1
            else:
                iguales[tipo] += 1

    emitidos = sb.table("recibos").select("*").eq("estado", "emitido").limit(2000).execute().data or []
    for r in emitidos:
        unidad = r.get("unidad") or "sin-unidad"
        num = r["num"]
        pdf = obtener_pdf_recibo(
            num=num,
            unidad=unidad,
            nombre=r.get("nombre") or "",
            desc=r.get("desc") or "",
            monto=float(r.get("monto") or 0),
            fecha_pago=_fecha(r.get("fecha")),
            forma_pago=r.get("forma") or "Transferencia",
        )
        fname = f"Recibo_{num}_{unidad.replace('/', '-')}.pdf"
        resultado = destino.poner("recibo", unidad, fname, pdf)
        if resultado == "copiado":
            copiados["recibo"] += 1
        else:
            iguales["recibo"] += 1

    anulados = sb.table("recibos").select("num,unidad").eq("estado", "anulado").limit(2000).execute().data or []
    renombrados = 0
    for r in anulados:
        if destino.anular_recibo(r.get("unidad") or "sin-unidad", r["num"]):
            renombrados += 1

    destino.asegurar_leeme()
    print(
        "Respaldo listo.",
        f"contratos nuevos {copiados['contrato']} (ya estaban {iguales['contrato']}),",
        f"anexos nuevos {copiados['anexo']} (ya estaban {iguales['anexo']}),",
        f"recibos nuevos {copiados['recibo']} (ya estaban {iguales['recibo']}),",
        f"comprobantes nuevos {copiados['comprobante']} (ya estaban {iguales['comprobante']}),",
        f"anulados renombrados {renombrados},",
        f"otros adjuntos sin copiar {omitidos}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        utils.configurar_cliente(None)

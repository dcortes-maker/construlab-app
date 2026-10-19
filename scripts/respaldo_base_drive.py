#!/usr/bin/env python3
"""Copia a Google Drive el contenido de la base de datos.

Fuente de verdad: las tablas de Supabase.
Destino: Construlab -> Proyectos -> 1. PROYECTO RIVIERA PARK -> Respaldos_Riviera_Park -> diario.

Cada corrida deja una carpeta con la fecha. Dentro, dos subcarpetas:
"1. Consultar en Excel" con los .csv y "2. Restaurar el sistema" con los .json
mas la estructura de las tablas.

Este respaldo NO toca "Riviera Par App de abonos": los documentos por apartamento
los copia scripts/respaldo_documentos_drive.py y siguen igual.

    python3 scripts/respaldo_base_drive.py

Variables:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    GOOGLE_SERVICE_ACCOUNT_JSON   JSON de la cuenta de servicio, en una sola linea
    DRIVE_FOLDER_ID               carpeta del proyecto Riviera. Tiene valor por defecto.
"""
import csv
import io
import json
import os
import shutil
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from supabase import create_client

from respaldo_documentos_drive import DRIVE_FOLDER_ID, _credenciales_supabase, _q

CARPETA_RESPALDOS = "Respaldos_Riviera_Park"
CARPETA_DIARIO = "diario"
EXCEL = "1. Consultar en Excel"
RESTAURAR = "2. Restaurar el sistema"
DIAS_QUE_SE_GUARDAN = 30
PAGINA = 1000

# Como se llama cada tabla en la carpeta, para que se entienda al abrirla.
NOMBRES = {
    "cuotas": "Plan de pagos y abonos",
    "reservas": "Reservas y separaciones",
    "recibos": "Recibos emitidos",
    "usuarios": "Usuarios de la app",
    "contadores": "Contadores de recibos",
}

DRIVE_LOCAL = Path(
    "/Users/daylincortes/Library/CloudStorage/"
    "GoogleDrive-dcortes@construlab.com.pa/"
    "Unidades compartidas/Construlab/Proyectos/"
    "1. PROYECTO RIVIERA PARK"
)


def _leeme_raiz(ultimo: str) -> str:
    return f"""# Respaldo diario de la base de datos

Aqui vive lo que la app guarda cuando alguien marca un pago, crea una reserva o
emite un recibo. Lo llena solo, todos los dias a las 7:00 p.m.

Ultimo respaldo: **{ultimo}**

## Como esta organizado

Una carpeta por dia, con la fecha al derecho (AAAA-MM-DD) para que queden en orden.
Dentro de cada dia:

| Carpeta | Para que es |
|---|---|
| `1. Consultar en Excel` | Los datos en .csv. Doble clic y se abren en Excel. Es para mirar, no para restaurar. |
| `2. Restaurar el sistema` | Los mismos datos en .json, mas la estructura de las tablas. Esto es lo que usa un tecnico si hay que volver a montar todo. |
| `LEEME.md` | Que se respaldo ese dia y cuantos registros tenia cada cosa. |

## Que NO esta aqui

Los contratos, anexos y recibos en PDF **no** estan en esta carpeta. Viven en
`Riviera Par App de abonos`, con una carpeta por apartamento. Son dos respaldos
distintos que corren juntos todas las noches.

El codigo de la app tampoco esta aqui: vive en GitHub
(`dcortes-maker/construlab-app`).

## Cuanto se guarda

Los ultimos {DIAS_QUE_SE_GUARDAN} dias completos. Ademas, **la carpeta del dia 1 de
cada mes no se borra nunca**, asi queda un historico mensual hacia atras.

## Como saber que esta funcionando

Mira la fecha de la carpeta mas reciente dentro de `diario`. Si es de hoy o de
ayer, todo bien. Si esta vieja, algo se detuvo.

## Cuidado

`Usuarios de la app` lleva las contrasenas (en hash, no en texto). Esta carpeta
no se comparte con terceros.
"""


def _leeme_dia(fecha: str, conteos: dict, hecho: str) -> str:
    filas = "\n".join(
        f"| {NOMBRES.get(t, t)} | {n} | `{t}` |" for t, n in sorted(conteos.items())
    )
    return f"""# Respaldo del {fecha}

Tomado el {hecho}.

| Que es | Registros | Tabla |
|---|---|---|
{filas}

**Total: {sum(conteos.values())} registros.**

- `1. Consultar en Excel` — para abrir y revisar. No sirve para restaurar.
- `2. Restaurar el sistema` — los .json y la estructura de las tablas.

Los PDF (contratos, anexos, recibos) no estan aqui: estan en
`Riviera Par App de abonos`, una carpeta por apartamento.
"""


def _spec(url: str, key: str) -> dict:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _tablas(spec: dict) -> list:
    """Las tablas salen de Supabase, no de una lista fija: asi una tabla nueva se respalda sola."""
    rutas = spec.get("paths") or {}
    return sorted(r.strip("/") for r in rutas if r != "/" and not r.startswith("/rpc"))


def _filas(sb, tabla: str) -> list:
    """Trae la tabla completa, de mil en mil."""
    filas, desde = [], 0
    while True:
        lote = sb.table(tabla).select("*").range(desde, desde + PAGINA - 1).execute().data or []
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        desde += PAGINA


def _csv(filas: list) -> bytes:
    if not filas:
        return b""
    columnas = list(dict.fromkeys(c for fila in filas for c in fila))
    buf = io.StringIO()
    escritor = csv.DictWriter(buf, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({c: fila.get(c) for c in columnas})
    return buf.getvalue().encode("utf-8-sig")


def _se_conserva(nombre: str) -> bool:
    """El dia 1 de cada mes se guarda para siempre; el resto, 30 dias."""
    try:
        dia = date.fromisoformat(nombre)
    except ValueError:
        return True
    return dia.day == 1 or dia >= date.today() - timedelta(days=DIAS_QUE_SE_GUARDAN)


class DestinoLocal:
    """Escribe en la carpeta que sincroniza Drive para escritorio."""

    def __init__(self):
        self.base = DRIVE_LOCAL / CARPETA_RESPALDOS
        self.raiz = self.base / CARPETA_DIARIO
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _escribir(self, destino: Path, data: bytes):
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe directo, sin pasar por un .tmp: Drive no deja renombrar sobre
        # un archivo que ya existe cuando el proceso lo lanza launchd de noche.
        destino.write_bytes(data)

    def poner(self, carpeta: str, nombre: str, data: bytes):
        self._escribir(self.raiz / carpeta / nombre, data)

    def poner_raiz(self, nombre: str, data: bytes):
        self._escribir(self.base / nombre, data)

    def limpiar(self) -> int:
        borradas = 0
        for sub in self.raiz.iterdir():
            if sub.is_dir() and not _se_conserva(sub.name):
                shutil.rmtree(sub)
                borradas += 1
        return borradas


class DestinoAPI:
    """Sube por la API de Drive. Asi el respaldo no depende de esta Mac."""

    def __init__(self, service, raiz_id: str):
        self.service = service
        self.raiz_id = raiz_id
        self.base_id = raiz_id
        self._carpetas = {}

    def _buscar(self, nombre: str, parent_id: str, solo_carpeta: bool = False):
        tipo = " and mimeType = 'application/vnd.google-apps.folder'" if solo_carpeta else ""
        res = self.service.files().list(
            q=f"name = '{_q(nombre)}' and '{parent_id}' in parents and trashed = false{tipo}",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        ).execute()
        archivos = res.get("files") or []
        return archivos[0] if archivos else None

    def carpeta(self, nombre: str, parent_id: str) -> str:
        clave = (parent_id, nombre)
        if clave not in self._carpetas:
            ya = self._buscar(nombre, parent_id, solo_carpeta=True)
            if ya:
                self._carpetas[clave] = ya["id"]
            else:
                creado = self.service.files().create(
                    body={
                        "name": nombre,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [parent_id],
                    },
                    fields="id",
                    supportsAllDrives=True,
                ).execute()
                self._carpetas[clave] = creado["id"]
        return self._carpetas[clave]

    def _ruta(self, carpeta: str) -> str:
        parent = self.raiz_id
        for tramo in carpeta.split("/"):
            if tramo:
                parent = self.carpeta(tramo, parent)
        return parent

    def poner(self, carpeta: str, nombre: str, data: bytes):
        self._subir(self._ruta(carpeta), nombre, data)

    def poner_raiz(self, nombre: str, data: bytes):
        self._subir(self.base_id, nombre, data)

    def _subir(self, parent: str, nombre: str, data: bytes):
        from googleapiclient.http import MediaIoBaseUpload

        mime = {
            ".json": "application/json",
            ".csv": "text/csv",
            ".md": "text/markdown",
            ".sql": "application/sql",
        }.get(Path(nombre).suffix, "application/octet-stream")
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
        ya = self._buscar(nombre, parent)
        if ya:
            self.service.files().update(
                fileId=ya["id"], media_body=media, supportsAllDrives=True
            ).execute()
        else:
            self.service.files().create(
                body={"name": nombre, "parents": [parent]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute()

    def limpiar(self) -> int:
        res = self.service.files().list(
            q=f"'{self.raiz_id}' in parents and trashed = false "
            f"and mimeType = 'application/vnd.google-apps.folder'",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
        ).execute()
        borradas = 0
        for carpeta in res.get("files") or []:
            if not _se_conserva(carpeta["name"]):
                self.service.files().delete(
                    fileId=carpeta["id"], supportsAllDrives=True
                ).execute()
                borradas += 1
        return borradas


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
        print(f"Drive por API. Cuenta {info.get('client_email', '')}", flush=True)
        destino = DestinoAPI(service, DRIVE_FOLDER_ID)
        destino.base_id = destino.carpeta(CARPETA_RESPALDOS, DRIVE_FOLDER_ID)
        destino.raiz_id = destino.carpeta(CARPETA_DIARIO, destino.base_id)
        return destino
    if DRIVE_LOCAL.exists():
        print("Drive por la carpeta local de esta Mac.", flush=True)
        return DestinoLocal()
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
    spec = _spec(url, key)

    hoy = date.today().isoformat()
    hecho = datetime.now().strftime("%d/%m/%Y a las %H:%M")
    conteos = {}

    for tabla in _tablas(spec):
        filas = _filas(sb, tabla)
        bonito = NOMBRES.get(tabla, tabla)
        destino.poner(f"{hoy}/{EXCEL}", f"{bonito}.csv", _csv(filas))
        destino.poner(
            f"{hoy}/{RESTAURAR}",
            f"{tabla}.json",
            json.dumps(filas, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        )
        conteos[tabla] = len(filas)
        print(f"  {bonito}: {len(filas)} registros", flush=True)

    # Sin la estructura de las tablas los datos no se pueden volver a cargar.
    destino.poner(
        f"{hoy}/{RESTAURAR}",
        "estructura_de_las_tablas.json",
        json.dumps(spec.get("definitions") or {}, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    destino.poner(
        f"{hoy}/{RESTAURAR}",
        "esquema.sql",
        (ROOT / "schema_supabase.sql").read_bytes(),
    )

    destino.poner(hoy, "LEEME.md", _leeme_dia(hoy, conteos, hecho).encode("utf-8"))
    destino.poner_raiz("LEEME.md", _leeme_raiz(hoy).encode("utf-8"))
    borradas = destino.limpiar()

    print(
        f"Respaldo de la base listo en {CARPETA_RESPALDOS}/{CARPETA_DIARIO}/{hoy}. "
        f"{sum(conteos.values())} registros en {len(conteos)} tablas. "
        f"Carpetas viejas borradas: {borradas}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

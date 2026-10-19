"""Llaves de la API. Se guarda el hash, nunca la llave.

Si la tabla api_claves existe, se usa esa. Si no (todavía no se pegó el SQL
en Supabase), los hashes viven en el bucket privado, archivo sistema/api_claves.json.
"""
import hashlib
import json
import secrets
import time
import urllib.request
from datetime import datetime, timezone

from utils import BUCKET

RUTA_JSON = "sistema/api_claves.json"


def hash_llave(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _tabla_disponible(sb) -> bool:
    try:
        sb.table("api_claves").select("id").limit(1).execute()
        return True
    except Exception as e:
        msg = str(e)
        if "PGRST205" in msg or "schema cache" in msg or "does not exist" in msg or "404" in msg:
            return False
        raise


def _leer_json(sb) -> list:
    """Lee la lista de llaves saltándose la caché.

    No usa storage.download(): esa ruta se sirve cacheada y devuelve la lista
    anterior, así que validar() rechazaría llaves recién creadas y crear()
    escribiría encima de las ya emitidas. Una URL firmada con un parámetro
    distinto en cada llamada siempre trae el archivo real.

    Solo devuelve vacío si el archivo todavía no existe. Cualquier otro fallo
    estalla: tragárselo es lo que borraría las llaves.
    """
    try:
        firmada = sb.storage.from_(BUCKET).create_signed_url(RUTA_JSON, 60)["signedURL"]
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "404" in msg or "does not exist" in msg:
            return []
        raise
    sep = "&" if "?" in firmada else "?"
    pedido = urllib.request.Request(
        f"{firmada}{sep}cb={time.time_ns()}",
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    with urllib.request.urlopen(pedido, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data if isinstance(data, list) else []


def _escribir_json(sb, rows: list):
    # Sin cache-control, Supabase cachea el archivo una hora: validar() seguiría
    # leyendo la lista vieja y rechazaría llaves recién creadas. Y sin borrar
    # antes, porque upsert ya reemplaza y el borrado deja un hueco sin archivo.
    blob = json.dumps(rows, ensure_ascii=False).encode()
    sb.storage.from_(BUCKET).upload(
        RUTA_JSON, blob,
        file_options={
            "content-type": "application/json",
            "upsert": "true",
            "cache-control": "0",
        },
    )


def _publica(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "key_hash"}


def listar(sb) -> list:
    if _tabla_disponible(sb):
        rows = sb.table("api_claves").select(
            "id,etiqueta,prefijo,activa,creado_por,created_at,ultimo_uso"
        ).order("created_at", desc=True).execute().data or []
        return rows
    return [_publica(r) for r in _leer_json(sb)]


def crear(sb, etiqueta: str, creado_por: str = "") -> str:
    """Crea una llave y devuelve el texto completo, una sola vez."""
    token = "cl_" + secrets.token_urlsafe(32)
    rec = {
        "id": secrets.token_hex(16),
        "etiqueta": (etiqueta or "").strip() or "Sin etiqueta",
        "key_hash": hash_llave(token),
        "prefijo": token[:7],
        "activa": True,
        "creado_por": creado_por or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ultimo_uso": None,
    }
    if _tabla_disponible(sb):
        sb.table("api_claves").insert(rec).execute()
    else:
        rows = _leer_json(sb)
        rows.append(rec)
        _escribir_json(sb, rows)
    return token


def revocar(sb, clave_id: str) -> bool:
    if _tabla_disponible(sb):
        sb.table("api_claves").update({"activa": False}).eq("id", clave_id).execute()
        return True
    rows = _leer_json(sb)
    ok = False
    for r in rows:
        if str(r.get("id")) == str(clave_id):
            r["activa"] = False
            ok = True
    if ok:
        _escribir_json(sb, rows)
    return ok


def validar(sb, token: str):
    """Devuelve la fila si la llave está activa. Actualiza ultimo_uso."""
    if not token:
        return None
    digest = hash_llave(token.strip())
    ahora = datetime.now(timezone.utc).isoformat()
    if _tabla_disponible(sb):
        rows = sb.table("api_claves").select("*").eq("key_hash", digest).eq("activa", True).execute().data or []
        if not rows:
            return None
        sb.table("api_claves").update({"ultimo_uso": ahora}).eq("id", rows[0]["id"]).execute()
        return rows[0]
    rows = _leer_json(sb)
    encontrada = None
    for r in rows:
        if r.get("key_hash") == digest and r.get("activa"):
            r["ultimo_uso"] = ahora
            encontrada = r
            break
    if encontrada:
        _escribir_json(sb, rows)
    return encontrada

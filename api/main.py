"""API para que otras apps suban contratos y anexos de pago.

Correr en esta Mac:
    python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8600
"""
import os
import re
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client

import utils
from api import claves
from api.ingesta import PROYECTOS, cargar_anexo, cargar_contrato
from utils import listar_unidades

_candado = threading.Lock()


def _credenciales():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if url and key:
        return url, key
    raw = Path(__file__).resolve().parent.parent.joinpath(".streamlit", "secrets.toml").read_text()
    found = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', raw, re.M))
    return found["url"], found["service_key"]


def _cliente():
    url, key = _credenciales()
    return create_client(url, key)


def _usar_cliente(sb):
    """Las funciones de utils leen un cliente global. Un candado evita que dos
    peticiones se pisen, porque la app de Streamlit no corre en este proceso."""
    class _ctx:
        def __enter__(self):
            _candado.acquire()
            utils.configurar_cliente(sb)
            return sb

        def __exit__(self, *exc):
            utils.configurar_cliente(None)
            _candado.release()
    return _ctx()


def exigir_llave(authorization: str = Header(default="")):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta la llave. Usa Authorization: Bearer …")
    token = authorization.split(" ", 1)[1].strip()
    sb = _cliente()
    with _usar_cliente(sb):
        fila = claves.validar(sb, token)
    if not fila:
        raise HTTPException(status_code=401, detail="Llave inválida o revocada.")
    return sb


app = FastAPI(title="ConstruLab — documentos", version="1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/salud")
def salud():
    return {"ok": True, "servicio": "construlab-documentos"}


@app.get("/v1/unidades")
def unidades(proyecto: str = "riviera-park-2", sb=Depends(exigir_llave)):
    if proyecto not in PROYECTOS:
        raise HTTPException(status_code=400, detail="Proyecto desconocido.")
    with _usar_cliente(sb):
        return {"proyecto": proyecto, "unidades": listar_unidades(proyecto)}


@app.post("/v1/anexos")
async def anexos(
    archivo: UploadFile = File(...),
    unidad: str = Form(""),
    nombre: str = Form(""),
    proyecto: str = Form("riviera-park-2"),
    sb=Depends(exigir_llave),
):
    data = await archivo.read()
    try:
        with _usar_cliente(sb):
            return cargar_anexo(data, archivo.filename or "anexo.pdf", unidad, nombre, proyecto)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/v1/contratos")
async def contratos(
    archivo: UploadFile = File(...),
    unidad: str = Form(...),
    proyecto: str = Form("riviera-park-2"),
    sb=Depends(exigir_llave),
):
    data = await archivo.read()
    try:
        with _usar_cliente(sb):
            return cargar_contrato(data, archivo.filename or "contrato.pdf", unidad, proyecto)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

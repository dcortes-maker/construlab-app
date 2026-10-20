"""Subida de anexos y contratos. La misma regla que la pantalla Plan de Pagos."""
from pathlib import Path

from utils import (
    agregar_filas_plan_bulk,
    extraer_datos_cliente,
    listar_unidades,
    migrar_reserva_a_plan,
    parsear_plan,
    subir_adjunto,
)

PROYECTOS = {"riviera-park-2", "villas-del-bosque"}
MAX_BYTES = 20 * 1024 * 1024


def exigir_pdf(nombre: str, data: bytes):
    if not nombre or not str(nombre).lower().endswith(".pdf"):
        raise ValueError("El archivo tiene que ser un PDF.")
    if not data.startswith(b"%PDF"):
        raise ValueError("El archivo no es un PDF válido.")
    if len(data) > MAX_BYTES:
        raise ValueError("El PDF supera los 20 MB.")


def _nombre_archivo(nombre: str) -> str:
    base = Path(nombre or "documento.pdf").name.replace("/", "-").replace("\\", "-").strip()
    return base or "documento.pdf"


def _fila(f: dict) -> dict:
    fv = f.get("fecha_venc")
    return {
        "num_cuota": f.get("num_cuota"),
        "desc": f.get("desc"),
        "fecha_venc": fv.isoformat() if hasattr(fv, "isoformat") else fv,
        "monto": f.get("monto"),
    }


def cargar_anexo(data: bytes, filename: str, unidad: str, nombre: str, proyecto: str) -> dict:
    if proyecto not in PROYECTOS:
        raise ValueError("Proyecto desconocido. Usa riviera-park-2 o villas-del-bosque.")
    exigir_pdf(filename, data)
    leido = extraer_datos_cliente(data, filename)
    unidad = (unidad or leido.get("unidad") or "").strip().upper()
    nombre = (nombre or leido.get("nombre") or "").strip().upper()
    if not unidad or not nombre:
        raise ValueError(
            "No pude leer la unidad o el nombre del cliente en el PDF. "
            "Envíalos en el formulario (unidad y nombre)."
        )
    filas = parsear_plan(data, filename)
    if not filas:
        raise ValueError("No encontré cuotas en ese anexo. Revisa que sea el plan de pagos.")

    insertadas = agregar_filas_plan_bulk(unidad, nombre, filas, proyecto=proyecto)
    fname = "Plan_de_Pagos_" + _nombre_archivo(filename)
    if not subir_adjunto(unidad, fname, data):
        detalle = getattr(subir_adjunto, "ultimo_error", "") or "no se pudo guardar el archivo"
        raise RuntimeError(f"Las cuotas se registraron, pero el PDF no quedó guardado: {detalle}")
    # Con el nombre, para no llevarle a este cliente la reserva de otro si el
    # apartamento tuviera más de una.
    mig = migrar_reserva_a_plan(unidad, proyecto=proyecto, nombre=nombre)
    return {
        "proyecto": proyecto,
        "unidad": unidad,
        "nombre": nombre,
        "archivo": fname,
        "cuotas_leidas": len(filas),
        "cuotas_nuevas": insertadas,
        "cuotas": [_fila(f) for f in filas],
        "reserva_migrada": bool(mig) and not mig.get("ambiguo"),
        "aviso": ("Ese apartamento tiene más de una reserva y no se pudo saber cuál "
                  "es la suya: ninguna se tocó." if mig.get("ambiguo") else None),
    }


def cargar_contrato(data: bytes, filename: str, unidad: str, proyecto: str) -> dict:
    if proyecto not in PROYECTOS:
        raise ValueError("Proyecto desconocido. Usa riviera-park-2 o villas-del-bosque.")
    exigir_pdf(filename, data)
    unidad = (unidad or "").strip().upper()
    if not unidad:
        raise ValueError("La unidad es obligatoria para un contrato.")
    fname = f"Contrato_{unidad.replace('/', '-').replace(' ', '_')}.pdf"
    if not subir_adjunto(unidad, fname, data):
        detalle = getattr(subir_adjunto, "ultimo_error", "") or "no se pudo guardar el archivo"
        raise RuntimeError(detalle)
    conocidas = {u["unidad"] for u in listar_unidades(proyecto)}
    return {
        "proyecto": proyecto,
        "unidad": unidad,
        "archivo": fname,
        "visible_en_inicio": unidad in conocidas,
    }

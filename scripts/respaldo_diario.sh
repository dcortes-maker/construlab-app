#!/bin/bash
# Lanza el respaldo completo: primero la base, despues los documentos.
# La base va primero porque es lo que no se puede reconstruir de ninguna otra forma.
# Lo corre a diario com.construlab.respaldo-riviera. Tambien se puede correr a mano.

cd "$(dirname "$0")/.." || exit 1

# En esta Mac es el python del sistema. En GitHub Actions se manda PYTHON_BIN,
# porque ahí las librerias se instalan contra otro interprete.
PY="${PYTHON_BIN:-/usr/bin/python3}"
fallo=0

echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

# PIPESTATUS[0] es el estado de python: el de grep no sirve para saber si fallo.
echo "--- base de datos ---"
"$PY" scripts/respaldo_base_drive.py 2>&1 | grep -v "WARNING streamlit"
[ "${PIPESTATUS[0]}" -eq 0 ] || fallo=1

echo "--- documentos ---"
"$PY" scripts/respaldo_documentos_drive.py 2>&1 | grep -v "WARNING streamlit"
[ "${PIPESTATUS[0]}" -eq 0 ] || fallo=1

if [ "$fallo" -ne 0 ]; then
    echo "ATENCION: el respaldo termino con errores."
else
    echo "Respaldo diario completo."
fi
exit "$fallo"

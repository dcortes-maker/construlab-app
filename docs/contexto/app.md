# ConstruLab — contexto de la app

Revisado: 2026-09-21

ConstruLab es el control de abonos de Riviera Park II y, en la misma base, de Villas del Bosque. En pantalla la marca es ConstruLab. Los recibos salen a nombre de Riviera Park Development S.A. (Las Mañanitas, ventas@gterrabona.com).

Una persona entra, elige el proyecto y trabaja los clientes de ese proyecto. En Inicio, el total en banco es la suma de los abonos del contrato de promesa de pago (CPP) más las reservas de quienes todavía no tienen CPP.

Este archivo se actualiza antes de cada `git push`. Es el mapa que el agente lee al empezar, junto con `AGENTS.md`.

## Plataformas

| Plataforma | Cómo se usa |
|---|---|
| Streamlit | Toda la interfaz. `streamlit run inicio.py`, puerto 8501, tema oscuro en `.streamlit/config.toml`. La app en vivo está en https://construlab-app-5dcduvha8grjn69qbbvcnu.streamlit.app — esa es la dirección que usa el equipo. |
| Supabase | PostgreSQL y los archivos. La app entra con la `service_key` de `.streamlit/secrets.toml`. Ese archivo no va a GitHub. RLS está apagado. |
| GitHub | Código en `dcortes-maker/construlab-app`, rama `main`. Subir ahí es lo que actualiza la app online. El remoto no lleva token en la URL. |
| Google Drive | Construlab → Proyectos → `1. PROYECTO RIVIERA PARK` → `Riviera Par App de abonos`. Una carpeta por apartamento, con su contrato, su anexo y sus recibos. |
| pdfplumber y pypdfium2 | Leen el anexo (PDF o Excel) y arman la vista previa. |
| ReportLab | Dibuja el recibo y el estado de cuenta. |
| openpyxl y pandas | Reportes de Excel y planes `.xlsx`. |
| FastAPI | API para que otras apps suban PDF. El servicio público es Railway (`railway.toml`). |

Los ids de pantalla son `riviera_park_2` y `villas_del_bosque`. En la base se llaman `riviera-park-2` y `villas-del-bosque`.

## Pantallas

El archivo de arranque es `inicio.py`. El resto está en `pages/`.

- **Inicio.** Totales, cuotas pagadas y atrasadas, y si la unidad tiene contrato.
- **Marcar Pagos.** Solo un admin marca, desmarca o anota un abono parcial. Emitir el recibo es otro paso: ahí se gasta el número.
- **Plan de Pagos.** Ver y editar el plan (editar es de admin), cargar un anexo y guardar documentos.
- **Reservas.** Quien pagó separación y todavía no tiene CPP. Agregar y borrar es de admin.
- **Reportes.** Excel de resumen, cuotas del mes, historial, mora, plan por cliente y reservas.
- **Admin.** Hasta 4 admins y 4 usuarios, y las llaves de la API.
- **Mi Cuenta.** Cambiar la propia contraseña.

La sesión dura 30 días en una cookie. Un usuario normal ve y descarga. No marca pagos, no toca reservas y no entra a Admin.

Los admins fijos salen de `secrets.toml`, con la contraseña en texto. Las cuentas creadas en la app viven en la tabla `usuarios`, con la contraseña en hash SHA-256.

## Datos

El detalle de columnas está en `estructura_db.json`. `schema_supabase.sql` es el SQL de referencia.

- **cuotas.** Plan de cada unidad. La columna del concepto se llama `descripcion`.
- **reservas.** Separación de quien aún no tiene CPP. Al guardar su plan, la reserva se borra de esta tabla y, si el monto alcanza, la cuota Reserva o Separación queda pagada.
- **usuarios.** Cuentas creadas en la app.
- **recibos.** Número, cuota, cliente, monto, fecha, forma y estado (`emitido` o `anulado`). El concepto de esta tabla sí se llama `desc`. El número arranca en 1020 y no se reutiliza. El PDF queda en Storage: `recibos/{unidad}/Recibo_{num}.pdf`.
- **contadores.** La fila `nombre = recibo` guarda el último número emitido.
- **api_claves.** Definida en el SQL. Mientras no se cree en el proyecto de Supabase, los hashes viven en Storage, archivo `sistema/api_claves.json`.
- **Storage, bucket privado `adjuntos`.** Una carpeta por unidad. El plan cargado desde la app se llama `Plan_de_Pagos_{archivo}`. Una unidad cuenta con contrato en Inicio cuando algún archivo de su carpeta tiene `contrato` o `cpp` en el nombre.

Al cargar un anexo, una cuota que ya existe (mismo número y la misma descripción) no se vuelve a insertar. Reserva y el primer pago pueden compartir el número 1: se guardan las dos porque el concepto es distinto.

## API de documentos

Otras apps se pegan al servicio FastAPI. En Railway el arranque está en `railway.toml`. En esta Mac, para probar:

```bash
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8600
```

El paquete para esas apps está en el escritorio: `ConstruLab-conexion.zip`.

La llave se crea en Admin → Llaves para otras apps. Se muestra una vez. Se envía así: `Authorization: Bearer cl_…`.

- `GET /v1/salud` — sin llave. Responde que el servicio está vivo.
- `GET /v1/unidades?proyecto=riviera-park-2` — unidades y clientes, para saber a quién pegar el archivo.
- `POST /v1/anexos` — PDF. Lee unidad, cliente y cuotas con el mismo lector de Plan de Pagos. Guarda `Plan_de_Pagos_{archivo}.pdf` y agrega las cuotas nuevas. Si el PDF no trae unidad o nombre, se mandan en el formulario. Si esa unidad estaba en reservas, la reserva pasa al plan igual que en la pantalla.
- `POST /v1/contratos` — PDF más la unidad. Se guarda como `Contrato_{unidad}.pdf`.

Solo PDF, hasta 20 MB. Proyecto por defecto `riviera-park-2`. El otro valor válido es `villas-del-bosque`.

Streamlit Cloud no publica esta API. El host es Railway.

## Copia en Drive

Son dos respaldos que corren juntos todas las noches a las 7:00 p.m. de Panamá, lanzados por `scripts/respaldo_diario.sh`:

- `scripts/respaldo_base_drive.py` — la base de datos. Va primero porque es lo único que no se puede reconstruir de ninguna otra forma. Destino: `1. PROYECTO RIVIERA PARK/Respaldos_Riviera_Park/diario/AAAA-MM-DD/`, con `1. Consultar en Excel` (.csv), `2. Restaurar el sistema` (.json más la estructura de las tablas) y un `LEEME.md` con los conteos del día. Guarda 30 días; el día 1 de cada mes no se borra nunca. Las tablas las pregunta a Supabase, así que una tabla nueva queda respaldada sola.
- `scripts/respaldo_documentos_drive.py` — los PDF, una carpeta por apartamento. No cambió.

Quien lo dispara en esta Mac es `com.construlab.respaldo-riviera` (en `~/Library/LaunchAgents`). El log queda en `/Users/daylincortes/Respaldos_Riviera_Park/diario/salida.log`.

Para escribir dentro de `~/Library/CloudStorage` desde una tarea de launchd, `/bin/bash` necesita Acceso a disco completo en Ajustes del Sistema. Sin ese permiso el proceso puede leer pero no crear ni modificar nada en la carpeta de Drive, y falla con `PermissionError: Operation not permitted`. Por lo mismo, los dos scripts escriben directo al archivo destino: pasar por un `.tmp` y renombrar también está prohibido ahí.

El cron de Railway (`railway.cron.toml`) sigue sin montarse: el proyecto no está creado y falta la cuenta de servicio de Google. Mientras tanto el respaldo depende de que esta Mac esté encendida a las 7:00 p.m.

Railway necesita estas variables, sin subirlas a GitHub:

- `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` — el JSON de una cuenta de servicio de Google, con permiso de editor sobre la carpeta ConstruLab de la unidad compartida
- `DRIVE_FOLDER_ID` — opcional. Si falta, usa la carpeta del proyecto Riviera (`1ATTQPzvtDORoOqMLsMnSjDVdIatFVIF3`). Dentro se crea `Riviera Par App de abonos`.

El mismo repo tiene dos servicios. El de la API lee `railway.toml`. El de respaldo se llama `respaldo-drive`, su config-as-code es `railway.cron.toml`, y su comando termina al acabar. Si ese proceso se queda abierto, Railway no lanza la siguiente noche.

Destino: `1. PROYECTO RIVIERA PARK/Riviera Par App de abonos/{apartamento}/`

En la carpeta de cada apartamento van juntos el contrato, el anexo y los recibos.

- Contrato: el nombre contiene `contrato` o `cpp`. Dos ya estaban como `CPP.pdf` y `1.CPP Javier Tellez.pdf`.
- Anexo: el nombre empieza por `Plan_de_Pagos` o contiene `anexo` o `plan de pago`.
- Recibos con estado `emitido`. Si se anula, el archivo pasa a llamarse `…_ANULADO.pdf`.

`CPP/` y `ABONOS DE CLIENTES/Plan de pagos/` siguen siendo las carpetas armadas a mano. Esta copia no las toca.

Los demás adjuntos (fotos, Word, comprobantes sin esas palabras) se quedan solo en Supabase.

## Qué estaba antes de la app

El control vivía en el Excel `ABONOS DE CLIENTES/CONTROL_ABONOS_RIVIERA_PARK.xlsm`. `migrar_supabase.py` fue la carga única hacia Supabase y no se vuelve a correr. Está en `.gitignore`.

Había un respaldo diario en `~/Respaldos_Riviera_Park/respaldo_diario.py`. Ese archivo ya no está. El respaldo de documentos vive en Railway.

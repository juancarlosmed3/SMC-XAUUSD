# Puente TradingView → MetaTrader 5 (Swissquote)

Servicio FastAPI que recibe las alertas de la estrategia Pine (`pine/poc_cluster_multi_tf.pine`) y envía las órdenes a MT5 con `MetaTrader5.order_send`.

## Requisitos

- **Windows** con el terminal de Swissquote instalado y sesión abierta (el paquete `MetaTrader5` solo existe en Windows).
- En MT5: *Herramientas → Opciones → Asesores expertos* → permitir *Algo Trading*.
- Python 3.10+.

## Ubicación en el PC de trading

El proyecto vive en `C:\Users\juanc\Documents\Ruah Commodities\RNT\Red Cluster POC`. Clona/copia el repo ahí y ejecuta `bridge\run_windows.bat`: crea el venv, instala dependencias, carga `bridge\.env` y levanta uvicorn en el puerto 8000. La ruta tiene espacios, así que si lanzas comandos a mano entrecomíllala.

## Instalación

```powershell
py -m venv .venv
.venv\Scripts\pip install -r bridge\requirements.txt
copy bridge\.env.example bridge\.env   # completar valores
```

Las credenciales se leen de variables de entorno; **nunca** se guardan en el repo. Variables: ver `bridge/.env.example`.

## Ejecución

```powershell
.venv\Scripts\uvicorn bridge.app:app --host 0.0.0.0 --port 8000
```

Empieza con `DRY_RUN=true` para verificar que llegan las alertas sin enviar órdenes.

## Conectar TradingView

TradingView no permite headers personalizados, así que el secreto va en la query:

```
https://tu-dominio/webhook?secret=<WEBHOOK_SECRET>
```

Necesitas exponer el puerto con HTTPS (túnel tipo Cloudflare Tunnel / ngrok, o un reverse proxy). El cuerpo del mensaje de la alerta puede quedar vacío: la estrategia ya envía el JSON desde `alert()`.

## Endpoints

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/health` | Estado y configuración efectiva (sin secretos). |
| POST | `/webhook` | Señal `BUY`/`SELL` → orden a mercado; `event=correction_start` → solo se registra. |

Controles de seguridad: secreto compartido, lista blanca de símbolos (`MT5_SYMBOLS`), tope de lotes (`MAX_LOTS`), volumen ajustado al `volume_step`/`volume_min` del broker y `DRY_RUN`.

## Tests

```bash
python -m pytest tests/
```

Los tests usan un doble de `MetaTrader5`, así que corren en cualquier plataforma.

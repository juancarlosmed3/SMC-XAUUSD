# POC Cluster Multi-TF (XAUUSD / XAGUSD)

Indicador en Pine Script v6 (`poc_cluster_multi_tf.pine`) para TradingView. No ejecuta ordenes ni hace backtest: pinta niveles, marca senales y emite alertas; la ejecucion la hace el puente de `bridge/`.

## Logica

1. **POC por temporalidad**: perfil de volumen sobre las ultimas `profileBars` velas de M1, M5, M15, M30, H1 y H4. El volumen de cada vela se reparte proporcionalmente entre las filas del perfil que atraviesa; el POC es el centro de la fila con mas volumen.
2. **Cluster**: se busca el subconjunto mas numeroso de POC cuyo rango no exceda la tolerancia (puntos fijos o `ATR(14) x factor`). Requiere al menos `minPocsInCluster` POC.
3. **Correcciones (pullbacks)**: con pivotes (`ta.pivothigh`/`ta.pivotlow`) se mide la pierna de impulso; si supera `impulseAtrMult x ATR`, se marca el **inicio de la correccion** en la primera vela que rompe la minima (correccion bajista) o la maxima (correccion alcista) anterior. Ese inicio emite una alerta informativa (`event=correction_start`) y no opera.
4. **Senales** (`entryMode = Pullback`, por defecto): no se senalizan los rallys. Se genera senal cuando la correccion retrocede entre `minRetrace` y `maxRetrace` % del impulso, toca la zona del cluster y el precio reanuda cerrando al otro lado del cluster. Con `entryMode = Rotura directa` se opera el cruce del cluster sin exigir correccion.
5. **Filtros**: SMA 200 define la direccion (solo BUY sobre la SMA, solo SELL debajo) y el volumen debe superar `volMult x` su media de `volLen` velas.
6. **SL/TP**: niveles informativos por multiplos de ATR, incluidos en el payload de la alerta.

## Uso

1. TradingView → Pine Editor → pegar el contenido de `poc_cluster_multi_tf.pine` → *Add to chart*.
2. Recomendado ejecutarlo en M5 o M15 (el TF del grafico solo define cuando se evalua la rotura).
3. Crear la alerta con condicion *"POC Cluster Multi-TF" → Any alert() function call*.
4. Ajustar tolerancia del cluster segun el activo: XAUUSD ≈ 2.0 USD, XAGUSD ≈ 0.05 USD.
5. Requiere plan de TradingView con acceso a datos intradia del broker/feed correspondiente.

## Alertas → MetaTrader 5 (Swissquote)

Cada senal emite un `alert()` con un JSON como:

```json
{"broker":"swissquote","action":"BUY","symbol":"XAUUSD","lots":0.1,"price":2635.40,
 "sl":2630.10,"tp":2646.00,"poc_cluster_low":2634.80,"poc_cluster_high":2635.90,
 "poc_count":5,"sma200":2620.15,"volume":1520,"volume_avg":880,"retrace_pct":41.2,
 "entry_mode":"Pullback","tf":"5","time":"2026-08-07T21:00:00+0000"}
```

Y el aviso de inicio de correccion:

```json
{"event":"correction_start","direction":"DOWN","symbol":"XAUUSD","price":2640.0,
 "impulse_from":2600.0,"impulse_to":2645.0,"poc_cluster_low":2634.8,"poc_cluster_high":2635.9,"tf":"15"}
```

El JSON se envia desde `alert()`, no hace falta escribir nada en el mensaje de la alerta. Apunta la URL del webhook al puente incluido en `bridge/` (ver `bridge/README.md`). TradingView **no** ejecuta ordenes en MT5 por si solo: el puente es obligatorio.

## Notas

- Los perfiles de volumen usan el volumen de tick del feed del broker; con CFD el volumen es indicativo, no volumen real de mercado.
- `profileBars` x `profileRows` altos aumentan el coste de calculo; si TradingView reporta timeout, reducir `profileBars` (p.ej. 100) o `profileRows` (p.ej. 30).
- Backtest en un TF intradia da resultados limitados por el historico disponible en tu plan.

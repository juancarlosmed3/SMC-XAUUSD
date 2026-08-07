# POC Cluster Multi-TF (XAUUSD / XAGUSD)

Estrategia en Pine Script v5 (`poc_cluster_multi_tf.pine`) para TradingView.

## Logica

1. **POC por temporalidad**: perfil de volumen sobre las ultimas `profileBars` velas de M1, M5, M15, M30, H1 y H4. El volumen de cada vela se reparte proporcionalmente entre las filas del perfil que atraviesa; el POC es el centro de la fila con mas volumen.
2. **Cluster**: se busca el subconjunto mas numeroso de POC cuyo rango no exceda la tolerancia (puntos fijos o `ATR(14) x factor`). Requiere al menos `minPocsInCluster` POC.
3. **Entradas**: BUY cuando el cierre supera el techo del cluster (primera vela que lo rompe); SELL cuando cierra por debajo del suelo.
4. **Filtros**: SMA 200 define la direccion (solo BUY sobre la SMA, solo SELL debajo) y el volumen debe superar `volMult x` su media de `volLen` velas.
5. **SL/TP**: multiplos de ATR, configurables.

## Uso

1. TradingView → Pine Editor → pegar el contenido de `poc_cluster_multi_tf.pine` → *Add to chart*.
2. Recomendado ejecutarlo en M5 o M15 (el TF del grafico solo define cuando se evalua la rotura).
3. Ajustar tolerancia del cluster segun el activo: XAUUSD ≈ 2.0 USD, XAGUSD ≈ 0.05 USD.
4. Requiere plan de TradingView con acceso a datos intradia del broker/feed correspondiente.

## Alertas → MetaTrader 5 (Swissquote)

Cada senal emite un `alert()` con un JSON como:

```json
{"broker":"swissquote","action":"BUY","symbol":"XAUUSD","lots":0.1,"price":2635.40,
 "sl":2630.10,"tp":2646.00,"poc_cluster_low":2634.80,"poc_cluster_high":2635.90,
 "poc_count":5,"sma200":2620.15,"volume":1520,"volume_avg":880,"tf":"5","time":"2026-08-07T21:00:00+0000"}
```

Al crear la alerta en TradingView, dejar el mensaje como `{{strategy.order.alert_message}}` no es necesario: el JSON ya se envia desde `alert()`. Configurar la URL del webhook apuntando a tu puente (bridge) que reciba el POST y llame a la API de MT5 (`MetaTrader5.order_send` en Python o un EA con socket/archivo). TradingView **no** ejecuta ordenes en MT5 por si solo: el puente es obligatorio.

## Notas

- Los perfiles de volumen usan el volumen de tick del feed del broker; con CFD el volumen es indicativo, no volumen real de mercado.
- `profileBars` x `profileRows` altos aumentan el coste de calculo; si TradingView reporta timeout, reducir `profileBars` (p.ej. 100) o `profileRows` (p.ej. 30).
- Backtest en un TF intradia da resultados limitados por el historico disponible en tu plan.

# Catálogo de métricas

[English](metrics.md) | [Türkçe](metrics.tr-TR.md) | [Deutsch](metrics.de-DE.md) | [Русский](metrics.ru-RU.md) | [Español](metrics.es-ES.md) | [简体中文](metrics.zh-CN.md) | [日本語](metrics.ja-JP.md)

> Traducción del documento [en inglés](metrics.md), que es la fuente de referencia. Revisión de sincronización: `045796b0c7bbdd21520ccce1c7972495aab929f8`, con fecha `2026-10-22`.

Este catálogo sigue `backend/app/analytics/shared/metrics.py`. Todos los intervalos son inclusivos. «No disponible»
significa que el módulo no puede responder para el archivo o la comparación; «datos insuficientes» significa que no
se alcanza el umbral de la métrica; un «resultado cero» es una respuesta válida sin filas coincidentes. La medida es
siempre **ventas brutas**, nunca ingresos.

| Clave | Nombre en la UI | Fórmula / numerador | Denominador | Ventana, ancla y salvedad |
| --- | --- | --- | --- | --- |
| `first_purchase` | Primera compra | Fecha de pedido más antigua de todo el historial | — | Todo el historial cargado; si no hay pedidos identificados, no está disponible |
| `acquisition_cohort` | Cohorte de adquisición | Mes natural que contiene la primera compra | — | Todo el historial; el mes se representa por su primer día |
| `gross_sales` | Ventas brutas | `SUM(quantity × unit_price)` | — | Intervalo activo; sin ventas devuelve 0 |
| `orders` | Pedidos distintos | `COUNT(DISTINCT order_id)` | — | Intervalo activo; sin pedidos devuelve 0 |
| `units_sold` | Unidades vendidas | `SUM(quantity)` | — | Intervalo activo; sin unidades devuelve 0 |
| `average_order_value` | Valor medio del pedido | Ventas brutas | Pedidos distintos | Intervalo activo; sin pedidos devuelve 0 |
| `change_percent` | Variación porcentual | `(current - comparison) / comparison × 100` | Valor de comparación | Comparación seleccionada; una base cero usa un estado textual y la variación absoluta |
| `product_revenue_share` | Cuota de ventas brutas | Ventas brutas del producto | Ventas brutas totales | Clave de compatibilidad; intervalo activo; no disponible cuando el total es cero |
| `gross_sales_share` | Cuota de ventas brutas | Ventas brutas del producto | Ventas brutas totales | Intervalo activo; no disponible cuando el total es cero |
| `cumulative_share` | Cuota acumulada de ventas brutas | Ventas brutas acumuladas de productos | Ventas brutas totales | Productos en orden descendente; no disponible cuando el total es cero |
| `top_20_percent_share` | Cuota del 20% superior de productos | Ventas brutas de los primeros `ceil(0.2 × product_count)` productos | Ventas brutas totales | Intervalo activo; no disponible cuando el total es cero |
| `products_to_80_percent` | Productos para alcanzar el 80% de las ventas brutas | Prefijo mínimo de productos que cumple el criterio | Ventas brutas totales | Intervalo activo; no disponible cuando el total es cero |
| `product_growth` | Crecimiento de ventas brutas del producto | Ventas brutas actuales menos ventas brutas de comparación | — | Comparación seleccionada; no disponible cuando la base no está disponible |
| `rising_products` | Productos en alza | Recuento con variación positiva de ventas brutas | — | Comparación seleccionada; se muestran signos y palabras, no solo color |
| `falling_products` | Productos a la baja | Recuento con variación negativa de ventas brutas | — | Comparación seleccionada; se muestran signos y palabras, no solo color |
| `new_products` | Productos nuevos | Presentes actualmente, ausentes en la comparación | — | Comparación seleccionada; sin comparación no está disponible |
| `no_current_sales_products` | Productos sin ventas actuales | Presentes en la comparación, ausentes actualmente | — | Comparación seleccionada; sin comparación no está disponible |
| `unchanged_products` | Productos sin cambios | Ventas brutas iguales en ambos periodos | — | Comparación seleccionada; sin comparación no está disponible |
| `growth_rank_absolute_change` | Clasificación del crecimiento del producto | Clasificación por variación absoluta de ventas brutas | — | Comparación seleccionada; las bases pequeñas no dominan |
| `dormancy` | Productos inactivos | Productos cuya distancia entre el ancla y la última venta es al menos la ventana | — | El ancla es el final del intervalo; ventana de 30, 60 o 90 días; el historial puede ser insuficiente |
| `cumulative_revenue_share` | Cuota acumulada de ventas brutas | Ventas brutas acumuladas de productos en orden descendente | Ventas brutas totales | Clave de compatibilidad; intervalo activo; no disponible cuando el total es cero |
| `weighted_unit_price` | Precio unitario realizado ponderado | `SUM(quantity × unit_price)` | `SUM(quantity)` | Intervalo diario/semanal/mensual del rango activo; sin unidades no está disponible; no afirma elasticidad |
| `order_penetration` | Penetración en pedidos | Pedidos que contienen el producto | Todos los pedidos | Intervalo activo; sin pedidos significa resultado cero |
| `basket_support` | Soporte de cesta | Pedidos compartidos de A y B | Pedidos de cesta aptos | Al menos 10 pedidos compartidos y 0.1% de soporte; los pedidos con >100 productos solo se excluyen aquí |
| `basket_confidence` | Confianza de cesta | Pedidos compartidos de A y B | Pedidos que contienen el producto de origen | Mismos umbrales de cesta; la dirección importa |
| `basket_lift` | Lift de cesta | Confianza direccional | Soporte del producto de destino | Mismos umbrales de cesta; compara la tasa observada del par con el soporte del destino |
| `identified_customers` | Clientes identificados | ID de cliente identificados distintos | — | Intervalo activo; ninguno es resultado cero |
| `customer_coverage` | Cobertura de clientes | Pedidos identificados distintos | Todos los pedidos distintos | Cobertura de pedidos del conjunto/intervalo; <50% suprimido, 50–<80% advertencia, ≥80% normal |
| `new_vs_returning` | Ventas brutas de clientes nuevos frente a recurrentes | Ventas brutas identificadas divididas por la primera fecha de pedido del historial completo | — | Intervalo activo; el ancla del primer pedido usa todo el historial |
| `repeat_purchase` | Tasa de compra repetida | Clientes activos con ≥2 pedidos distintos hasta el final | Clientes identificados activos | Cuentan pedidos anteriores al inicio; sin clientes activos los datos son insuficientes |
| `days_between_purchases` | Días entre compras | Mediana de intervalos consecutivos entre fechas de pedidos identificados | — | El pedido posterior debe estar en el intervalo; el intervalo del mismo día es 0; tramos inclusivos fijos |
| `cohort_retention` | Retención de cohortes | Clientes retenidos en cohorte/desfase mensual | Tamaño de la cohorte de todo el historial | El corte es el final seleccionado; las celdas futuras indican «Aún no observado», nunca 0 |
| `historical_customer_value` | Valor histórico del cliente | Ventas brutas identificadas observadas por cliente; mediana del valor por cliente | Clientes identificados | Solo observado, sin pronóstico; la cohorte usa el mes de adquisición de todo el historial |
| `projected_customer_value` | Valor proyectado del cliente a 12 meses | Valor observado más estimación incremental de cohortes maduras | Clientes identificados | Solo estimación: 18 meses de historial, 500 clientes, 70% de cobertura, 5 cohortes maduras, horizonte de 12 meses |
| `rfm` | Segmentos RFM | Puntuaciones relativas por quintiles de recencia, frecuencia y valor monetario; `FM = F + M` | Clientes identificados | Hasta el final seleccionado; menos de 5 es insuficiente; relativo a esta carga, no es referencia universal |
| `rfm_drilldown` | Desgloses de segmentos RFM | Recuentos agregados de segmentos, ventas brutas y distribuciones fijas | Totales de segmentos | Solo agregados; sin ID de clientes; misma salvedad de RFM |
| `purchase_frequency` | Frecuencia de compra | Clientes agrupados por número de pedidos identificados distintos | Clientes identificados hasta el final | Tramos fijos 1, 2, 3, 4, 5, 6–10, 11–20, 21+ |
| `concentration` | Concentración de clientes | Ventas brutas de los primeros `ceil(N / 10)` clientes | Ventas brutas identificadas | Intervalo activo; menos de 10 clientes o ventas cero es insuficiente |

La proyección es una estimación, no una garantía ni una medida causal/de beneficios. Los ID de clientes son seudónimos,
no anónimos; todas las respuestas de clientes son agregadas y no exponen listas, búsquedas, exportaciones ni valores
por cliente.

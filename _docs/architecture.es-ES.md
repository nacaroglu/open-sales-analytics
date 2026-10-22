# Arquitectura

[English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

> Traducción del documento [en inglés](architecture.md), que es la fuente de referencia. Revisión de sincronización: `045796b0c7bbdd21520ccce1c7972495aab929f8`, con fecha `2026-10-22`.

Open Sales Analytics es una aplicación React/Vite de un solo origen servida por FastAPI. El frontend conserva el
identificador del conjunto de datos y el token bearer en el `sessionStorage` de una pestaña del navegador; envía al
backend las opciones de intervalo de fechas y comparación, y representa respuestas agregadas. El backend no mantiene
estado entre solicitudes, salvo un archivo DuckDB por conjunto de datos y una caché de respuestas local al proceso y
de tamaño limitado.

## Dominios del repositorio

| Dominio | Ruta real | Responsabilidad |
| --- | --- | --- |
| API y ciclo de vida | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | Carga/creación de ejemplo, autorización, caducidad, metadatos y envolturas de respuesta |
| Resumen | `backend/app/analytics/overview/` | Ventas brutas, pedidos distintos, unidades, valor medio de pedido, tendencias y comparaciones |
| Productos | `backend/app/analytics/products/` | Clasificaciones, cuota/Pareto, crecimiento, inactividad, historial de precios, penetración y afinidad de cesta |
| Clientes | `backend/app/analytics/customers/` | Cobertura, agregados de clientes, cohortes, RFM y proyección |
| Periodos y disponibilidad compartidos | `backend/app/analytics/shared/` | Filtros de fechas inclusivos, periodos de comparación, elección de intervalos, disponibilidad y definiciones de métricas |
| Importación y persistencia | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | Validar un CSV, crear hechos, escribir el archivo del conjunto de datos y eliminar datos de preparación |
| Interfaz web | `frontend/src/` | Carga, navegación del panel, estados accesibles, tablas y alternativas textuales de gráficos |

Las fórmulas y estados autorizados de las métricas están en `backend/app/analytics/shared/metrics.py`; el catálogo
legible se encuentra en [_docs/metrics.es-ES.md](metrics.es-ES.md). La especificación de producto de Phase 3 está en
[_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md).

## Archivo del conjunto de datos

Cada carga se convierte en un archivo DuckDB privado dentro de `DATASET_DIR`. La importación calcula una sola vez los
hechos reutilizables; las consultas filtran esos hechos durante las solicitudes según el intervalo inclusivo y el
periodo de comparación seleccionados.

| Tabla | Columnas | Significado |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | Líneas de origen validadas; una fila por línea de producto, con el ID opaco de cliente opcional |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | Una fila por pedido y sus totales de líneas/pedido durante toda su vida útil |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | Una fila por producto y los hechos de cartera de toda su vida útil |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | Una fila por cliente identificado; ausente o vacía para datos de seis columnas |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | Identidad, ciclo de vida, verificación del token respetuosa con la privacidad y recuentos de cobertura |

Los bytes de la carga original solo se guardan de forma provisional durante la validación/importación y se eliminan
cuando termina la importación. Las tablas derivadas se eliminan con el conjunto de datos. Los hechos de clientes solo
contienen ID seudónimos y nunca se devuelven como una lista de clientes.

## Flujo de solicitudes

1. `POST /api/datasets` valida el CSV multipart, aplica las reglas de fila y entre filas, crea los hechos de DuckDB,
   guarda únicamente un hash SHA-256 del token y devuelve el ID del conjunto de datos, el token de un solo uso, los
   metadatos y el resumen inicial.
2. `require_dataset` valida la cabecera bearer, el ID del conjunto de datos, la legibilidad del archivo, la caducidad
   y el token antes de ejecutar un controlador de módulo. La autorización se realiza antes de cada solicitud, incluso
   cuando la respuesta está en caché.
3. El controlador resuelve el intervalo activo inclusivo y el modo de comparación, crea una clave de caché y devuelve
   un cuerpo JSON correcto almacenado en caché o abre el conjunto de datos en modo de solo lectura y calcula la
   respuesta del módulo.
4. La respuesta es exclusivamente JSON agregado. La caché solo guarda cuerpos serializados correctos, con una clave
   que contiene el ID del conjunto de datos, el módulo, las fechas activas, el modo de comparación y las opciones del módulo.
5. La caducidad, la eliminación explícita y el barrido de limpieza invalidan las entradas de caché del conjunto de
   datos. La caché es local al proceso, segura entre hilos, está limitada mediante LRU y caduca cada entrada cuando
   llega primero su TTL o la caducidad del conjunto de datos.

## Superficie de la API

Todas las rutas de conjuntos de datos requieren `Authorization: Bearer <token>`, salvo las rutas públicas de estado,
configuración y descarga del ejemplo. El esquema OpenAPI activo es la autoridad; `backend/tests/test_documentation.py`
comprueba esta tabla frente a él.

| Método | Ruta | Autorización | Propósito y opciones principales |
| --- | --- | --- | --- |
| GET | `/api/health` | No | Comprobación de actividad |
| GET | `/api/config` | No | Indicador de demo pública y límites de carga; nunca secretos ni rutas |
| POST | `/api/datasets` | No | Carga multipart; campo de formulario `currency` |
| POST | `/api/datasets/sample` | No | Importar el ejemplo incluido en USD |
| GET | `/api/sample.csv` | No | Descargar el CSV de ejemplo incluido |
| GET | `/api/datasets/{id}` | Sí | Metadatos, capacidades, cobertura y caducidad del conjunto de datos |
| GET | `/api/datasets/{id}/analytics` | Sí | Resumen general heredado; `start`, `end` opcionales |
| DELETE | `/api/datasets/{id}` | Sí | Eliminar el conjunto de datos e invalidar su caché |
| GET | `/api/datasets/{id}/overview` | Sí | KPI de resumen y tendencia; `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | Sí | Análisis de cartera; `start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | Sí | Detalle del producto; `product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | Sí | Agregados de clientes y proyección; `start`, `end`, `comparison` |

## Forma del despliegue

La imagen de Docker compila el frontend en una etapa de Node, instala el entorno del backend con `uv` y ejecuta un
único proceso FastAPI. FastAPI sirve la SPA compilada y `/api` desde el puerto 8000. `DATASET_DIR` debe ser un volumen
persistente privado si los conjuntos de datos deben sobrevivir a un reinicio; no hay una base de datos compartida ni
una capa de escalado horizontal.

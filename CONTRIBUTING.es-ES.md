# Cómo contribuir

[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> Traducción del documento [en inglés](CONTRIBUTING.md), que es la fuente de referencia. Revisión de sincronización: `045796b0c7bbdd21520ccce1c7972495aab929f8`, con fecha `2026-10-22`.

Gracias por ayudar con Open Sales Analytics. Los informes de errores, las ideas y los pull requests son bienvenidos.

## Informar de un error o solicitar una función

Abra un issue con la plantilla **Bug report** o **Feature request**. Para un error, lo más útil es el CSV más pequeño
que lo reproduzca. Nunca adjunte datos reales de clientes: use identificadores inventados de pedidos y clientes.
Informe de los problemas de seguridad de forma privada mediante el botón **Report a vulnerability** de GitHub, en la
pestaña Security, y no en un issue público.

## Cómo se organiza el trabajo

- El trabajo se registra como issues de GitHub, de uno en uno. Cada issue indica su objetivo, los criterios de
  aceptación, lo que queda fuera del alcance y sus restricciones ([`_docs/task-template.md`](_docs/task-template.md)).
- Trabaje en una rama cuyo nombre corresponda al issue, por ejemplo `feature/issue-42-short-name`. Nunca haga commits
  directamente en `main`.
- Un pull request por issue. Se fusiona después de la revisión y cuando pasan las comprobaciones obligatorias de CI.

El proceso completo se encuentra en [`_docs/process.md`](_docs/process.md).

## Configuración

Necesita [uv](https://docs.astral.sh/uv/) y Node 22 o posterior.

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

La sección [Desarrollo](README.es-ES.md#desarrollo) del README explica cómo ejecutar el backend y el frontend.

## Antes de abrir un pull request

Ejecute las comprobaciones que ejecuta CI:

```sh
uv run pytest
uv run ruff check backend
uv run ruff format --check backend
uv run mypy backend/app
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Para un cambio en un recorrido de usuario, ejecute también las pruebas de navegador (`npm run e2e` en `frontend/`;
consulte [Prueba de navegador](README.es-ES.md#prueba-de-navegador)).

## Reglas

- **Pruebas.** El comportamiento nuevo debe incluir pruebas. Lea primero
  [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).
- **UI.** Todo lo que afecte a la interfaz debe respetar [`_docs/design-system.md`](_docs/design-system.md). Si un patrón
  no está contemplado, añada una línea allí en el mismo cambio.
- **Dependencias.** Pregunte en el issue antes de añadir una. Las dependencias se declaran en `pyproject.toml` y
  `frontend/package.json`.
- **Redacción.** La medida es «ventas brutas» (gross sales), nunca «ingresos».
- **Privacidad.** No se pueden registrar ni mostrar tokens, contenido de archivos o identificadores de clientes
  (consulte [Privacidad](README.es-ES.md#privacidad)).

## Licencia

Al contribuir, acepta que sus contribuciones se licencien conforme a la [Apache License 2.0](LICENSE).

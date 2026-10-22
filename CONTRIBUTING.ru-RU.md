# Участие в разработке

[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> Перевод документа [на английском языке](CONTRIBUTING.md), который является источником истины. Версия синхронизации: `045796b0c7bbdd21520ccce1c7972495aab929f8` от `2026-10-22`.

Спасибо, что помогаете Open Sales Analytics. Мы рады сообщениям об ошибках, идеям и pull request.

## Сообщение об ошибке или запрос функции

Создайте issue по шаблону **Bug report** или **Feature request**. При сообщении об ошибке полезнее всего приложить
минимальный CSV, который ее воспроизводит. Никогда не прикладывайте реальные данные клиентов: используйте вымышленные
идентификаторы заказов и клиентов. О проблемах безопасности сообщайте приватно с помощью кнопки GitHub
**Report a vulnerability** на вкладке Security, а не в общедоступном issue.

## Организация работы

- Работа отслеживается в GitHub issues, по одному за раз. В issue указываются цель, критерии приемки, то, что не входит
  в объем работы, и ограничения ([`_docs/task-template.md`](_docs/task-template.md)).
- Работайте в ветке, названной по номеру issue, например `feature/issue-42-short-name`. Никогда не фиксируйте изменения
  непосредственно в `main`.
- Для каждого issue создается один pull request. Он сливается после проверки и успешного прохождения обязательных
  проверок CI.

Полное описание процесса находится в [`_docs/process.md`](_docs/process.md).

## Настройка окружения

Потребуются [uv](https://docs.astral.sh/uv/) и Node 22 или новее.

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

В разделе [Разработка](README.ru-RU.md#разработка) README объясняется, как запустить backend и frontend.

## Перед созданием pull request

Выполните проверки, которые запускает CI:

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

Если изменение затрагивает пользовательский сценарий, также запустите браузерные тесты (`npm run e2e` в `frontend/`,
см. [Браузерный тест](README.ru-RU.md#браузерный-тест)).

## Правила

- **Тесты.** Новое поведение сопровождается тестами. Сначала прочитайте
  [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).
- **UI.** Все изменения UI должны соответствовать [`_docs/design-system.md`](_docs/design-system.md). Если в нем нет
  нужного шаблона, добавьте его описание в тот же набор изменений.
- **Зависимости.** Прежде чем добавлять зависимость, спросите разрешение в issue. Зависимости объявляются в
  `pyproject.toml` и `frontend/package.json`.
- **Терминология.** Показатель называется «валовые продажи» (gross sales), а не «выручка».
- **Конфиденциальность.** Нельзя записывать в журналы или отображать токены, содержимое файлов или идентификаторы
  клиентов (см. [Конфиденциальность](README.ru-RU.md#конфиденциальность)).

## Лицензия

Внося свой вклад, вы соглашаетесь с тем, что ваш вклад распространяется на условиях
[Apache License 2.0](LICENSE).

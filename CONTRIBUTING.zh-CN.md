# 贡献指南

语言：[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> 本译文以[英文原文](CONTRIBUTING.md)为准；同步修订版本 `045796b0c7bbdd21520ccce1c7972495aab929f8`，同步日期 `2026-10-22`。

感谢您帮助改进 Open Sales Analytics。我们欢迎错误报告、想法和拉取请求。

## 报告错误或请求功能

请使用 **Bug report** 或 **Feature request** 模板创建议题。报告错误时，能够复现问题的最小 CSV 最有帮助。切勿附上真实客户数据：请使用虚构的订单 ID 和客户 ID。安全问题请通过 Security 标签页上的 GitHub **Report a vulnerability** 按钮私下报告，不要发布到公开议题中。

## 工作组织方式

- 工作通过 GitHub 议题逐项跟踪。议题会说明目标、验收标准、范围外事项和约束（[`_docs/task-template.md`](_docs/task-template.md)）。
- 在以议题命名的分支上工作，例如 `feature/issue-42-short-name`。切勿直接提交到 `main`。
- 每个议题对应一个拉取请求。通过审查且所有必需的 CI 检查通过后方可合并。

完整流程见 [`_docs/process.md`](_docs/process.md)。

## 环境设置

您需要 [uv](https://docs.astral.sh/uv/) 和 Node 22 或更高版本。

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

README 中的[开发](README.zh-CN.md#开发)章节说明了如何运行后端和前端。

## 创建拉取请求之前

运行 CI 所执行的检查：

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

如果更改了用户流程，还应运行浏览器测试（在 `frontend/` 中运行 `npm run e2e`，参见[浏览器测试](README.zh-CN.md#浏览器测试)）。

## 规则

- **测试。** 新行为必须附带测试。请先阅读 [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md)。
- **UI。** 任何涉及 UI 的内容都必须遵循 [`_docs/design-system.md`](_docs/design-system.md)。若其中未涵盖某种模式，应在同一次更改中补充说明。
- **依赖项。** 添加依赖项之前须在议题中征得同意。依赖项声明于 `pyproject.toml` 和 `frontend/package.json`。
- **措辞。** 指标一律称为“gross sales”（总销售额），不得称为“revenue”（营收）。
- **隐私。** 不得记录或显示令牌、文件内容或客户 ID（参见[隐私](README.zh-CN.md#隐私)）。

## 许可证

提交贡献即表示您同意您的贡献按 [Apache License 2.0](LICENSE) 授权。

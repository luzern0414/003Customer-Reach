# 内置 OpenCLI（定制版）

- 来源：npm `@jackwener/opencli` 1.8.8（https://github.com/jackwener/opencli），Apache-2.0，原许可证见 `LICENSE`。
- 用途：Client Reach 的招投标平台适配器与网页读取/检索运行时；项目不再依赖全局 `npm i -g` 安装。
- 依赖：在本目录执行 `npm install --omit=dev --ignore-scripts`（`node_modules` 不提交）。

## 本项目的修改

| 文件 | 修改 |
|---|---|
| `dist/src/discovery.js` | 新增 `OPENCLI_PLUGIN_DIRS`：从项目目录直接加载插件（同名优先于 `~/.opencli/plugins`），并把插件内 `@jackwener/opencli` 链接到本内置包 |

插件代码在 `src/opencli-plugin/`（插件名 `acq`）。升级 OpenCLI 时先对比上表修改，再替换 `dist/`。

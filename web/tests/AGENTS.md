# 前端本地回归

- 2026-10-09来源卡片测试按ES2022转译，保持Map迭代与真实Vite一致；不使用默认ES3转译误判Map.values为空。浏览器字号验收遍历可见文本节点，覆盖来源抽屉/弹窗；截图等待浮层过渡完成，防止截到仍在屏外的卡片。

2026-10-03，Codex。继承web/AGENTS.md。
- 使用Node原生test runner验证文本工具，不接CI；命令node --test tests/markdown.test.ts。
- 流式Markdown的临时展示处理不可重写持久消息，不可删除代码或最终原文星号。
- 2026-10-09：`node --test tests/company-overview.test.cjs tests/markdown.test.ts`验证最新期/混币种/空金额/非法份额/建设概算与Markdown；使用既有TypeScript转译器加载纯投影，不新增测试依赖。界面仍须真实浏览器核验。

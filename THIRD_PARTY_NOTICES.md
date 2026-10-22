# 开源复用与许可

2026-10-02，Codex。v0.2实际安装许可与对应源码入口已核查。

初代直接安装并调用以下开源库，没有整体复制其他CRM工程：

| 项目 | 本项目复用位置 | 许可与来源 |
|---|---|---|
| LangGraph 1.2.12 / checkpoint-sqlite 3.1.1 | backend/app/agent.py，真实StateGraph、持久checkpoint、BaseStore | MIT，https://github.com/langchain-ai/langgraph |
| LangChain OpenAI 1.6.7 | backend/app/model_gateway.py，bind_tools/function_calling/astream | MIT，https://github.com/langchain-ai/langchain |
| LangSmith 0.14.3 | tracing_context/traceable/Client原生链路，默认正文隐藏 | MIT，https://github.com/langchain-ai/langsmith-sdk |
| markstream-vue 2.0.14 | Home.vue，流式Markdown及HTML escape策略 | MIT，https://github.com/simon-he95/markstream-vue |
| markdown-it / markdown-it-cjk-friendly 3.0.0 | markstream-vue自定义解析器，修复中文标点邻接强调且保留原文 | MIT，各包附LICENSE；https://github.com/markdown-it/markdown-it ，https://github.com/tats-u/markdown-cjk-friendly |
| Trafilatura 2.2.0 | research_tools.py，公开HTML正文提取 | Apache-2.0，https://github.com/adbar/trafilatura |
| jieba 0.42.1 / tiktoken | knowledge.py中文检索 / model_gateway.py预算估算 | MIT，各安装包许可 |
| Element Plus | 表格、表单、抽屉、状态、分页与时间选择 | MIT，https://github.com/element-plus/element-plus |
| Element Plus X / PydanticAI | v0.1历史实现参考；v0.2运行代码已不使用，未重复复制其工程 | MIT，各包许可 |
| Vue / Vue Router / Vite | 前端与路由构建 | MIT，各包自带许可 |
| FastAPI / SQLAlchemy | HTTP接口、SQLite ORM | MIT，各包自带许可 |
| MCP Python SDK | Exa搜索/读取协议适配 | MIT，https://github.com/modelcontextprotocol/python-sdk |
| RapidOCR 3.9.2 / ONNX Runtime 1.30.0 | 本地中文PDF/Word插图OCR | Apache-2.0 / MIT，https://github.com/RapidAI/RapidOCR ，https://github.com/microsoft/onnxruntime |
| python-docx / openpyxl / xlrd 2.0.2 | Word正文顺序与Excel公式/缓存值解析 | MIT / MIT / BSD，官方包自带许可 |
| LibreOffice / Poppler | 通过本机CLI转换DOC与光栅化PDF，不复制其源码 | MPL-2.0及相应组件许可 / GPL，独立安装；分发CLI二进制时保留其许可义务 |
| reportlab 5.0.1 / xlwt 1.3.0 | 本地测试二进制PDF/XLS样例 | BSD，安装包许可 |

PydanticAI bank_support.py 的工具与类型化上下文结构作为实现参考，未复制示例业务逻辑：
https://github.com/pydantic/pydantic-ai/blob/main/examples/pydantic_ai_examples/bank_support.py

调研但未复制源码：LangMem（MIT）、smolagents（Apache-2.0）、Vben Admin（MIT）、Twenty（混合AGPL/商业/MIT子包）、Frappe CRM与EspoCRM（AGPL）。CRM项目仅参考工作流和布局，未引入AGPL源码。LangGraph已经是实际运行引擎，LangMem尚未安装。

本轮参考assistant-ui MIT工具分组/ThreadList理念但沿用Vue实现，没有复制React工程。WorkBuddy官方会话文档与非官方DeepChat界面仅作布局研究；不把非官方DeepChat说成DeepSeek官方实现。未引入PyMuPDF（AGPL/商业）。OCR模型源自PaddleOCR，保留RapidAI/百度相关模型许可与版权，不能把库许可等同于任意模型权利。

2026-10-03另核实下载官方DeepSeek Harness（MIT，developer preview）、openai/codex（Apache-2.0，CLI/app-server协议）、LangChain agent-chat-ui（MIT），位于.codex-tmp/harness-reference，仅参考生命周期/中断/工具配对/交付物投影，未整体移植这些运行时。
版本：Codex 4cedd0caac89f9fdcb5ad385e8093da5363d91c2；DeepSeek Harness 639ed015397290b3745d163aafe02ffee4aa3f84；agent-chat-ui cf72cb0f68a04d24db93eb19afb2d46f3a5261d4。许可原文保留各clone内；不把DeepSeek-R1/V3权重项目与Harness混为一谈，也不宣称Codex Desktop右侧UI已开源。

## MIT 原文（适用于下列版权声明）

Copyright (c) Pydantic Services Inc. 2024 to present

Copyright (c) 2020-PRESENT Element Plus

Copyright (c) 2025 HeJiaYue520

Copyright (c) 2024 LangChain, Inc.

Copyright (c) 2022 Simon He

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

核查链接：
https://github.com/pydantic/pydantic-ai/blob/main/LICENSE
https://github.com/element-plus/element-plus/blob/dev/LICENSE
https://github.com/HeJiaYue520/Element-Plus-X/blob/main/LICENSE

间接依赖的完整许可随各依赖分发；打包对外发布时应同时保留依赖许可。本文件不赋予第三方网站数据的再分发权。

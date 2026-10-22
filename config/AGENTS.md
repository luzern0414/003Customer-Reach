# config 模块约定

- 来源权限、字段用途、限速、保留期和导出规则集中维护在这里。
- 凭据优先环境变量；用户指定config/apikey.txt允许只读加载独立模型及LangSmith Key，不输出、不复制密钥。langsmith.json仅保存enabled/project，不保存Key。
- 修改 schema 或来源门禁时，同步更新文档和测试样例。
- 用户授权完整密钥备份：config/secrets可保存项目相关外部配置的本地副本，只进入AES-256-GCM密文；config/backup-keys为独立恢复钥，只在本地，禁止提交源码或包含在密文内。复制备份不改变原凭据加载路径。
- `marketing_allowed` 默认必须为 `false`；按用户要求真实公开业务联系号码完整展示/导出，调试日志不含完整电话或密钥，系统不自动发销售消息。

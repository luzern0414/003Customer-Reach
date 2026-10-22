# Client Reach 项目约定

- 项目运行方式和架构以 README.md 及各模块 AGENTS.md 为准，业务数据在 data/app；源码不得包含真实 API Key。
- GitLab 使用私有仓库 yitian/Customer-Reach，默认 main，当前开发和完整加密备份放 dev。Git 操作添加 ci.skip，不触发远程流水线。
- 本地 config/apikey.txt 仍是模型与 LangSmith 的凭据来源；config/secrets 保存项目相关外部配置副本，不改变原运行路径。
- config/backup-keys 保存独立恢复钥，仅本地保存，从 Git 及密文归档中排除。backups 保存 AES-256-GCM 密文分片与公开哈希清单；禁止将恢复钥与密文提交到同一仓库。
- 一致性备份先停止本项目 API/Worker，冻结整个 data/app，核验数据库后恢复服务，再归档冻结副本。项目外 junction 只记录目标，不重复归档共享依赖。

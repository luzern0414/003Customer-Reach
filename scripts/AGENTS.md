# scripts 模块约定

- 脚本必须可重复执行、默认不破坏已有文件，并在失败时返回非零退出码。
- 外部仓库下载使用 `opensource-crawlers/bootstrap.ps1` 的 allowlist。
- 脚本不得把真实凭据写入文件，也不得默认运行第三方源码。
- `mcp_probe.py` 是三种已登记服务的只读协议验证客户端；不是可绕过来源门禁的生产采集器。
- MCP 必须区分安装、登记、握手/工具调用通过及当前聊天工具目录可见四种状态；不能以配置文件存在代替真实调用。
- `research/` 是 AI 研究与 Excel 导出工具；只采集公开业务资料，事实需带引文，遇 Exa 429 停止并保留已完成证据。
- 根目录start.ps1/stop.ps1保持UTF8 BOM及隐藏启动，记录runtime/lifecycle.jsonl的service_created/stop_requested、核对后PID、调用者PID及上海时间，不写凭据/环境/任意命令正文。停止意图不代表已确认退出，进程退出码须由句柄实际核验。
- 短时观察脚本只能针对已核对本项目命令/路径的具体PID，保留句柄读取退出码；请求超时不能当进程退出，不以观察失败擅自重启。
- runtime-logs.ps1仅定义Preserve-ServiceLogs；根start确认服务不运行后调用，将固定stdout/stderr移到runtime/archive，保留原字节和唯一时间/GUID名。失败阻止覆盖，已运行服务跳过归档，禁止用清空日志替代保留证据。辅助脚本也保持UTF8 BOM，原生PowerShell5.1测试在backend/tests/test_runtime_logs.py；夹具不启动生产、不递归清理。
- project-backup.py完整枚举隐藏/忽略文件，用标准cryptography AES-256-GCM流式加密并拆分16MiB密文；凭据只进入密文。恢复钥保存在本地config/backup-keys且从归档/源码仓库排除。restore-backup.py先核验密文哈希与GCM认证，之后核验归档逐文件哈希；恢复只能写空目录，不自动建立外部junction。运行中的data/app先停止本项目服务、冻结整体副本、恢复服务后再压缩。
- Windows后台进程继承PIPE时，Python的communicate即使杀死启动器也可能等待子进程EOF；start.ps1和长时Git操作应使用文件日志，Git可直接调用mingw64/bin/git.exe并持有本次进程句柄。GitLab已写入提交以远端ref和blob哈希核验，不能仅凭本地超时认定未上传；确认后再清理本次Git进程树、按固定index续传，不重新采集其他协作者的业务改动。
- autocrlf可能使本地JSON为CRLF、Git内为LF；远端清单raw应与已提交blob逐字节对比并核对JSON语义。密文分片仍必须按原字节核验SHA-256，不能应用文本换行规则。

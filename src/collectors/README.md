# 采集器约定

每个采集器输出统一的原始记录，不直接覆盖 CRM：

```json
{
  "source_id": "example_site",
  "source_uri": "https://example.com/page",
  "captured_at": "2026-09-30T00:00:00Z",
  "raw_payload_ref": "data/raw/example_site/2026-09-30/record.json",
  "license_basis": "待填写：API 合同/公开页面/客户提供",
  "fields": {}
}
```

必须实现限速、重试上限、失败日志、来源链接和停止开关；禁止绕过验证码、登录或技术访问控制。

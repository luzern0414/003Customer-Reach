# 来源适配器

适配器用于把不同来源映射为统一的 `source_record`，不负责营销触达。

当前预留：

- `authorized_enterprise_api`：授权企业信息服务
- `public_company_website`：企业官网公开业务信息
- `public_tender_feed`：授权招投标/采购公告
- `customer_import`：客户主动提供的 CSV/Excel
- `qichacha_authorized`：待确认授权 API 或人工导出，不实现页面绕过
- `alibaba_1688_authorized`：待确认授权接口或人工导出，不实现反爬绕过
- `store_directory_public`：门店目录公开业务字段，需逐站点审核条款

import json
import pytest


def test_structured_quote_resolves_exact_path_and_value():
    from app.qcc_evidence import validate_quote
    body = json.dumps({'企业名称':'合成企业','联系人':{'姓名':'王某'},'items':[{'name':'软件'}]}, ensure_ascii=False)
    assert validate_quote(body, '$.企业名称: 合成企业')
    assert validate_quote(body, '$.items[0].name: 软件')
    assert not validate_quote(body, '$.不存在: 合成企业')
    assert not validate_quote(body, '$.联系人.姓名: 合成企业')
    assert not validate_quote(body, '$.企业名称: 合成')


def test_authorized_qcc_wrong_path_cannot_be_company_identity(client):
    from app.db import Evidence
    from app.company_identity import _candidate
    source=Evidence(id='synthetic',channel='qcc_mcp',kind='授权数据',title='企业授权信息',url='',body='{"name":"另一企业","mention":"合成企业"}',
        source_meta={'origin':'qcc_mcp','authorized':True})
    assert _candidate('合成企业','合成企业',source,'$.name: 合成企业') is None


def test_sdk_text_response_is_unwrapped_without_inventing_fields():
    from app.qcc_mcp import _project_response
    result=type('Result',(),{'content':[type('Text',(),{'text':'{"企业名称":"合成企业"}'})()], 'structured_content':None})()
    assert _project_response(result) == {'企业名称':'合成企业'}


def test_product_and_shareholder_names_are_not_registration_identity(client):
    from app.qcc_evidence import identity_quote
    from app.company_identity import _candidate
    from app.db import Evidence
    body='{"企业名称":"另一公司","产品":[{"name":"查询名"}]}'
    assert identity_quote(body,'查询名')==''
    source=Evidence(id='synthetic',channel='qcc_mcp',kind='授权数据',title='工商信息',url='',body=body,source_meta={'origin':'qcc_mcp','authorized':True})
    assert _candidate('查询名','查询名',source,'$.产品[0].name: 查询名') is None

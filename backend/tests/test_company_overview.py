"""综合页报告期及指定企业附件匹配回归；隔离数据库，模型替身不当真实AI验收。"""
import asyncio
import json
import uuid
import pytest


@pytest.mark.parametrize('period,expected', [
    ('2025-01-01至2025-12-31', 'annual'),
    ('2026-01-01至2026-06-30', 'half_year'),
    ('2026-01-01至2026-03-31', 'as_of'),
    ('2026-06-30', 'as_of'),
    ('2025-01-01至2026-06-30', 'as_of'),
    ('2026年第一季度', 'quarter'),
    ('2026年上半年/期末2026-06-30', 'half_year'),
])
def test_explicit_revenue_interval(period, expected):
    """period是显式报告期，expected是正确口径；不凭截至6月时点推导半年度。"""
    from app.company_models import CompanyFact
    from app.company_service import fact_view
    row = CompanyFact(unique_key=uuid.uuid4().hex, company_id='isolated-period', field='revenue',
        label='营业收入', raw_value='123', numeric_value=123, unit='元', raw_unit='元',
        report_period=period, provenance={}, status='verified')
    assert fact_view(row)['period_kind'] == expected


def test_company_match_context_preserves_facts_plans_and_sources(client):
    """client为专用QA接口；匹配输入只来自所选持久企业，计划不成为成交，未知不补零。"""
    from app.company_service import company_match_context
    ids = client.post('/api/companies/import-history').json()['company_ids']
    detail = client.get('/api/companies/' + ids[0]).json()
    context = json.loads(company_match_context(ids[0]))
    assert context['company_name'] == detail['header']['name']
    assert len(company_match_context(ids[0])) <= 22000
    assert context['facts'] and context['sources']
    assert all(row['record_kind'] == 'plan' for row in context['projects'])
    assert any(row['budget'] == 17571600 for row in context['projects'])
    assert any(row['quantity'] is None for row in context['projects'])
    assert all(row['source_ids'] for row in context['facts'])
    assert context['coverage']['selected_facts'] <= context['coverage']['total_facts']
    assert '不证明当前购买意向' in context['limitations'][0]
    with pytest.raises(Exception, match='企业不存在'):
        company_match_context('missing-overview-company')


def test_product_match_runs_document_graph_with_bound_company(client, monkeypatch):
    """client为隔离API，monkeypatch只替模型；真实提交/附件/图/结果验证不进入搜索和事实保存。"""
    from app import agent
    from app.db import Session, Job
    from langchain_core.messages import AIMessageChunk
    cid = client.post('/api/companies/import-history').json()['company_ids'][0]
    company = client.get('/api/companies/' + cid).json()['header']['name']
    attachment = client.post('/api/attachments', files={'file': ('QA产品资料.txt', '隔离测试产品：智慧仓储软件QA-WMS，支持库存和物料管理。'.encode())}).json()
    conv = client.post('/api/conversations').json()['id']
    payload = {'content': '只读取已上传产品资料，不要搜索或寻找其他客户。结合目标企业已归档资料分析产品匹配度和购买意向线索。',
        'attachment_ids': [attachment['id']], 'client_token': uuid.uuid4().hex, 'company_id': cid, 'query_mode': 'company_match'}
    job = client.post('/api/conversations/' + conv + '/messages', json=payload).json()
    assert job['metrics']['target_company_id'] == cid
    assert client.post('/api/conversations/' + conv + '/messages', json=payload).json()['id'] == job['id']
    before = client.get('/api/companies/' + cid).json()['header']['fact_count']
    class Chat:
        async def astream(self, messages):
            prompt = messages[-1].content
            assert company in prompt and 'QA-WMS' in prompt and '17571600' in prompt
            assert '目标企业已归档公开资料' in prompt and '不得生成购买概率' in prompt
            assert 'quote' in prompt and 'source_ids' in prompt
            yield AIMessageChunk(content='隔离模型替身：产品方向与仓储计划相关；需核验外购范围，不能确认订单。')
    async def forbidden(*args, **kwargs):
        raise AssertionError('产品匹配错误进入公开搜索或企业事实写入')
    monkeypatch.setattr(agent, 'model', lambda: Chat())
    # 当前并发升级增加模型意图节点；只替其模型判断，实际图与作用域门禁仍执行。
    from app import intent
    from app.company_research_schemas import IntentDecision
    async def document_intent(state):
        # 模型误分类为企业查询也不能扩大用户选择的文件匹配范围。
        return IntentDecision(intent='company_query', research_prompt=state['prompt'], title='产品匹配')
    monkeypatch.setattr(intent, 'recognize_intent', document_intent)
    from app import model_gateway
    def unexpected_model(*args, **kwargs):
        """外部模型构造须被本用例明确替身覆盖；漏掉新入口时立即失败，避免误发真实请求。"""
        raise AssertionError('文件匹配夹具意外调用外部模型')
    monkeypatch.setattr(model_gateway, 'model', unexpected_model)
    for name in ['profile_node', 'plan_node', 'search_node', 'read_node', 'extract_node', 'save_node', 'learn_node']:
        monkeypatch.setattr(agent, name, forbidden)
    with Session.begin() as db: db.get(Job, job['id']).status = 'running'
    asyncio.run(agent.run_job(job['id']))
    final = client.get('/api/jobs/' + job['id']).json()
    assert final['status'] == 'completed'
    assert final['metrics']['company_match_context'] is True
    assert final['metrics']['intent'] == 'document' and final['metrics']['model_intent'] == 'company_query'
    assert set(final['metrics']['stage_timings']) == {'intent', 'context', 'answer'}
    assert client.get('/api/companies/' + cid).json()['header']['fact_count'] == before
    analysis = client.get('/api/companies/' + cid).json()['purchase_analysis']
    assert analysis['job_id'] == job['id'] and analysis['origin'] == 'model_document_match'
    assert '隔离模型替身' in analysis['content'] and analysis['source_as_of']
    assert any('隔离模型替身' in message['content'] for message in client.get('/api/conversations/' + conv).json()['messages'])

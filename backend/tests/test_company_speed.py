"""提速保持真实预算、事务、引用和后台重放；外部请求明确替身，不冒称公网验收。"""
import asyncio
import time
import uuid
import pytest
from sqlalchemy import select
from test_research_pipeline_v3 import make_job


def test_latest_results_sorted_before_pagination(client):
    """更新时间优先于集团类型/采购数量，分页后的第二条仍保持稳定顺序。"""
    from app.db import Session
    from app.company_service import ensure_company
    suffix=uuid.uuid4().hex
    with Session.begin() as db:
        older=ensure_company(db,'排序'+suffix+'集团',view_scope='group');older.updated_at='2026-01-01 00:00:00'
        newer=ensure_company(db,'排序'+suffix+'有限公司');newer.updated_at='2026-10-09 21:00:00';nid=newer.id;oid=older.id
    assert client.get('/api/companies',params={'q':suffix,'page_size':1}).json()['items'][0]['id']==nid
    assert client.get('/api/companies',params={'q':suffix,'page_size':1,'page':2}).json()['items'][0]['id']==oid


def test_independent_searches_overlap(client,monkeypatch):
    """两个检索都已开始才允许返回，确保真实调度并行且只读每方向一个优先页面。"""
    from app import company_research
    starts=[];reads=[]
    async def run():
        both=asyncio.Event()
        class Broker:
            async def execute(self,name,args):
                if name=='search_accounts':
                    starts.append(args['query'])
                    if len(starts)==2:both.set()
                    await asyncio.wait_for(both.wait(),1)
                    return {'sources':[{'id':str(len(starts))+args['query'],'url':'https://example.com/'+args['query'],'title':'测试企业','body':'正文'}]}
                reads.append(args['url']);return {'sources':[]}
        monkeypatch.setattr(company_research,'broker_for',lambda state:Broker())
        return await company_research.company_collect({'job_id':'isolated','prompt':'查询测试企业','company_targets':['测试企业'],
            'steps':[{'entity_name':'测试企业','query':'企业简介','channel':'official'},{'entity_name':'测试企业','query':'企业采购','channel':'official'}],
            'options':{'research_pages_per_query':4}})
    result=asyncio.run(run())
    assert result['cursor']==2 and len(starts)==2 and len(reads)==2


def test_queued_search_respects_new_provider_cooldown_without_attempt(client,monkeypatch):
    """第三路在门外排队；前两路限流后不发送第三路且不占检索额度。"""
    from app import research_tools
    from app.db import Session,ToolCall
    from app.source_errors import SourceRateLimit
    job=make_job(client);sent=[]
    async def network(tool,args):
        sent.append(args['query']);await asyncio.sleep(.03)
        raise SourceRateLimit(delay=30)
    monkeypatch.setattr(research_tools,'call_exa',network)
    async def run():
        broker=research_tools.ToolBroker(job['id'],{'enabled_channels':['official'],'max_searches':3,'max_reads':2}, {})
        return await asyncio.gather(*(broker.execute('search_accounts',{'query':'并发检索'+str(i),'channel':'official'}) for i in range(3)))
    try:
        result=asyncio.run(run());assert len(sent)==2 and all(item['error']=='provider_rate_limited' for item in result)
        with Session() as db:assert len(list(db.scalars(select(ToolCall).where(ToolCall.job_id==job['id'],ToolCall.tool=='search_accounts'))))==2
    finally:
        with Session.begin() as db:
            for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job['id'])):row.retry_after_epoch=0


def test_separate_procurement_buyer_and_quantity_quotes_commit_with_sources(client):
    """相隔段落独立引用可以落项目；伪造买方片段仍拒绝，首批计时只在业务提交后存在。"""
    from app.db import Session,Evidence,Job
    from app.company_validation import save_snapshot
    from app.company_research_schemas import CompanySnapshot,ResearchProject
    from app.source_models import EntrySourceBinding,SourceFragment
    name='分段采购'+uuid.uuid4().hex+'有限公司';job=make_job(client,'查询'+name)
    identity='企业名称：'+name+'。';title='测试设备采购招标公告';project_quote=title+'\n项目编号：T20261009'
    buyer='1.6、采购人：'+name;quantity='采购数量：2台'
    with Session.begin() as db:
        source=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title=title,kind='网页正文',
            body='\n'.join([identity,project_quote,'独立条款。'*40,quantity,buyer]))
        db.add(source);db.flush();sid=source.id
    item=ResearchProject(buyer_name=name,title=title,project_number='T20261009',stage='open',quantity=2,unit='台',
        source_id=sid,quote=project_quote,buyer_quote=buyer,quantity_quote=quantity)
    result=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=identity,projects=[item]),{sid},[name])
    assert result['accepted_fields']==1 and not result['rejected']
    with Session() as db:
        assert db.get(Job,job['id']).metrics['first_verified_result_ms']>0
        spans=list(db.execute(select(EntrySourceBinding.role,SourceFragment.text).join(SourceFragment,EntrySourceBinding.fragment_id==SourceFragment.id)
            .where(EntrySourceBinding.project_id==result['accepted_refs'][-1]['id'])))
        assert ('buyer',buyer) in spans and ('quantity',quantity) in spans
    item.buyer_quote='采购人：错误买方有限公司'
    second=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=identity,projects=[item]),{sid},[name])
    assert second['accepted_fields']==0 and second['rejected']


def test_read_budget_exhaustion_records_review_before_answer(client):
    """计划未完成但读取耗尽也必须保存真实停止原因，不能从图直接消失。"""
    from app.db import Session,ToolCall
    from app.company_models import ResearchDataset
    from app.company_research import company_gap
    job=make_job(client)
    with Session.begin() as db:db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',status='completed',attempts=1))
    output=asyncio.run(company_gap({'job_id':job['id'],'prompt':job['prompt'],'options':{'max_reads':1,'max_searches':4},
        'company_targets':['测试企业'],'steps':[{'query':'待执行'}],'cursor':0}))
    assert output['company_stop_reason']=='tool_budget_exhausted'
    with Session() as db:assert db.scalar(select(ResearchDataset).where(ResearchDataset.job_id==job['id'],ResearchDataset.phase=='review')).payload['stop_reason']=='tool_budget_exhausted'


def test_deferred_clean_restarts_from_persisted_source_and_failure_is_visible(client,monkeypatch):
    """无内存任务也能重放清洗，重复执行幂等；出错保留failed，不宣称沉淀成功。"""
    from app import research_dataset
    from app.db import Session,Evidence,serialize
    from app.company_models import ResearchDataset
    job=make_job(client)
    with Session.begin() as db:
        row=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title='后台清洗测试',body='原始摘要100万元。',kind='搜索摘录')
        db.add(row);db.flush();source=serialize(row)
    did=research_dataset.defer_clean(job['id'],source)
    assert research_dataset.drain_deferred()>0 and research_dataset.defer_clean(job['id'],source)==did
    with Session() as db:
        row=db.get(ResearchDataset,did);assert row.payload['cleaned_body']=='原始摘要100万元。' and not row.payload['has_full_text']
    source={**source,'id':uuid.uuid4().hex}
    failed=research_dataset.defer_clean(job['id'],source);research_dataset.drain_deferred()
    with Session() as db:assert db.get(ResearchDataset,failed).status=='failed'


def test_grounding_binds_real_identity_and_omits_only_invalid_optional_project_fields(client):
    """错误编号身份从同源完整原名绑定；模型伪造表格不入库，真实项目与买方仍可完整核验。"""
    from app.db import Session,Evidence
    from app.company_research import ground_batch,company_save
    from app.company_research_schemas import CompanyBatch,CompanySnapshot,ResearchProject
    name='身份绑定'+uuid.uuid4().hex+'有限公司';job=make_job(client,'查询'+name)
    title='动力设备采购招标公告';buyer='采购人：'+name;number='采购号：CG202610099'
    with Session.begin() as db:
        row=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title=title,kind='网页正文',body='\n'.join([name,title,number,buyer,'数量：1套','独立原文。'*40]))
        db.add(row);db.flush();sid=row.id
    batch=CompanyBatch(companies=[CompanySnapshot(name=name,source_id=sid,identity_quote='模型改写企业名：'+name,
        projects=[ResearchProject(buyer_name=name,title=title,project_number='CG202610099',project_number_quote=number,
            source_id=sid,quote=title,buyer_quote=buyer,quantity=1,unit='套',quantity_quote='|数量|1套|',metadata_quote=number+'\n|数量|1套|',stage='open')])])
    repaired,changes=ground_batch(batch,[name],[])
    assert repaired.companies[0].identity_quote==name and repaired.companies[0].projects[0].quantity is None
    assert changes and batch.companies[0].projects[0].quantity==1
    result=asyncio.run(company_save({'job_id':job['id'],'prompt':job['prompt'],'options':{'enabled_channels':['official'],'max_searches':1,'max_reads':1},
        'source_ids':[sid],'company_targets':[name],'company_batches':[repaired.companies[0].model_dump()]}))
    assert result['company_ids'] and result['company_updates']==1
    from app.db import Job,Message,JobEvent
    with Session() as db:
        row=db.get(Job,job['id']);assert row.metrics['first_answer_ms']>0
        assert '首批资料已保存' in db.get(Message,row.reply_message_id).content
        assert len(list(db.scalars(select(JobEvent).where(JobEvent.job_id==job['id'],JobEvent.event_type=='message.delta'))))==1


def test_original_deadline_preserves_precision_and_rejects_publication_mixups():
    """截止24:00不编造次日，下载期/计划日不能当公告发布时间；不同截止有歧义则不自动提取。"""
    from app.company_validation import original_deadline,notice_date
    from app.service import ServiceError
    assert original_deadline('五、投标截止时间：2021年1月26日24:00:00。')[0]=='2021-01-26'
    assert original_deadline('投标截止时间：202 3年 1月 3日23:59:59')[0]=='2023-01-03 23:59:59'
    assert original_deadline('投标截止日期：2023年1月3日；投标截止日期：2023年1月4日')==('','')
    with pytest.raises(ServiceError):notice_date('2022-12-28','计划于2022年12月28日发布招标需求','publication')


def test_reprinted_notice_merges_only_with_same_verified_buyer_title_deadline(client):
    """同截止跨域转载合成一个项目，另一截止仍独立；无截止不凭相似标题猜重购。"""
    from app.db import Session,Evidence
    from app.company_research_schemas import CompanySnapshot,ResearchProject
    from app.company_validation import save_snapshot
    from app.company_models import ProcurementProject
    name='转载验证'+uuid.uuid4().hex+'有限公司';job=make_job(client);title='商务车采购招标公告';identity='企业名称：'+name;buyer='采购人：'+name
    ids=[]
    for index,deadline in enumerate(['2023-01-03','2023-01-03 23:59:59','2023-02-03 23:59:59']):
        date=deadline.split(' ')[0];quote='投标截止时间：'+(deadline+' 23:59:59' if len(deadline)==10 else deadline)
        with Session.begin() as db:
            source=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title=title,kind='网页正文',body='\n'.join([identity,'关于'+title,title,buyer,quote,'独立测试说明。'*30]))
            db.add(source);db.flush();sid=source.id
        result=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=identity,projects=[ResearchProject(
            buyer_name=name,title='关于'+title if index==1 else title,source_id=sid,quote=title,buyer_quote=buyer,deadline=deadline,deadline_quote=quote,stage='open')]),{sid},[name])
        assert not result['rejected'];ids.append(result['accepted_refs'][-1]['id'])
    assert ids[0]==ids[1] and ids[2]!=ids[0]
    from app.company_models import ProcurementNotice
    with Session() as db:
        assert len(list(db.scalars(select(ProcurementNotice).where(ProcurementNotice.project_id.in_(ids)))))==2


def test_group_footer_contact_cannot_borrow_buyer_identity(client):
    """集团页尾与采购人联系块分开，即使页面有完整买方名也不能借集团电话。"""
    from app.db import Session,Evidence
    from app.company_research_schemas import CompanySnapshot,ResearchFact
    from app.company_validation import save_snapshot
    name='集团页脚验证'+uuid.uuid4().hex+'有限公司';job=make_job(client);identity='企业名称：'+name
    quote='电话：0591-83682412';body='福建测试集团股份有限公司\n'+quote+'\n'+identity+'\n采购人：'+name+'\n本采购要求。'*50
    with Session.begin() as db:
        source=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title='福建测试集团股份有限公司',kind='网页正文',body=body)
        db.add(source);db.flush();sid=source.id
    result=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=identity,facts=[ResearchFact(field='phone',label='电话',
        value='0591-83682412',source_id=sid,quote=quote)]),{sid},[name])
    assert result['accepted_fields']==0 and result['rejected']


def test_parallel_pause_cancels_siblings_and_blocks_resume_until_cleanup(client):
    """兄弟抑制取消时有持久清理标志，恢复409；释放后标志归零，没有无界等待。"""
    from app.research_tools import parallel,Paused
    from app.db import Session,Job
    job=make_job(client)
    async def run():
        ready=asyncio.Event();release=asyncio.Event();finished=asyncio.Event()
        async def pause():await ready.wait();raise Paused()
        async def late():
            ready.set()
            try:await release.wait()
            except asyncio.CancelledError:await release.wait()
            finally:finished.set()
        with pytest.raises(Paused):await parallel([pause(),late()],job['id'])
        with Session.begin() as db:db.get(Job,job['id']).status='paused'
        assert client.post('/api/jobs/'+job['id']+'/resume').status_code==409
        release.set();await asyncio.wait_for(finished.wait(),1);await asyncio.sleep(.02)
        with Session() as db:assert db.get(Job,job['id']).metrics.get('pending_cleanup')==0
    asyncio.run(run())


def test_explicit_related_target_becomes_visible_without_admitting_procurement_as_products(client):
    """既有关联主体查询后可见；采购设备和未来拓展产品仍拒绝为当前产品能力。"""
    from app.db import Session,Evidence
    from app.company_service import ensure_company
    from app.company_research_schemas import CompanySnapshot,ResearchFact
    from app.company_validation import save_snapshot
    name='关联可见'+uuid.uuid4().hex+'有限公司';job=make_job(client,'查询'+name);identity='企业名称：'+name
    quotes=['本项目的柴油发电机组拟采购。','未来5年内，公司将重点拓展海洋工程船。']
    with Session.begin() as db:
        company=ensure_company(db,name,visibility='related')
        source=Evidence(job_id=job['id'],url='https://example.com/'+uuid.uuid4().hex,title=name,kind='网页正文',body=identity+'\n'+'\n'.join(quotes)+'独立可见性验证。'*30)
        db.add(source);db.flush();sid=source.id
    result=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=identity,facts=[
        ResearchFact(field='products',label='设备',value='柴油发电机组',source_id=sid,quote=quotes[0]),
        ResearchFact(field='products',label='未来产品',value='海洋工程船',source_id=sid,quote=quotes[1])]),{sid},[name])
    assert result['accepted_fields']==0 and len(result['rejected'])==2
    assert client.get('/api/companies',params={'q':name}).json()['total']==1

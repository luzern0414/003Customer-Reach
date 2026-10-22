"""研究保存与条目片段的同事务集成；隔离夹具不代表真实企业采购。"""
import uuid
import pytest
from sqlalchemy import select
from app.db import Session,Conversation,Job,Evidence
from app.company_models import Company,CompanyRelation,ProcurementProject,ProcurementNotice
from app.company_research_schemas import CompanySnapshot,ResearchRelation,ResearchProject
from app.company_validation import save_snapshot
from app.source_models import SourceDocument,SourceFragment,EntrySourceBinding


def sources(name):
    """name为隔离测试企业完整名；返回一个Job和两个不同原文/URL的真实数据库来源ID。"""
    identity='企业名称：'+name+'。';counterparty='引用测试供应商有限公司'
    quotes=[f'2025年采购供应商{counterparty}100元人民币。',f'2025年向供应商{counterparty}采购，金额100元人民币。']
    metadata=['2025年第一份报告的本企业采购口径。','2025年第二份报告的本企业采购口径。']
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush()
        job=Job(conversation_id=conv.id,client_token=uuid.uuid4().hex,prompt='研究'+name);db.add(job);db.flush()
        rows=[]
        for quote,meta in zip(quotes,metadata):
            row=Evidence(job_id=job.id,url='https://example.com/'+uuid.uuid4().hex,title=name,kind='网页正文',
                body=identity+quote+meta+('本地条目引用集成验证夹具。'*20))
            db.add(row);db.flush();rows.append(row.id)
    return job.id,rows,identity,counterparty,quotes,metadata


def test_reconfirmed_relation_keeps_each_sources_own_spans_and_url(client):
    """重复业务值合并记录，但新来源自己的value/metadata必须独立绑定，不能复制旧metadata。"""
    name='条目引用'+uuid.uuid4().hex+'有限公司';jid,ids,identity,counterparty,quotes,metadata=sources(name)
    snapshots=[CompanySnapshot(name=name,source_id=sid,identity_quote=identity,relations=[ResearchRelation(counterparty_name=counterparty,
        relation_type='supplier',report_period='2025',amount='100',unit='元',currency='CNY',source_id=sid,quote=quote,metadata_quote=meta)])
        for sid,quote,meta in zip(ids,quotes,metadata)]
    first=save_snapshot(jid,snapshots[0],set(ids),[name]);second=save_snapshot(jid,snapshots[1],set(ids),[name])
    assert first['new_records']==1 and second['reconfirmed_records']==1
    assert second['accepted_refs'][-1]['url'].startswith('https://example.com/') and set(second['accepted_refs'][-1]['source_ids'])==set(ids)
    with Session() as db:
        relation=db.scalar(select(CompanyRelation).where(CompanyRelation.company_id==first['company_id']))
        assert len(list(db.scalars(select(CompanyRelation).where(CompanyRelation.company_id==first['company_id']))))==1
        citations=relation.payload['source_citations']
        assert {(c['source_id'],c['quote'],c['role']) for c in citations}=={(ids[0],quotes[0],'value'),(ids[0],metadata[0],'metadata'),
            (ids[1],quotes[1],'value'),(ids[1],metadata[1],'metadata')}
        rows=list(db.execute(select(EntrySourceBinding.role,SourceFragment.text).join(SourceFragment,EntrySourceBinding.fragment_id==SourceFragment.id)
            .join(SourceDocument,SourceFragment.document_id==SourceDocument.id).where(EntrySourceBinding.relation_id==relation.id,SourceDocument.evidence_id==ids[1])))
        assert set(rows)=={('value',quotes[1]),('metadata',metadata[1])}
    third=save_snapshot(jid,snapshots[1],set(ids),[name])
    assert third['source_bindings']=={'documents':0,'fragments':0,'bindings':0}


def test_binding_failure_rolls_back_company_and_preserves_original_evidence(client,monkeypatch):
    """片段关联失败不能留下只有事实没有证据的企业；已归档Evidence保留供恢复。"""
    from app import source_service
    name='事务引用'+uuid.uuid4().hex+'有限公司';jid,ids,identity,_,_,_=sources(name)
    original=source_service.bind_company_sources
    def fail(db,company_id):
        original(db,company_id)
        raise RuntimeError('明确标记的绑定失败夹具')
    monkeypatch.setattr(source_service,'bind_company_sources',fail)
    with pytest.raises(RuntimeError):save_snapshot(jid,CompanySnapshot(name=name,source_id=ids[0],identity_quote=identity),set(ids),[name])
    with Session() as db:
        assert db.scalar(select(Company.id).where(Company.name==name)) is None
        assert all(db.get(Evidence,sid) for sid in ids)
        assert db.get(Job,jid).company_ids==[]
        assert not list(db.scalars(select(SourceDocument).where(SourceDocument.evidence_id.in_(ids))))


def test_group_research_binds_subsidiary_projects_to_actual_buyer(client):
    """集团已有明确子公司关系时，接受的子公司项目和公告必须同事务形成该买方的条目片段。"""
    from app.company_service import ensure_company
    suffix=uuid.uuid4().hex;name='集团引用'+suffix+'有限公司';child_name='子公司引用'+suffix+'有限公司'
    identity='企业名称：'+name+'。';relation_quote=name+'控股子公司'+child_name+'。'
    project_quote='隔离采购项目，采购公告：采购人'+child_name+'。'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,client_token=suffix,prompt='研究'+name);db.add(job);db.flush()
        source=Evidence(job_id=job.id,url='https://example.com/'+suffix,title='隔离采购公告',kind='网页正文',
            body=identity+relation_quote+project_quote+('集团与子公司证据绑定隔离验证。'*20))
        db.add(source);db.flush();sid=source.id;jid=job.id
        parent=ensure_company(db,name,view_scope='group');child=ensure_company(db,child_name,visibility='related');child_id=child.id
        db.add(CompanyRelation(unique_key=suffix,company_id=parent.id,counterparty_name=child_name,counterparty_id=child.id,
            relation_type='subsidiary',source_ids=[sid],quote=relation_quote))
    result=save_snapshot(jid,CompanySnapshot(name=name,source_id=sid,identity_quote=identity,
        projects=[ResearchProject(buyer_name=child_name,title='隔离采购项目',project_number='',stage='open',source_id=sid,quote=project_quote)]),{sid},[name])
    assert result['accepted_fields']==1 and result['rejected']==[]
    with Session() as db:
        project=db.scalar(select(ProcurementProject).where(ProcurementProject.buyer_id==child_id));assert project
        notice=db.scalar(select(ProcurementNotice).where(ProcurementNotice.project_id==project.id));assert notice
        assert db.scalar(select(EntrySourceBinding.id).where(EntrySourceBinding.company_id==child_id,EntrySourceBinding.project_id==project.id))
        assert db.scalar(select(EntrySourceBinding.id).where(EntrySourceBinding.company_id==child_id,EntrySourceBinding.notice_id==notice.id))

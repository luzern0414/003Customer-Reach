"""所有测试先配置隔离SQLite及上传/checkpoint目录，绝不接触真实CRM数据。"""
import os
import uuid
from pathlib import Path
import pytest

task_tmp=Path(__file__).resolve().parents[2]/'.codex-tmp/tests'
task_tmp.mkdir(parents=True,exist_ok=True)
os.environ['CLIENTREACH_DATABASE_URL']='sqlite:///'+str(task_tmp/(uuid.uuid4().hex+'.db'))
os.environ['CLIENTREACH_DATA_DIR']=str(task_tmp/('files-'+uuid.uuid4().hex))
# 用户已配置真实追踪凭据，普通回归必须保持离线；专项追踪测试自行指定本机收集器与夹具密钥。
os.environ['LANGSMITH_TRACING']='false'
# 招投标平台采集访问真实站点，普通回归关闭；专项测试替换采集器验证图集成。
os.environ['CLIENTREACH_TENDER_ENABLED']='false'
os.environ['CLIENTREACH_QCC_ENABLED']='false'
os.environ['CLIENTREACH_BIDRESEARCH_ENABLED']='false'
# Exa失败时的OpenCLI百度/搜狗兜底会启动真实浏览器，普通回归关闭。
os.environ['CLIENTREACH_SEARCH_FALLBACK']='false'


@pytest.fixture(autouse=True)
def intent_decision(monkeypatch, request):
    """普通回归替外部意图适配器，保留生产节点；配置可覆盖决策，real_intent标记测试真实缓存边界。

    旧规则仅用于历史测试夹具，不参与生产路由。返回可变配置；外部调用专门验收单独执行。
    """
    if request.node.get_closest_marker('real_intent'):
        yield {}
        return
    from app import intent
    from app.company_research_schemas import IntentDecision
    config={}
    async def recognize(state):
        if config:return IntentDecision(**config)
        from app.conversation import mode,company_request,short_title
        from app.db import Session,Job,serialize
        from sqlalchemy import select
        with Session() as db:
            job=db.get(Job,state['job_id'])
            previous=[serialize(row) for row in db.scalars(select(Job).where(Job.conversation_id==job.conversation_id,Job.id!=job.id).order_by(Job.created_at.desc()).limit(3))]
            attachments=job.attachment_ids
        prompt=company_request(state['prompt'],attachments,previous)
        return IntentDecision(intent='company_query' if prompt else mode(state['prompt'],attachments),
            research_prompt=prompt or state['prompt'],title=short_title(prompt or state['prompt']),requested_fields=['name','industry','business'] if prompt else [])
    monkeypatch.setattr(intent,'recognize_intent',recognize)
    yield config


def pytest_configure(config):
    """config为pytest运行配置；登记专门意图适配测试标记，避免普通回归调用真实服务。"""
    config.addinivalue_line('markers','real_intent: 保留意图适配器，仅替外部结构化模型响应')

@pytest.fixture(scope='session')
def client():
    """启动真实FastAPI生命周期，返回隔离TestClient；外部模型仅专项真实验收调用。"""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as instance:yield instance

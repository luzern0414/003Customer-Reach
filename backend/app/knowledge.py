"""持久记忆、中文全文知识检索与销售反馈；公开事实和用户偏好分开保存。"""
import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
import jieba
from sqlalchemy import select, text
from langgraph.store.base import BaseStore, GetOp, PutOp, SearchOp, ListNamespacesOp, Item, SearchItem
from .db import Session, Memory, Knowledge, Feedback, Lead, Evidence, now, serialize
from .service import ServiceError

jieba.setLogLevel(40)
WORKSPACE = 'local'


def terms(value: str) -> list[str]:
    """value可为空；返回去重中文词/英文词及双字词，用于FTS而不是拼接裸查询语法。"""
    tokens = [x.lower() for x in jieba.cut(value or '') if re.fullmatch(r'[\w\u4e00-\u9fff]+',x) and len(x)>1]
    for part in re.findall(r'[\u4e00-\u9fff]+',value or ''):
        tokens.extend(part[i:i+2] for i in range(len(part)-1))
    return list(dict.fromkeys(tokens))[:3000]


def expires(days: int) -> str:
    """days为正天数，返回上海时间的系统复核期限；不代表来源发布日期。"""
    return (datetime.now(timezone(timedelta(hours=8)))+timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


class WorkspaceStore(BaseStore):
    """LangGraph BaseStore的本地持久实现，不使用RAM冒充跨进程长期记忆。"""
    def batch(self, ops):
        """ops为官方Get/Put/Search/List操作；返回同序结果，删除仅标记inactive，禁止跨workspace写。"""
        result=[]
        with Session.begin() as db:
            for op in ops:
                namespace=tuple(getattr(op,'namespace',getattr(op,'namespace_prefix',())))
                if namespace and namespace[0]!=WORKSPACE:
                    raise ServiceError('记忆作用域不匹配',403)
                if isinstance(op,(GetOp,PutOp)):
                    unique=hashlib.sha256(json.dumps([namespace,op.key],ensure_ascii=False).encode()).hexdigest()
                    row=db.scalar(select(Memory).where(Memory.unique_key==unique))
                    if isinstance(op,PutOp):
                        if not row and op.value is not None:
                            row=Memory(namespace='/'.join(namespace),key=op.key,unique_key=unique,value=op.value)
                            db.add(row)
                        if row:
                            row.status='active' if op.value is not None else 'inactive'
                            row.value=op.value if op.value is not None else row.value
                            row.updated_at=now()
                        result.append(None)
                    else:
                        result.append(self.to_item(row) if row and row.status=='active' else None)
                elif isinstance(op,SearchOp):
                    rows=list(db.scalars(select(Memory).where(Memory.status=='active').order_by(Memory.updated_at.desc())))
                    items=[]
                    query_terms=terms(op.query or '')
                    for row in rows:
                        ns=tuple(row.namespace.split('/'))
                        if ns[:len(namespace)]!=namespace or ns[0]!=WORKSPACE: continue
                        if op.filter and any(row.value.get(k)!=v for k,v in op.filter.items()): continue
                        score=sum(word in json.dumps(row.value,ensure_ascii=False).lower() for word in query_terms)
                        if query_terms and not score: continue
                        base=self.to_item(row)
                        items.append(SearchItem(namespace=base.namespace,key=base.key,value=base.value,
                            created_at=base.created_at,updated_at=base.updated_at,score=float(score)))
                    if query_terms: items.sort(key=lambda x:x.score or 0,reverse=True)
                    result.append(items[op.offset:op.offset+op.limit])
                elif isinstance(op,ListNamespacesOp):
                    namespaces={tuple(x.namespace.split('/')) for x in db.scalars(select(Memory).where(Memory.status=='active'))}
                    filtered=[]
                    for ns in sorted(namespaces):
                        if ns[0]!=WORKSPACE: continue
                        if op.match_conditions and not all(ns[:len(c.path)]==tuple(c.path) if c.match_type=='prefix' else ns[-len(c.path):]==tuple(c.path) for c in op.match_conditions): continue
                        filtered.append(ns[:op.max_depth] if op.max_depth else ns)
                    result.append(list(dict.fromkeys(filtered))[op.offset:op.offset+op.limit])
        return result

    async def abatch(self, ops):
        """ops为非空或空操作序列，在线程执行同步短事务；异常原样传播，不持有网络事务。"""
        return await asyncio.to_thread(self.batch,list(ops))

    @staticmethod
    def to_item(row):
        """row为非空Memory行；投影为官方Item，不返回唯一键或其他工作空间记录。"""
        zone=timezone(timedelta(hours=8))
        return Item(value=row.value,key=row.key,namespace=tuple(row.namespace.split('/')),
            created_at=datetime.strptime(row.created_at,'%Y-%m-%d %H:%M:%S').replace(tzinfo=zone),
            updated_at=datetime.strptime(row.updated_at,'%Y-%m-%d %H:%M:%S').replace(tzinfo=zone))


store=WorkspaceStore()


def upsert_knowledge(title: str, body: str, kind: str, source_id: str | None=None,
                     source_url: str='', entity_id: str | None=None, expiry: str | None=None) -> dict:
    """title/body必须有真实文本，kind区分产品/公开事实；可空来源用于用户资料，返回幂等知识条目。"""
    unique=hashlib.sha256(f'{WORKSPACE}|{source_id}|{entity_id}|{body}'.encode()).hexdigest()
    with Session.begin() as db:
        row=db.scalar(select(Knowledge).where(Knowledge.unique_key==unique))
        if not row:
            row=Knowledge(unique_key=unique,workspace_id=WORKSPACE,title=title,body=body,kind=kind,
                          source_id=source_id,source_url=source_url,entity_id=entity_id,expires_at=expiry)
            db.add(row);db.flush()
            db.execute(text('INSERT INTO knowledge_fts(item_id,workspace_id,title,body) VALUES (:id,:w,:t,:b)'),
                       {'id':row.id,'w':WORKSPACE,'t':' '.join(terms(title)),'b':' '.join(terms(body))})
        return serialize(row)


def ingest_attachment(attachment) -> int:
    """attachment为数据库用户文件；按1200字块、120字重叠入库，不把它当公开客户证据。"""
    count=0
    for start in range(0,len(attachment.text),1080):
        upsert_knowledge(attachment.filename,attachment.text[start:start+1200],'product',source_id='attachment:'+attachment.id)
        count+=1
    return count


def search_knowledge(query: str, limit: int=8, kind: str='') -> list[dict]:
    """query为空返回有效最新记录；limit限定1..30，kind空不限；只召回本工作空间未失效知识。"""
    limit=max(1,min(30,limit));words=terms(query)[:32]
    with Session() as db:
        condition=[Knowledge.workspace_id==WORKSPACE,Knowledge.status=='active',
                   (Knowledge.expires_at.is_(None))|(Knowledge.expires_at>now())]
        if kind: condition.append(Knowledge.kind==kind)
        if words:
            found=db.execute(text('SELECT item_id FROM knowledge_fts WHERE knowledge_fts MATCH :q AND workspace_id=:w ORDER BY bm25(knowledge_fts) LIMIT 60'),
                             {'q':' OR '.join('"'+w+'"' for w in words),'w':WORKSPACE}).scalars().all()
            rows=list(db.scalars(select(Knowledge).where(*condition,Knowledge.id.in_(found))))
            rows.sort(key=lambda x:found.index(x.id))
        else: rows=list(db.scalars(select(Knowledge).where(*condition).order_by(Knowledge.updated_at.desc()).limit(limit)))
        return [serialize(x) for x in rows[:limit]]


def knowledge_list(query: str='') -> dict:
    """query可空，供管理页查看知识，返回总量和有效检索结果，不隐藏失效记录。"""
    with Session() as db:
        rows=db.scalars(select(Knowledge).where(Knowledge.workspace_id==WORKSPACE).order_by(Knowledge.updated_at.desc()).limit(150))
        values=[serialize(x) for x in rows]
        if query: values=[x for x in values if query.lower() in (x['title']+x['body']).lower()]
        for row in values:
            if row['status']=='active' and row['expires_at'] and row['expires_at']<=now():row['status']='expired'
        return {'items':values,'active':sum(x['status']=='active' for x in values)}


def deactivate_knowledge(item_id: str) -> dict:
    """item_id非空；只软失效当前空间条目，不存在404，保留原文与索引审计。"""
    with Session.begin() as db:
        row=db.get(Knowledge,item_id)
        if not row or row.workspace_id!=WORKSPACE: raise ServiceError('知识不存在',404)
        row.status='inactive';row.updated_at=now()
    return {'inactive':True}


def memory_list() -> list[dict]:
    """返回当前工作空间的画像、偏好、排除项与配方绩效，不跨namespace泄露数据。"""
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(Memory).where(Memory.namespace.startswith(WORKSPACE+'/'),Memory.status=='active').order_by(Memory.updated_at.desc()))]


def add_memory(kind: str, content: str) -> list[dict]:
    """kind为已校验用户记忆类型，content非空；标用户来源并返回最新列表，不伪装网页事实。"""
    if not content.strip():raise ServiceError('记忆内容不能为空')
    key=hashlib.sha256(content.encode()).hexdigest()[:24]
    store.put((WORKSPACE,kind),key,{'content':content.strip(),'source':'用户明确提供','updated_at':now()})
    return memory_list()


def deactivate_memory(item_id: str) -> dict:
    """item_id非空，软停用本空间记忆；不存在404，不物理删除历史。"""
    with Session.begin() as db:
        row=db.get(Memory,item_id)
        if not row or not row.namespace.startswith(WORKSPACE+'/'):raise ServiceError('记忆不存在',404)
        row.status='inactive';row.updated_at=now()
    return {'inactive':True}


def record_feedback(lead_id: str, kind: str, content: str='') -> dict:
    """lead_id须存在，kind为校验反馈，content可空；使受影响知识失效并学习排除项，原始证据不改。"""
    with Session.begin() as db:
        row=db.get(Lead,lead_id)
        if not row or row.archived:raise ServiceError('客户不存在',404)
        feedback=Feedback(lead_id=lead_id,kind=kind,content=content);db.add(feedback);db.flush()
        if kind in {'nonbuyer','incorrect','stale'}:
            for item in db.scalars(select(Knowledge).where(Knowledge.entity_id==lead_id)):
                item.status='disputed' if kind=='incorrect' else 'inactive';item.updated_at=now()
            if kind=='nonbuyer': row.qualification={**(row.qualification or {}),'eligible':False,'reason':'用户标记非买家'};row.score=0
            row.tags=list(dict.fromkeys([*(row.tags or []),{'nonbuyer':'非买家','incorrect':'信息有误','stale':'信息失效'}[kind]]))
            if kind in {'incorrect','stale'}:
                row.facts={k:{**v,'verification':'disputed' if kind=='incorrect' else 'inactive'} if k not in (row.manual_fields or []) else v for k,v in (row.facts or {}).items()}
                from .procurement import signals
                qualification=dict(row.qualification or {})
                qualification['procurement_signals']=[{**item,'verification':'disputed' if kind=='incorrect' else 'inactive'} for item in signals(qualification)]
                qualification['signal_score']=0;row.qualification=qualification
                row.score=0
        result=serialize(feedback);name=row.display_name;facts=row.facts or {}
        from .procurement import signals
        purchases=signals(row.qualification)
        channels=set(db.scalars(select(Evidence.channel).where(Evidence.id.in_([x.get('source_id') for x in row.evidence or []]))))
    if kind=='nonbuyer':store.put((WORKSPACE,'exclusion'),lead_id,{'content':name,'entity_id':lead_id,'source':'用户反馈','reason':content or '非买家'})
    store.put((WORKSPACE,'feedback'),feedback.id,{'lead_id':lead_id,'name':name,'kind':kind,'content':content,'source':'用户反馈',
        'created_at':result['created_at'],'facts':facts,'procurement_signals':purchases})
    for item in store.search((WORKSPACE,'recipes'),limit=200):
        # 没有客户归因的旧统计不猜测所属产品，反馈不能污染同渠道其他产品/地区。
        if item.value.get('channel') in channels and lead_id in item.value.get('credited_lead_ids',[]):
            key='positive_feedback' if kind=='relevant' else 'negative_feedback'
            store.put(item.namespace,item.key,{**item.value,key:item.value.get(key,0)+1})
    return result


def invalidated_fact(name: str, fact, source: dict) -> bool:
    """name为候选主体，fact为逐字段事实，source为实际证据；有误值禁止复用，失效资料须重新采集。"""
    for item in store.search((WORKSPACE,'feedback'),limit=500):
        value=item.value
        if value.get('name')!=name or value.get('kind') not in {'incorrect','stale'}:continue
        old=value.get('facts',{}).get(fact.field,{})
        if not old:continue
        if value['kind']=='incorrect' and old.get('value')==fact.value:return True
        if value['kind']=='stale' and (old.get('source_id')==fact.source_id or source.get('captured_at','')<=value.get('created_at','')):return True
    return False


def invalidated_procurement(name: str, signal, source: dict) -> bool:
    """name为主体，signal为结构化公告，source为真实来源；纠错引文禁止复用，失效公告须重新取证，否则返回False。"""
    from .procurement import signals
    records=[]
    for item in store.search((WORKSPACE,'feedback'),limit=500):
        value=item.value
        if value.get('name')==name and value.get('kind') in {'incorrect','stale'}:
            records.extend((row,value['kind'],value.get('created_at','')) for row in value.get('procurement_signals',[]))
    # 兼容反馈快照尚未包含公告的旧数据；保留的争议/失效公告本身也是禁止复用依据。
    with Session() as db:
        for lead in db.scalars(select(Lead).where(Lead.display_name==name)):
            records.extend((row,'incorrect' if row.get('verification')=='disputed' else 'stale',lead.updated_at)
                for row in signals(lead.qualification) if row.get('verification') in {'disputed','inactive'})
    for old,kind,stamp in records:
        if kind=='incorrect' and (old.get('source_id')==signal.source_id or re.sub(r'\s+','',old.get('quote',''))==re.sub(r'\s+','',signal.quote)):return True
        if kind=='stale' and (old.get('source_id')==signal.source_id or source.get('captured_at','')<=stamp):return True
    return False

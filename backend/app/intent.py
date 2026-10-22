"""每条消息的模型意图入口；历史补指代，网络权限仍以当前用户请求为边界。"""
import json
from sqlalchemy import select
from .db import Session, Job, Message, Conversation, identifier
from .company_models import Company
from .company_research_schemas import IntentDecision
from .research_tools import emit


async def recognize_intent(state: dict) -> IntentDecision:
    """state含本轮job/conversation/prompt，均不可空；真实模型识别，每个新Job一次，恢复复用结果。

    返回Pydantic决策；模型/预算/取消错误按原异常传播，不退回规则路由。
    """
    from .agent import cached_model
    with Session() as db:
        job=db.get(Job,state['job_id'])
        saved=(job.metrics or {}).get('intent_decision')
        # 同一任务恢复时近期消息可能已增加失败答复；沿用本任务成功决策，不能因此重新消耗意图预算。
        if saved and not (job.metrics or {}).get('intent_pending',True):return IntentDecision.model_validate(saved)
        messages=list(db.scalars(select(Message).where(Message.conversation_id==job.conversation_id).order_by(Message.id.desc()).limit(8)))
        history=[{'role':row.role,'content':row.content[:1800]} for row in reversed(messages)]
        selected=db.get(Company,(job.metrics or {}).get('target_company_id')) if (job.metrics or {}).get('target_company_id') else None
        constraints={'query_mode':job.query_mode,'attachment_ids':job.attachment_ids,'selected_company':selected.name if selected else ''}
    prompt=('每条新消息都识别意图，只返回结构化决策。quick为问候/应用身份，chat为解释/计算/普通回答，document为仅处理附件，research为从产品寻找买家，company_query为指定企业资料/采购/上下游研究。'
        '当前消息优先；历史仅解释“都要/继续/企业名称”等紧接的明确承接，不因历史研究使普通聊天联网。'
        'selected_company非空时研究只针对该主体；query_mode的显式选择为范围约束，但仍识别实际需求。'
        '指定企业无需卖方产品。targets保留用户给出的原名或明确指代对应原名，禁止编造企业、联系人和URL；不把简称自动认作另一集团或子公司。'
        'research_prompt保留本轮需求与明确承接的原企业/约束；不用助手回答作为企业事实。'
        'requested_fields从name/industry/business/products/phone/email/address/website/headcount/revenue/procurement_rule/procurement/supplier/customer/subsidiary/credit_code/competitor/detail选择。'
        '竞争对手请求必须包含competitor；工商登记、股东、资质等其他资料包含detail。新会话仅给企业名时按完整画像研究；明确承接历史限定范围时保留原限定。'
        '只查主营就name/business；完整画像默认涵盖上述主要企业资料；只查采购就name/procurement/procurement_rule；只查上下游就name/supplier/customer。'
        'questions只用于确实未指定主体或产品等必要输入，不因企业信息缺失先拦研究。title是最多10字的问题概括。'
        '用户明确不要联网/仅读文件仍遵守，不擅自研究旧请求。'
        '\n本轮：'+state['prompt']+'\n约束：'+json.dumps(constraints,ensure_ascii=False)+
        '\n同会话消息：'+json.dumps(history,ensure_ascii=False))
    return await cached_model(state,IntentDecision,prompt,'intent')


async def intent_node(state: dict) -> dict:
    """state为图初态；持久化模型决策并返回授权研究正文/意图，不修改用户原始Message或Job.prompt。"""
    decision=await recognize_intent(state)
    fields=[field for field in decision.requested_fields if field in {
        'name','industry','business','products','phone','email','address','website','headcount','revenue',
        'procurement_rule','procurement','supplier','customer','subsidiary','credit_code','competitor','detail'}]
    prompt=decision.research_prompt or state['prompt']
    with Session.begin() as db:
        job=db.get(Job,state['job_id']);conv=db.get(Conversation,job.conversation_id)
        model_intent = decision.intent
        # UI已明确选择指定企业的文件匹配；仍识别需求，但操作范围禁止转成公网企业研究。
        if job.query_mode == 'company_match' or (job.metrics or {}).get('operation_scope')=='lead_product_analysis': decision.intent = 'document'
        elif (job.metrics or {}).get('counterparty_only'): decision.intent = 'company_query'
        elif (job.metrics or {}).get('target_company_id') and decision.intent not in {'chat','quick','document'}:decision.intent='company_query'
        job.metrics={**(job.metrics or {}),'intent':decision.intent,'intent_decision':decision.model_dump(),
            'research_prompt':prompt,'requested_fields':fields,'intent_pending':False,
            'model_intent': model_intent, **({'operation_scope':'company_document_match'} if job.query_mode == 'company_match' else {})}
        if decision.intent=='company_query':job.query_mode='company_query'
        if decision.title:
            conv.title=decision.title;job.metrics={**job.metrics,'conversation_title':decision.title}
    emit(state['job_id'],'intent.completed',{'intent':decision.intent,'title':decision.title,'requested_fields':fields})
    from .source_catalog import active_channels
    options={**state['options'],'enabled_channels':active_channels(prompt,state['options']['enabled_channels']),
        'hybrid_research':decision.intent in {'research','company_query'},'research_targets':decision.targets}
    return {'intent':decision.intent,'intent_decision':decision.model_dump(),'prompt':prompt,
        'options':options,
        'company_requested_fields':fields,'company_intent_targets':decision.targets,
        'company_questions':decision.questions if decision.intent=='company_query' else [],
        'metrics':{**state.get('metrics',{}),'intent':decision.intent,'intent_decision':decision.model_dump()}}


async def quick_node(state: dict) -> dict:
    """state已通过真实模型识别为quick；返回应用已知信息，不调用企业研究或再请求回答模型。"""
    from .conversation import quick_reply
    answer=quick_reply(state['prompt'])
    generation=identifier()
    with Session.begin() as db:
        job=db.get(Job,state['job_id'])
        row=db.get(Message,job.reply_message_id) if job.reply_message_id else None
        if not row:
            row=Message(conversation_id=job.conversation_id,role='assistant',content=answer);db.add(row);db.flush();job.reply_message_id=row.id
        row.content=answer;job.generation_id=generation;message_id=row.id
    emit(state['job_id'],'message.reset',{'message_id':message_id,'generation_id':generation})
    emit(state['job_id'],'message.delta',{'message_id':message_id,'generation_id':generation,'delta':answer})
    emit(state['job_id'],'message.completed',{'message_id':message_id,'generation_id':generation,'content':answer})
    return {'answer':answer,'metrics':{**state.get('metrics',{}),'intent':'quick','answer_mode':'application'}}

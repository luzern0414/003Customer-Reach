"""当前消息的轻量路由；明确承接上一轮企业请求时才复用研究范围。"""
import re


def mode(content: str, attachment_ids: list | None=None) -> str:
    """content为当前正文，附件可空；返回quick/chat/document/research，不发网络或执行历史任务。"""
    value=re.sub(r'\s+','',content).lower()
    if re.search(r'^(?:你好[，,!！]*)?(?:你是谁|你是什么|介绍一下你自己|你能做什么|你有什么功能)[？?。！!]*$',value) or value in {'你好','您好','hi','hello','谢谢','感谢'}:return 'quick'
    # “资料/表格”也出现在普通解释里，只有明确指向文件才进入文档路径。
    document = bool(attachment_ids) or bool(re.search(r'文件|附件|文档|产品目录|表格(?:里|中)|(?:这份|这张|上传|刚才|上次).*(?:资料|目录|表格)',value))
    only_read = re.search(r'(?:不要|无需|不必|先不|不需要)(?:再|去|进行|联网)?(?:搜索|检索|找客户|寻找客户|获客|联网)',value)
    research = re.search(r'(?:找|寻找|搜索|检索|核验|爬取).*(?:客户|买家|经销|门店)|获客|补查|继续检索',value)
    file_question = re.search(r'总结|概括|读取|解析|提取|列出|对照表|分析文件|(?:文件|附件|文档|目录|资料|表格).*(?:型号|功率|规格|价格|什么|哪些|多少)',value)
    if document and (only_read or file_question and not research):
        return 'document'
    if attachment_ids:return 'research'
    # 明确指定网页的复核后解释仍需真实读取，不能因同句出现“解释/为什么”被普通问答抢走。
    explain_only=re.match(r'^(?:请|帮我)?(?:解释|翻译|改写|润色|计算)',value)
    if not explain_only and re.search(r'(?:仅|只|请|帮我)(?:再次|重新|再)?(?:复核|核验|读取)(?:以下|下列|这些|这个|指定|该).*https?://',value):return 'research'
    if re.search(r'(?:帮我|请|替我)(?:去|再)?(?:找|查|搜|检索|爬|核验|补)|^(?:查找|寻找|搜索|检索|爬取|核验|补查)',value):return 'research'
    # 解释、询问已有结果属于对话；不能把出现“客户/采购”当作执行检索的授权。
    if re.search(r'怎么|如何|为什么|解释|什么意思|是谁|有哪些功能|刚才|上一轮|目前进度|多久|介绍你',value):return 'chat'
    if re.search(r'^(?:请|帮我)?(?:改写|润色|翻译|计算|写一个|写一篇|写个|生成一段)|(?:改写|润色|翻译).*(?:句|中文|英文)',value):return 'chat'
    if re.search(r'找|寻找|搜索|检索|爬取|获客|线索|买家|经销商|采购|帮我查|核验|继续|再来|补查|销售|供应|主营|最多\d+|我们.*(?:卖|产品)|公司.*产品|产品[：:]|改成|换成',value):return 'research'
    return 'chat'


def quick_reply(content: str) -> str:
    """content为已判定quick的消息；返回应用身份或礼貌响应，不调用模型，不伪称研究完成。"""
    if content.strip().lower() in {'谢谢','感谢'}:return '不客气。'
    return '你好，我是 Reach，你的 B 端获客助手，可以帮你分析产品、寻找客户和管理线索。'


def company_intent(content: str, attachment_ids=None) -> bool:
    """content为当前非空需求，attachment_ids可空；返回企业研究授权，解释/文件/卖方获客不抢路由。"""
    value=re.sub(r'\s+','',content)
    if attachment_ids or re.search(r'(?:我们|我司|本公司).*(?:销售|卖|产品)|(?:找|寻找|搜索|检索)(?:到|一些)?(?:客户|买家|经销商)|解释|什么意思|如何|怎么|^(?:请|帮我)?(?:改写|润色|翻译|计算|写)',value):return False
    if re.search(r'(?:不要|无需|不必|不需要)(?:再|去|进行|联网)?(?:查|查询|搜索|检索|研究)',value):return False
    action=r'(?:查(?:询|一下)?|研究|检索|搜索|分析|核验|补查|了解(?:一下)?)'
    if re.search(action+r'.*(?:企业画像|公司画像|客户画像|完整画像|上下游|招投标信息|采购信息)',value):return True
    # 企业名不一定有“公司”后缀；船厂、学校和医院同样可作为研究主体。
    if re.match(r'^(?:请|帮我|替我)?'+action+r'.*(?:有限公司|股份|集团|公司|船厂|工厂|医院|大学|研究院|研究所|银行|合作社)',value):return True
    subject=re.match(r'^(?:请|帮我|替我)?'+action+r'(.{2,60}?)(?:的)?(?:信息|资料|情况|概况)[。！？?！]*$',value)
    return bool(subject and not re.search(r'结果|记录|进度|上一轮|刚才|功能|系统|今天|天气|日期|文件|附件',subject.group(1)))


def company_request(content: str, attachment_ids=None, previous: list[dict] | None=None) -> str:
    """content为本轮原文、附件可空，previous为同会话最近任务（新到旧，最多3轮）。

    返回获授权的企业研究正文，未授权返回空串；仅短确认/待补名称可承接，普通聊天隔断历史。
    不发网络、不从助手回答或产品记忆推断研究目标。
    """
    if company_intent(content,attachment_ids):return content
    if attachment_ids:return ''
    value=re.sub(r'\s+','',content)
    confirmation=bool(re.fullmatch(r'(?:请)?(?:都要|全部|都查|全部查询|都需要|可以|好的|好|是的|确认|开始|开始查询|继续|继续查询|继续补查)[。！!]*',value))
    for item in (previous or [])[:3]:
        prior=item.get('research_prompt') or item.get('prompt','')
        enterprise=item.get('query_mode')=='company_query' or company_intent(prior,item.get('attachment_ids'))
        # 回答企业名称只允许承接确实缺输入的企业任务，不能将一般聊天自动升级研究。
        name_reply=item.get('status')=='needs_input' and enterprise and bool(re.fullmatch(r'[\w\u4e00-\u9fff·（）()\-]{2,80}',value)) and mode(content)=='chat'
        if enterprise and (confirmation or name_reply):return prior+'\n本轮补充：'+content
        if confirmation and re.fullmatch(r'(?:都要|全部|都查|都需要|可以|好的|好|确认|继续)[。！!]*',re.sub(r'\s+','',item.get('prompt',''))):continue
        break
    return ''


def short_title(content: str) -> str:
    """content为问题或旧会话标题，可空；返回最多10字的规则概括，不调用模型或改写业务事实。"""
    if not content or content=='新的获客对话':return '新研究'
    value=re.sub(r'https?://\S+','',content).strip()
    if re.match(r'^仅复核以下两份报',value):return '多企业研究'
    # 同一问题包含两个或更多完整企业名时，用范围标题避免把公司长名挤进导航栏。
    if len(re.findall(r'(?:股份有限公司|有限责任公司|有限公司)',value))>=2:return '多企业研究'
    value=re.sub(r'^(?:仅|只)?(?:复核|查询|研究|检索|分析)?(?:以下|下列)\s*','',value)
    value=re.sub(r'^(?:两份|两家|多份)报告[，,：: ]*','',value)
    value=re.sub(r'^(?:请|帮我|替我)?(?:查询|查一下|查找|研究|搜索|检索|核验|分析|了解一下|了解)\s*','',value)
    value=re.split(r'[，,。；;\n]',value)[0]
    value=re.sub(r'(?:的)?(?:完整)?(?:企业画像|公司画像|客户画像|画像|信息|资料|情况|概况).*$', '',value).strip(' ：:的')
    value=re.sub(r'研究$', '',value)
    return (value[:8]+'研究' if value else '新研究')[:10]

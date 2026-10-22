"""已许可公共交易公告的可见表格；不联网、不补造金额，不把普通投标人当候选/中标。"""
import hashlib
import re
from urllib.parse import urlparse
from sqlalchemy import select
from .db import Session, Evidence


def supported(url):
    """仅公共部门域名与已核验交易中心支持HTML表格补提取。"""
    host=(urlparse(url).hostname or '').lower()
    return host.endswith('.gov.cn') or host=='www.msggzy.org.cn' or host=='msggzy.org.cn'


def table_text(html, url):
    """返回DOM中可见表格连续单元格文本；补充被文章抽取省略的表格，隐藏节点不参与。"""
    if not supported(url):return ''
    from lxml import html as parser
    from trafilatura.utils import decode_file
    try:root=parser.fromstring(decode_file(html) if isinstance(html,bytes) else html)
    except (ValueError,TypeError):return ''
    def visible(node):
        for ancestor in [node,*node.iterancestors()]:
            style=re.sub(r'\s+','',ancestor.get('style','')).lower()
            if (ancestor.tag in {'script','style','noscript'} or ancestor.get('hidden') is not None or
                ancestor.get('aria-hidden','').lower()=='true' or 'display:none' in style or 'visibility:hidden' in style):return False
        return True
    tables=[]
    for table in root.xpath('//table')[:80]:
        if not visible(table) or table.xpath('.//table'):continue
        rows=[]
        for row in table.xpath('.//tr')[:250]:
            cells=[re.sub(r'\s+',' ',' '.join(cell.itertext())).strip() for cell in row.xpath('./th|./td') if visible(cell)]
            if cells:rows.append('| '+' | '.join(cells)+' |')
        if rows:tables.append('\n'.join(rows))
    return '\n\n'.join(tables)


def table_rows(body):
    """遍历真实Markdown表头/同行原文；宽度变化/空行切断，保留原文引文。"""
    header=[];header_line='';section='';offset=0
    for raw in (body or '').splitlines(keepends=True):
        start=offset;offset+=len(raw);line=raw.strip()
        if not line.startswith('|'):
            header=[];header_line=''
            if line:section=line
            continue
        cells=[cell.strip() for cell in line.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?',cell) for cell in cells if cell):continue
        if any(re.search(r'供应商名称|中标候选人名称|投标人名称|投标单位名称',cell) for cell in cells):
            header=cells;header_line=line;continue
        if header and len(cells)==len(header):
            yield header,cells,line,header_line,section,start+len(raw)-len(raw.lstrip())


def bid_context(body,company):
    """目标同行报价/评审价/得分；只能是报价，不能成为成交金额或预算。"""
    for header,cells,line,head,section,start in table_rows(body):
        name_key=next((i for i,key in enumerate(header) if re.search('中标候选人名称|投标人名称|投标单位名称',key)),None)
        if name_key is None or cells[name_key]!=company:continue
        price_key=next((i for i,key in enumerate(header) if '投标报价' in key),None)
        if price_key is None:continue
        value=re.match(r'([\d,]+(?:\.\d+)?)\s*(万元|亿元|元)?(?:\s*\([^)]*\)|\s*（[^）]*）)?$',cells[price_key])
        if not value:continue
        unit=value[2] or next((u for u in ('万元','亿元','元') if u in header[price_key]),'')
        if not unit:continue
        result={'price':value[1],'unit':unit,'quote':head+'\n'+line,
            'basis':'普通投标人报价' if '其他投标人' in section or '投标人名称' in header else '候选人投标报价'}
        for field,pattern in [('review_price','经评审|评审价'),('score','综合.*得分|综合评估')]:
            index=next((i for i,key in enumerate(header) if re.search(pattern,key)),None)
            if index is not None and re.fullmatch(r'[\d,]+(?:\.\d+)?',cells[index]):result[field]=cells[index]
        # 引文必须包含真实的全部中间内容，不能拼接表头与隔行数据。
        head_start=body.rfind(head,0,start)
        if head_start>=0:result['quote']=body[head_start:start+len(line)]
        return result
    return {}


def save_public_notices(job_id, source_ids, targets, options):
    """只消费本Job许可正文并保存明确表格角色；实际原文支持才生成TenderRecord。"""
    from .tender_intel import TenderCollector,stable_key
    from .tender_parse import parse_detail, clean_name, MASK_RE
    from .bidresearch_mcp import grounded_party,grounded_amount
    from .industry_navigation import factual_body
    summaries={}
    with Session() as db:
        sources=list(db.scalars(select(Evidence).where(Evidence.id.in_(source_ids),Evidence.job_id==job_id,
            Evidence.channel.in_(['procurement','official']),Evidence.kind.in_(['网页正文','网页读取']))))
    for target in targets:
        collector=TenderCollector(job_id,target,options);used=[]
        for source in sources:
            if not supported(source.url):continue
            body=factual_body(source.body)
            title=source.title
            if target not in body or not re.search('中标|成交|评标|开标',title+' '+body[:1000]):continue
            found=None;award='';parties=[]
            for header,cells,line,head,section,start in table_rows(body):
                name_key=next((i for i,key in enumerate(header) if re.fullmatch('供应商名称|中标候选人名称|投标人名称|投标单位名称',key)),None)
                if name_key is None or cells[name_key]!=target:continue
                if header[name_key]=='供应商名称' and re.search('中标|成交',title) and not re.search('候选|备选',title):
                    party=grounded_party(body,{'name':target,'label':'供应商名称','role':'winner','quote':line})
                    price_key=next((i for i,key in enumerate(header) if re.search('中标.*金额|成交.*金额',key)),None)
                    if party:
                        found=party
                        if price_key is not None:
                            amount=grounded_amount(body,{'original':cells[price_key],'kind':'award','label':header[price_key],'quote':line})
                            if amount and not MASK_RE.search(cells[price_key]):award=amount['display_value']
                elif header[name_key]=='中标候选人名称':
                    found={'role':'candidate','quote':body[body.rfind(head,0,start):start+len(line)]}
                else:
                    # 其他投标人/开标参与者不是“中标候选人”。
                    found={'role':'mentioned','quote':body[body.rfind(head,0,start):start+len(line)]}
                if found:
                    parties=[clean_name(row[name_key]) for h,row,*_ in table_rows(body) if h==header and clean_name(row[name_key])]
                    break
            if not found:continue
            parsed=parse_detail(body,target,title)
            buyer=parsed['buyer']
            if not buyer:
                for line in body.splitlines():
                    cells=[c.strip() for c in line.strip().strip('|').split('|')]
                    for i,label in enumerate(cells[:-1]):
                        value=clean_name(cells[i+1])
                        if label in {'采购人','采购单位','招标人','项目业主'} and value and re.search('公司|局|支队|中心|大学|学院|医院|委员会|集团|厂|办公室|部门|管理处',value):buyer=value;break
                    if buyer:break
            key=stable_key('public-table-1',source.url,hashlib.sha256(body.encode()).hexdigest())
            collector.records[key]={'record_key':key,'title':title[:300],'role':found['role'],'confidence':'detail',
                'quote':found['quote'][:1200],'buyer_name':buyer,'amount':award,'budget':'',
                'winner_names':[target] if found['role']=='winner' else [],'candidate_names':parties if found['role']=='candidate' else [],
                'published_at':parsed['published_at'] or source.published_at or '', 'project_number':parsed['project_number'],
                'platform':urlparse(source.url).hostname or '', 'url':source.url,'evidence_id':source.id,'items':parsed['items'],
                'evidence_fields':{'bid':bid_context(body,target),'role_basis':'可见公告表头与同一投标人行'}}
            used.append(source.id)
        if collector.records:
            collector.derive_relations();summary=collector.persist()
            summaries[target]={**summary,'native_source_ids':used}
    return summaries

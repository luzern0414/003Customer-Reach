"""确定性证据上下文选择；只裁剪真实正文，不补客户事实或拼接引文。"""
import re


def target_names(prompt: str, rows: list[dict], region: str, seller: str='') -> list[str]:
    """prompt为当前要求、rows为来源、region可空、seller为我方名称；仅返回查找指令中的买方，不生成名称。"""
    if not region:return []
    pattern=re.escape(region)+r'[^\s。；;，,:：|<>()（）\n]{1,60}(?:有限公司|商行|经营部|学校|灯饰店|照明店)'
    found=[]
    # 明确“核验以下…”的同一句名单可能含多个URL，不能用距动词60字限制漏掉后面的主体。
    listing=re.search(r'(?:核验|核对|查找|寻找|补查|研究|请找|请查)[^。；\n]{0,40}(?:以下|下列)',prompt)
    list_end=prompt.find('。',listing.end()) if listing else -1
    if listing and list_end<0:list_end=len(prompt)
    for row in rows:
        for match in re.finditer(pattern,(row.get('title','') or '')+'\n'+row.get('body','')):
            name=match.group()
            position=prompt.find(name)
            before=prompt[max(0,position-60):position] if position>=0 else ''
            after=prompt[position+len(name):position+len(name)+20] if position>=0 else ''
            requested=bool(re.search('查找|核验|寻找|核对|补查|研究|请找|请查|请核',before) or re.search('请核验|请核对|请查找|帮我查',after)
                or listing and listing.end()<=position<list_end)
            if position>=0 and requested and name!=seller and name not in found:found.append(name)
        # 商场目录通常只有独立店名，不包含城市或法律后缀；只锚定用户明确请求且原文独立列出的店名。
        for line in row.get('body','').splitlines():
            name=re.sub(r'^\s*#{1,6}\s*','',line).strip()
            if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9·]{2,40}(?:灯饰|照明|灯具|电气)(?:店|商行)?',name):continue
            position=prompt.find(name)
            before=prompt[max(0,position-80):position] if position>=0 else ''
            if position>=0 and (re.search('查找|核验|寻找|核对|补查|研究|请找|请查|请核',before) or listing and listing.end()<=position<list_end) and name not in seller and name not in found:
                found.append(name)
    return sorted(found,key=len,reverse=True)[:8]


def source_aliases(sources: list[dict]) -> tuple[list[dict],dict[str,str]]:
    """sources为已选择真实证据；返回短编号模型上下文及精确映射，不截断、猜测或改变存档ID。"""
    aliases={f'S{index+1}':source['id'] for index,source in enumerate(sources)}
    return [{**source,'id':alias} for alias,source in zip(aliases,sources)],aliases


def resolve_sources(candidate, aliases: dict[str,str]):
    """candidate为Pydantic候选、aliases为本次短编号映射；只替换确切短编号，未知ID保留供服务端拒绝。"""
    facts=[fact.model_copy(update={'source_id':aliases.get(fact.source_id,fact.source_id)}) for fact in candidate.facts]
    signal=candidate.procurement_signal
    if signal:signal=signal.model_copy(update={'source_id':aliases.get(signal.source_id,signal.source_id)})
    return candidate.model_copy(update={'facts':facts,'procurement_signal':signal})


def evidence_excerpt(body: str, names: list[str], limit: int=3500) -> str:
    """body为真实正文，names为目标主体（空则按角色定位），limit为正字符预算；返回带省略标记的原文块。"""
    if len(body)<=limit:return body
    anchors=[match.start() for name in names for match in re.finditer(re.escape(name),body)]
    if not anchors:anchors=[match.start() for match in re.finditer('经销|授权|批发|零售|门市|专卖店|商户|采购人|采购方',body)]
    if not names and re.search(r'店\s+入驻品牌',body):
        # 首次自主发现尚无客户名；目录中部灯饰分区不能被开头厨电及末尾家具挤掉。
        anchors.extend(match.start() for match in re.finditer(r'(?m)^灯饰\s*$',body))
    # 首尾各保留一小段，预算优先给中间含真实买家角色的完整相邻记录。
    prefix=1000 if re.search(r'店\s+入驻品牌',body) else 300
    spans=[(0,prefix),(len(body)-300,len(body))]
    for point in anchors:
        candidate=(max(0,point-180),min(len(body),point+650))
        merged=[]
        for start,end in sorted([*spans,candidate]):
            if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
            else:merged.append((start,end))
        if sum(end-start for start,end in merged)+len(merged)*20<=limit:spans=merged
    return '\n[…原文片段省略…]\n'.join(body[start:end] for start,end in sorted(spans))


def evidence_context(rows: list[dict], names: list[str], region: str, source_order: list[str], recent_ids: list[str]) -> list[dict]:
    """rows是有id/url/body/kind的证据，names可空，region可空，source_order是取得顺序，recent_ids是本轮发现ID。

    返回最多6个真实URL片段：同URL优先完整正文，至少优先纳入本轮来源，正文总预算约14k字符。
    """
    positions={identifier:index for index,identifier in enumerate(source_order)}
    grouped={}
    for row in rows:
        from .source_content import has_content
        if row.get('kind') in {'网页正文','网页读取'} and not has_content(row):continue
        # 乱码记录保留在原始证据库，但不能挤掉可核验的搜索摘录或后来正确解码的正文。
        if row['body'].count('\ufffd')>max(3,len(row['body'])//100):continue
        previous=grouped.get(row['url'])
        rank=lambda item:(item['kind']!='搜索摘录',positions.get(item['id'],-1))
        if previous is None or rank(row)>rank(previous):grouped[row['url']]=row
    fresh_urls={row['url'] for row in rows if row['id'] in recent_ids}
    rank=lambda row:(any(name in row['body'] for name in names),bool(re.search('经销|授权|零售|门市|商户|采购人',row['body'])),bool(region and region in row['body']),positions.get(row['id'],-1))
    fresh=sorted((row for row in grouped.values() if row['url'] in fresh_urls),key=rank,reverse=True)
    older=sorted((row for row in grouped.values() if row['url'] not in fresh_urls),key=rank,reverse=True)
    if names:
        related=lambda row:any(name in row['body'] or name in row.get('title','') for name in names)
        selected=[*[row for row in fresh if related(row)],*[row for row in older if related(row)],*[row for row in fresh if not related(row)]][:6]
    else:selected=[*fresh[:5],*older][:6]
    limit=min(3500,14000//max(1,len(selected)))
    return [{key:row[key] for key in ('id','url','title','kind')}|{'body':evidence_excerpt(row['body'],names,limit)} for row in selected]

"""招投标解析：使用真实页面快照验证角色、对手方、清单与遮挡处理，不访问网络。"""
from pathlib import Path
from app.tender_parse import parse_detail, parse_listing, parse_partners, parse_supplier_table, title_buyer, parse_items, clean_name

FIXTURES = Path(__file__).parent / 'fixtures' / 'tender'
TARGET = '北京航天广通科技有限公司'


def read(name: str) -> str:
    """name为夹具文件名（不含扩展名）；返回UTF-8正文。"""
    return (FIXTURES / f'{name}.md').read_text(encoding='utf-8')


def test_platform_rfq_header_identifies_buyer_and_items():
    """采购企业被遮挡时，以“招标详情”标题下的发布企业为采购人，并解析物资清单。"""
    result = parse_detail(read('rfq_detail'), TARGET, 'GTXJD2026100801')
    assert result['role'] == 'buyer' and result['buyer'] == TARGET
    assert result['project_number'] == ''
    assert result['items'][0]['name'] == '昆仑变压器油' and result['items'][0]['quantity'] == '8.0' and result['items'][0]['unit'] == '桶'


def test_award_label_identifies_winner_amount_and_date():
    """“确定成交结果单位”标签确认中标，报价与发布时间按原文保留。"""
    result = parse_detail(read('award_buaa'), TARGET, '外协单位遴选专家组论证结果公示')
    assert result['role'] == 'winner'
    assert TARGET in result['quote']
    assert result['amount'].startswith('8,398,000.00')
    assert result['published_at'] == '2026-07-14'


def test_masked_aggregator_detail_does_not_invent_buyer():
    """会员遮挡的“采购企业: ****”不能当作采购人，目标未出现时只能是提及。"""
    result = parse_detail(read('ql_detail'), TARGET, 'GTXJD2026100901')
    assert result['buyer'] == '' and result['role'] == 'mentioned'
    assert any(item['name'] == '真空继电器' for item in result['items'])


def test_listing_titles_and_dates():
    """企业主页公告列表按标题保留，日期只附给紧邻的上一条。"""
    rows = parse_listing(read('hub_tenders'))
    assert rows[0] == {'title': 'GTXJD2026100901', 'published_at': '2026-10-09'}
    assert {'title': '【产品】HF项目用产品', 'published_at': '2026-10-09'} in rows
    assert all('咨询热线' not in row['title'] for row in rows)


def test_win_listing_titles_yield_buyers():
    """中标列表标题开头的机构名作为采购方线索。"""
    rows = parse_listing(read('hub_wins'))
    buyers = {title_buyer(row['title']) for row in rows}
    assert '中国原子能科学研究院' in buyers and '云南广播电视台' in buyers


def test_partner_tables_split_suppliers_and_customers():
    """合作乙方是供应商、合作甲方是客户，序号前缀被去掉，次数保留。"""
    result = parse_partners(read('hub_partners'))
    assert {'name': '湖南航天诚远精密机械有限公司', 'count': 2} == {k: result['supplier'][0][k] for k in ('name', 'count')}
    assert any(x['name'] == '北京航天科迪科技有限公司' for x in result['supplier'])
    assert result['customer'][0]['name'] == '中国原子能科学研究院' and result['customer'][0]['count'] == 7


def test_third_party_supplier_table():
    """第三方供应商列表只取供应商名称列，注册信息表不混入。"""
    names = [x['name'] for x in parse_supplier_table(read('supplier_list'))]
    assert names[0] == '北京宏宇航天技术有限公司' and len(names) == 7
    assert TARGET not in names


def test_clean_name_rejects_masks():
    """遮挡与非机构值返回空串。"""
    assert clean_name('****点击查看') == '' and clean_name('4 北京航天科迪科技有限公司') == '北京航天科迪科技有限公司'


def test_items_from_markdown_header_table():
    """标准Markdown表头的清单同样解析。"""
    text = '| 序号 | 货物名称 | 规格型号 | 数量 | 单位 |\n| --- | --- | --- | --- | --- |\n| 1 | 示波器 | DSOX1204G | 2 | 台 |'
    assert parse_items(text) == [{'name': '示波器', 'spec': 'DSOX1204G', 'quantity': '2', 'unit': '台'}]


def test_win_summary_table_rows():
    """建设通中标业绩表按“目标企业中标”行取项目与金额范围。"""
    from app.tender_parse import parse_win_table
    text = '| 序号 | 中标项目工程 | 地区 | 项目经理 | 中标金额范围 |\n| --- | --- | --- | --- | --- |\n| 1 | 北京航天广通科技有限公司中标北京师范大学卫星地面接收站项目 | 北京市 | -- | 1000万以下 |'
    rows = parse_win_table(text, TARGET)
    assert rows == [{'title': '北京航天广通科技有限公司中标北京师范大学卫星地面接收站项目', 'region': '北京市', 'amount': '1000万以下',
                     'buyer': '北京师范大学', 'line': rows[0]['line']}]


def test_vertical_result_table_identifies_winner_and_number():
    """“表头逐行、数据逐行”的结果公告：中选人列确认中标，项目编号与采购人标签分别取值，引文含表头。"""
    result = parse_detail(read('award_vertical'), TARGET, '中国原子能科学研究院C波段激励源、S波段激励源、同轴传输元件采购结果公告')
    assert result['role'] == 'winner' and result['buyer'] == '中国原子能科学研究院'
    assert result['project_number'] == 'CIAE-XJD-26-01242'
    assert result['quote'].startswith('序号') and result['quote'].endswith(TARGET)


def test_owner_page_suppliers_projects_and_registration():
    """建设通业主页：常合作供应商带次数/金额/最近时间，历史发包带中标企业，工商表取官网电话等且“--”不取。"""
    from app.tender_parse import parse_owner_page, parse_info_pairs
    text = read('cbi_proprietor')
    parsed = parse_owner_page(text, '湖南航天诚远精密机械有限公司')
    assert parsed['suppliers'][0]['name'] == '湖南航天建筑工程有限公司' and parsed['suppliers'][0]['count'] == 2
    assert parsed['projects'][0]['winner'] == '湖南航天建筑工程有限公司' and parsed['projects'][0]['published_at'] == '2014-10-09'
    info = parse_info_pairs(text)
    assert info['统一信用代码'] == '91430000712105839U' and '企业官网' not in info


def test_shuidi_roles_budget_and_buyer():
    """水滴标讯：招采单位为采购记录（含预算），中标单位记录带“招采单位：”采购方。"""
    from app.tender_parse import parse_shuidi
    rows = parse_shuidi(read('shuidi_company'), '湖南航天诚远精密机械有限公司')
    assert rows[0]['role'] == 'buyer' and rows[0]['budget'] == '3万元'
    win = next(r for r in rows if r['role'] == 'winner')
    assert win['buyer'] == '航天科工实验室' and win['title'] == '【产品】整机结构加工'


def test_title_key_merges_cross_platform_titles():
    """去掉企业名前缀、类别标记、平台后缀与公告后缀后，同一公告的不同平台标题得到相同键。"""
    from app.tender_parse import title_key
    assert title_key('【产品】HF项目用产品', TARGET) == title_key('北京航天广通科技有限公司HF项目用产品招标公告', TARGET) == 'HF项目用产品'
    assert title_key('北京航天广通科技有限公司采购滤波器招标公告 - 乙方宝', TARGET) == '滤波器'


def test_group_portal_notices_and_membership():
    """集团采购平台：国网首页公告解析出标题与日期；企业按集团关键词匹配平台，不可读平台不返回。"""
    from app.procurement_portals import parse_portal_notices, portals_for, name_variants
    rows = parse_portal_notices((FIXTURES / 'portal_sgcc.md').read_text(encoding='utf-8'))
    assert rows and rows[0]['published_at'] == '2026-10-10' and '国家电网有限公司' in rows[0]['title'] and '![' not in rows[0]['title']
    assert [p.key for p in portals_for('国网上海市电力公司')] == ['sgcc']
    assert portals_for('中国建材集团有限公司') == [] and portals_for('北京航天广通科技有限公司') == []
    assert name_variants('国网江苏省电力有限公司') == ['国网江苏省电力有限公司', '国网江苏省电力']


def test_candidate_context_keeps_own_bid_and_six_disclosed_contracts():
    from app.tender_parse import candidate_context
    body = read('hongtianzhi_candidates')
    result = candidate_context(body, '成都宏天智电子有限公司')
    assert result['bid']['rank'] == '第三名'
    assert result['bid']['price'] == '1149600.00'
    assert result['bid']['unit'] == '元'
    assert result['bid']['quote'] in body
    history = result['disclosed_performance']
    assert len(history) == 6
    assert history[0]['contract_amount'] == '152.9069万元'
    assert history[-1]['signed_at'] == '2024.11.26'
    assert all(x['quote'] in body and '成都宏天智电子有限公司' in x['quote'] for x in history)
    assert not any('海康' in x['title'] or '吉化' in x['title'] for x in history)


def test_candidate_context_does_not_borrow_unknown_or_other_party_rows():
    from app.tender_parse import candidate_context
    body = read('hongtianzhi_candidates')
    assert candidate_context(body, '未出现的公司有限公司') == {'bid': {}, 'disclosed_performance': []}
    # 下一家完整主体行终止继承；无完整表头的片段不能恢复合并单元格的归属。
    body += '\n| 第四中标候选人 | 其他电子有限公司 | 中标候选人业绩 | 其他合同 | 2025.1.1 | 100万元 | |\n'
    assert len(candidate_context(body, '成都宏天智电子有限公司')['disclosed_performance']) == 6
    fragment = '| 中标候选人业绩 | 无主合同 | 2025.1.1 | 100万元 | |'
    assert candidate_context(fragment, '成都宏天智电子有限公司')['disclosed_performance'] == []


def test_award_candidate_for_label_does_not_prefix_company_name():
    body=read('hongtianzhi_post_candidates')
    parsed=parse_detail(body,'成都宏天智电子有限公司','成交候选人公示')
    assert parsed['role']=='candidate'
    assert '成都宏天智电子有限公司' in parsed['candidates']
    assert all(not name.startswith('为') for name in parsed['candidates'])

"""答复资料覆盖整批客户，不让冗长证据挤掉末尾记录；仅隔离合成数据。"""
import json
from app.answer_summary import answer_context


def test_all_customers_survive_large_evidence_with_status_and_scope():
    """大引文批次仍保留每条客户/采购元数据，角色原文用于区分同名分店，不改写原事实。"""
    rows=[]
    for index in range(12):
        rows.append({'id':str(index),'display_name':'隔离同名灯饰','city':'深圳','buyer_role':'retailer',
            'facts':{'phone':{'value':'82345678','verification':'inactive'},
                     'revenue':{'value':'界面验证营收','effective_date':'2025-12-31','scope':'隔离统计口径'}},
            'evidence':[{'field':'address','quote':'隔离长引文。'*5000,'url':'https://example.org/'+str(index)},
                        {'field':'buyer_role','quote':f'隔离第{index}店 入驻品牌','url':'https://example.org/'+str(index)}],
            'qualification':{'procurement_signals':[{'stage':'historical','deadline':'2025-01-01 09:00:00','quote':'隔离长公告。'*5000}]}})
    compact=answer_context(rows)
    assert [row['id'] for row in compact]==[str(index) for index in range(12)]
    assert len(json.dumps(compact,ensure_ascii=False))<18000
    assert compact[-1]['role_context'][0]['quote']=='隔离第11店 入驻品牌'
    assert compact[-1]['facts']['phone']['value']=='82345678'
    assert compact[-1]['facts']['revenue']['scope']=='隔离统计口径'
    assert 'phone' in compact[-1]['contact_summary']['missing_fields']
    assert not compact[-1]['contact_summary']['usable_fields']
    assert compact[-1]['procurement_signals'][0]['deadline']=='2025-01-01 09:00:00'
    assert rows[-1]['evidence'][0]['quote']=='隔离长引文。'*5000


def test_field_alternatives_keep_values_and_scope_without_copying_long_quotes():
    """无参数；争议逐字段保留值和总数，四条展示上限显式标记，不混淆名称/地址或改原始记录。"""
    names=[{'value':'隔离替代'+str(index),'source_id':str(index),'quote':'长引文。'*5000} for index in range(6)]
    row={'id':'s','display_name':'隔离完整主体','facts':{'name':{'value':'隔离完整主体','verification':'disputed','alternatives':names},
        'address':{'value':'深圳隔离路1号','verification':'原文匹配；时效及实际业务待核'}},'evidence':[]}
    result=answer_context([row])[0]['facts']
    assert result['name']['alternatives_count']==6 and result['name']['alternatives_truncated']
    assert [item['value'] for item in result['name']['alternatives']]==[item['value'] for item in names[:4]]
    assert all('quote' not in item for item in result['name']['alternatives'])
    assert result['address']['verification']==row['facts']['address']['verification']
    assert len(row['facts']['name']['alternatives'])==6


def test_contact_evidence_preserves_original_directory_record_without_splicing():
    """无参数；同条name/phone原文去重，分店城市保持独立片段，不靠角色表头猜号码归属。"""
    record='隔离灯饰\nTel: 13169928365';city='隔离分店位于深圳西部。'
    row={'id':'s','display_name':'隔离灯饰','facts':{},'evidence':[
        {'field':'buyer_role','quote':'隔离沙井店 入驻品牌','url':'https://example.org/branch'},
        {'field':'name','quote':record,'url':'https://example.org/branch'},
        {'field':'phone','quote':record,'url':'https://example.org/branch'},
        {'field':'city','quote':city,'url':'https://example.org/branch'}]}
    result=answer_context([row])[0]
    assert result['contact_evidence']==[{'fields':['name','phone'],'url':'https://example.org/branch','quote':record},
        {'fields':['city'],'url':'https://example.org/branch','quote':city}]
    assert result['role_context'][0]['quote']=='隔离沙井店 入驻品牌'

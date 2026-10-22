"""对升级前角色推断做非破坏性复核；只降级无直接角色值的记录，原文证据不改。"""
import re
from sqlalchemy import select
from app.db import Session,Lead,Knowledge,Job,Message,now

def main():
    """按新角色证据规则复核当前库，保留来源；输出纠正数量，不输出客户手机或密钥。"""
    signals={'dealer':'经销|代理|授权|批发|销售点','retailer':'门市|门店|零售|专卖店|专营店|直营门市|店铺|灯具店|灯饰店',
             'mall':'家居城|灯饰城|灯饰市场|卖场|商场|灯饰商城','project_buyer':'采购人|采购方|招标人'}
    count=0
    with Session.begin() as db:
        for row in db.scalars(select(Lead)):
            if row.buyer_role not in signals or 'buyer_role' in (row.manual_fields or []):continue
            value=(row.facts or {}).get('buyer_role',{}).get('value','')
            if re.search(signals[row.buyer_role],value):continue
            row.buyer_role='unknown';row.score=min(row.score,35)
            row.qualification={**(row.qualification or {}),'eligible':False,'role':'unknown','role_score':0,'reason':'直接角色证据不足'}
            row.updated_at=now();count+=1
            for item in db.scalars(select(Knowledge).where(Knowledge.entity_id==row.id)):
                if item.kind=='public_fact' and item.body==row.display_name:item.status='disputed'
    print({'roles_corrected':count})

if __name__=='__main__':main()

"""精确修复普通对话误写的画像运行状态；原值先落盘，不改变产品、地区和用户偏好。"""
import json
import re
from sqlalchemy import select
from app.db import Session,Conversation,Memory
from app.config import ROOT


def main():
    """无参数；仅匹配本次已复现的身份问答运行文案，备份后清除questions和临时summary。"""
    original=[]
    with Session.begin() as db:
        for table in (Conversation,Memory):
            for row in db.scalars(select(table)):
                value=row.profile if table is Conversation else (row.value or {}).get('profile')
                if not value:continue
                transient=' '.join(value.get('questions',[]))+' '+value.get('summary','')
                if not re.search('助手身份|仅询问.*身份|本轮.*不执行',transient):continue
                original.append({'table':table.__tablename__,'id':row.id,'profile':value})
                fixed={**value,'questions':[],'summary':'产品：'+'、'.join(x['name'] for x in value.get('products',[]))}
                if table is Conversation:row.profile=fixed
                else:row.value={**row.value,'profile':fixed}
        # 备份成功才允许事务提交，防止误修复无法恢复。
        path=ROOT/'.codex-tmp/identity-profile-repair.json'
        if original:path.write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    print({'repaired_profiles':len(original)})


if __name__=='__main__':main()

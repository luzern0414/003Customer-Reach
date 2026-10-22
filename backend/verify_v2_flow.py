"""实际模型/检索/SSE/CRM联通验收，结果仅记录真实系统输出，不补造线索。"""
import json
import time
import uuid
import httpx
from app.config import ROOT
from app.schemas import SettingsInput


def main():
    """无参数；临时收紧任务预算并恢复设置，真实请求的ID/耗时/来源/预算落盘供复核。"""
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=360) as client:
        previous=client.get('/api/settings').json();allowed=set(SettingsInput.model_fields)
        original={k:v for k,v in previous.items() if k in allowed}
        client.patch('/api/settings',json={**original,'max_leads':1,'max_searches':3,'max_reads':4,'max_seconds':300}).raise_for_status()
        try:
            conv=client.post('/api/conversations').json()['id']
            response=client.post(f'/api/conversations/{conv}/messages',json={
                'content':'沿用吊灯、吸顶灯、轨道灯产品。核验深圳市三雄照明电器有限公司是否为深圳灯具代理或销售点，最多1家，补公开电话、地址、主营品类。只使用有主体关联的原文，资料不足换渠道，不推测采购或营收。',
                'client_token':uuid.uuid4().hex});response.raise_for_status();job_id=response.json()['id']
            first=None;done=None;deltas=0;ids=[];event=''
            with client.stream('GET',f'/api/jobs/{job_id}/events') as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if line.startswith('id: '):ids.append(int(line[4:]))
                    if line.startswith('event: '):event=line[7:]
                    if line.startswith('data: '):
                        payload=json.loads(line[6:])
                        if event=='message.delta':deltas+=1;first=first or time.time()
                        if event=='message.completed':done=time.time()
            final=client.get('/api/jobs/'+job_id).json()
            assert final['status'] in {'completed','partial','failed'}
            assert ids==sorted(set(ids))
            if final['status']=='completed':assert first and done and first<done and deltas>1
            leads=[client.get('/api/leads/'+lead_id).json() for lead_id in final['lead_ids']]
            result={'job_id':job_id,'conversation_id':conv,'status':final['status'],'elapsed_ms':final['elapsed_ms'],
                'lead_ids':final['lead_ids'],'lead_names':[x['display_name'] for x in leads],'source_count':final['source_count'],
                'delta_events':deltas,'first_delta_at':first,'message_completed_at':done,'metrics':final['metrics'],'error':final['error']}
            (ROOT/'.codex-tmp/v2-final-live-flow.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(result)
        finally:client.patch('/api/settings',json=original).raise_for_status()


if __name__=='__main__':main()

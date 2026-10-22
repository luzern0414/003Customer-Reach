"""真实运行恢复验收：先建立任务并安全暂停，重启服务后以同一ID恢复检查点。"""
import json
import sys
import time
import uuid
from pathlib import Path
import httpx
from app.config import ROOT

ARTIFACT=ROOT/'.codex-tmp/v2-live-recovery.json'

def main(mode: str):
    """mode为start或resume，实际调用本机API；失败抛异常，不把超时当完成，不显示联系人/密钥。"""
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
        if mode=='start':
            conversation=client.post('/api/conversations').json()
            response=client.post('/api/conversations/'+conversation['id']+'/messages',json={
                'content':'继续寻找深圳灯具零售门店，明确的直营门市或专卖店优先，不选制造商。最多1家。先复用已有信息，缺电话或地址从其他渠道补查。',
                'client_token':uuid.uuid4().hex})
            response.raise_for_status();job_id=response.json()['id']
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                job=client.get('/api/jobs/'+job_id).json()
                if job['status'] not in {'queued','running','cancelling'}:raise RuntimeError('任务已终止，尚未证明恢复')
                if job['stage'] in {'plan','decide','search','read','extract'} and any(x['tool']=='product_profile' and x['status']=='completed' for x in job['tools']):
                    client.post('/api/jobs/'+job_id+'/pause').raise_for_status();break
                time.sleep(.5)
            else:raise TimeoutError('未观察到可暂停阶段')
            for _ in range(40):
                job=client.get('/api/jobs/'+job_id).json()
                if job['status']=='paused':break
                time.sleep(.5)
            assert job['status']=='paused'
            checkpoint=client.get('/api/jobs/'+job_id+'/state').json()
            assert checkpoint['checkpoint_id'] and checkpoint['next']
            result={'job_id':job_id,'conversation_id':conversation['id'],'paused_elapsed_ms':job['elapsed_ms'],
                    'checkpoint_id':checkpoint['checkpoint_id'],'next':checkpoint['next'],
                    'successful_operations':[x['operation_id'] for x in job['tools'] if x['status']=='completed']}
            ARTIFACT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(result)
        elif mode=='resume':
            result=json.loads(ARTIFACT.read_text(encoding='utf-8'));job_id=result['job_id']
            before=client.get('/api/jobs/'+job_id).json();assert before['status']=='paused'
            assert before['elapsed_ms']==result['paused_elapsed_ms']
            profile=client.get('/api/conversations/'+result['conversation_id']).json()['profile']
            assert profile['products'] and not profile['questions']
            result['recalled_products']=[x['name'] for x in profile['products']]
            client.post('/api/jobs/'+job_id+'/resume').raise_for_status()
            deadline=time.monotonic()+700;events=[];first_delta=None;completed_at=None
            with client.stream('GET','/api/jobs/'+job_id+'/events') as stream:
                stream.raise_for_status()
                event_name=''
                for line in stream.iter_lines():
                    if time.monotonic()>deadline:raise TimeoutError('恢复未结束')
                    if line.startswith('event: '):event_name=line[7:]
                    if line.startswith('data: '):
                        payload=json.loads(line[6:]);stamp=time.time()
                        events.append({'type':event_name,'at':stamp,'data':payload})
                        if event_name=='message.delta' and first_delta is None:first_delta=stamp
                        if event_name=='message.completed':completed_at=stamp
            final=client.get('/api/jobs/'+job_id).json()
            assert final['status'] in {'completed','partial'} and final['elapsed_ms']>before['elapsed_ms']
            operations=[x['operation_id'] for x in final['tools']]
            assert len(operations)==len(set(operations))
            assert all(x in operations for x in result['successful_operations'])
            assert sum(x['tool']=='product_profile' and x['status']=='completed' for x in final['tools'])==1
            assert first_delta is not None and completed_at is not None and first_delta<completed_at
            result.update(status=final['status'],elapsed_ms=final['elapsed_ms'],lead_ids=final['lead_ids'],
                unique_operations=len(operations),first_delta_at=first_delta,completed_at=completed_at,
                delta_events=sum(x['type']=='message.delta' for x in events),metrics=final['metrics'])
            ARTIFACT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(result)
        else:raise ValueError('mode must be start or resume')

if __name__=='__main__':main(sys.argv[1])

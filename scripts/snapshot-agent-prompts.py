"""生成可核对的 Agent 源码快照；只解析白名单文本，不导入业务模块或读取凭据。"""
import argparse
import ast
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'docs/02-产品与开发/设计文档/Agent运行提示词源码快照.md'
SECTIONS={
    'backend/app/intent.py':['recognize_intent'],
    'backend/app/agent.py':['load_context','profile_node','plan_node','decide_node','extract_node','save_node','answer_node'],
    'backend/app/company_research.py':['company_context','company_plan','company_extract','company_gap','tender_context','company_answer'],
    'backend/app/model_gateway.py':['structured'],
    'backend/app/research_tools.py':['SearchAccounts','FetchSource','SearchKnowledge','PersistLead','ParseAccount','PersistCompany',
        'QccCompanyLookup','QccOperationLookup','QccTenderLookup','ToolBroker.execute','ToolBroker.search_tenders','ToolBroker.get_tender_detail','ToolBroker.search_goal','ToolBroker.persist'],
    'backend/app/bidresearch_mcp.py':['BidSearch','BidDetail'],
    'backend/app/source_catalog.py':None,
    'backend/skills/buyer-research/SKILL.md':None,
    'backend/skills/buyer-research/references/runtime-playbook.md':None,
    'backend/app/schemas.py':None,
    'backend/app/company_research_schemas.py':None,
    'backend/app/answer_summary.py':None,
    'backend/app/prompts/acquisition.py':None,
    'backend/app/lead_analysis.py':None,
    'backend/app/company_service.py':['company_match_context'],
    'backend/app/company_validation.py':['save_snapshot'],
}


def render():
    """仅从固定源文件生成静态 Markdown 与逐文件 SHA-256；不填入运行时资料。"""
    parts=['# Agent 运行提示词源码快照','',
        '2026-10-14，执行者：Codex。配合[项目完整提示词与Agent接续执行](项目完整提示词与Agent接续执行.md)使用。','',
        '这是当前白名单源码的模板、拼装函数及参数契约，不是某次任务实际发送的完整 messages。动态画像、正文、用户需求、附件、记忆、工具结果和 JSON Schema 在运行时填入。','',
        '保留函数条件与变量引用；源码为权威。生成器只用 AST 和文件读取，不导入业务 app，不读凭据、数据库或上传文件。','',
        '同步命令：`python scripts/snapshot-agent-prompts.py`；只校验：`python scripts/snapshot-agent-prompts.py --check`。企查查与采购工具使用范围见[接入与验收](13-agent-mcp.md)。','']
    hashes=[]
    for file,names in SECTIONS.items():
        raw=(ROOT/file).read_bytes();source=raw.decode('utf-8-sig').replace('\r\n','\n')
        hashes.append((file,hashlib.sha256(raw).hexdigest()))
        parts.extend(['## '+file,''])
        if names is None:
            parts.extend(['```'+('python' if file.endswith('.py') else 'markdown'),source.rstrip(),'```',''])
            continue
        tree=ast.parse(source)
        nodes={node.name:node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        for name in names:
            owner,_,member=name.partition('.')
            node=nodes[owner]
            if member:node=next(item for item in node.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name==member)
            parts.extend(['### '+name,'','来源：`'+file+':'+str(node.lineno)+'`。','',
                '```python',ast.get_source_segment(source,node),'```',''])
    parts.extend(['## 快照一致性清单','','| 源文件 | SHA-256 |','| --- | --- |'])
    parts.extend('| `'+file+'` | `'+digest+'` |' for file,digest in hashes)
    parts.extend(['','源码/Skill 变化后同步生成并核验；应用运行时直接读取源码/Skill，不读取本快照。',''])
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();expected=render()
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding='utf-8')!=expected:raise SystemExit('Agent snapshot is stale')
        print('Agent snapshot matches all allowlisted sources')
    else:
        TARGET.write_text(expected,encoding='utf-8')
        print(str(TARGET))


if __name__=='__main__':main()

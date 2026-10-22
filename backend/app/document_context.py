"""选择有界附件上下文；显式保留未读限制，不声称整个文件进入模型。"""
import re


def attachment_context(attachment, prompt: str, budget: int = 20000) -> str:
    """attachment为已解析附件，prompt为本轮文本；budget正数，返回文件范围和原文片段。

    超预算取首尾与关键词段落，未选段落不推断；为空文本只返回元信息。
    """
    content = attachment.text or ''
    info = attachment.parse_info or {}
    prefix = f'文件：{attachment.filename}；提取警告：{info.get("warnings", [])}；截断：{attachment.truncated}\n'
    if len(content) <= budget:
        return prefix + content
    blocks = [content[start:start+2500] for start in range(0, len(content), 2500)]
    tokens = list(dict.fromkeys(re.findall(r'[A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,6}', prompt)))
    scores = sorted(range(1, len(blocks)-1), key=lambda i: sum(token in blocks[i] for token in tokens), reverse=True)
    selected = sorted(set([0, len(blocks)-1, *scores[:max(0, budget//2500-2)]]))
    return prefix + '模型上下文为选定原文片段，其他段落未读取，不可声称已完整分析。\n' + '\n'.join(
        f'[字符位置{index*2500+1}]\n{blocks[index]}' for index in selected)

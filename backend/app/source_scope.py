"""识别当前用户明确限定的网页复核范围，避免缺口补查扩大授权范围。"""
import re


def reference_only(prompt: str, references: list) -> bool:
    """prompt为当前消息、references为已解析链接（可空）；明确禁止额外搜索/读页且有链接时返回True，否则False，不改变开放获客流程。"""
    if not references:return False
    text=re.sub(r'\s+','',prompt or '')
    return bool(re.search(r'(?:不得|不要|禁止|无需|不需要|不)(?:再|去)?(?:搜索|检索|读取)(?:任何)?(?:其他|其它|别的)(?:页面|网页|网站|链接|网址)',text) or
        re.search(r'(?:仅|只)(?:复核|读取|分析|核验)(?:这个|这些|该|以下|指定|此)(?:[0-9一二三四五六七八九十]+个?)?(?:已读取的?|已取得的?)?(?:公开)?(?:页面|网页|链接|网址|目录)',text))

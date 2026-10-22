"""真实检索探针；只打印公开来源和工具结构，不读取模型密钥。"""
import asyncio
from app.gateway import call_exa, split_sources

async def main():
    """验证公开检索和读取的返回格式；失败抛异常，不绕过限流。"""
    text = await call_exa('web_search_exa', {'query':'深圳 灯饰 商场 经销商 联系电话', 'numResults':3})
    print(text[:14000])
    rows = split_sources(text)
    print('PARSED SOURCES:', len(rows))
    if rows:
        content = await call_exa('web_fetch_exa', {'urls':[rows[0]['url']], 'maxCharacters':18000})
        print('FETCH:', content[:14000])
        print('PARSED FETCH:', len(split_sources(content)))

if __name__ == '__main__':
    asyncio.run(main())

"""真实验证6luna通过LangChain的工具、Pydantic和流式能力，输出仅为能力指标。"""
import asyncio
from app.model_gateway import test_connection

if __name__=='__main__':
    print(asyncio.run(asyncio.wait_for(test_connection(),timeout=90)))

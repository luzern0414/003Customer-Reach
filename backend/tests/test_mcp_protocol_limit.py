"""初始化阶段JSON-RPC限流必须进入已有供应商熔断，不返回供应商原始消息。"""
from types import SimpleNamespace
from app.source_errors import source_limit


class ProtocolError(Exception):
    """模拟实际MCP error对象形状，仅用于本地分类验证。"""
    def __init__(self,message):
        """message为原始协议错误说明，构造SDK同形error，不发送任何网络请求。"""
        self.error=SimpleNamespace(code=-32000,message=message)


def test_free_mcp_limit_during_initialize_is_classified_without_raw_message():
    """无入参；真实协议消息形状在嵌套组中也识别，输出只保留安全类别。"""
    error=ProtocolError("You've hit Exa's free MCP rate limit. Create your own Exa API key.")
    result=source_limit(ExceptionGroup('transport',[error]))
    assert result.scope=='provider' and result.delay>=60
    assert str(result)=='provider_rate_limited'
    assert source_limit(ProtocolError('Unknown tool name')) is None
    assert source_limit(ProtocolError('Too many requests, retry after 300 seconds')).delay==300

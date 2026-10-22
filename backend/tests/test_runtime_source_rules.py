"""运行Skill必须覆盖全部启用渠道，不能被历史记录挤掉或注入客户种子。"""
import pytest
from app import source_catalog


def test_all_enabled_channels_are_present_without_customer_seeds():
    """全公开渠道规则须完整且有界，授权渠道不误暴露；已知客户及号码不混入规划。"""
    channels=source_catalog.available_channels(list(source_catalog.CHANNELS))
    guide=source_catalog.source_rules(channels)
    assert len(guide)<=6000
    assert all('渠道规则['+key+']' in guide for key in ['common',*channels])
    assert 'openapi.qcc.com' in guide and 'open.1688.com' in guide
    assert 'provider_rate_limited' in guide and '567' in guide and 'robots' in guide
    assert '飞利浦灯饰' not in guide and '美东灯饰' not in guide and '18926563839' not in guide
    assert '/company/detail/' not in guide and 'subbranch-detail/i-' not in guide
    assert '渠道规则[company_api]' not in guide
    qcc=source_catalog.source_rules(['qcc_public'])
    assert '渠道规则[qcc_public]' in qcc and '渠道规则[mall_directory]' not in qcc
    assert 'leanju.com' not in qcc


def test_oversize_rule_configuration_fails_instead_of_dropping_channels(monkeypatch):
    """配置超限明确报错，不能看似成功但末尾平台规则缺失；只拦截本轮运行规则文件。"""
    original=source_catalog.Path.read_text
    def read(path,*args,**kwargs):
        """path/args/kwargs为真实读取参数；仅测试规则文件返回超限配置，其他文件保留原行为。"""
        if path.name=='runtime-playbook.md':return '## common\n'+('x'*6001)+'\n## qcc_public\n企查查规则'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(source_catalog.Path,'read_text',read)
    with pytest.raises(ValueError,match='channel_rules_exceed_limit'):
        source_catalog.source_rules(['qcc_public'])

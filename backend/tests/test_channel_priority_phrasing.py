"""复现真实自主Agent任务中的画像渠道抢先及两家网站数量误读。"""
import pytest
from app.source_catalog import requested_channels,preferred_channels,active_channels,required_sites

def test_explicit_first_channels_override_earlier_buyer_description():
    """无参数；用户目标先提家居城，明确先尝试平台必须成为实际渠道前缀。"""
    channels=['official','b2b_1688','qcc_public','industry_directory','mall_directory']
    prompt='自主寻找深圳经销商和家居城。先尝试1688、企查查的公开信息，再更换行业黄页和企业官网。至少两家不同网站核验每个客户。'
    assert requested_channels(prompt,channels)[:2]==['b2b_1688','qcc_public']
    assert preferred_channels(prompt,channels)[:2]==['b2b_1688','qcc_public']
    assert required_sites(prompt)==2

def test_explicit_first_does_not_enable_or_unban_channel():
    """无参数；显式先查不能突破原启用范围和当前否定，未指定仍原位置顺序。"""
    channels=['qcc_public','mall_directory','industry_directory']
    prompt='找家居城。先尝试1688、企查查，不查企查查，改用行业黄页。'
    assert 'qcc_public' not in active_channels(prompt,channels)
    assert requested_channels(prompt,channels)==['mall_directory','industry_directory']
    assert requested_channels('先查企查查再查1688',['qcc_public','b2b_1688'])==['qcc_public','b2b_1688']

@pytest.mark.parametrize('prompt,expected',[('至少两家不同网站',2),('三家独立平台',3),('两处独立来源',2),('找3家深圳客户',1),('找两家经销商',1)])
def test_source_count_is_not_buyer_count(prompt,expected):
    """prompt为真实量词变体，expected为所需来源数；仅来源名紧随数字时认可。"""
    assert required_sites(prompt)==expected

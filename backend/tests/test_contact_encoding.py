"""GBK/UTF-8实际内容与旧GB2312声明不一致时，不丢联系区或商场正文。"""
import asyncio
import pytest


@pytest.mark.parametrize('encoding',['gbk','utf-8'])
def test_visible_contact_keeps_original_text_without_native_encoding_error(encoding,capfd):
    """encoding为实际字节编码、capfd捕获native stderr；完全合成HTML，保留扩展字/原号码并拒绝隐藏电话。"""
    from app.public_contacts import contact_blocks
    edge=bytes.fromhex('88b6c7f8').decode('gbk')
    phrase='电话仅作合成编码验证，地址深圳照明。'+edge
    content=('<html><meta charset=gb2312><div class=contact>'+phrase*20+
        '业务电话：0755-23004025<span hidden>电话13900000004</span><span style="display:none">电话13900000005</span>'+
        '</div><div class=contact hidden>隐藏电话：13900000003</div></html>').encode(encoding)
    result=asyncio.run(asyncio.to_thread(contact_blocks,content))
    assert edge in result and '0755-23004025' in result and '13900000003' not in result
    assert '13900000004' not in result and '13900000005' not in result
    output=capfd.readouterr()
    assert 'encoding error' not in output.err and 'encoder error' not in output.err


def test_mall_directory_uses_same_decoder_as_main_body(capfd):
    """capfd捕获C解析器输出；保留合成目录标题/租户号码和扩展字符，原声明不改写为企业事实。"""
    from app.public_directory import directory_text
    edge=bytes.fromhex('88b6c7f8').decode('gbk')
    content=('<html><meta charset=gb2312><div class="subbranch-det"><p>'+('深圳合成目录介绍'+edge)*20+
        '</p><div class="de-tit">隔离测试店 入驻品牌</div><p>隔离照明店</p><p>Tel:0755-23004025</p></div></html>').encode('gbk')
    result=asyncio.run(asyncio.to_thread(directory_text,content,'http://www.leanju.com:8080/subbranch-detail/i-1.html'))
    assert edge in result and '隔离照明店' in result and '0755-23004025' in result
    output=capfd.readouterr()
    assert 'encoding error' not in output.err and 'encoder error' not in output.err

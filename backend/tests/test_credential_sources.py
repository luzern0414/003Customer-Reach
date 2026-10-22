"""凭据文件来源隔离；全部密钥为虚构夹具，不访问云端。"""
import pytest
from app import config,tracing


@pytest.mark.parametrize('content',[
    'https://example.org/v1\nsk-model-fixture\nlsv2_trace-fixture',
    '{"api_key":"sk-model-fixture","langsmith_api_key":"lsv2_trace-fixture"}',
    '{"langsmith":{"api_key":"lsv2_trace-fixture"}}'])
def test_file_trace_key_is_separate(content,tmp_path,monkeypatch):
    """content为虚构支持格式，tmp_path隔离文件；模型Key不会被用为追踪Key。"""
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    path=tmp_path/'apikey.txt';path.write_text(content,encoding='utf-8')
    assert config.langsmith_key(path)=='lsv2_trace-fixture'
    monkeypatch.setenv('LANGSMITH_API_KEY','environment-fixture')
    assert config.langsmith_key(path)=='environment-fixture'
    monkeypatch.setenv('LANGSMITH_API_KEY','')
    assert not config.langsmith_key(path)


def test_model_does_not_fall_back_to_trace_key(tmp_path,monkeypatch):
    """tmp_path只含独立追踪Key；模型配置必须失败，不能把云追踪凭据发给模型端点。"""
    monkeypatch.delenv('CLIENTREACH_MODEL_KEY',raising=False)
    monkeypatch.delenv('CLIENTREACH_MODEL_URL',raising=False)
    monkeypatch.setattr(config,'ROOT',tmp_path)
    (tmp_path/'config').mkdir()
    (tmp_path/'config/apikey.txt').write_text('https://example.org/v1\nlsv2_trace-fixture',encoding='utf-8')
    with pytest.raises(ValueError):config.credentials()


def test_status_uses_file_without_exposing_secret(tmp_path,monkeypatch):
    """tmp_path是虚构文件配置；状态只返回布尔值，不含凭据。"""
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setattr(tracing,'ROOT',tmp_path)
    (tmp_path/'config').mkdir()
    (tmp_path/'config/apikey.txt').write_text('lsv2_trace-fixture',encoding='utf-8')
    status=tracing.tracing_status()
    assert status['configured'] and status['enabled'] and 'fixture' not in str(status)

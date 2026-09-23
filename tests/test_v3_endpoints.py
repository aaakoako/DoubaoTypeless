import pytest
from doubao_typeless.services.endpoints import normalize_endpoint,EndpointError
from doubao_typeless.services.byok import chat_url


@pytest.mark.parametrize('raw,expected',[
    ('api.example.com','https://api.example.com/v1/chat/completions'),
    (' https://api.example.com/v1/ ','https://api.example.com/v1/chat/completions'),
    ('https://api.example.com/V1/Completion','https://api.example.com/v1/chat/completions'),
    ('https:/api.example.com/v1','https://api.example.com/v1/chat/completions'),
    ('https//api.example.com/v1','https://api.example.com/v1/chat/completions'),
    ('https://api.example.com/v1/v1/chat/completions/','https://api.example.com/v1/chat/completions'),
    ('https://api.example.com/v1/chat','https://api.example.com/v1/chat/completions'),
    ('https://api.example.com/v1/chat/completions/chat/completions','https://api.example.com/v1/chat/completions'),
    ('https://api.example.com/api/chat/completions','https://api.example.com/api/chat/completions'),
    ('https://api.example.com/chat/completions','https://api.example.com/chat/completions'),
    ('https://open.bigmodel.cn/api/paas/v4','https://open.bigmodel.cn/api/paas/v4/chat/completions'),
    ('openrouter.ai','https://openrouter.ai/api/v1/chat/completions'),
    ('openrouter.ai/api/v1/','https://openrouter.ai/api/v1/chat/completions'),
    ('localhost:11434','http://localhost:11434/v1/chat/completions'),
    ('http://[::1]:1234/v1','http://[::1]:1234/v1/chat/completions'),
])
def test_common_chat_addresses(raw,expected):
    assert chat_url(raw)==expected
    assert chat_url(expected)==expected


@pytest.mark.parametrize('raw,expected',[
    ('api.typesafe.ai','https://api.typesafe.ai/v1/systemone'),
    ('openrouter.ai/api','https://openrouter.ai/api/v1/systemone'),
    ('openrouter.ai/api/v1/systemone','https://openrouter.ai/api/v1/systemone'),
    ('https://openrouter.ai/api/alpha/decisions','https://openrouter.ai/api/v1/systemone'),
    ('ai-gateway.vercel.sh','https://ai-gateway.vercel.sh/typesafe/v1/systemone'),
    ('https://ai-gateway.vercel.sh/typesafe/v1/systemone','https://ai-gateway.vercel.sh/typesafe/v1/systemone'),
    ('https://my.example/systemone','https://my.example/systemone'),
    ('https://my.example/evaluate/systemone','https://my.example/evaluate/systemone'),
])
def test_decision_addresses(raw,expected):
    assert normalize_endpoint(raw,'systemone')==expected
    assert normalize_endpoint(expected,'systemone')==expected


@pytest.mark.parametrize('raw',['v1','https://','file:///secret','https://name:token@example.com/v1',
    'https://example.com/v1?api_key=secret','https://example.com:0/v1','https://example.com:bad/v1',
    'https://example.com:99999/v1','https://example .com/v1'])
def test_malformed_addresses_do_not_become_network_requests(raw):
    with pytest.raises(EndpointError):normalize_endpoint(raw)

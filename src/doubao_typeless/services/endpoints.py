"""Normalize compatible API addresses without ever probing guessed hosts."""
import ipaddress
import re
from urllib.parse import urlsplit,urlunsplit


class EndpointError(ValueError):
    pass


def _parts(value):
    raw=str(value or '').strip().strip('`\"\'').replace('\\','/')
    raw=re.sub(r'(?i)^(https?)(?::/*|//)',r'\1://',raw)
    if not raw:return None
    if len(raw)>2048 or re.search(r'\s',raw):raise EndpointError('地址格式有误')
    if '://' not in raw:
        host=urlsplit('//'+raw).hostname or ''
        local=host.lower()=='localhost'
        try:local=local or ipaddress.ip_address(host).is_private
        except ValueError:pass
        raw=('http://' if local else 'https://')+raw
    try:
        parts=urlsplit(raw);port=parts.port
    except ValueError as exc:raise EndpointError('端口格式有误') from exc
    if parts.scheme.lower() not in {'http','https'}:raise EndpointError('仅支持 HTTP 或 HTTPS 地址')
    if port==0:raise EndpointError('端口格式有误')
    if not parts.hostname or parts.hostname.lower() in {'http','https','v1','v2','chat','completion','completions'}:
        raise EndpointError('地址缺少服务商域名')
    if parts.username or parts.password:raise EndpointError('请把密钥填到 Key 栏')
    if parts.query or parts.fragment:raise EndpointError('地址不要附带查询参数或网页锚点')
    host=parts.hostname.lower()
    if ':' in host:host='['+host+']'
    netloc=host+(f':{port}' if port else '')
    return parts._replace(scheme=parts.scheme.lower(),netloc=netloc)


def normalize_endpoint(value,kind='chat'):
    parts=_parts(value)
    if parts is None:return ''
    if kind not in {'chat','systemone'}:raise ValueError('unknown API kind')
    path=re.sub('/+','/',parts.path).rstrip('/')
    path=re.sub(r'(?i)/v1(?:/v1)+(?=/|$)','/v1',path)
    path=re.sub(r'(?i)/(v\d+(?:beta\d*)?)(?=/|$)',lambda m:'/'+m[1].lower(),path)
    had_method=bool(re.search(r'(?i)/(?:chat/)?completions?$|/systemone$',path))
    # Remove a complete or misspelled terminal method, then append exactly one.
    while re.search(r'(?i)/(?:chat/)?completions?$|/systemone$',path):
        path=re.sub(r'(?i)/(?:chat/)?completions?$|/systemone$','',path)
    if path.lower().endswith('/chat'):path=path[:-5]
    if parts.hostname=='openrouter.ai':
        if path.lower()=='/api/alpha/decisions':path='/api/v1'
        if not path.startswith('/api'):path='/api'+path
    if parts.hostname=='ai-gateway.vercel.sh' and kind=='systemone' and not path.startswith('/typesafe'):
        path='/typesafe'+path
    if not had_method and not re.search(r'/v\d+(?:beta\d*)?(?:/|$)',path):path+='/v1'
    suffix='/chat/completions' if kind=='chat' else '/systemone'
    return urlunsplit(parts._replace(path=path+suffix))


def endpoint_origin(value):
    try:parts=_parts(value)
    except (EndpointError,ValueError):return ('','',None)
    return (parts.scheme,parts.hostname,parts.port) if parts else ('','',None)

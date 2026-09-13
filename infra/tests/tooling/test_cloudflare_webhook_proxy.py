"""Real loopback HTTP relay checks authentication, framing, bounds and redirects."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import http.client
from pathlib import Path
import sys
import threading
import time

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tofu/cloudflare'))
from webhook_proxy import Handler, BODY_LIMIT, RESPONSE_LIMIT


@pytest.fixture
def relay():
    received=[]
    class Upstream(BaseHTTPRequestHandler):
        status=200
        payload=b'{"ok":true}'
        def log_message(self,*args): pass
        def do_POST(self):
            received.append((self.path,dict(self.headers),self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(type(self).status)
            if self.status==302: self.send_header('Location','http://127.0.0.1:1/leak')
            self.send_header('Content-Length',str(len(type(self).payload)))
            self.end_headers();self.wfile.write(type(self).payload)
    origin=HTTPServer(('127.0.0.1',0),Upstream)
    class Proxy(Handler):
        secret='test-only-secret-not-a-production-key'*2
        upstream='http://127.0.0.1:'+str(origin.server_port)
    Handler.window_count=0;Handler.window_start=time.monotonic()
    proxy=HTTPServer(('127.0.0.1',0),Proxy)
    threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (origin,proxy)]
    for thread in threads: thread.start()
    def call(method='POST',path='/webhook/disposable',body=b'{}',headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',proxy.server_port,timeout=3)
        conn.request(method,path,body=body,headers={'X-Telegram-Bot-Api-Secret-Token':Proxy.secret,**(headers or {})})
        response=conn.getresponse();data=response.read();status=response.status;conn.close()
        return status,data
    yield call,received,Upstream,proxy.server_port,Proxy.secret
    for server in (proxy,origin): server.shutdown();server.server_close()
    for thread in threads: thread.join(timeout=3)


def test_authorized_json_forwarded_without_caller_credentials(relay):
    call,received,_,_,_=relay
    assert call(headers={'Authorization':'Bearer must-not-forward','Cookie':'must-not-forward'})==(200,b'{"ok":true}')
    path,headers,body=received[0]
    assert path=='/webhook/disposable' and body==b'{}'
    assert not {'Authorization','Cookie','X-Telegram-Bot-Api-Secret-Token'} & headers.keys()


@pytest.mark.parametrize('method,path,headers,status',[
    ('POST','/webhook/test',{'X-Telegram-Bot-Api-Secret-Token':'wrong'},401),
    ('GET','/webhook/test',{},405),('TRACE','/webhook/test',{},405),
    ('POST','/',{},404),('POST','/webhook/../admin',{},404),
    ('POST','/webhook/%2e%2e/admin',{},404),('POST','/webhook/test?query=1',{},404)])
def test_invalid_requests_never_reach_origin(relay,method,path,headers,status):
    call,received,_,_,_=relay
    assert call(method,path,headers=headers)[0]==status and received==[]


@pytest.mark.parametrize('body,status',[(b'not-json',400),(b'[]',400),(b'',413),(b'x'*(BODY_LIMIT+1),413)])
def test_body_must_be_bounded_json_object(relay,body,status):
    call,received,_,_,_=relay
    assert call(body=body)[0]==status and received==[]


def test_ambiguous_credentials_and_length_rejected(relay):
    _,received,_,port,secret=relay
    for header in ['Content-Length','X-Telegram-Bot-Api-Secret-Token']:
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
        conn.putrequest('POST','/webhook/test')
        conn.putheader('Content-Length','2')
        conn.putheader('X-Telegram-Bot-Api-Secret-Token',secret)
        conn.putheader(header,'2' if header=='Content-Length' else secret)
        conn.endheaders(b'{}')
        response=conn.getresponse();assert response.status in {400,401};response.read();conn.close()
    assert received==[]


def test_rate_limit_prevents_forwarding(relay):
    call,received,_,_,_=relay
    Handler.window_start=time.monotonic();Handler.window_count=60
    assert call()[0]==429 and received==[]


def test_redirect_is_returned_without_forwarding_secret(relay):
    call,received,upstream,_,_=relay
    upstream.status=302
    assert call()[0]==302 and len(received)==1


def test_upstream_response_is_bounded(relay):
    call,received,upstream,_,_=relay
    upstream.payload=b'x'*(RESPONSE_LIMIT+1)
    assert call()[0]==502 and len(received)==1


def test_missing_telegram_header_never_reaches_origin(relay):
    _,received,_,port,_=relay
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
    connection.request('POST','/webhook/test',body=b'{}')
    response=connection.getresponse()
    assert response.status==401 and received==[]
    response.read();connection.close()


def test_incomplete_headers_cannot_hold_proxy_indefinitely(relay):
    import socket
    _,received,_,port,_=relay
    with socket.create_connection(('127.0.0.1',port),timeout=7) as connection:
        connection.sendall(b'POST /webhook/test HTTP/1.1\r\n')
        assert connection.recv(1)==b''
    assert received==[]


@pytest.mark.parametrize('value',['','chunked'])
def test_transfer_encoding_is_rejected_even_if_empty(relay,value):
    call,received,_,_,_=relay
    assert call(headers={'Transfer-Encoding':value})[0]==400 and received==[]

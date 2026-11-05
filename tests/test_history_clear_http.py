"""The destructive HTTP surface is confirmed, asynchronous and idle by default."""
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from memstara.control.history import HistoryReset, CONFIRMATION


def test_reset_http_requires_confirmation_blocks_mutations_and_preserves_ownership(tmp_path,monkeypatch):
    from memstara.control import service,history
    workspace=SimpleNamespace(lock=threading.RLock())
    reset=HistoryReset(workspace,None,root=tmp_path)
    class Thread:
        def __init__(self,**kwargs):pass
        def start(self):pass
    # Only the reset worker is inert; the HTTP server uses the original Thread.
    original_thread=threading.Thread
    monkeypatch.setattr(history.threading,'Thread',Thread)
    monkeypatch.setattr(service,'HISTORY',reset)
    monkeypatch.setattr(service,'WORKSPACE',workspace)
    server=ThreadingHTTPServer(('127.0.0.1',0),service.Handler)
    # ThreadingMixIn itself needs real request-handler threads.
    monkeypatch.setattr(history.threading,'Thread',original_thread)
    monkeypatch.setattr(reset,'_worker',lambda record:None)
    thread=original_thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def request(path,body=None,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        r=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(r,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as response:return response.code,json.load(response)
    try:
        assert request('/control/history-reset')[1]['state']=='idle'
        assert not reset.state_path.exists()
        assert request('/control/history-reset',{})[0]==409
        body={'mode':'backup','confirmation':CONFIRMATION,'request_id':str(uuid4())}
        assert request('/control/history-reset',body,origin='https://untrusted.example')[0]==403
        status,result=request('/control/history-reset',body)
        assert status==202 and result['state']=='stopping'
        assert request('/control/history-reset',body)[1]['id']==result['id']
        assert request('/control/runs',{'pipeline_id':'any'})[0]==409
        assert request('/control/pipelines',{'action':'remove','id':'any'})[0]==409
        assert 'owner_identity' not in result and 'exceptions' not in result
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

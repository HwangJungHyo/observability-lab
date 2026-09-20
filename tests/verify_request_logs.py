"""HTTP integration check: JSON logs, correlation, error levels, no ID metric labels."""
import concurrent.futures,json,os,re,socket,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
APP=Path(__file__).resolve().parents[1]/'services/order-lab/app.py'
procs=[]
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]
def request(p,amount=10000,rid=None):
    headers={'Content-Type':'application/json'}
    if rid is not None:headers['X-Request-ID']=rid
    req=Request(f'http://127.0.0.1:{p}/orders',data=json.dumps({'amount':amount}).encode(),headers=headers)
    try:r=urlopen(req,timeout=5)
    except HTTPError as e:r=e
    with r:return r.status,r.headers.get('X-Request-ID'),r.read()
def start(role,p,out,**extra):
    f=open(out,'w');proc=subprocess.Popen([sys.executable,str(APP)],env=dict(os.environ,SERVICE_NAME=role,PORT=str(p),**extra),stdout=f,stderr=subprocess.DEVNULL);f.close();procs.append(proc)
    for _ in range(100):
        try:
            with urlopen(f'http://127.0.0.1:{p}/healthz',timeout=1) as r:
                if r.status==200:return proc
        except OSError:time.sleep(.02)
    raise RuntimeError('startup failed')
try:
    with tempfile.TemporaryDirectory() as d:
        pp,op=port(),port();pl=Path(d)/'payment';ol=Path(d)/'orders'
        payment=start('payment',pp,pl)
        start('order-api',op,ol,PAYMENT_URL=f'http://127.0.0.1:{pp}/payments')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:
            results=list(e.map(lambda i:request(op,rid=f'log-test-{i}'),range(4)))
        assert all(status==201 and rid==f'log-test-{i}' for i,(status,rid,_) in enumerate(results))
        status,generated,_=request(op,rid='bad id');assert status==201 and re.fullmatch(r'[a-f0-9-]{36}',generated)
        assert request(op,0,'bad-amount')[0]==400
        payment.terminate();payment.wait()
        assert request(op,rid='payment-down')[0]==502
        with urlopen(f'http://127.0.0.1:{op}/metrics') as r:
            assert 'request_id' not in r.read().decode()
        # Replies can arrive just before finally writes the completion log.
        for _ in range(100):
            orders=[json.loads(s) for s in ol.read_text().splitlines()]
            if any(x.get('request_id')=='payment-down' for x in orders):break
            time.sleep(.01)
        payments=[json.loads(s) for s in pl.read_text().splitlines()]
        orders=[x for x in orders if x['event']=='request_completed']
        payments=[x for x in payments if x['event']=='request_completed']
        assert len(orders)==7 and len(payments)==5
        for i in range(4):
            a=[x for x in orders if x['request_id']==f'log-test-{i}'];b=[x for x in payments if x['request_id']==f'log-test-{i}']
            assert len(a)==len(b)==1 and a[0]['status_code']==201 and b[0]['status_code']==200
        assert any(x['level']=='warn' and x['error']=='invalid_request' for x in orders)
        assert any(x['level']=='error' and x['error']=='payment_unavailable' for x in orders)
        assert all(x['timestamp'].endswith('+00:00') and x['duration_ms']>=0 for x in orders)
        assert all('amount' not in x and 'body' not in x for x in orders+payments)
        assert all('trace_id' not in x and 'span_id' not in x for x in orders+payments)
        print('PASS: concurrent request ID propagation, response header, generated ID, JSON levels/errors/UTC, health suppression, no ID metric labels')
finally:
    for p in procs:
        if p.poll() is None:p.terminate()
    for p in procs:p.wait(timeout=3)

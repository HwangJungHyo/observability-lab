import os,sys,subprocess,time,json,urllib.request,urllib.error,socket,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from prometheus_client.parser import text_string_to_metric_families
from pathlib import Path
APP=str(Path(__file__).resolve().parents[1] / 'services/order-lab/app.py')
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]
def request(p,path,data=None):
    r=urllib.request.Request(f'http://127.0.0.1:{p}{path}',data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(r,timeout=4) as f:return f.status,f.read().decode()
    except urllib.error.HTTPError as e:return e.code,e.read().decode()
def start(role,p,extra={}):
    env=dict(os.environ,SERVICE_NAME=role,PORT=str(p),**extra)
    proc=subprocess.Popen([sys.executable,APP],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    procs.append(proc)
    for _ in range(100):
        try:
            if request(p,'/healthz')[0]==200:return proc
        except OSError:pass
        time.sleep(.03)
    raise RuntimeError('startup failed')
def samples(p):
    return [s for f in text_string_to_metric_families(request(p,'/metrics')[1]) for s in f.samples]
def value(ss,name,**labels):
    return sum(s.value for s in ss if s.name==name and all(s.labels.get(k)==v for k,v in labels.items()))
procs=[]
try:
    pp,op=port(),port()
    payment=start('payment',pp)
    start('order-api',op,{'PAYMENT_URL':f'http://127.0.0.1:{pp}/payments'})
    before=samples(op)
    assert value(before,'lab_http_requests_total')==0
    assert request(op,'/orders',{'amount':10000})[0]==201
    assert request(op,'/orders',{'amount':0})[0]==400
    assert request(op,'/random-id',{'amount':1})[0]==404
    assert request(op,'/healthz')[0]==200
    ss=samples(op)
    assert value(ss,'lab_http_requests_total',status_code='201')==1
    assert value(ss,'lab_http_requests_total',status_code='400')==1
    assert value(ss,'lab_http_requests_total')==2
    assert value(ss,'lab_http_request_duration_seconds_count')==2
    assert value(ss,'lab_http_request_duration_seconds_sum')>=.08
    assert value(samples(pp),'lab_http_requests_total',status_code='200')==1
    payment.terminate(); payment.wait()
    assert request(op,'/orders',{'amount':10000})[0]==502
    assert value(samples(op),'lab_http_requests_total',status_code='502')==1
    # A slow dependency verifies 504 and elapsed-time observation.
    class Slow(BaseHTTPRequestHandler):
        def do_POST(self):time.sleep(.4)
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Slow)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    tp=port()
    start('order-api',tp,{'PAYMENT_URL':f'http://127.0.0.1:{server.server_port}/payments','PAYMENT_TIMEOUT_SECONDS':'.1'})
    assert request(tp,'/orders',{'amount':10000})[0]==504
    assert value(samples(tp),'lab_http_requests_total',status_code='504')==1
    assert value(samples(tp),'lab_http_request_duration_seconds_sum')>=.1
    server.shutdown();server.server_close()
    print('PASS: 201/400/502/504, payment counter, histogram counts/duration, health/metrics/404 excluded, zero series initialized')
finally:
    for p in procs:
        if p.poll() is None:p.terminate()
    for p in procs:p.wait(timeout=3)

"""Real HTTP processes -> OTLP protobuf receiver; no Docker/Tempo required."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

APP = Path(__file__).resolve().parents[1] / 'services/order-lab/app.py'
records, procs = [], []
lock = threading.Lock()

class Collector(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == '/v1/traces'
        data = ExportTraceServiceRequest()
        data.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
        with lock:
            for resource in data.resource_spans:
                service = next(a.value.string_value for a in resource.resource.attributes
                               if a.key == 'service.name')
                for scope in resource.scope_spans:
                    records.extend((service, span) for span in scope.spans)
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-protobuf')
        self.send_header('Content-Length', '0')
        self.end_headers()
    def log_message(self, *args):
        pass

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

collector = ThreadingHTTPServer(('127.0.0.1', 0), Collector)
threading.Thread(target=collector.serve_forever, daemon=True).start()

def start(role, p, **extra):
    env = dict(os.environ, SERVICE_NAME=role, PORT=str(p),
               OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=f'http://127.0.0.1:{collector.server_port}/v1/traces',
               **extra)
    proc = subprocess.Popen([sys.executable, str(APP)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(proc)
    for _ in range(150):
        if proc.poll() is not None:
            raise RuntimeError('app exited')
        try:
            with urlopen(f'http://127.0.0.1:{p}/healthz', timeout=1):
                return proc
        except OSError:
            time.sleep(.03)
    raise RuntimeError('startup timeout')

def order(p, rid, amount=10000, parent=None):
    headers = {'Content-Type': 'application/json', 'X-Request-ID': rid}
    if parent:
        headers['traceparent'] = parent
    req = Request(f'http://127.0.0.1:{p}/orders',
                  data=json.dumps({'amount': amount}).encode(), headers=headers)
    try:
        r = urlopen(req, timeout=5)
    except HTTPError as e:
        r = e
    with r:
        r.read()
        assert r.headers['X-Request-ID'] == rid
        tid = r.headers['X-Trace-ID']
        assert re.fullmatch('[0-9a-f]{32}', tid)
        return r.status, tid

def wait_trace(tid, count):
    for _ in range(150):
        with lock:
            found = [(svc, s) for svc, s in records if s.trace_id.hex() == tid]
        if len(found) == count:
            return found
        time.sleep(.04)
    raise AssertionError(f'{tid}: expected {count}, got {len(found)}')

def attributes(span):
    return {a.key: a.value for a in span.attributes}

try:
    pp, op = port(), port()
    payment = start('payment', pp)
    start('order-api', op, PAYMENT_URL=f'http://127.0.0.1:{pp}/payments')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda n: order(op, f'trace-{n}'), range(2)))
    assert all(status == 201 for status, _ in results)
    assert len({tid for _, tid in results}) == 2
    for _, tid in results:
        spans = wait_trace(tid, 3)
        root = next(s for svc, s in spans if svc == 'order-api' and s.kind == 2)
        client = next(s for svc, s in spans if svc == 'order-api' and s.kind == 3)
        child = next(s for svc, s in spans if svc == 'payment' and s.kind == 2)
        assert not root.parent_span_id
        assert client.parent_span_id == root.span_id
        assert child.parent_span_id == client.span_id
        assert root.name == 'POST /orders' and child.name == client.name == 'POST /payments'
        assert root.start_time_unix_nano <= client.start_time_unix_nano < client.end_time_unix_nano <= root.end_time_unix_nano
        assert (child.end_time_unix_nano-child.start_time_unix_nano)/1e9 >= .08
        assert attributes(root)['http.response.status_code'].int_value == 201
        assert attributes(child)['http.response.status_code'].int_value == 200
        assert all(s.status.code == 0 for _, s in spans)
    known = '0123456789abcdef0123456789abcdef'
    status, tid = order(op, 'parent-test', parent=f'00-{known}-0123456789abcdef-01')
    assert status == 201 and tid == known
    root = next(s for svc, s in wait_trace(tid, 3) if svc == 'order-api' and s.kind == 2)
    assert root.parent_span_id.hex() == '0123456789abcdef'
    status, tid = order(op, 'bad-amount', amount=0)
    assert status == 400
    assert wait_trace(tid, 1)[0][1].status.code == 0  # server 4xx is not a server fault
    payment.terminate()
    payment.wait(timeout=3)
    status, tid = order(op, 'payment-down')
    assert status == 502
    failed = wait_trace(tid, 2)
    assert all(svc == 'order-api' and s.status.code == 2 for svc, s in failed)
    with urlopen(f'http://127.0.0.1:{op}/metrics') as r:
        metrics = r.read().decode()
        assert 'trace_id' not in metrics and 'request_id' not in metrics
    with lock:
        assert len(records) == 12  # health and metrics do not create spans
        assert all(not s.events for _, s in records)  # no raw exception/body events
    # An unreachable exporter must not change the business response.
    collector.shutdown()
    collector.server_close()
    payment = start('payment', pp)
    assert order(op, 'collector-down')[0] == 201
    print('PASS: OTLP protobuf export, concurrent isolation, 3-span parent chain, W3C propagation, 400/502 status, no health spans/ID metric labels, business success without collector')
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        p.wait(timeout=3)
    collector.shutdown()
    collector.server_close()

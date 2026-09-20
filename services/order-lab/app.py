"""Local synthetic services with metrics, JSON logs and optional OTLP tracing."""
import json
import logging
import re
import sys
from datetime import datetime, timezone
import math
import os
import socket
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE = os.getenv("SERVICE_NAME", "order-api")
PORT = int(os.getenv("PORT", "8080"))
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment:8081/payments")
PAYMENT_TIMEOUT = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "2"))

PAYMENT_DELAY = float(os.getenv("PAYMENT_DELAY_SECONDS", "0.08"))
if not math.isfinite(PAYMENT_DELAY) or not 0 <= PAYMENT_DELAY <= 10:
    raise SystemExit("PAYMENT_DELAY_SECONDS must be finite and between 0 and 10")

# Only enable export when the tracing Compose overlay supplies an endpoint.
# Each lab root is sampled; child services respect the parent's sampling flag.
TRACE_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
if TRACE_ENDPOINT:
    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE,
                                  "deployment.environment.name": "lab"}),
        sampler=ParentBased(ALWAYS_ON),
    )
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=TRACE_ENDPOINT, timeout=3),
        schedule_delay_millis=1000, max_queue_size=2048,
        max_export_batch_size=256,
    ))
    trace.set_tracer_provider(provider)
TRACER = trace.get_tracer("observability-lab.order", "0.1.0")
PROPAGATOR = TraceContextTextMapPropagator()

REQUESTS = Counter(
    "lab_http_requests_total", "Completed business POST requests by response status.",
    ["service", "method", "route", "status_code"],
)
DURATION = Histogram(
    "lab_http_request_duration_seconds", "Server-side business POST duration.",
    ["service", "method", "route"],
    buckets=(0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 1, 2, 2.5, 5),
)
# Initialize known series so idle targets and zero server errors are visible.
BUSINESS_ROUTE = "/orders" if SERVICE == "order-api" else "/payments"
for status in (200, 201, 400, 500, 502, 504):
    REQUESTS.labels(SERVICE, "POST", BUSINESS_ROUTE, str(status))
DURATION.labels(SERVICE, "POST", BUSINESS_ROUTE)

LOG = logging.getLogger("order_lab")
LOG.setLevel(logging.INFO)
LOG.propagate = False
_stream = logging.StreamHandler(sys.stdout)
_stream.setFormatter(logging.Formatter("%(message)s"))
LOG.addHandler(_stream)


def emit_log(level, event, **fields):
    LOG.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level, "service": SERVICE, "event": event, **fields,
    }, ensure_ascii=True))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Business requests are logged once as JSON in do_POST's finally block.
        # This lab excludes health, metrics, unknown paths and unsupported methods.
        pass

    def reply(self, status, payload):
        self.response_status = status
        self.response_error = payload.get("error")
        body = json.dumps(payload).encode()
        self.send_response(status)
        if getattr(self, "request_id", None):
            self.send_header("X-Request-ID", self.request_id)
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            self.send_header("X-Trace-ID", format(span_context.trace_id, "032x"))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/metrics":
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/healthz":
            self.reply(200, {"status": "ok", "service": SERVICE})
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self):
        # Only the fixed business route is counted; raw URLs/IDs are not labels.
        if self.path != BUSINESS_ROUTE:
            self.reply(404, {"error": "not_found"})
            return
        incoming_id = self.headers.get("X-Request-ID", "")
        self.request_id = (incoming_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", incoming_id)
                           else str(uuid.uuid4()))
        # Normalize incoming header names before W3C traceparent extraction.
        parent = PROPAGATOR.extract({k.lower(): v for k, v in self.headers.items()})
        with TRACER.start_as_current_span(
            f"POST {BUSINESS_ROUTE}", context=parent, kind=SpanKind.SERVER,
            attributes={"http.request.method": "POST", "http.route": BUSINESS_ROUTE},
            record_exception=False, set_status_on_exception=False,
        ) as span:
            started = time.perf_counter()
            self.response_status = 500
            self.response_error = None
            try:
                self.handle_business_post()
            except Exception:
                self.reply(500, {"error": "internal_error"})
            finally:
                span.set_attribute("http.response.status_code", self.response_status)
                if self.response_status >= 500:
                    span.set_status(Status(StatusCode.ERROR, self.response_error or "internal_error"))
                    span.set_attribute("error.type", self.response_error or "internal_error")
                REQUESTS.labels(SERVICE, "POST", BUSINESS_ROUTE,
                                str(self.response_status)).inc()
                elapsed = time.perf_counter() - started
                DURATION.labels(SERVICE, "POST", BUSINESS_ROUTE).observe(elapsed)
                level = ("error" if self.response_status >= 500 else
                         "warn" if self.response_status >= 400 else "info")
                emit_log(level, "request_completed", request_id=self.request_id,
                         method="POST", route=BUSINESS_ROUTE, status_code=self.response_status,
                         duration_ms=round(elapsed * 1000, 3), error=self.response_error)

    def handle_business_post(self):
        expected = "/orders" if SERVICE == "order-api" else "/payments"
        if self.path != expected:
            self.reply(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("object required")
            amount = payload.get("amount")
            if type(amount) is not int or not 1 <= amount <= 100000000:
                raise ValueError("amount must be a positive integer <= 100000000")
        except (ValueError, UnicodeDecodeError) as exc:
            self.reply(400, {"error": "invalid_request", "detail": str(exc)})
            return

        if SERVICE == "payment":
            # Deterministic simulation only: no real payment processor or money.
            time.sleep(PAYMENT_DELAY)
            self.reply(200, {"status": "approved", "payment_id": str(uuid.uuid4())})
            return

        request = Request(PAYMENT_URL, data=json.dumps({"amount": amount}).encode(),
                          headers={"Content-Type": "application/json",
                                   "X-Request-ID": self.request_id}, method="POST")
        try:
            payment = self.call_payment(request)
            if payment.get("status") != "approved":
                raise ValueError("unexpected payment response")
            self.reply(201, {"order_id": str(uuid.uuid4()), "status": "confirmed",
                             "amount": amount, "payment_id": payment["payment_id"]})
        except HTTPError:
            self.reply(502, {"error": "payment_failed"})
        except (TimeoutError, socket.timeout):
            self.reply(504, {"error": "payment_timeout"})
        except URLError as exc:
            timeout = isinstance(exc.reason, (TimeoutError, socket.timeout))
            self.reply(504 if timeout else 502,
                       {"error": "payment_timeout" if timeout else "payment_unavailable"})
        except (ValueError, KeyError, AttributeError):
            self.reply(502, {"error": "invalid_payment_response"})

    def call_payment(self, request):
        # The client span covers the outbound request and reading its response.
        # No raw URL, payload, auth headers or exception text is exported.
        with TRACER.start_as_current_span(
            "POST /payments", kind=SpanKind.CLIENT,
            attributes={"http.request.method": "POST", "server.address": "payment"},
            record_exception=False, set_status_on_exception=False,
        ) as span:
            carrier = {}
            PROPAGATOR.inject(carrier)
            for key, value in carrier.items():
                request.add_header(key, value)
            try:
                with urlopen(request, timeout=PAYMENT_TIMEOUT) as response:
                    span.set_attribute("http.response.status_code", response.status)
                    return json.load(response)
            except Exception as exc:
                if isinstance(exc, HTTPError):
                    span.set_attribute("http.response.status_code", exc.code)
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise


if __name__ == "__main__":
    if SERVICE not in {"order-api", "payment"}:
        raise SystemExit("SERVICE_NAME must be order-api or payment")
    emit_log("info", "service_started", port=PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

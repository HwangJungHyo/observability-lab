"""Chapter 4-2: local-only synthetic services with Prometheus metrics."""
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
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE = os.getenv("SERVICE_NAME", "order-api")
PORT = int(os.getenv("PORT", "8080"))
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment:8081/payments")
PAYMENT_TIMEOUT = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "2"))

PAYMENT_DELAY = float(os.getenv("PAYMENT_DELAY_SECONDS", "0.08"))
if not math.isfinite(PAYMENT_DELAY) or not 0 <= PAYMENT_DELAY <= 10:
    raise SystemExit("PAYMENT_DELAY_SECONDS must be finite and between 0 and 10")

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
        started = time.perf_counter()
        self.response_status = 500
        self.response_error = None
        try:
            self.handle_business_post()
        except Exception:
            self.reply(500, {"error": "internal_error"})
        finally:
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
            with urlopen(request, timeout=PAYMENT_TIMEOUT) as response:
                payment = json.load(response)
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


if __name__ == "__main__":
    if SERVICE not in {"order-api", "payment"}:
        raise SystemExit("SERVICE_NAME must be order-api or payment")
    emit_log("info", "service_started", port=PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

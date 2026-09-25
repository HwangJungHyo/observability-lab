"""Integration probe: signed S3 CRUD, unsigned denial, Mimir ready/query.
Uses only Python standard library. Never prints credentials or response bodies.
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://object-store:8333")
MIMIR_ENDPOINT = os.environ.get("MIMIR_ENDPOINT", "http://mimir:9009")
BUCKET = "mimir-lab"
ACCESS = os.environ["AWS_ACCESS_KEY_ID"]
SECRET = os.environ["AWS_SECRET_ACCESS_KEY"]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def http(method, url, body=None, headers=None):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with OPENER.open(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()

def s3(method, key="", query="", body=b"", signed=True):
    path = "/" + BUCKET + ("/" + urllib.parse.quote(key, safe="/-_.~") if key else "")
    url = ENDPOINT + path + ("?" + query if query else "")
    headers = {}
    if signed:
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        payload = hashlib.sha256(body).hexdigest()
        host = urllib.parse.urlsplit(ENDPOINT).netloc
        names = "host;x-amz-content-sha256;x-amz-date"
        canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload}\nx-amz-date:{stamp}\n"
        canonical = "\n".join([method, path, query, canonical_headers, names, payload])
        scope = f"{day}/us-east-1/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        def mac(key_bytes, message):
            return hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
        signing = mac(mac(mac(mac(("AWS4" + SECRET).encode(), day), "us-east-1"), "s3"), "aws4_request")
        signature = hmac.new(signing, to_sign.encode(), hashlib.sha256).hexdigest()
        headers = {"x-amz-date": stamp, "x-amz-content-sha256": payload,
                   "Authorization": f"AWS4-HMAC-SHA256 Credential={ACCESS}/{scope}, SignedHeaders={names}, Signature={signature}"}
    return http(method, url, body if method in ("PUT", "POST") else None, headers)

def expect(condition, message):
    if not condition:
        raise RuntimeError(message)

def wait_ready(check, name, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                print("PASS:", name, flush=True)
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError(name + " timed out")

def storage():
    wait_ready(lambda: s3("HEAD")[0] == 200, "signed bucket HEAD")
    key = "_lab_probe/" + uuid.uuid4().hex
    data = b"mimir-s3-roundtrip-v1"
    written = False
    try:
        status, _ = s3("PUT", key, body=data)
        expect(status == 200, f"PUT returned HTTP {status}")
        written = True
        status, got = s3("GET", key)
        expect(status == 200 and got == data, "GET content mismatch")
        query = "list-type=2&prefix=" + urllib.parse.quote(key, safe="")
        status, listing = s3("GET", query=query)
        expect(status == 200, f"LIST returned HTTP {status}")
        keys = [node.text for node in ET.fromstring(listing).iter() if node.tag.split("}")[-1] == "Key"]
        expect(key in keys, "LIST missing probe key")
        status, _ = s3("GET", key, signed=False)
        expect(status in (401, 403), f"unsigned GET must be denied, got HTTP {status}")
        print("PASS: signed PUT/GET/LIST and unsigned GET denied", flush=True)
    finally:
        if written:
            status, _ = s3("DELETE", key)
            expect(status in (200, 204), f"probe DELETE failed HTTP {status}; key={key}")
    expect(s3("HEAD", key)[0] == 404, "deleted key still visible")
    print("PASS: DELETE and missing object confirmed", flush=True)

def mimir():
    wait_ready(lambda: http("GET", MIMIR_ENDPOINT + "/ready")[0] == 200, "Mimir /ready")
    status, body = http("GET", MIMIR_ENDPOINT + "/prometheus/api/v1/query?query=vector%281%29",
                        headers={"X-Scope-OrgID": "lab"})
    expect(status == 200, f"Mimir query HTTP {status}")
    result = json.loads(body)
    expect(result.get("status") == "success" and result["data"]["result"][0]["value"][1] == "1",
           "Mimir vector(1) failed")
    print("PASS: tenant lab query vector(1); ingestion not tested yet", flush=True)

if __name__ == "__main__":
    try:
        {"storage": storage, "mimir": mimir}[sys.argv[1]]()
    except Exception as error:
        print("FAIL:", type(error).__name__, str(error), file=sys.stderr)
        sys.exit(1)

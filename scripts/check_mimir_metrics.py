"""Run via existing order-api container; no extra Python packages required."""
import json
import time
import urllib.parse
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def get(url, headers=None):
    with opener.open(urllib.request.Request(url, headers=headers or {}), timeout=5) as response:
        result = json.load(response)
    if result.get("status") != "success":
        raise RuntimeError("API returned unsuccessful status")
    return result["data"]

def query(base, expression, at, headers=None):
    data = get(base + "/api/v1/query?" + urllib.parse.urlencode({"query": expression, "time": at}), headers)
    if data["resultType"] != "vector":
        raise RuntimeError("Expected vector")
    return {tuple(sorted(row["metric"].items())): float(row["value"][1]) for row in data["result"]}

def check():
    prom = "http://prometheus:9090"
    mimir = "http://mimir:9009/prometheus"
    tenant = {"X-Scope-OrgID": "lab"}
    selector = 'up{job=~"order-api|payment|mimir"}'
    deadline = time.monotonic() + 150
    last_error = "no samples"
    while time.monotonic() < deadline:
        try:
            active = get(prom + "/api/v1/status/config")["yaml"]
            if "http://mimir:9009/api/v1/push" not in active or "mimir_lab" not in active:
                raise RuntimeError("remote_write is not in active Prometheus config")
            now = time.time()
            reload_values = query(prom, "prometheus_config_last_reload_successful", now)
            if not reload_values or any(v != 1 for v in reload_values.values()):
                raise RuntimeError("Prometheus config reload not successful")
            # Compare at one explicit instant, leaving time for remote delivery.
            at = now - 30
            local = query(prom, selector, at)
            remote = query(mimir, selector, at, tenant)
            if len(local) != 3 or local != remote or any(v != 1 for v in local.values()):
                raise RuntimeError("Three healthy target series have not matched yet")
            local_ts = query(prom, "timestamp(" + selector + ")", at)
            remote_ts = query(mimir, "timestamp(" + selector + ")", at, tenant)
            if len(local_ts) != 3 or local_ts != remote_ts:
                raise RuntimeError("Source sample timestamps have not matched yet")
            if any(at - value > 45 or value > at for value in local_ts.values()):
                raise RuntimeError("Matching samples are stale")
            print("PASS: active remote_write and successful reload")
            print("PASS: order-api/payment/mimir up=1 on Prometheus and Mimir")
            print("PASS: identical labels, values and source sample timestamps")
            print("evaluation_time_unix=" + str(at))
            for labels, value in sorted(local_ts.items()):
                print("sample", dict(labels), "source_timestamp=" + str(value))
            print("Scope: sampled series only; block upload/retention/failure recovery not tested.")
            return
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            last_error = type(error).__name__ + ": " + str(error)
        time.sleep(5)
    raise SystemExit("FAIL: " + last_error)

check()

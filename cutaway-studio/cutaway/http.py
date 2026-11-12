"""Tiny HTTP helper on the standard library, with retries on network errors and 5xx.

Tests replace `transport` with a fake so nothing real is called.
"""

import json
import random
import time
import urllib.error
import urllib.request


class ApiError(RuntimeError):
    def __init__(self, status, detail, url=""):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status} from {url}: {detail}")


def _urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


transport = _urllib_transport


def request(method, url, headers=None, json_body=None, data=None, timeout=60, retries=4):
    headers = dict(headers or {})
    body = data
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers.setdefault("Content-Type", "application/json")
    delay = 2.0
    last = None
    for attempt in range(retries + 1):
        try:
            status, resp_headers, payload = transport(method, url, headers, body, timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = ApiError(0, f"network error: {e}", url)
        else:
            if status < 400:
                return status, resp_headers, payload
            detail = _detail(payload)
            if status == 429 or status >= 500:
                last = ApiError(status, detail, url)
                wait = resp_headers.get("Retry-After")
                if wait and str(wait).isdigit():
                    delay = max(delay, float(wait))
            else:
                raise ApiError(status, detail, url)
        if attempt < retries:
            time.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 2, 30)
    raise last


def request_json(method, url, **kw):
    _, _, payload = request(method, url, **kw)
    return json.loads(payload.decode() or "{}")


def _detail(payload):
    try:
        data = json.loads(payload.decode())
        if isinstance(data, dict):
            return data.get("detail") or data.get("error") or data.get("message") or data
        return data
    except Exception:
        return payload[:300].decode(errors="replace") if payload else ""


def download(url, path, timeout=300):
    status, _, payload = request("GET", url, timeout=timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import Handler as AppHandler


ALLOWED_CLIENT_IP = "43.134.124.9"
HNA_RELAY_BASE = "https://app.hnair.com/ticket/lfs/ffl/airLowFareSearch"
FORWARDED_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "ekingcode",
    "hna-app",
    "hna-channel",
    "user-agent",
}


def _restore_original_path(path):
    parsed = urlsplit(path)
    original_path = None
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "__path" and original_path is None:
            original_path = value
        else:
            query_items.append((key, value))
    if not original_path:
        return path
    query = urlencode(query_items, doseq=True)
    return original_path + (("?" + query) if query else "")


def _client_ip(headers):
    forwarded = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (headers.get("x-real-ip") or "").strip()


class handler(AppHandler):
    """Vercel 入口。"""

    def do_GET(self):
        self.path = _restore_original_path(self.path)
        return super().do_GET()

    def do_POST(self):
        self.path = _restore_original_path(self.path)
        if urlsplit(self.path).path != "/api/hna-relay":
            self.send_response(404)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return

        if _client_ip(self.headers) != ALLOWED_CLIENT_IP:
            self.send_response(403)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"error":"forbidden"}')
            return

        try:
            length = int(self.headers.get("content-length") or "0")
            if length <= 0 or length > 262144:
                raise ValueError("invalid body length")
            envelope = json.loads(self.rfile.read(length).decode("utf-8"))
            query = envelope.get("query") or {}
            body = envelope.get("body")
            headers = envelope.get("headers") or {}
            if not isinstance(query, dict) or not isinstance(body, dict) or not isinstance(headers, dict):
                raise ValueError("invalid envelope")
            target = HNA_RELAY_BASE
            if query:
                target += "?" + urlencode({str(k): str(v) for k, v in query.items()})
            forwarded_headers = {
                str(k): str(v)
                for k, v in headers.items()
                if str(k).lower() in FORWARDED_HEADERS
            }
            forwarded_headers["content-type"] = "application/json"
            payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request = Request(target, data=payload, headers=forwarded_headers, method="POST")
            try:
                upstream = urlopen(request, timeout=25)
                status = upstream.status
                response_body = upstream.read()
                response_headers = upstream.headers
            except HTTPError as error:
                status = error.code
                response_body = error.read()
                response_headers = error.headers

            self.send_response(status)
            content_type = response_headers.get("content-type") or "application/json; charset=utf-8"
            self.send_header("content-type", content_type)
            self.send_header("cache-control", "no-store")
            self.send_header("x-ffl-relay", "ffl365")
            for name in ("server", "via", "retry-after"):
                value = response_headers.get(name)
                if value:
                    self.send_header(f"x-ffl-upstream-{name}", value)
            self.end_headers()
            self.wfile.write(response_body)
        except (ValueError, json.JSONDecodeError) as error:
            self.send_response(400)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8"))
        except (URLError, TimeoutError, OSError) as error:
            self.send_response(502)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "relay upstream failed", "detail": str(error)[:160]}, ensure_ascii=False).encode("utf-8"))

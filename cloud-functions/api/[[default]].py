import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import Handler as AppHandler


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return AppHandler.log_message(self, fmt, *args)

    def send_json(self, data, status=200):
        return AppHandler.send_json(self, data, status)

    def send_file(self, path):
        return AppHandler.send_file(self, path)

    def do_GET(self):
        return AppHandler.do_GET(self)

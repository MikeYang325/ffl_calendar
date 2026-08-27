import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import Handler as AppHandler


class handler(AppHandler):
    """
    Vercel 入口。

    原始请求例如：
        /api/search?origin=PEK&destination=HGH

    vercel.json 会附加 __path，
    这里恢复成 app.py 原本认识的路径。
    """

    def do_GET(self):
        parsed = urlsplit(self.path)

        original_path = None
        query_items = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True
        ):
            if key == "__path" and original_path is None:
                original_path = value
            else:
                query_items.append((key, value))

        if original_path:
            query = urlencode(query_items, doseq=True)
            self.path = original_path

            if query:
                self.path += "?" + query

        return super().do_GET()

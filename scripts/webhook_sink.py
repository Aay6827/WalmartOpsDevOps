import json
from http.server import BaseHTTPRequestHandler, HTTPServer

EVENTS = []


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            status = payload.get("status")
            alerts = [
                {"alertname": a.get("labels", {}).get("alertname"), "status": a.get("status")}
                for a in payload.get("alerts", [])
            ]
        except Exception:
            status, alerts = "unparseable", []
        EVENTS.append({"seq": len(EVENTS) + 1, "status": status, "alerts": alerts})
        print("NOTIFY", status, alerts, flush=True)
        self._send(200, '{"ok": true}')

    def do_GET(self):
        if self.path == "/events":
            self._send(200, json.dumps(EVENTS))
        else:
            self._send(200, '{"status": "ok"}')

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
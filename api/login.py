import os
import json
import hashlib
import time
from http.server import BaseHTTPRequestHandler

# Simple token generation - hash of username + password + secret
def generate_token(username: str, password: str) -> str:
    secret = os.environ.get("AUTH_SECRET", "default-secret-change-me")
    data = f"{username}:{password}:{secret}"
    return hashlib.sha256(data.encode()).hexdigest()


def verify_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("AUTH_USERNAME", "")
    expected_pass = os.environ.get("AUTH_PASSWORD", "")

    if not expected_user or not expected_pass:
        return False

    return username == expected_user and password == expected_pass


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send(400, json.dumps({"error": "Invalid JSON"}), "application/json")
                return

            username = data.get("username", "")
            password = data.get("password", "")

            if not username or not password:
                self._send(400, json.dumps({"error": "Username and password required"}), "application/json")
                return

            if verify_credentials(username, password):
                token = generate_token(username, password)
                self._send(200, json.dumps({"token": token}), "application/json")
            else:
                self._send(401, json.dumps({"error": "Invalid credentials"}), "application/json")

        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}), "application/json")

    def do_GET(self):
        self._send(405, json.dumps({"error": "POST only"}), "application/json")

    def _send(self, status: int, body: str, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

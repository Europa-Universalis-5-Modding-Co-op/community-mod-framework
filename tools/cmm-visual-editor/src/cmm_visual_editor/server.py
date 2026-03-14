"""HTTP server for CMM Visual Editor."""

import json
import io
import os
import threading
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from .encoding import encode_bom, encode_json
from .generator import generate_all, merge_with_existing
from .models import dict_to_model, model_to_dict
from .parser import parse_mod_directory, parse_uploaded_files

STATIC_DIR = Path(__file__).parent / "static"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=400):
        self._send_json({"error": message}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json({"status": "ok"})
            return

        if path == "/api/browse":
            self._handle_browse()
            return

        if path == "/api/auto-open":
            self._send_json({"directory": self.server.auto_open_dir or ""})
            return

        if path == "/api/templates":
            self._send_json({
                "mod_id": "",
                "file_prefix": "",
                "mod_name": "",
                "mod_desc": "",
                "metadata_name": "",
                "metadata_id": "",
                "metadata_version": "0.1",
                "metadata_short_description": "",
                "metadata_tags": ["Utilities"],
                "metadata_game_version": "1.1.*",
                "tabs": [],
            })
            return

        # Serve static files
        if path == "/":
            path = "/index.html"

        file_path = (STATIC_DIR / path.lstrip("/")).resolve()

        if not str(file_path).startswith(str(STATIC_DIR.resolve())):
            self.send_error(403)
            return

        if file_path.is_file():
            ext = file_path.suffix.lower()
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            # SPA fallback
            index = STATIC_DIR / "index.html"
            if index.is_file():
                data = index.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/generate":
                self._handle_generate()
            elif path == "/api/download":
                self._handle_download()
            elif path == "/api/export":
                self._handle_export()
            elif path == "/api/import":
                self._handle_import()
            elif path == "/api/import-upload":
                self._handle_import_upload()
            elif path == "/api/shutdown":
                self._send_json({"status": "shutting down"})
                threading.Thread(target=self.server.shutdown).start()
            else:
                self._send_error("Not found", 404)
        except Exception as e:
            self._send_error(str(e), 500)

    def _handle_generate(self):
        body = json.loads(self._read_body())
        model = dict_to_model(body)
        files = generate_all(model)
        self._send_json({"files": files})

    def _handle_download(self):
        body = json.loads(self._read_body())
        model = dict_to_model(body)
        files = generate_all(model)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for filepath, content in files.items():
                if filepath.endswith(".json"):
                    zf.writestr(filepath, encode_json(content))
                else:
                    zf.writestr(filepath, encode_bom(content))

        zip_data = buf.getvalue()
        prefix = model.file_prefix or model.mod_id or "cmm_mod"
        filename = f"{prefix}_cmm_integration.zip"

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(zip_data)))
        self.end_headers()
        self.wfile.write(zip_data)

    def _handle_export(self):
        body = json.loads(self._read_body())
        output_dir = body.get("output_dir", "")
        model_data = body.get("model", body)
        if "output_dir" in body:
            model_data = body.get("model", {})

        if not output_dir:
            self._send_error("output_dir is required")
            return

        model = dict_to_model(model_data)
        files = generate_all(model)
        output_path = Path(output_dir)
        files = merge_with_existing(files, output_path)

        written = []
        for filepath, content in files.items():
            full_path = output_path / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if filepath.endswith(".json"):
                full_path.write_bytes(encode_json(content))
            else:
                full_path.write_bytes(encode_bom(content))
            written.append(str(full_path))

        self._send_json({"written": written})

    def _handle_import(self):
        body = json.loads(self._read_body())
        directory = body.get("directory", "")
        if not directory:
            self._send_error("directory is required")
            return

        dir_path = Path(directory)
        if not dir_path.is_dir():
            self._send_error(f"Directory not found: {directory}")
            return

        model, warnings = parse_mod_directory(dir_path)
        result = model_to_dict(model)
        result["_warnings"] = warnings
        self._send_json(result)

    def _handle_browse(self):
        result = [None]

        def pick():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                path = filedialog.askdirectory(title="Select Mod Directory")
                root.destroy()
                result[0] = path or ""
            except Exception:
                result[0] = ""

        # tkinter must run; use a thread to avoid blocking if already on main
        t = threading.Thread(target=pick)
        t.start()
        t.join(timeout=120)
        self._send_json({"directory": result[0]})

    def _handle_import_upload(self):
        body = json.loads(self._read_body())
        model, warnings = parse_uploaded_files(body)
        result = model_to_dict(model)
        result["_warnings"] = warnings
        self._send_json(result)


def run_server(host: str, port: int, auto_open_dir: str = None):
    server = HTTPServer((host, port), RequestHandler)
    server.auto_open_dir = auto_open_dir
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()

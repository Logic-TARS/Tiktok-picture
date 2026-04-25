from __future__ import annotations

import cgi
import json
import mimetypes
import shutil
import importlib.util
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from app import database
from app.config import ROOT_DIR, load_config, public_config, save_config
from app.deepseek_client import generate_caption
from app.logger import get_logger, setup_logging
from app.media.scanner import scan_paths
from app.media.uploads import save_uploaded_files
from app.media.video_mixer import ffmpeg_available
from app.services.jobs import create_gallery_jobs, publish_job_async


STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = get_logger("app.main")


class AppHandler(BaseHTTPRequestHandler):
    server_version = "TiktokPictureLocal/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/":
                self.send_static("index.html")
            elif path.startswith("/static/"):
                self.send_static(path.removeprefix("/static/"))
            elif path == "/api/health":
                self.send_json(
                    {
                        "ok": True,
                        "ffmpeg": ffmpeg_available(),
                        "playwright": module_available("playwright"),
                        "deepseek_configured": bool(load_config().get("deepseek_api_key")),
                    }
                )
            elif path == "/api/config":
                self.send_json(public_config())
            elif path == "/api/jobs":
                self.send_json({"jobs": database.list_jobs()})
            elif path == "/api/records":
                self.send_json({"records": database.list_records()})
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            LOGGER.exception("GET %s failed", path)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/config":
                payload = self.read_json()
                config = save_config(payload)
                self.send_json(public_config(config))
            elif path == "/api/materials/upload":
                form = self.read_multipart()
                group_size = int(form.getfirst("group_size", "4") or "4")
                source_label = (form.getfirst("source_label", "") or "").strip()
                uploaded_files: list[tuple[str, bytes]] = []
                field_items = form["files"] if "files" in form else []
                if not isinstance(field_items, list):
                    field_items = [field_items]
                for item in field_items:
                    if getattr(item, "filename", None):
                        uploaded_files.append((item.filename, item.file.read()))
                if not uploaded_files:
                    raise RuntimeError("No files were selected.")

                upload_result = save_uploaded_files(uploaded_files)
                scan_result = scan_paths([str(upload_result["upload_dir"])], group_size=group_size)
                scan_result.update(upload_result)
                scan_result["source_label"] = source_label
                self.send_json(scan_result, status=HTTPStatus.CREATED)
            elif path == "/api/materials/scan":
                payload = self.read_json()
                config = load_config()
                group_size = int(payload.get("group_size") or config.get("group_size") or 4)
                result = scan_paths(payload.get("paths") or [], group_size=group_size)
                self.send_json(result)
            elif path == "/api/captions/generate":
                payload = self.read_json()
                caption = generate_caption(load_config(), payload)
                self.send_json(caption)
            elif path == "/api/jobs":
                payload = self.read_json()
                result = create_gallery_jobs(payload)
                self.send_json(result, status=HTTPStatus.CREATED)
            elif path.startswith("/api/jobs/") and path.endswith("/publish"):
                job_id = path.split("/")[3]
                job = publish_job_async(job_id)
                self.send_json({"job": job, "message": "publish_started"})
            elif path.startswith("/api/jobs/"):
                payload = self.read_json()
                job_id = path.split("/")[3]
                fields = {
                    key: payload[key]
                    for key in ["title", "body", "hashtags", "cover_path", "status"]
                    if key in payload
                }
                job = database.update_job(job_id, **fields)
                self.send_json({"job": job})
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            LOGGER.exception("POST %s failed", path)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def read_multipart(self) -> cgi.FieldStorage:
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
        }
        return cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ=environ,
            keep_blank_values=True,
        )

    def send_static(self, relative_path: str) -> None:
        target = (STATIC_DIR / relative_path).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Static file not found")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status=status)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)


def module_available(name: str) -> bool:
    return shutil.which("python") is not None and importlib.util.find_spec(name) is not None


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    setup_logging()
    database.init_db()
    LOGGER.info("Workspace: %s", ROOT_DIR)
    LOGGER.info("Open: http://%s:%s", host, port)
    server = ThreadingHTTPServer((host, port), AppHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()

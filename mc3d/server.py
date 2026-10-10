"""HTTP job server that the Minecraft plugin talks to.

    POST /jobs                {"prompt": "...", "size": 48, ...}  -> {"id": "..."}
    GET  /jobs/<id>           job status (queued / running / done / error)
    GET  /jobs/<id>/schem     the generated .schem
    GET  /jobs/<id>/preview   preview PNG
    GET  /health

Jobs run one at a time on a single worker thread (one GPU).
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .ai.text_to_image import build_prompt
from .blocks import DATA_VERSIONS, DEFAULT_MC_VERSION, PALETTE_GROUPS
from .pipeline import ConvertOptions, model_to_schem

MAX_SIZE = 256


@dataclass
class Job:
    id: str
    name: str
    params: dict
    status: str = "queued"  # queued | running | done | error
    stage: str = ""
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    shape: list[int] | None = None
    block_count: int | None = None
    top_blocks: dict[str, int] | None = None
    schem_path: str | None = None
    preview_path: str | None = None

    def public(self, position: int | None) -> dict:
        data = asdict(self)
        for key in ("params", "schem_path", "preview_path"):
            data.pop(key)
        data["queue_position"] = position
        if self.started:
            data["elapsed"] = round((self.finished or time.time()) - self.started, 1)
        return data


def _clean_name(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_-]+", "_", name).strip("_").lower()
    return name[:40] or "build"


class Generator:
    """Runs jobs on the configured backend ("local" GPU or free "cloud" APIs)."""

    def __init__(self, backend: str, out_dir: str, hf_token: str | None = None,
                 quality: bool = False, steps: int = 12):
        self.backend = backend
        self.out_dir = out_dir
        self.hf_token = hf_token
        self.quality = quality
        self.steps = steps
        os.makedirs(out_dir, exist_ok=True)

    def run(self, job: Job, set_stage) -> None:
        p = job.params
        stem = os.path.join(self.out_dir, f"{job.name}_{job.id}")
        seed = int(p.get("seed", 0))
        quality = bool(p.get("quality", self.quality))

        image_path = stem + "_image.png"
        if p.get("image_base64"):
            with open(image_path, "wb") as f:
                f.write(base64.b64decode(p["image_base64"]))
        else:
            set_stage("text→image")
            prompt = build_prompt(p["prompt"], bool(p.get("raw_prompt")))
            if self.backend == "local":
                from .local.models import text_to_image
                try:
                    text_to_image(prompt, image_path, seed=seed)
                except ImportError:  # diffusers missing -> free API
                    from .ai.text_to_image import generate_image
                    generate_image(p["prompt"], image_path, seed=seed,
                                   raw_prompt=bool(p.get("raw_prompt")), log=lambda *_: None)
            else:
                from .ai.text_to_image import generate_image
                generate_image(p["prompt"], image_path, seed=seed, hf_token=self.hf_token,
                               raw_prompt=bool(p.get("raw_prompt")), log=lambda *_: None)

        set_stage("image→3D")
        if self.backend == "local":
            from .local.models import image_to_3d
            model_path, up = image_to_3d(image_path, stem + "_model", seed=seed,
                                         steps=self.steps, quality=quality)
        else:
            from .ai.image_to_3d import generate_model
            model_path = generate_model(image_path, stem + "_model", seed=seed,
                                        hf_token=self.hf_token, log=lambda *_: None)
            up = "y"

        set_stage("voxelize→schem")
        opts = ConvertOptions(
            size=int(p.get("size", 48)),
            fit=p.get("fit", "max"),
            fill=bool(p.get("fill", False)),
            up_axis=up,
            palette_groups=p.get("palette") or None,
            exclude=p.get("exclude") or [],
            mc_version=p.get("mc_version", DEFAULT_MC_VERSION),
            seed=seed,
        )
        result = model_to_schem(model_path, stem + ".schem", opts, log=lambda *_: None)
        job.shape = list(result.shape)
        job.block_count = result.block_count
        job.top_blocks = dict(list(result.block_usage.items())[:8])
        job.schem_path = result.schem_path
        job.preview_path = result.preview_path


def validate(params: dict) -> dict:
    if not isinstance(params, dict):
        raise ValueError("body must be a JSON object")
    if not params.get("prompt") and not params.get("image_base64"):
        raise ValueError("prompt or image_base64 is required")
    size = int(params.get("size", 48))
    if not 4 <= size <= MAX_SIZE:
        raise ValueError(f"size must be between 4 and {MAX_SIZE}")
    params["size"] = size
    if params.get("mc_version", DEFAULT_MC_VERSION) not in DATA_VERSIONS:
        raise ValueError(f"mc_version must be one of {', '.join(DATA_VERSIONS)}")
    palette = params.get("palette")
    if isinstance(palette, str):
        palette = [g.strip() for g in palette.split(",") if g.strip()]
    if palette and set(palette) - set(PALETTE_GROUPS):
        raise ValueError(f"palette groups must be from {', '.join(PALETTE_GROUPS)}")
    params["palette"] = palette
    if params.get("fit", "max") not in ("max", "height"):
        raise ValueError("fit must be max or height")
    return params


class JobManager:
    def __init__(self, generator: Generator, max_queue: int = 10, keep: int = 100):
        self.generator = generator
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.queue: queue.Queue[str] = queue.Queue()
        self.max_queue = max_queue
        self.keep = keep
        self.lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, params: dict) -> Job:
        params = validate(params)
        with self.lock:
            pending = sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))
            if pending >= self.max_queue:
                raise OverflowError("queue is full, try again later")
            name = _clean_name(params.get("name") or params.get("prompt") or "image")
            job = Job(id=uuid.uuid4().hex[:8], name=name, params=params)
            self.jobs[job.id] = job
            self.order.append(job.id)
            while len(self.order) > self.keep:
                self.jobs.pop(self.order.pop(0), None)
        self.queue.put(job.id)
        return job

    def position(self, job: Job) -> int | None:
        if job.status != "queued":
            return None
        with self.lock:
            queued = [j for j in self.order if self.jobs[j].status == "queued"]
        return queued.index(job.id) + 1 if job.id in queued else None

    def _worker(self) -> None:
        while True:
            job_id = self.queue.get()
            job = self.jobs.get(job_id)
            if job is None:
                continue
            job.status, job.started = "running", time.time()
            try:
                self.generator.run(job, lambda s: setattr(job, "stage", s))
                job.status = "done"
            except Exception as e:
                traceback.print_exc()
                job.status, job.error = "error", f"{type(e).__name__}: {e}"
            job.finished = time.time()
            job.stage = ""
            print(f"[job {job.id}] {job.status} in {job.finished - job.started:.1f}s"
                  + (f": {job.error}" if job.error else ""), flush=True)


def make_handler(manager: JobManager, api_key: str | None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter logs
            pass

        def _json(self, code: int, data) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: str | None, ctype: str) -> None:
            if not path or not os.path.exists(path):
                return self._json(404, {"error": "file not available"})
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if api_key and self.headers.get("X-API-Key") != api_key:
                self._json(401, {"error": "invalid api key"})
                return False
            return True

        def do_GET(self):
            if not self._authorized():
                return
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts == ["health"]:
                return self._json(200, {"ok": True, "backend": manager.generator.backend})
            if len(parts) >= 2 and parts[0] == "jobs":
                job = manager.jobs.get(parts[1])
                if job is None:
                    return self._json(404, {"error": "job not found"})
                if len(parts) == 2:
                    return self._json(200, job.public(manager.position(job)))
                if parts[2:] == ["schem"]:
                    return self._file(job.schem_path, "application/octet-stream")
                if parts[2:] == ["preview"]:
                    return self._file(job.preview_path, "image/png")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return
            if self.path.split("?")[0].rstrip("/") != "/jobs":
                return self._json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                params = json.loads(self.rfile.read(length) or b"{}")
                job = manager.submit(params)
            except OverflowError as e:
                return self._json(429, {"error": str(e)})
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            self._json(202, job.public(manager.position(job)))

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, backend: str = "local",
          out_dir: str = "output/server", hf_token: str | None = None,
          api_key: str | None = None, quality: bool = False, steps: int = 12,
          warmup: bool = True) -> None:
    if backend == "local" and warmup:
        print("[serve] loading models onto the GPU ...", flush=True)
        from .local.models import warmup as do_warmup
        try:
            do_warmup()
        except ImportError as e:
            print(f"[serve] text-to-image model not loaded ({e}); will use the free API",
                  flush=True)
            do_warmup(text=False)
    manager = JobManager(Generator(backend, out_dir, hf_token, quality, steps))
    httpd = ThreadingHTTPServer((host, port), make_handler(manager, api_key))
    print(f"[serve] backend={backend} listening on http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

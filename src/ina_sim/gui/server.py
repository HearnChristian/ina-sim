"""Stdlib HTTP server for the INA-sim GUI — offline-first, no external deps.

Usage:
    ina-sim gui
    ina-sim gui --port 8765 --no-browser
"""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ina_sim import __version__
from ina_sim.library.loader import filter_candidates, load_candidates
from ina_sim.library.molecular import parse_upload
from ina_sim.library.registry import (
    candidate_to_dict,
    clear_session,
    list_session,
    load_persisted,
    register,
    unregister,
)
from ina_sim.models.conditions import Conditions, conditions_clamp_report
from ina_sim.physics.atmosphere import atmosphere_state
from ina_sim.physics.claims import extract_claims
from ina_sim.physics.evidence import evidence_summary
from ina_sim.physics.ns import registry_summary
from ina_sim.physics.research_xref import cross_reference_screen
from ina_sim.physics.validate import (
    clamp,
    is_finite_number,
)
from ina_sim.provenance import DEFAULT_ASSUMPTIONS, build_provenance
from ina_sim.schema import assert_screen_payload
from ina_sim.screen.rank import rank_candidates, temperature_sweep
from ina_sim.validation.runner import run_validation

STATIC_DIR = Path(__file__).resolve().parent / "static"
_PERSIST_LOADED = False
_PERSIST_LOCK = threading.Lock()


def _ensure_persisted_loaded() -> None:
    global _PERSIST_LOADED
    with _PERSIST_LOCK:
        if not _PERSIST_LOADED:
            try:
                load_persisted()
            except OSError:
                pass
            _PERSIST_LOADED = True


def _parse_float(qs: dict[str, list[str]], key: str, default: float) -> float:
    vals = qs.get(key)
    if not vals or vals[0] == "":
        return default
    try:
        v = float(vals[0])
    except ValueError as e:
        raise ValueError(f"invalid float for {key}: {vals[0]!r}") from e
    if not is_finite_number(v):
        raise ValueError(f"{key} must be finite")
    return v


def _parse_bool(qs: dict[str, list[str]], key: str, default: bool = True) -> bool:
    vals = qs.get(key)
    if not vals:
        return default
    return vals[0].lower() not in ("0", "false", "no", "off")


def _parse_ids(qs: dict[str, list[str]]) -> list[str] | None:
    ids_raw = qs.get("ids", [None])[0]
    if not ids_raw:
        return None
    return [x.strip() for x in ids_raw.split(",") if x.strip()]


def _conditions_from_qs(qs: dict[str, list[str]], *, clamp_inputs: bool = True) -> Conditions:
    mode = qs.get("mode", ["immersion"])[0].lower().strip()
    if mode not in {"immersion", "deposition", "contact"}:
        raise ValueError("mode must be immersion|deposition|contact")
    track = qs.get("track", ["ice"])[0].lower().strip()
    if track not in {"ice", "warm_cloud"}:
        raise ValueError("track must be ice|warm_cloud")
    c = Conditions(
        temperature_c=_parse_float(qs, "temp", -10.0),
        relative_humidity_pct=_parse_float(qs, "rh", 95.0),
        pressure_hpa=_parse_float(qs, "pressure", 850.0),
        cloud_volume_m3=_parse_float(qs, "volume", 1e6),
        seeding_density_per_l=_parse_float(qs, "density", 100.0),
        mode=mode,
        particle_diameter_um=_parse_float(qs, "diameter", 1.0),
        track=track,
    )
    return c.clamped() if clamp_inputs else c


def _select_candidates(
    starter_set: bool,
    ids: list[str] | None,
    *,
    include_uploads: bool = True,
) -> list:
    _ensure_persisted_loaded()
    tags = ["starter-set"] if starter_set and not ids else None
    cands = filter_candidates(
        ids=ids, tags=tags, include_uploads=include_uploads and not starter_set
    )
    if not cands:
        cands = list(load_candidates(include_uploads=include_uploads))
    # When not starter-set, merge uploads explicitly if filter dropped them
    if include_uploads and not starter_set and not ids:
        have = {c.id for c in cands}
        for u in list_session():
            if u.id not in have:
                cands.append(u)
    return cands


def run_screen_payload(
    *,
    temperature_c: float = -10.0,
    relative_humidity_pct: float = 95.0,
    pressure_hpa: float = 850.0,
    cloud_volume_m3: float = 1e6,
    seeding_density_per_l: float = 100.0,
    mode: str = "immersion",
    track: str = "ice",
    particle_diameter_um: float = 1.0,
    starter_set: bool = True,
    sort_key: str = "relative_ina",
    ids: list[str] | None = None,
    include_uploads: bool = True,
    validate_schema: bool = True,
) -> dict[str, Any]:
    allowed_sort = {"relative_ina", "efficiency", "condensable", "ina_per_kg", "cnt_score"}
    if sort_key not in allowed_sort:
        raise ValueError(f"sort must be one of {sorted(allowed_sort)}")
    if mode not in {"immersion", "deposition", "contact"}:
        raise ValueError("mode must be immersion|deposition|contact")
    if track not in {"ice", "warm_cloud"}:
        raise ValueError("track must be ice|warm_cloud")

    cands = _select_candidates(
        starter_set, ids, include_uploads=include_uploads
    )
    requested = Conditions(
        temperature_c=temperature_c,
        relative_humidity_pct=relative_humidity_pct,
        pressure_hpa=pressure_hpa,
        cloud_volume_m3=cloud_volume_m3,
        seeding_density_per_l=seeding_density_per_l,
        mode=mode,
        particle_diameter_um=particle_diameter_um,
        track=track,
    )
    conditions = requested.clamped()
    conditions.validate()
    clamp_info = conditions_clamp_report(requested, conditions)

    ranked = rank_candidates(cands, conditions, sort_key=sort_key)
    rows = [r.as_row() for r in ranked]
    warns = sorted({w for r in ranked for w in r.warnings})
    atm = atmosphere_state(
        conditions.temperature_c,
        conditions.relative_humidity_pct,
        conditions.pressure_hpa,
        conditions.cloud_volume_m3,
    )
    ranked_ids = [r.candidate.id for r in ranked]
    agent_classes = {r.candidate.id: r.candidate.agent_class.value for r in ranked}
    lit = cross_reference_screen(
        ranked_ids=ranked_ids,
        temperature_c=conditions.temperature_c,
        relative_humidity_pct=conditions.relative_humidity_pct,
        pressure_hpa=conditions.pressure_hpa,
        mode=conditions.mode,
        agent_classes=agent_classes,
    )
    scores = {r.candidate.id: r.relative_ina_score for r in ranked}
    lit_fails = [
        c["id"] for c in lit.get("checks", []) if c.get("status") == "fail"
    ]
    claims = extract_claims(
        ranked_ids=ranked_ids,
        scores=scores,
        temperature_c=conditions.temperature_c,
        mode=conditions.mode,
        track=conditions.track,
        literature_ok=bool(lit.get("summary", {}).get("ok")),
        literature_fails=lit_fails,
    )
    # Empirical layer: which of these rankings is backed by a measurement, and
    # does this build still reproduce the literature it cites? Additive block -
    # existing consumers of the payload are unaffected.
    evidence_blocks = [
        r.details.get("evidence") or {"evidence": "none"} for r in ranked
    ]
    empirical = {
        "summary": evidence_summary(evidence_blocks),
        "registry": {
            k: v for k, v in registry_summary().items() if k != "parameterizations"
        },
    }
    try:
        validation = run_validation()
        empirical["validation"] = validation.as_dict()["summary"]
    except Exception as exc:  # never let a self-check break a screen
        empirical["validation"] = {"ok": None, "error": str(exc)}

    starter_flag = bool(starter_set and not ids)
    prov = build_provenance(
        conditions,
        sort_key=sort_key,
        starter_set=starter_flag,
        n_agents=len(ranked),
    )
    mechanism = (
        "Ranking liquid-drop seeds (CCN) — ice nucleants demoted. "
        "CCN = cloud condensation nuclei (grow water drops)."
        if conditions.track == "warm_cloud"
        else "Ranking ice nucleants (INA) — salts demoted. "
        "INA = ice-nucleating agent (helps form ice crystals). "
        "Score scale: 0–1 with AgI peak = 1."
    )

    payload = {
        "version": __version__,
        "fidelity": "L0+L1-table+CNT",
        "baseline": "agi",
        "score_scale": {
            "min": 0.0,
            "max": 1.0,
            "meaning": "relative effectiveness vs AgI peak (peak_strength × a(T) × mode × load)",
            "agi_peak_strength": 1.0,
        },
        "offline": True,
        "fingerprint": prov["fingerprint"],
        "provenance": prov,
        "assumptions": prov["assumptions"],
        "mechanism_banner": mechanism,
        "disclaimer": DEFAULT_ASSUMPTIONS["disclaimer"],
        "conditions": conditions.as_dict(),
        "conditions_requested": clamp_info["requested"],
        "conditions_used": clamp_info["used"],
        "clamped": clamp_info["clamped"],
        "clamp_fields": clamp_info["fields"],
        "atmosphere": atm.as_dict(),
        "filter": {
            "starter_set": starter_flag,
            "ids": ids,
            "sort": sort_key,
            "include_uploads": include_uploads,
            "n_uploads": len(list_session()),
            "track": conditions.track,
        },
        "results": rows,
        "warnings": warns,
        "literature_xref": lit,
        "empirical_claims": claims,
        "empirical_layer": empirical,
    }
    if validate_schema:
        assert_screen_payload(payload)
    return payload


class InaSimHandler(BaseHTTPRequestHandler):
    server_version = f"INA-sim-GUI/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            print(f"[gui] {self.address_string()} {args[0]}", file=sys.stderr)
        except Exception:
            pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_json(self, code: int, payload: Any) -> None:
        try:
            body = json.dumps(payload, indent=2, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as e:
            body = json.dumps({"error": f"json encode failed: {e}"}).encode("utf-8")
            code = 500
        self._send(code, body, "application/json; charset=utf-8")

    def _read_body(self, max_bytes: int = 5_000_000) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > max_bytes:
            raise ValueError(f"Content-Length out of range (max {max_bytes})")
        if length == 0:
            return b""
        return self.rfile.read(length)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch_get()
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"error": f"internal error: {e}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._dispatch_post()
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"error": f"internal error: {e}"})

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            self._dispatch_delete()
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"error": f"internal error: {e}"})

    def _dispatch_get(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return
        if path in ("/reference", "/reference/", "/figures"):
            self._serve_reference_figures()
            return
        if path == "/api/health":
            _ensure_persisted_loaded()
            self._send_json(
                200,
                {
                    "ok": True,
                    "version": __version__,
                    "name": "ina-sim",
                    "fidelity": "L0+L1-heuristic+CNT",
                    "offline": True,
                    "n_uploads": len(list_session()),
                },
            )
            return
        if path == "/api/candidates":
            _ensure_persisted_loaded()
            include = _parse_bool(qs, "include_uploads", True)
            rows = [
                {
                    "id": c.id,
                    "name": c.name,
                    "class": c.agent_class.value,
                    "tags": list(c.tags),
                    "optimal_temp_c": c.optimal_temp_c,
                    "lattice_match_score": c.lattice_match_score,
                    "source": c.source,
                }
                for c in load_candidates(include_uploads=include)
            ]
            self._send_json(200, {"candidates": rows})
            return
        if path == "/api/uploads":
            _ensure_persisted_loaded()
            rows = [candidate_to_dict(c) for c in list_session()]
            self._send_json(200, {"uploads": rows, "count": len(rows)})
            return
        if path == "/api/atmosphere":
            try:
                c = _conditions_from_qs(qs)
                c.validate()
                atm = atmosphere_state(
                    c.temperature_c,
                    c.relative_humidity_pct,
                    c.pressure_hpa,
                    c.cloud_volume_m3,
                )
                self._send_json(200, atm.as_dict())
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
            return
        if path == "/api/screen":
            try:
                c = _conditions_from_qs(qs)
                payload = run_screen_payload(
                    temperature_c=c.temperature_c,
                    relative_humidity_pct=c.relative_humidity_pct,
                    pressure_hpa=c.pressure_hpa,
                    cloud_volume_m3=c.cloud_volume_m3,
                    seeding_density_per_l=c.seeding_density_per_l,
                    mode=c.mode,
                    track=c.track,
                    particle_diameter_um=c.particle_diameter_um,
                    starter_set=_parse_bool(qs, "starter_set", True),
                    sort_key=qs.get("sort", ["relative_ina"])[0],
                    ids=_parse_ids(qs),
                    include_uploads=_parse_bool(qs, "include_uploads", True),
                )
                self._send_json(200, payload)
            except (ValueError, KeyError, TypeError) as e:
                self._send_json(400, {"error": str(e)})
            return
        if path == "/api/tsweep":
            try:
                starter = _parse_bool(qs, "starter_set", True)
                ids = _parse_ids(qs)
                cands = _select_candidates(
                    starter,
                    ids,
                    include_uploads=_parse_bool(qs, "include_uploads", True),
                )
                c = _conditions_from_qs(qs)
                from ina_sim.physics.validate import clamp_temperature_c

                t_min = clamp_temperature_c(_parse_float(qs, "t_min", -30.0))
                t_max = clamp_temperature_c(_parse_float(qs, "t_max", 0.0))
                step = clamp(_parse_float(qs, "step", 2.0), 0.25, 20.0)
                sweep = temperature_sweep(
                    cands,
                    t_min=t_min,
                    t_max=t_max,
                    step=step,
                    relative_humidity_pct=c.relative_humidity_pct,
                    pressure_hpa=c.pressure_hpa,
                    mode=c.mode,
                    track=c.track,
                    seeding_density_per_l=c.seeding_density_per_l,
                    particle_diameter_um=c.particle_diameter_um,
                    cloud_volume_m3=c.cloud_volume_m3,
                )
                self._send_json(
                    200,
                    {
                        "version": __version__,
                        "baseline": "agi",
                        "points": sweep,
                        "n_temps": len(sweep),
                        "n_agents": len(cands),
                    },
                )
            except (ValueError, KeyError, TypeError) as e:
                self._send_json(400, {"error": str(e)})
            return

        if path.startswith("/static/"):
            name = path[len("/static/") :]
            if ".." in name or name.startswith("/"):
                self._send_json(400, {"error": "bad path"})
                return
            self._serve_static(name)
            return

        self._send_json(404, {"error": "not found", "path": path})

    def _serve_reference_figures(self) -> None:
        """Static reference figures, rebuilt from the registry on each request
        so the page can never disagree with the numbers the tool is using."""
        from ina_sim.figures import build_figures, render_page

        body = render_page(build_figures()).encode("utf-8")
        self._send(200, body, "text/html; charset=utf-8")

    def _dispatch_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/api/upload", "/api/upload/molecule"):
            self._handle_upload(qs)
            return
        if path == "/api/uploads/clear":
            n = clear_session(delete_files=_parse_bool(qs, "delete_files", False))
            self._send_json(200, {"cleared": n})
            return

        self._send_json(404, {"error": "not found", "path": path})

    def _dispatch_delete(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        # /api/uploads/<id>
        prefix = "/api/uploads/"
        if path.startswith(prefix):
            cid = urllib.parse.unquote(path[len(prefix) :]).strip()
            if not cid or "/" in cid or ".." in cid:
                self._send_json(400, {"error": "bad id"})
                return
            ok = unregister(cid)
            self._send_json(200 if ok else 404, {"deleted": ok, "id": cid})
            return
        self._send_json(404, {"error": "not found", "path": path})

    def _handle_upload(self, qs: dict[str, list[str]]) -> None:
        _ensure_persisted_loaded()
        ctype = (self.headers.get("Content-Type") or "").lower()
        body = self._read_body()

        name = qs.get("name", [None])[0]
        fmt = qs.get("format", [None])[0]
        filename = qs.get("filename", [None])[0]
        notes = qs.get("notes", [""])[0] or ""
        candidate_id = qs.get("id", [None])[0]
        content: str | None = None

        if "application/json" in ctype or (
            body[:1] in (b"{", b"[") and "multipart" not in ctype
        ):
            try:
                data = json.loads(body.decode("utf-8") if body else "{}")
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                self._send_json(400, {"error": f"invalid JSON body: {e}"})
                return
            if not isinstance(data, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return
            # Prefer explicit content/smiles/text fields; else whole object as candidate JSON
            content = data.get("content") or data.get("text") or data.get("smiles")
            if content is None and ("id" in data or "atoms" in data or "smiles" in data):
                content = json.dumps(data)
            name = data.get("name") or name
            fmt = data.get("format") or fmt
            filename = data.get("filename") or filename
            notes = data.get("notes") or notes
            candidate_id = data.get("id") if candidate_id is None else candidate_id
            if content is None:
                self._send_json(
                    400,
                    {
                        "error": "JSON needs content/text/smiles or a full candidate object",
                    },
                )
                return
            content = str(content)
        elif "multipart/form-data" in ctype:
            try:
                content, filename, name, fmt, notes = _parse_multipart(
                    body, ctype, filename, name, fmt, notes
                )
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
        else:
            # raw text body
            try:
                content = body.decode("utf-8")
            except UnicodeDecodeError:
                self._send_json(400, {"error": "body must be UTF-8 text"})
                return

        try:
            rec, cand = parse_upload(
                content,
                filename=filename,
                format=fmt,
                name=name,
                candidate_id=candidate_id,
                notes=notes,
            )
            register(cand, persist=True)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            self._send_json(400, {"error": str(e)})
            return

        self._send_json(
            201,
            {
                "ok": True,
                "candidate": candidate_to_dict(cand),
                "molecule": rec.as_dict(),
                "message": (
                    "Registered as exploratory upload for screening / molecular builder feed. "
                    "Uncheck Starter set to include in ranks."
                ),
            },
        )

    def _serve_static(self, name: str) -> None:
        if name == "index.html":
            target = STATIC_DIR / "index.html"
        else:
            target = (STATIC_DIR / name).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self._send_json(400, {"error": "bad path"})
                return
        if not target.is_file():
            self._send_json(404, {"error": f"missing {name}"})
            return
        data = target.read_bytes()
        ctype, _ = mimetypes.guess_type(str(target))
        if name.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif name.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif name.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        self._send(200, data, ctype or "application/octet-stream")


def _parse_multipart(
    body: bytes,
    content_type: str,
    filename: str | None,
    name: str | None,
    fmt: str | None,
    notes: str,
) -> tuple[str, str | None, str | None, str | None, str]:
    """Minimal multipart/form-data parser for file + fields (offline, no deps)."""
    if "boundary=" not in content_type:
        raise ValueError("multipart missing boundary")
    boundary = content_type.split("boundary=", 1)[1].strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    sep = b"--" + boundary.encode("ascii", errors="ignore")
    parts = body.split(sep)
    content = None
    for part in parts:
        if not part or part in (b"--", b"--\r\n", b"\r\n"):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        disp = ""
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disp = line
        # field name
        m_name = None
        m_file = None
        for piece in disp.split(";"):
            piece = piece.strip()
            if piece.startswith("name="):
                m_name = piece.split("=", 1)[1].strip().strip('"')
            if piece.startswith("filename="):
                m_file = piece.split("=", 1)[1].strip().strip('"')
        text = data.decode("utf-8", errors="replace")
        if text.endswith("\r\n"):
            text = text[:-2]
        if m_file is not None or m_name in ("file", "content", "molecule"):
            content = text
            if m_file:
                filename = m_file
        elif m_name == "name":
            name = text.strip() or name
        elif m_name == "format":
            fmt = text.strip() or fmt
        elif m_name == "notes":
            notes = text
        elif m_name == "smiles" and content is None:
            content = text.strip()
            fmt = fmt or "smiles"
    if content is None:
        raise ValueError("multipart: no file/content field found")
    return content, filename, name, fmt, notes


class _ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):  # noqa: ANN001
        # Don't dump full trace for client disconnects
        err = sys.exc_info()[1]
        if isinstance(err, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def run_gui(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    open_browser: bool = True,
) -> None:
    """Start the GUI server (blocking). Offline-local only."""
    if not (STATIC_DIR / "index.html").is_file():
        raise FileNotFoundError(f"GUI assets missing under {STATIC_DIR}")

    _ensure_persisted_loaded()
    httpd = _ReusableThreadingServer((host, port), InaSimHandler)
    url = f"http://{host}:{port}/"
    print(f"INA-sim GUI v{__version__} (offline)")
    print(f"  Open: {url}")
    print(f"  Uploads in session: {len(list_session())}")
    print("  Ctrl+C to stop")
    print("  Learning lab — not operational weather control.")

    if open_browser:

        def _open() -> None:
            time.sleep(0.35)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass

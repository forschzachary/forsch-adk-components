"""mimo_stream_runner — reusable streaming subprocess for the MiMo CLI.

Streams the mimo CLI's JSON event output and surfaces terminal events
(error / step_finish) without hanging on provider errors.

Implementation: a worker thread reads stdout (and stderr) into a queue.
The main thread polls the queue. On an error event, the worker thread
terminates and we kill the subprocess. On step_finish, the worker
drains any remaining output and we return.

Why a thread: readline() in non-blocking mode returns '' (EOF) on a
pipe with no data, which looks identical to actual EOF. Several
attempts at polling-with-os.read() failed to actually receive the error
event. Thread + queue is the simplest reliable approach.

Pure stdlib. No external deps. Reusable from any project that calls
the MiMo CLI.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional


def run(
    cmd: list[str],
    *,
    cwd: Optional[Path | str] = None,
    timeout: float = 120.0,
) -> dict:
    """Run a mimo-style streaming JSON subprocess and return terminal state."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"{cmd[0] if cmd else 'mimo'} not installed", "response": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "response": ""}

    q: "queue.Queue[str]" = queue.Queue()
    response_text = ""
    error_text = ""
    output_tail: list[str] = []
    session_id = ""
    finished_cleanly = False

    def _reader():
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                q.put(line)
        except Exception as e:
            q.put(f"__READER_ERROR__:{e}")
        finally:
            q.put("__EOF__")

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    def _process(line: str) -> None:
        nonlocal response_text, error_text, session_id, finished_cleanly, error_event_seen
        s = line.strip()
        if s:
            output_tail.append(s[:500])
            del output_tail[:-12]
        if not s or not s.startswith("{"):
            if not error_text and ("Model not found:" in s or "API key" in s or "Unauthorized" in s):
                error_text = s[:500]
                error_event_seen = True
            return
        try:
            evt = json.loads(s)
        except json.JSONDecodeError:
            return
        etype = evt.get("type")
        if etype == "text" and evt.get("part", {}).get("text"):
            response_text += evt["part"]["text"]
        elif etype == "error":
            error = evt.get("error") or {}
            data = error.get("data") if isinstance(error, dict) else {}
            if isinstance(data, dict):
                error_text = (
                    data.get("message")
                    or data.get("responseBody")
                    or data.get("error")
                    or ""
                )
            if not error_text and isinstance(error, dict):
                error_text = error.get("name") or "MiMo error"
            error_event_seen = True
        elif etype == "step_finish":
            finished_cleanly = True
        if evt.get("sessionID") and not session_id:
            session_id = evt["sessionID"]

    start = time.time()
    error_event_seen = False
    try:
        while True:
            if time.time() - start > timeout:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "ok": False, "response": response_text,
                    "error": f"timeout after {timeout}s", "session_id": session_id,
                }
            try:
                line = q.get(timeout=0.1)
            except queue.Empty:
                # If process exited and reader thread is done, exit loop.
                if proc.poll() is not None and not t.is_alive():
                    # Drain any remaining lines.
                    while True:
                        try:
                            line = q.get_nowait()
                            if line == "__EOF__":
                                break
                            _process(line)
                        except queue.Empty:
                            break
                    break
                continue

            if line == "__EOF__":
                break
            if line.startswith("__READER_ERROR__:"):
                # Reader crashed; continue to drain.
                continue
            _process(line)

            if error_event_seen:
                try:
                    proc.kill()
                except Exception:
                    pass
                break
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return {"ok": False, "response": response_text, "error": f"stream error: {e}", "session_id": session_id}

    try:
        returncode = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            returncode = proc.wait(timeout=2)
        except Exception:
            returncode = proc.returncode
            pass

    if error_text:
        return {
            "ok": False, "response": response_text, "error": error_text[:500],
            "session_id": session_id, "finished_cleanly": finished_cleanly,
        }
    if returncode not in (0, None):
        diagnostic = "\n".join(output_tail[-4:]).strip()
        return {
            "ok": False,
            "response": response_text,
            "error": (diagnostic or f"mimo exited with code {returncode}")[:500],
            "session_id": session_id,
            "finished_cleanly": finished_cleanly,
        }
    if not response_text and not finished_cleanly:
        diagnostic = "\n".join(output_tail[-4:]).strip()
        return {
            "ok": False,
            "response": "",
            "error": (diagnostic or "mimo produced no response")[:500],
            "session_id": session_id,
            "finished_cleanly": finished_cleanly,
        }
    return {
        "ok": True,
        "response": response_text or "(no response)",
        "session_id": session_id,
        "finished_cleanly": finished_cleanly,
    }

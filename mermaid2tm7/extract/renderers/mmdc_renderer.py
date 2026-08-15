"""mmdc renderer backend — shells out to @mermaid-js/mermaid-cli.

Browser-accurate (headless Chromium), matching what a user sees in a VS Code
Markdown preview. Requires Node and a Chromium download. This is the fidelity
path; ``mermaidx`` is the fast/CI path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ...errors import MermaidSyntaxError, RendererUnavailableError


class MmdcRenderer:
    name = "mmdc"

    def __init__(self, mmdc_path: str | None = None) -> None:
        self._mmdc = mmdc_path or os.environ.get("MMDC_PATH") or "mmdc"

    def _resolve(self) -> str:
        exe = shutil.which(self._mmdc)
        if exe:
            return exe
        # Fall back to npx if a global install is absent but Node is present.
        if shutil.which("npx"):
            return "npx:@mermaid-js/mermaid-cli"
        raise RendererUnavailableError(
            "mmdc (@mermaid-js/mermaid-cli) not found. Install it with "
            "`npm install -g @mermaid-js/mermaid-cli`, which also needs Node and "
            "a Chromium download."
        )

    def available(self) -> bool:
        try:
            self._resolve()
            return True
        except RendererUnavailableError:
            return False

    def _command(self, args: list[str]) -> list[str]:
        exe = self._resolve()
        if exe.startswith("npx:"):
            return ["npx", "-y", exe.split(":", 1)[1], *args]
        return [exe, *args]

    def version(self) -> str:
        try:
            out = subprocess.run(
                self._command(["--version"]),
                capture_output=True,
                text=True,
                timeout=120,
            )
            return out.stdout.strip() or "unknown"
        except Exception:  # pragma: no cover
            return "unknown"

    def mermaid_version(self) -> str:
        # mmdc's --version reports the CLI version; the bundled mermaid version
        # tracks it closely. Recorded verbatim in provenance.
        return self.version()

    def render(self, source: str, config: dict | None = None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "in.mmd"
            out_path = Path(tmp) / "out.svg"
            in_path.write_text(source, encoding="utf-8")
            args = ["-i", str(in_path), "-o", str(out_path)]
            if config:
                cfg_path = Path(tmp) / "config.json"
                cfg_path.write_text(json.dumps(config), encoding="utf-8")
                args += ["-c", str(cfg_path)]
            try:
                proc = subprocess.run(
                    self._command(args),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except FileNotFoundError as exc:
                raise RendererUnavailableError(str(exc)) from exc
            if proc.returncode != 0 or not out_path.exists():
                raise MermaidSyntaxError(
                    f"mmdc failed (exit {proc.returncode}): {proc.stderr.strip()}"
                )
            return out_path.read_text(encoding="utf-8")

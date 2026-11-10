#!/usr/bin/env python3
"""Open/raise the native file window for one Herdr terminal."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--terminal", required=True)
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]+", args.terminal):
    parser.error("Bu sürüm yalnızca yerel Herdr oturumlarını destekliyor.")
app_home = Path(__file__).resolve().parents[2]
bundle = Path.home() / ".local/share/herdr-outputs/Herdr Outputs.app"
if not (bundle / "Contents/MacOS/HerdrOutputs").is_file():
    raise SystemExit("Çıktı penceresi kurulu değil. Önce native/build.py çalıştırılmalı.")
folder = app_home / "data/outputs-browser/requests"
folder.mkdir(parents=True, exist_ok=True)
request = folder / f"{args.terminal}.herdroutputs"
with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as file:
    json.dump(dict(terminal=args.terminal, app_home=str(app_home)), file)
    temporary = Path(file.name)
temporary.replace(request)
subprocess.run(["/usr/bin/open", "-a", str(bundle), str(request)], check=True, timeout=10)

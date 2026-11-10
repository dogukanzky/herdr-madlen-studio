"""Launch the optional outputs browser, or explain how to install it."""
from pathlib import Path
import subprocess
import sys

script=Path(__file__).resolve().parents[1]/'outputs-browser/launch.py'
if not script.is_file():
    raise SystemExit('Çıktılar eklentisi henüz kurulu değil. Tema paketinde python3 install.py --with-outputs çalıştırın (Xcode Command Line Tools gerekir).')
raise SystemExit(subprocess.call([sys.executable,str(script),*sys.argv[1:]]))

#!/usr/bin/env python3
"""Install Herdr Outputs without replacing the person's existing layout."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

NAME = "outputs-browser"
OWNER = "madlen-herdr-outputs"


def find_tabs(node):
    if node.get("id") == "tabs" and node.get("type") == "block" and node.get("content", {}).get("mod"):
        return node
    for child in node.get("children", []):
        result = find_tabs(child)
        if result is not None:
            return result
    return None


def has_launcher(node):
    if node.get("content", {}).get("mod") == NAME and node.get("content", {}).get("props", {}).get("toolbar"):
        return True
    return any(has_launcher(child) for child in node.get("children", []))


def add_launcher(tree):
    if has_launcher(tree):
        return tree
    tabs = find_tabs(tree)
    if tabs is not None:
        original = deepcopy(tabs)
        original["id"] = "outputs-original-tabs"
        original.pop("size", None)
        original.pop("min", None)
        original.pop("max", None)
        tabs.pop("content")
        tabs["type"] = "row"
        tabs["resizable"] = False
        tabs["children"] = [original, {
            "id": "outputs-launcher", "type": "block", "size": {"px": 100},
            "content": {"mod": NAME, "props": {"toolbar": True}},
        }]
    else:
        tree.setdefault("floating", []).append({
            "id": "outputs-launcher", "content": {"mod": NAME, "props": {"toolbar": True}},
            "edge": "top", "align": "end",
        })
    return tree


def run(command, env=None):
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def install(package, home, app_dir, no_ui=False, layout_name=NAME):
    if not (package / "mod/release.json").is_file():
        raise RuntimeError("Kurulum paketi eksik. ZIP’in tamamını çıkarıp içindeki install.py dosyasını çalıştırın.")
    if platform.system() != "Darwin":
        raise RuntimeError("Bu paket macOS 13 ve üzeri içindir. Linux ve Windows sürümü henüz yok.")
    if sys.version_info < (3, 9):
        raise RuntimeError("Python 3.9 veya üzeri gerekiyor.")
    for program in ("herdr-app", "hc", "swiftc"):
        if not shutil.which(program):
            raise RuntimeError(f"{program} bulunamadı. Herdr Desktop ve Xcode Command Line Tools kurulu olmalı.")
    home = Path(home).expanduser().resolve()
    if not no_ui and not (home / "AGENTS.md").exists():
        raise RuntimeError("Herdr Desktop’ı bir kez açtıktan sonra yeniden çalıştırın.")
    env = dict(os.environ, HERDR_APP_HOME=str(home))
    module = home / "mods" / NAME
    if module.exists():
        metadata = module / "release.json"
        if not metadata.exists() or json.loads(metadata.read_text()).get("owner") != OWNER:
            raise RuntimeError(f"{module} başka bir moda ait. Kurulum durduruldu; mevcut dosyalar değiştirilmedi.")
    # Check the build tool before writing any of the person's files.
    run(["swiftc", "--version"])
    previous_layout = None
    if not no_ui:
        previous_layout = json.loads(run(["herdr-app", "status"], env))["layout"]
    backup = None
    if module.exists():
        backup = home / "backups/outputs-browser" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(module, backup)
    module.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package / "mod", module, dirs_exist_ok=True)
    try:
        run(["herdr-app", "check", str(module)], env)
        output = run([sys.executable, str(module / "native/build.py"), "--output", str(app_dir)])
        print(output.strip())
        if not no_ui:
            layout_file = home / "layouts" / (layout_name + ".json")
            if layout_file.exists() and has_launcher(json.loads(layout_file.read_text())):
                run(["herdr-app", "do", "layout.switch", json.dumps({"name": layout_name})], env)
            else:
                candidate = layout_name
                number = 2
                while (home / "layouts" / (candidate + ".json")).exists():
                    candidate = f"{layout_name}-{number}"
                    number += 1
                run(["herdr-app", "do", "layout.clone", json.dumps({"name": previous_layout, "as": candidate})], env)
                layout_file = home / "layouts" / (candidate + ".json")
                tree = add_launcher(json.loads(layout_file.read_text()))
                temporary = layout_file.with_suffix(".json.installing")
                temporary.write_text(json.dumps(tree, ensure_ascii=False, indent=2) + "\n")
                temporary.replace(layout_file)
                run(["herdr-app", "status"], env)
                layout_name = candidate
        (module / "installation.json").write_text(json.dumps({
            "previous_layout": previous_layout, "layout": layout_name if not no_ui else None,
            "app_dir": str(app_dir), "backup": str(backup) if backup else None,
        }, indent=2))
    except Exception:
        if backup:
            shutil.rmtree(module)
            shutil.copytree(backup, module)
        if previous_layout:
            subprocess.run(["herdr-app", "do", "layout.switch", json.dumps({"name": previous_layout})], env=env, capture_output=True)
        raise
    print("Kurulum tamamlandı. Herdr’da bir Codex veya Claude Code oturumunu seçip Çıktılar’a basın.")
    if previous_layout:
        print("Önceki düzene dönüş: herdr-app do layout.switch '" + json.dumps({"name": previous_layout}) + "'")
    return module


def main():
    parser = argparse.ArgumentParser(description="Herdr Çıktılar · macOS kurulumu")
    parser.add_argument("--home", type=Path, default=Path(os.environ.get("HERDR_APP_HOME", str(Path.home() / ".config/herdr-app"))))
    parser.add_argument("--app-dir", type=Path, default=Path.home() / ".local/share/herdr-outputs/Herdr Outputs.app")
    parser.add_argument("--no-ui", action="store_true", help="Test için Herdr düzenini değiştirmeden kur")
    args = parser.parse_args()
    try:
        install(Path(__file__).resolve().parent, args.home, args.app_dir, args.no_ui)
    except Exception as error:
        print("Kurulum tamamlanamadı: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

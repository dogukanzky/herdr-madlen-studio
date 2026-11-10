#!/usr/bin/env python3
"""Build the local, unsandboxed AppKit helper. No global Herdr binary changes."""
from pathlib import Path
import argparse
import plistlib
import platform
import shutil
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path.home() / ".local/share/herdr-outputs/Herdr Outputs.app")
parser.add_argument("--universal", action="store_true")
args = parser.parse_args()
bundle = args.output
contents = bundle / "Contents"
executable = contents / "MacOS/HerdrOutputs"
executable.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    binaries = []
    for architecture in (["arm64", "x86_64"] if args.universal else [platform.machine()]):
        binary = Path(temporary) / architecture
        subprocess.run(["/usr/bin/swiftc", "-swift-version", "5", "-target", f"{architecture}-apple-macosx13.0", "-Onone", str(source / "main.swift"),
                        "-o", str(binary), "-framework", "AppKit", "-framework", "WebKit", "-framework", "ImageIO", "-framework", "UniformTypeIdentifiers"], check=True)
        binaries.append(binary)
    if args.universal:
        subprocess.run(["/usr/bin/lipo", "-create", *map(str, binaries), "-output", str(executable)], check=True)
    else:
        shutil.copy2(binaries[0], executable)
resources = contents / "Resources/reader"
shutil.copytree(source.parent / "web", resources, dirs_exist_ok=True)
plist = {
    "CFBundleIdentifier": "local.herdr.outputs",
    "CFBundleName": "Herdr Outputs",
    "CFBundleDisplayName": "Herdr Çıktılar",
    "CFBundleExecutable": "HerdrOutputs",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "4.0",
    "CFBundleVersion": "5",
    "HerdrAppHome": str(source.parents[2]),
    "PythonExecutable": str(Path(sys.executable).resolve()),
    "LSUIElement": True,
    "NSHighResolutionCapable": True,
    "LSMinimumSystemVersion": "13.0",
    "CFBundleDocumentTypes": [{"CFBundleTypeName": "Herdr output request", "CFBundleTypeRole": "Viewer",
                              "CFBundleTypeExtensions": ["herdroutputs"], "LSHandlerRank": "Owner"}],
}
with (contents / "Info.plist").open("wb") as file:
    plistlib.dump(plist, file)
subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(bundle)], check=True)
print(bundle)

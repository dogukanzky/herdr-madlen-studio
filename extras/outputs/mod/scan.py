"""Read file references from the selected conversation. Never opens a file."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlparse
from history import read_history

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg"}


def resolve(raw, cwd):
    raw = raw.strip().strip('`\"\'<>')
    if raw.startswith("file://"):
        uri = urlparse(raw)
        if uri.netloc not in ("", "localhost"):
            return None
        raw = unquote(uri.path)
    elif re.match(r"^[a-zA-Z][\w+.-]*://", raw):
        return None
    raw = re.sub(r":\d+(?::\d+)?$", "", raw)
    raw = re.sub(r"#L\d+(?:-L\d+)?$", "", raw)
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        if not cwd:
            return None
        path = Path(cwd) / path
    for candidate in (path, Path(str(path).rstrip(".,;:!?)]}"))):
        if candidate.exists():
            return candidate.absolute()
    return None


def references(text, cwd):
    # Markdown and quoted references preserve spaces and parentheses.
    found = []
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith(("/", "~/", "file://")):
            p = resolve(raw, cwd)
            if p and p not in found:
                found.append(p)
    patterns = [r'\]\(\s*(<[^>\n]+>|[^\n]+?)\s*\)', r'`([^`\n]+)`',
                r'"((?:file://|/|~/)[^"\n]+)"', r"'((?:file://|/|~/)[^'\n]+)'",
                r'(?:file://(?:localhost)?/|(?<![\w:/])/(?!/)|~/)[^\s`\"<>]+']
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            raw = match.group(1) if match.lastindex else match.group()
            p = resolve(raw, cwd)
            if p and p not in found:
                found.append(p)
    return found[:100]


def dimensions(path):
    try:
        if path.suffix.lower() == ".svg":
            import xml.etree.ElementTree as ET
            el = ET.parse(path).getroot()
            vb = el.attrib.get("viewBox", "").replace(",", " ").split()
            if len(vb) == 4:
                return float(vb[2]), float(vb[3])
            return float(el.attrib["width"].removesuffix("px")), float(el.attrib["height"].removesuffix("px"))
        r = subprocess.run(["/usr/bin/sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                           capture_output=True, text=True, timeout=5)
        w = re.search(r"pixelWidth:\s*(\d+)", r.stdout)
        h = re.search(r"pixelHeight:\s*(\d+)", r.stdout)
        if w and h:
            return int(w[1]), int(h[1])
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        pass
    return None


def item(path, source, app_home):
    try:
        st = path.stat()
        ext = path.suffix.lower()
        kind = "folder" if path.is_dir() else "html" if ext in {".html", ".htm"} else "markdown" if ext in {".md", ".markdown"} else "json" if ext == ".json" else "zip" if ext == ".zip" else "file"
        out = dict(path=str(path), name=path.name, directory=path.is_dir(), source=source,
                   size=st.st_size, mtime=st.st_mtime, kind=kind)
        if not out["directory"] and path.suffix.lower() in IMAGES and st.st_size < 100_000_000:
            size = dimensions(path)
            if size and min(size) > 0:
                key = hashlib.sha256(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:24]
                rel = f"data/outputs-browser/{key}{path.suffix.lower()}"
                target = Path(app_home) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(path, target)
                out.update(kind="image", rel=rel, w=size[0], h=size[1])
        return out
    except (OSError, ValueError):
        return None


def reference_context(text, path, cwd):
    needles = [str(path), path.as_uri(), path.name]
    if cwd:
        try:
            needles.append(str(path.relative_to(cwd)))
        except ValueError:
            pass
    lines = text.splitlines()
    indices = [i for i, line in enumerate(lines) if any(n and n in line for n in needles)]
    chosen = sorted({j for i in indices for j in range(max(0, i - 1), min(len(lines), i + 2))})
    return " ".join(lines[i].strip() for i in chosen)[:5000]


def scan(request):
    if request.get("terminal"):
        history = read_history(request["terminal"])
        messages = history["messages"]
        source = "conversation"
    else:
        history = {}
        messages = [dict(text=request.get("text", ""), cwd=request.get("cwd"))]
        source = "added"
    # Messages arrive newest first. Deduplicate by the most recent mention, not file mtime.
    items, seen = [], {}
    for message in messages:
        for p in references(message["text"], message.get("cwd")):
            key = str(p.resolve())
            context = reference_context(message["text"], p, message.get("cwd"))
            if key in seen:
                previous = seen[key]
                if context and context not in previous["search_text"]:
                    previous["search_text"] = (previous["search_text"] + " " + context)[:12000]
                continue
            if source == "conversation" and (str(p) in {"/", "/Users"} or (not p.is_dir() and not p.suffix and os.access(p, os.X_OK))):
                continue
            value = item(p, source, request["app_home"])
            if value:
                value["ordinal"] = message.get("ordinal")
                value["mentioned_at"] = message.get("at")
                value["search_text"] = context
                items.append(value)
                seen[key] = value
    return dict(items=items, message_count=history.get("message_count", 0), session=history.get("session"), kind=history.get("kind"))


if __name__ == "__main__":
    try:
        print(json.dumps(scan(json.loads(sys.argv[1])), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error": str(error), "items": []}))

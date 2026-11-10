#!/usr/bin/env python3
"""Install only the versioned theme; preserve sessions and unrelated configuration."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
OWNER = 'herdr-madlen-studio'
VERSION = '1.0.3'
REQUIRED_MODS = ('files', 'changes', 'new-menu', 'menu', 'machine-add')


def run(argv, env=None):
    p = subprocess.run(argv, capture_output=True, text=True, env=env)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip() or str(argv))
    return p.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(source):
    return sorted(p for p in source.rglob('*') if p.is_file() and 'data' not in p.relative_to(source).parts and '__pycache__' not in p.parts and p.suffix != '.pyc')


def install(source, home, activate=True, check=True, replace_modified=False):
    home = home.expanduser().resolve()
    manifest = home / 'packages' / OWNER / 'installation.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else None
    if old and old.get('owner') != OWNER:
        raise RuntimeError('Kurulum manifesti başka pakete ait.')
    incoming = {str(p.relative_to(source)): p for p in files(source)}
    owned = (old or {}).get('files', {})
    # Check every destination before any write. Unrelated same-name mods are never adopted.
    for rel, p in incoming.items():
        dest = home / rel
        if any(parent.is_symlink() for parent in [dest, *dest.parents] if parent != home.parent):
            raise RuntimeError('Sembolik bağlantı üzerine kurulum yapılmaz: ' + str(dest))
        if dest.exists() and rel not in owned:
            raise RuntimeError('Aynı adlı kişisel dosya var; değiştirilmedi: ' + str(dest))
        if dest.exists() and digest(dest) != owned.get(rel) and not replace_modified:
            raise RuntimeError('Yerel değişiklik var. İnceledikten sonra --replace-modified kullanın: ' + rel)
    env = dict(os.environ, HERDR_APP_HOME=str(home))
    before = json.loads(run(['herdr-app', 'status'], env))['layout'] if check else None
    previous = (old or {}).get('previous_layout') or before
    if check:
        for name in REQUIRED_MODS:
            if not (home / 'mods' / name / 'main.js').is_file():
                raise RuntimeError('Herdr mod bağımlılığı eksik: ' + name + '. Önce Herdr Desktop’ı açın/güncelleyin.')
    backup = home / 'backups' / OWNER / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    existing = [rel for rel in incoming if (home / rel).exists()]
    for rel in existing:
        p = backup / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(home / rel, p)
    switched = False
    try:
        for rel, p in incoming.items():
            dest = home / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
                f.write(p.read_bytes())
                temporary = Path(f.name)
            temporary.replace(dest)
        if check:
            for mod in sorted((source / 'mods').iterdir()):
                run(['herdr-app', 'check', str(home / 'mods' / mod.name)], env)
        if activate:
            switched = True
            run(['herdr-app', 'do', 'layout.switch', json.dumps({'name':'madlen-studio'})], env)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(dict(owner=OWNER, version=VERSION, previous_layout=previous,
            backup=str(backup) if existing else None,
            files={rel:digest(p) for rel,p in incoming.items()}), indent=2)+'\n')
    except Exception:
        for rel in incoming:
            dest = home / rel
            if rel in existing:
                shutil.copy2(backup / rel, dest)
            elif dest.is_file():
                dest.unlink()
        if switched and before:
            subprocess.run(['herdr-app','do','layout.switch',json.dumps({'name':before})],env=env,capture_output=True)
        raise
    return previous


def main():
    p = argparse.ArgumentParser(description='Madlen Studio — Herdr teması')
    p.add_argument('--home', type=Path, default=Path(os.environ.get('HERDR_APP_HOME',str(Path.home()/'.config/herdr-app'))))
    p.add_argument('--no-activate', action='store_true', help='Kur, mevcut görünümü değiştirme')
    p.add_argument('--replace-modified', action='store_true', help='Bu paketin değiştirilmiş dosyalarını yedekleyip güncelle')
    p.add_argument('--with-outputs', action='store_true', help='İsteğe bağlı Çıktılar uygulamasını kaynak koddan derle (swiftc gerekir)')
    args=p.parse_args()
    try:
        if platform.system()!='Darwin':
            raise RuntimeError('Bu sürüm macOS için doğrulandı; Linux/Windows kurulumu desteklenmiyor.')
        for program in ['herdr-app','hc'] + (['swiftc'] if args.with_outputs else []):
            if not shutil.which(program):raise RuntimeError(program+' bulunamadı. Önce gerekli uygulamayı kurun.')
        if args.with_outputs:
            # Existing standalone installer has its own ownership checks and backup.
            run([sys.executable,str(ROOT/'extras/outputs/install.py'),'--home',str(args.home),'--no-ui'])
        previous=install(ROOT/'theme',args.home,not args.no_activate,replace_modified=args.replace_modified)
        print('Madlen Studio kuruldu.' + (' Etkinleştirilmedi.' if args.no_activate else ' Tema etkin.'))
        if previous:print('Geri dönüş: herdr-app do layout.switch '+repr(json.dumps({'name':previous})))
        if not shutil.which('quota-axi'):print('Not: Kullanım halkaları için isteğe bağlı quota-axi gerekiyor.')
        if not args.with_outputs:print('Çıktılar isteğe bağlı: python3 install.py --with-outputs')
    except Exception as e:
        print('Kurulum tamamlanamadı: '+str(e),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())

"""Compile the small AppKit adapter once; subsequent paste operations use its cache."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import images


def helper():
    source=Path(__file__).with_suffix('.swift')
    key=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    directory=images.HOME/'data/madlen-chat/bin';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    binary=directory/('clipboard-'+key)
    if not binary.exists():
        compiler=shutil.which('swiftc')
        if not compiler:raise ValueError('Görsel yapıştırmak için Xcode Command Line Tools gerekiyor.')
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            target=Path(tmp)/'clipboard'
            result=subprocess.run([compiler,str(source),'-o',str(target)],capture_output=True,text=True,timeout=90)
            if result.returncode:raise ValueError('Görsel desteği derlenemedi. Xcode Command Line Tools kurulumunu kontrol edin.')
            target.replace(binary)
    return binary


def capture():
    folder=images.HOME/'data/madlen-chat/uploads';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(suffix='.png',dir=folder) as f:
        result=subprocess.run([str(helper()),'capture',f.name],capture_output=True,text=True,timeout=10)
        data=json.loads(result.stdout)
        if result.returncode:raise ValueError(data.get('error','Görsel alınamadı.'))
        return images.local(f.name,upload=True)


def attach(terminal,path):
    hc=shutil.which('hc')
    if not hc:raise ValueError('hc bulunamadı.')
    result=subprocess.run([str(helper()),'attach',terminal,str(path),hc],capture_output=True,text=True,timeout=20)
    data=json.loads(result.stdout)
    if result.returncode:raise ValueError(data.get('error','Görsel aktarılamadı.'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--file',action='append');args=parser.parse_args()
    try:print(json.dumps({'images':[images.local(p,upload=True) for p in args.file]} if args.file else {'images':[capture()]}))
    except Exception as e:print(json.dumps({'error':str(e)}));raise SystemExit(1)

"""Local image cache for GPUI: no remote downloads, no transcript mutation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

HOME=Path(__file__).resolve().parents[2]
MAX_BYTES=20*1024*1024

def keep(data, upload=False):
    if not data or len(data)>MAX_BYTES:raise ValueError('Görsel en fazla 20 MB olabilir.')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
    elif data.startswith(b'\xff\xd8\xff'):ext='jpg'
    elif data[:6] in (b'GIF87a',b'GIF89a'):ext='gif'
    elif data[:4]==b'RIFF' and data[8:12]==b'WEBP':ext='webp'
    else:raise ValueError('PNG, JPEG, GIF veya WebP görseli gerekiyor.')
    folder=HOME/'data/madlen-chat'/('uploads' if upload else 'images');folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(hashlib.sha256(data).hexdigest()+'.'+ext)
    if not path.exists():
        path.write_bytes(data);path.chmod(0o600)
    meta=path.with_suffix('.json')
    if meta.exists():return json.loads(meta.read_text())
    if ext=='png':w,h=struct.unpack('>II',data[16:24])
    elif ext=='gif':w,h=struct.unpack('<HH',data[6:10])
    else:
        p=subprocess.run(['/usr/bin/sips','-g','pixelWidth','-g','pixelHeight',str(path)],capture_output=True,text=True,timeout=5)
        values={line.split(':')[0].strip():line.split(':')[1].strip() for line in p.stdout.splitlines() if ':' in line}
        w,h=int(values.get('pixelWidth',640)),int(values.get('pixelHeight',480))
    if w<=0 or h<=0 or w*h>80_000_000:raise ValueError('Görsel boyutları desteklenmiyor.')
    result=dict(path=str(path.relative_to(HOME)),width=w,height=h)
    meta.write_text(json.dumps(result));meta.chmod(0o600)
    return result

def local(path,upload=False):
    p=Path(path).expanduser()
    if not p.is_file():return dict(missing=True,name=p.name)
    if p.stat().st_size>MAX_BYTES:raise ValueError('Görsel en fazla 20 MB olabilir.')
    return keep(p.read_bytes(),upload)

def from_content(content):
    attachments=[]
    for c in content if isinstance(content,list) else []:
        if not isinstance(c,dict):continue
        try:
            if c.get('type')=='localImage' and c.get('path'):attachments.append(local(c['path']))
            elif c.get('type')=='image' and c.get('source',{}).get('type')=='base64':
                raw=c['source'].get('data','')
                if len(raw)>MAX_BYTES*4//3+8:raise ValueError('Görsel çok büyük.')
                attachments.append(keep(base64.b64decode(raw,validate=True)))
        except (ValueError,OSError,struct.error):attachments.append(dict(missing=True,name='Görsel kullanılamıyor'))
    return attachments

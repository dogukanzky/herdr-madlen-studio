import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
import images
import bridge


def png():
    def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'+b'\x20\x60\xff'*2))+chunk(b'IEND',b'')

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.patch=patch.object(images,'HOME',self.home);self.patch.start();self.addCleanup(self.patch.stop)
    def test_cache_preserves_aspect_and_deduplicates(self):
        a=images.keep(png());b=images.keep(png())
        self.assertEqual(a,b);self.assertEqual((a['width'],a['height']),(2,1))
        self.assertEqual((self.home/a['path']).read_bytes(),png())
        self.assertEqual((self.home/a['path']).stat().st_mode&0o777,0o600)
    def test_local_missing_and_invalid(self):
        self.assertTrue(images.local(self.home/'gone.png')['missing'])
        with self.assertRaises(ValueError):images.keep(b'<svg>not raster</svg>')
        with patch.object(images,'MAX_BYTES',4):
            with self.assertRaises(ValueError):images.keep(png())
    def test_claude_image_only_message(self):
        source={'type':'base64','media_type':'image/png','data':base64.b64encode(png()).decode()}
        p=self.home/'claude.jsonl';p.write_text(json.dumps({'type':'user','uuid':'image','message':{'role':'user','content':[{'type':'image','source':source}]}}))
        row=bridge.records(p,'claude')[0]
        self.assertEqual(row['role'],'user');self.assertEqual(len(row['attachments']),1)
        self.assertEqual(row['attachments'][0]['width'],2)
    def test_codex_local_image(self):
        p=self.home/'local.png';p.write_bytes(png())
        row=bridge.codex_item({'type':'userMessage','id':'img','content':[{'type':'localImage','path':str(p)}]},0)
        self.assertEqual(row['attachments'][0]['height'],1)
    def test_never_download_remote_image(self):
        self.assertEqual(images.from_content([{'type':'image','source':{'type':'url','url':'https://example.invalid/private.png'}}]),[])
    def test_send_rejects_external_attachment_before_clipboard(self):
        with patch.object(bridge,'resolve',return_value=({'status':{'state':'idle'}},'codex','s',Path('/tmp'),True)),patch.object(bridge.clipboard,'helper') as helper:
            with self.assertRaisesRegex(ValueError,'geçersiz'):bridge.send('t1','s','Look',['../../outside.png'])
            helper.assert_not_called()
    def test_verified_image_send_and_failed_paste_never_submit(self):
        path=images.keep(png(),upload=True)['path']
        session=({'status':{'state':'idle'}},'codex','s',Path('/tmp'),True)
        from types import SimpleNamespace
        replies=[SimpleNamespace(returncode=0,stdout=json.dumps({'text':'empty composer'})),SimpleNamespace(returncode=0,stdout=json.dumps({'text':'[Image #1]'})),SimpleNamespace(returncode=0,stdout='{}')]
        with patch.object(bridge,'resolve',return_value=session),patch.object(bridge.clipboard,'helper'),patch.object(bridge.clipboard,'attach') as attach,patch.object(bridge.b,'run',side_effect=replies) as run:
            self.assertEqual(bridge.send('t1','s','Look',[path]),{'ok':True})
            attach.assert_called_once_with('t1',(self.home/path).resolve())
            self.assertEqual(run.call_args.args[0],['hc','send','--if','idle','t1','Look'])
        with patch.object(bridge,'resolve',return_value=session),patch.object(bridge.clipboard,'helper'),patch.object(bridge.clipboard,'attach'),patch.object(bridge.b,'run',side_effect=replies) as run:
            self.assertEqual(bridge.send('t1','s','',[path]),{'ok':True})
            self.assertEqual(run.call_args.args[0],['hc','keys','t1','enter'])
        with patch.object(bridge,'resolve',return_value=session),patch.object(bridge.clipboard,'helper'),patch.object(bridge.clipboard,'attach',side_effect=ValueError('paste failed')),patch.object(bridge.b,'run',return_value=replies[0]) as run:
            result=bridge.send('t1','s','Look',[path]);self.assertTrue(result['attachments_staged']);self.assertIn('error',result)
            self.assertEqual(run.call_count,1)

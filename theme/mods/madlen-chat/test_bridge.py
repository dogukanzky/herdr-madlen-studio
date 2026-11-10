import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge

class BridgeTests(unittest.TestCase):
    def test_question_card(self):
        v=bridge.codex_item({'type':'mcpToolCall','id':'q','tool':'request_user_input','arguments':{'questions':[{'question':'Renk?','options':[{'label':'Açık'}]}]}},1)
        self.assertEqual(v['role'],'question');self.assertEqual(v['questions'][0]['options'][0]['label'],'Açık')
    def test_reasoning_and_host_context_excluded(self):
        self.assertIsNone(bridge.codex_item({'type':'reasoning','text':'private'},1))
        self.assertIsNone(bridge.codex_item({'type':'userMessage','content':[{'type':'text','text':'# AGENTS.md instructions hidden'}]},1))
    def test_codex_user_text(self):
        v=bridge.codex_item({'type':'userMessage','content':[{'type':'text','text':'Merhaba'},{'type':'localImage','path':'/tmp/a.png'}]},1)
        self.assertEqual(v['text'],'Merhaba');self.assertEqual(v['attachments'],['/tmp/a.png'])
    def test_claude_tools_and_result(self):
        rows=[{'uuid':'u','message':{'role':'user','content':'Merhaba'}},{'uuid':'a','message':{'role':'assistant','content':[{'type':'thinking','thinking':'private'},{'type':'text','text':'Bakıyorum'},{'type':'tool_use','id':'t','name':'Read','input':{'file_path':'test'}}]}},{'uuid':'r','message':{'role':'user','content':[{'type':'tool_result','tool_use_id':'t','content':'result'}]}}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.jsonl';p.write_text('\n'.join(map(json.dumps,rows))+'\n{"partial":')
            m=bridge.records(p,'claude')
        self.assertEqual([x['role'] for x in m],['user','assistant','tool']);self.assertEqual(m[-1]['output'],'result');self.assertNotIn('private',str(m))
    def test_send_refuses_changed_session_or_busy(self):
        with patch.object(bridge,'resolve',return_value=({'status':{'state':'idle'}},'codex','new',Path('/tmp'),True)),patch.object(bridge.b,'run') as run:
            with self.assertRaisesRegex(ValueError,'Oturum değişti'):bridge.send('t1','old','hello')
            run.assert_not_called()
        with patch.object(bridge,'resolve',return_value=({'status':{'state':'blocked'}},'codex','s',Path('/tmp'),True)),patch.object(bridge.b,'run') as run:
            with self.assertRaisesRegex(ValueError,'Agent çalışıyor'):bridge.send('t1','s','yes')
            run.assert_not_called()
    def test_send_exact_target_no_shell(self):
        with patch.object(bridge,'resolve',return_value=({'status':{'state':'idle'}},'claude','s',Path('/tmp'),False)),patch.object(bridge.b,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='{"started":true}'
            bridge.send('t1','s','hello $(no-shell)')
            run.assert_called_once_with(['hc','send','--if','idle','t1','hello $(no-shell)'])
    def test_done_send_and_delayed_working_signal_are_accepted(self):
        with patch.object(bridge,'resolve',return_value=({'status':{'state':'done'}},'codex','s',Path('/tmp'),True)),patch.object(bridge.b,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='{"started":false,"turn":4}'
            self.assertEqual(bridge.send('t1','s','hello'),{'ok':True})
            run.assert_called_once_with(['hc','send','t1','hello'])
    def test_history_is_not_cut_to_last_180_records(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.jsonl'
            p.write_text(''.join(json.dumps({'uuid':str(i),'message':{'role':'assistant','content':[{'type':'text','text':str(i)}]}})+'\n' for i in range(700)))
            messages=bridge.records(p,'claude')
        self.assertEqual(len(messages),700)
        self.assertEqual(messages[0]['text'],'0');self.assertEqual(messages[-1]['text'],'699')
    def test_short_reply_binding_needs_two_matches_and_unique_session(self):
        texts=['Araç kullanma. Sadece iki satırlı mesaj alındı. yaz.','iki satırlı mesaj alındı.']
        screen=' '.join(texts)
        self.assertEqual(bridge.b.bind_recent([('a',texts)],texts[-1],screen),'a')
        self.assertIsNone(bridge.b.bind_recent([('a',texts),('b',texts)],texts[-1],screen))
        self.assertIsNone(bridge.b.bind_recent([('a',[texts[-1]])],texts[-1],screen))
    def test_remote_refused(self):
        with self.assertRaisesRegex(ValueError,'yerel'):bridge.terminal('xps/t1')

if __name__=='__main__':unittest.main()

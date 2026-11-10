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
        self.assertEqual(v['text'],'Merhaba');self.assertEqual(len(v['attachments']),1)
    def test_claude_tools_and_result(self):
        rows=[{'uuid':'u','message':{'role':'user','content':'Merhaba'}},{'uuid':'a','message':{'role':'assistant','content':[{'type':'thinking','thinking':'private'},{'type':'text','text':'Bakıyorum'},{'type':'tool_use','id':'t','name':'Read','input':{'file_path':'test'}}]}},{'uuid':'r','message':{'role':'user','content':[{'type':'tool_result','tool_use_id':'t','content':'result'}]}}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.jsonl';p.write_text('\n'.join(map(json.dumps,rows))+'\n{"partial":')
            m=bridge.records(p,'claude')
        self.assertEqual([x['role'] for x in m],['user','assistant','tool']);self.assertEqual(m[-1]['output'],'result');self.assertNotIn('private',str(m))
    def claude_records(self,rows):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.jsonl';p.write_text('\n'.join(map(json.dumps,rows)))
            return bridge.records(p,'claude')
    def test_background_notification_is_tool_not_user(self):
        body='<task-notification><task-id>fixture-task</task-id><status>completed</status><summary>Test command completed</summary></task-notification>'
        rows=[{'type':'api-request-blob','message':{'role':'user','content':'<system-reminder>'+body+'</system-reminder>'}},
              {'type':'user','uuid':'event','origin':{'kind':'task-notification'},'promptSource':'system','message':{'role':'user','content':body}}]
        messages=self.claude_records(rows)
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0]['role'],'tool');self.assertEqual(messages[0]['name'],'Arka plan görevi')
        self.assertEqual(messages[0]['text'],'Test command completed')
        self.assertEqual(messages[0]['status'],'completed')
    def test_user_xml_examples_are_preserved(self):
        for text in ['<task-notification><status>failed</status><summary>Example</summary></task-notification>',
                     '<system-reminder>This is my example</system-reminder>',
                     'Explain this: <task-notification>example</task-notification>']:
            message=self.claude_records([{'type':'user','uuid':'human','message':{'role':'user','content':text}}])[0]
            self.assertEqual(message['role'],'user');self.assertEqual(message['text'],text)
    def test_api_assistant_blob_is_not_a_duplicate_reply(self):
        payload={'role':'assistant','content':'Reply'}
        messages=self.claude_records([{'type':'api-request-blob','message':payload},{'type':'assistant','uuid':'real','message':payload}])
        self.assertEqual(len(messages),1);self.assertEqual(messages[0]['id'],'real')
    def test_failed_and_malformed_notifications_stay_non_user(self):
        for body in ['<task-notification><status>failed</status><summary>A &amp; B</summary></task-notification>','<task-notification>partial']:
            message=self.claude_records([{'type':'user','uuid':'event','turnOrigin':'task_notification','message':{'role':'user','content':body}}])[0]
            self.assertEqual(message['role'],'tool')
            self.assertNotIn('<task-notification>',message['text'])
            if 'failed' in body:self.assertEqual(message['status'],'failed');self.assertEqual(message['text'],'A & B')
    def test_meta_text_does_not_hide_tool_results(self):
        rows=[{'type':'assistant','uuid':'a','message':{'role':'assistant','content':[{'type':'tool_use','id':'tool1','name':'Read','input':{}}]}},
              {'type':'user','uuid':'r','isMeta':True,'message':{'role':'user','content':[{'type':'text','text':'System context'},{'type':'tool_result','tool_use_id':'tool1','content':'Result'}]}}]
        messages=self.claude_records(rows)
        self.assertEqual([m['role'] for m in messages],['tool','tool'])
        self.assertEqual(messages[0]['output'],'Result')
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
    def test_invalid_address_refused(self):
        with self.assertRaisesRegex(ValueError,'Geçersiz'):bridge.terminal('xps/t1/invalid')

if __name__=='__main__':unittest.main()

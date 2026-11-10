"""Local, read-only transcript adapter; sending always targets the verified live TUI."""
import argparse
from html import unescape
import json
from pathlib import Path
import re
import sys
import binding as b


def terminal(address):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', address):
        raise ValueError('Sohbet görünümü şu anda yerel oturumları destekliyor.')
    r=b.run(['hc','get',address,'--json'])
    if r.returncode: raise ValueError('Oturum bulunamadı; terminal görünümüne dönün.')
    t=json.loads(r.stdout); fg=t.get('foreground') or {}
    app=(t.get('status') or {}).get('app') or fg.get('name','')
    kind='codex' if 'codex' in app else 'claude' if 'claude' in app else None
    if not kind or not fg.get('pid'): raise ValueError('Bu görünüm Codex ve Claude Code içindir.')
    return t,kind,fg['pid']


def resolve(address):
    t,kind,pid=terminal(address); home=Path.home(); root=home/'.codex'
    if kind=='codex':
        r=b.run(['hc','read',address,'--lines','0','--json'])
        screen=json.loads(r.stdout).get('text','') if r.returncode==0 else ''
        match=b.codex_thread(pid,root,screen)
        if match:return t,kind,match[0],Path(match[1]),True
    path=b.exact_log(pid,kind,home)
    if not path:raise ValueError('Bu terminalin sohbet kaydı henüz kesin eşleştirilemedi. Bir yanıt oluştuktan sonra tekrar deneyin.')
    return t,kind,path.stem,path,False


def text_content(content):
    if isinstance(content,str):return content
    return '\n'.join(c.get('text','') for c in content or [] if isinstance(c,dict) and c.get('type') in ('text','input_text','output_text'))


def clean(text):
    # Host instructions and internal context are not user-authored chat bubbles.
    if text.startswith(('# AGENTS.md instructions','<environment_context>','<permissions instructions>')):return ''
    return text


def question_list(args):
    if isinstance(args,str):
        try:args=json.loads(args)
        except ValueError:return []
    if not isinstance(args,dict):return []
    return [q for q in args.get('questions',[]) if isinstance(q,dict)]


def tool(id,name,args,status='completed',output=None):
    q=question_list(args) if any(s in name.lower() for s in ('request_user_input','askuserquestion')) else []
    detail=args if isinstance(args,str) else json.dumps(args,ensure_ascii=False,indent=2)
    return dict(id=id,role='question' if q else 'tool',name=name,text=detail[:10000],status=status,questions=q,output=(str(output)[:10000] if output else ''))


def codex_item(item,ordinal):
    typ=item.get('type'); id=str(item.get('id') or ordinal)
    if typ=='userMessage':
        text=clean(text_content(item.get('content')))
        attachments=[c.get('path') for c in item.get('content',[]) if c.get('type')=='localImage' and c.get('path')]
        return dict(id=id,role='user',text=text,attachments=attachments) if text or attachments else None
    if typ=='agentMessage':return dict(id=id,role='assistant',text=item.get('text',''))
    if typ=='commandExecution':return tool(id,'Terminal komutu',item.get('command',''),item.get('status'),item.get('aggregatedOutput'))
    if typ in ('mcpToolCall','dynamicToolCall'):
        return tool(id,item.get('tool') or item.get('name') or 'Araç',item.get('arguments',{}),item.get('status'),item.get('error') or item.get('result'))
    if typ=='fileChange':return tool(id,'Dosya değişiklikleri',item.get('changes',[]),item.get('status'))
    if typ=='webSearch':return tool(id,'Web araması',item.get('query') or item.get('action') or {},'completed')
    if typ=='imageGeneration':return tool(id,'Görsel oluşturma',item.get('savedPath') or '',item.get('status'))
    return None


def projected(sid):
    with b.database(Path.home()/'.codex/thread_history_1.sqlite') as db:
        rows=db.execute("SELECT rollout_ordinal,item_json FROM thread_items WHERE thread_id=? AND item_type!='reasoning' ORDER BY rollout_ordinal DESC",(sid,)).fetchall()
    return [v for i,raw in reversed(rows) if (v:=codex_item(json.loads(raw),i)) and (v.get('text') or v.get('attachments'))]


def claude_system_event(record, text, rid):
    """Use producer metadata, never XML-looking user text, to identify automation."""
    origin=record.get('origin') or {}
    kind=origin.get('kind') if isinstance(origin,dict) else None
    automated=(kind=='task-notification' or record.get('turnOrigin')=='task_notification'
               or record.get('promptSource')=='system' or record.get('isMeta') is True)
    if not automated:return None
    def field(name):
        match=re.search(r'<'+name+r'>(.*?)</'+name+r'>',text,re.S)
        return unescape(match.group(1).strip()) if match else ''
    if kind=='task-notification' or record.get('turnOrigin')=='task_notification':
        status=field('status')
        summary=field('summary') or 'Arka plan görevi güncellendi.'
        state='failed' if status in ('failed','error') else 'inProgress' if status in ('running','in_progress') else 'completed' if status=='completed' else 'unknown'
        return tool('notification-'+rid,'Arka plan görevi',summary,state)
    return tool('system-'+rid,'Sistem bildirimi',text)


def records(path,kind):
    out=[]; results={}
    rows=list(enumerate(b.reverse_json(path)))
    for ordinal,r in reversed(rows):
        if r.get('isSidechain'):continue
        # API request blobs duplicate turns and include hidden prompt wrappers.
        if kind=='claude' and r.get('type') not in (None,'user','assistant'):continue
        p=r.get('payload',{}) if kind=='codex' else r.get('message',{})
        if kind=='codex' and r.get('type')!='response_item':continue
        role=p.get('role');content=p.get('content',[]);rid=r.get('uuid') or str(ordinal)
        if kind=='codex':
            typ=p.get('type')
            if typ=='message' and role in ('user','assistant') and p.get('channel')!='analysis':
                txt=clean(text_content(content))
                if txt:out.append(dict(id=rid,role=role,text=txt))
            elif typ in ('function_call','custom_tool_call'):
                out.append(tool(p.get('call_id',rid),p.get('name','Araç'),p.get('arguments') or p.get('input','')))
            elif typ in ('function_call_output','custom_tool_call_output'):results[p.get('call_id')]=p.get('output')
        elif role in ('user','assistant'):
            txt=clean(text_content(content))
            if txt:
                event=claude_system_event(r,txt,rid) if role=='user' else None
                out.append(event if event is not None else dict(id=rid,role=role,text=txt))
            for c in content if isinstance(content,list) else []:
                if c.get('type')=='tool_use':out.append(tool(c.get('id',rid),c.get('name','Araç'),c.get('input',{})))
                elif c.get('type')=='tool_result':results[c.get('tool_use_id')]=text_content(c.get('content'))
    for m in out:
        if m['id'] in results:m['output']=str(results[m['id']])[:10000]
    return out


def snapshot(address):
    t,kind,sid,path,projection=resolve(address)
    messages=projected(sid) if projection else records(path,kind)
    status=(t.get('status') or {}).get('state','idle')
    return dict(terminal=address,session=sid,kind=kind,status=status,messages=messages)


def send(address,expected,text):
    if not text.strip():raise ValueError('Mesaj boş olamaz.')
    if len(text)>50000:raise ValueError('Bu mesaj çok uzun. Terminal görünümünü kullanın.')
    t,kind,sid,path,projection=resolve(address)
    if sid!=expected:raise ValueError('Oturum değişti. Sohbeti yenileyip tekrar deneyin.')
    if (t.get('status') or {}).get('state') not in ('idle','done'):
        raise ValueError('Agent çalışıyor veya yanıt bekliyor. Terminal görünümünden devam edin.')
    if text.lstrip().startswith('/'):
        raise ValueError('Slash komutlarını terminal görünümünde kullanın.')
    # Core only supports --if idle/working; a completed TUI reports done.
    # Default send still rejects blocked programs; never use --force.
    guard=['--if','idle'] if (t.get('status') or {}).get('state')=='idle' else []
    r=b.run(['hc','send',*guard,address,text])
    if r.returncode:raise ValueError(r.stderr or 'Mesaj gönderilemedi.')
    result=json.loads(r.stdout)
    # started=false means the text was sent but no working signal arrived yet.
    # Treating that as a failed send would invite duplicate submissions.
    return dict(ok=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--terminal',required=True);p.add_argument('--session');p.add_argument('--text');a=p.parse_args()
    try:
        result=send(a.terminal,a.session,a.text) if a.text is not None else snapshot(a.terminal)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        print(json.dumps(dict(error=str(e)),ensure_ascii=False));return 1
    return 0

if __name__=='__main__':sys.exit(main())

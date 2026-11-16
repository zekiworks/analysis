"""R4 completion handoff: synthetic real HTTP, actual child exit after fsynced empty_done."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import Server,PRICE,PAYLOAD,BODY,reply

class CompletionHandoff(unittest.TestCase):
    def test_received_second_reply_survives_done_before_caller_stores_it(self):
        def answer(text,cost=0):
            r=reply(cost);r['choices'][0]['message']['content']=text;return r
        expected=answer('synthetic second reply')
        # Uncut protocol control: first empty, one second attempt, same final result.
        control=Server([(200,answer('')),(200,expected)])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                g=bo.SpendGuard(Path(tmp)/'ledger',1.0,PRICE)
                result,first=bo.post_chat(control.url,PAYLOAD,{},5,None,'OpenRouter',True,g)
                self.assertEqual(control.count,2);self.assertEqual(result,expected);self.assertTrue(bo.empty_reply(first))
        finally:control.close()
        server=Server([(200,answer('')),(200,expected),(200,answer('synthetic third reply'))])
        code='''import os,sys
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import PRICE,PAYLOAD
p,url=sys.argv[1:]
g=bo.SpendGuard(Path(p),1.0,PRICE)
append=g._append
def cut(record):
    append(record)
    if record.get("t")=="empty_done":os._exit(73)
g._append=cut
bo.post_chat(url,PAYLOAD,{},5,None,"OpenRouter",True,g)
'''
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'ledger'
                p=subprocess.run([sys.executable,'-B','-c',code,str(path),server.url],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
                self.assertEqual(p.returncode,73,p.stdout)
                self.assertEqual(server.count,2,'both original replies arrived before child was cut')
                records=[json.loads(line)for line in path.read_text().splitlines()]
                self.assertEqual(records[-1]['t'],'empty_done')
                # No caller has received/stored the second result; reopen real source as on resume.
                reopened=bo.SpendGuard(path,1.0,PRICE)
                result,first=bo.post_chat(server.url,PAYLOAD,{},5,None,'OpenRouter',True,reopened)
                self.assertEqual(server.count,2,'done erased the received result before caller durability and allowed a third send')
                self.assertEqual(result,expected,'replayed third answer replaced the received second answer')
        finally:server.close()

if __name__=='__main__':unittest.main()

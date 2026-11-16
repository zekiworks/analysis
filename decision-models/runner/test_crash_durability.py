"""Actual child-process crash controls for durable R3/R4, synthetic HTTP only."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import Server,PRICE,PAYLOAD,BODY,reply

class CrashDurability(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ledger.jsonl'
        self.bound=((BODY+bo.SPEND_INPUT_MARGIN)+1000)/1_000_000
    def tearDown(self):self.tmp.cleanup()
    def child(self,code,*args):
        p=subprocess.run([sys.executable,'-B','-c',code,*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
        self.assertEqual(p.returncode,73,p.stdout)
        return p
    def test_crash_after_overbound_settlement_before_halt_still_stops_next_send(self):
        server=Server([(200,reply(2*self.bound))])
        code='''import os,sys
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import PRICE,PAYLOAD
p,url,cap=sys.argv[1:]
g=bo.SpendGuard(Path(p),float(cap),PRICE)
append=g._append
def cut(line):
    append(line)
    if line.get("t")=="settle":os._exit(73)
g._append=cut
bo.post_json(url,PAYLOAD,{},5,None,"OpenRouter",g)
'''
        try:
            self.child(code,self.path,server.url,3.5*self.bound)
            rows=[json.loads(x)for x in self.path.read_text().splitlines()]
            self.assertTrue(any(x.get('t')=='settle' for x in rows))
            self.assertFalse(any(x.get('t')=='halt' for x in rows))
            reopened=bo.SpendGuard(self.path,3.5*self.bound,PRICE)
            with self.assertRaises(bo.SpendCapReached):
                bo.post_json(server.url,PAYLOAD,{},5,None,'OpenRouter',reopened)
        finally:server.close()
        self.assertEqual(server.count,1)
    def test_crash_after_empty_taken_before_retry_send_preserves_two_attempt_protocol(self):
        def empty(cost):
            r=reply(cost);r['choices'][0]['message']['content']='';return r
        good=reply(0);good['choices'][0]['message']['content']='synthetic third answer'
        server=Server([(200,empty(self.bound)),(200,empty(.5*self.bound)),(200,good)])
        g=bo.SpendGuard(self.path,2.5*self.bound,PRICE)
        other=g.reserve(BODY,1000)
        try:
            with self.assertRaises(bo.SpendCapReached):
                bo.post_chat(server.url,PAYLOAD,{},5,None,'OpenRouter',True,g)
            self.assertEqual(server.count,1)
            g.settle(other,{'usage':{'cost':0}})
            code='''import os,sys
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import PRICE,PAYLOAD
p,url,cap=sys.argv[1:]
g=bo.SpendGuard(Path(p),float(cap),PRICE)
append=g._append
def cut(line):
    append(line)
    if line.get("t")=="empty_taken":os._exit(73)
g._append=cut
bo.post_chat(url,PAYLOAD,{},5,None,"OpenRouter",True,g)
'''
            self.child(code,self.path,server.url,2.5*self.bound)
            self.assertEqual(server.count,1,'child crashed before any retry HTTP attempt')
            reopened=bo.SpendGuard(self.path,2.5*self.bound,PRICE)
            result,first=bo.post_chat(server.url,PAYLOAD,{},5,None,'OpenRouter',True,reopened)
            self.assertEqual(server.count,2,'crash reset the empty-reply allowance')
            self.assertTrue(bo.empty_reply(result),'third reply replaced the two-empty outcome')
        finally:server.close()

if __name__=='__main__':unittest.main()

"""Synthetic, credential-free regressions for the exact #9934 candidate. No benchmark items."""
import json
import math
import tempfile
import unittest
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import Server, PRICE, PAYLOAD, BODY, reply

class ReviewBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ledger.jsonl'
        self.bound = ((BODY + bo.SPEND_INPUT_MARGIN) + 1000) / 1_000_000
    def tearDown(self):
        self.tmp.cleanup()
    def guard(self, multiplier):
        return bo.SpendGuard(self.path, multiplier*self.bound, PRICE)
    def send(self, server, guard):
        return bo.post_json(server.url, PAYLOAD, {'Content-Type':'application/json'}, 5, None, 'OpenRouter', guard)
    def test_positive_regular_reservations_block_overcommit(self):
        g=self.guard(2.5)
        g.reserve(BODY,1000); g.reserve(BODY,1000)
        with self.assertRaises(bo.SpendCapReached): g.reserve(BODY,1000)
    def test_invalid_settlements_do_not_restore_spend(self):
        for name,cost in [('negative',-self.bound),('nan',float('nan')),('negative_infinity',float('-inf'))]:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as d:
                g=bo.SpendGuard(Path(d)/'ledger',2.5*self.bound,PRICE)
                first=g.reserve(BODY,1000)
                g.settle(first,{'usage':{'cost':cost}})
                g.reserve(BODY,1000)
                with self.assertRaises(bo.SpendCapReached): g.reserve(BODY,1000)
    def test_nan_cap_is_refused(self):
        with self.assertRaises(ValueError):
            bo.SpendGuard(self.path,float('nan'),PRICE)
    def test_partial_tail_does_not_hide_next_live_reservation(self):
        g=self.guard(2.5)
        g.reserve(BODY,1000) # one valid unsettled request before the crash
        with self.path.open('a') as f: f.write('{"t":"settle"')
        g.reserve(BODY,1000) # this live reservation must remain visible
        with self.assertRaises(bo.SpendCapReached): g.reserve(BODY,1000)
    def test_known_over_bound_cost_stops_before_another_underpriced_send(self):
        g=self.guard(3.5)
        server=Server([(200,reply(2*self.bound))])
        try:
            self.send(server,g)
            with self.assertRaises(bo.SpendCapReached): self.send(server,g)
        finally: server.close()
        self.assertEqual(server.count,1)
    def test_empty_reply_cap_pause_does_not_add_a_third_protocol_attempt(self):
        def empty(cost):
            r=reply(cost); r['choices'][0]['message']['content']=''; return r
        good=reply(.5*self.bound)
        good['choices'][0]['message']['content']='{"synthetic":"nonempty"}'
        # Positive continuous-run control: two empty replies consume the original retry allowance.
        control=Server([(200,empty(self.bound)),(200,empty(.5*self.bound)),(200,good)])
        try:
            result,first=bo.post_chat(control.url,PAYLOAD,{},5,None,'OpenRouter',True,self.guard(2.5))
            self.assertTrue(bo.empty_reply(result)); self.assertIsNotNone(first)
            self.assertEqual(control.count,2)
        finally: control.close()
        # Fresh ledger: another batch's in-flight reservation temporarily blocks the empty retry.
        self.path.unlink()
        g=self.guard(2.5); other=g.reserve(BODY,1000)
        server=Server([(200,empty(self.bound)),(200,empty(.5*self.bound)),(200,good)])
        try:
            with self.assertRaises(bo.SpendCapReached):
                bo.post_chat(server.url,PAYLOAD,{},5,None,'OpenRouter',True,g)
            self.assertEqual(server.count,1)
            # The other batch settles, so the ORIGINAL cap has room on resume.
            g.settle(other,{'usage':{'cost':0.0}})
            result,first=bo.post_chat(server.url,PAYLOAD,{},5,None,'OpenRouter',True,g)
            self.assertLessEqual(server.count,2,'cap pause/resume silently granted an extra model attempt')
            self.assertTrue(bo.empty_reply(result),'a third good reply replaced the original two-empty outcome')
        finally: server.close()

if __name__=='__main__': unittest.main()

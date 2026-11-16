"""Inert exact run-loop test: a resumed uncertain batch must not discard another received batch."""
from pathlib import Path
from types import SimpleNamespace
import tempfile,threading,unittest
from concurrent.futures import wait as real_wait, ALL_COMPLETED
from unittest import mock
import benchmark_ollama as bo
from test_spend_guard import PRICE

class UncertainDrain(unittest.TestCase):
    def test_other_received_outcomes_are_stored_before_uncertainty_stops_run(self):
        questions=[SimpleNamespace(question_id=i,answer='A') for i in range(2)]
        selection=SimpleNamespace(questions=questions)
        args=SimpleNamespace(batch_size=1,concurrency=2,progress_every=1)
        connection=mock.Mock()
        connection.execute.return_value=[]
        identity=SimpleNamespace(run_id=17)
        received=threading.Event();stored=[];entered=[]
        def ask(args,batch,thinking,log):
            q=batch[0];entered.append(q.question_id)
            if q.question_id==0:
                if not received.wait(5):raise AssertionError('second worker never returned its outcome')
                raise bo.UncertainRetry('synthetic retained uncertain request; no transport was invoked')
            received.set()
            return ['A'],'synthetic retained good reply'
        def store(conn,run_id,batch,predictions,raw,elapsed,duration):
            stored.extend(q.question_id for _,q in batch)
        def collected_together(futures,return_when):
            # FIRST_COMPLETED legally returns multiple already-done futures. Force that scheduling case,
            # without replacing either real worker/future or altering any product exception/store handling.
            return real_wait(futures,return_when=ALL_COMPLETED)
        with tempfile.TemporaryDirectory() as tmp:
            guard=bo.SpendGuard(Path(tmp)/'ledger',1.0,PRICE)
            with mock.patch.object(bo,'wait',side_effect=collected_together),mock.patch.object(bo,'SPEND_GUARD',guard),mock.patch.object(bo,'ask_batch',side_effect=ask),mock.patch.object(bo,'store_answers',side_effect=store),mock.patch.object(bo,'score',return_value=(0,0,0,{})),mock.patch.object(bo,'write_verbose'),mock.patch.object(bo,'runtime_info',return_value='synthetic'):
                with self.assertRaises(bo.UncertainRetry):
                    bo.evaluate(selection,connection,identity,args,True,None)
        self.assertEqual(sorted(entered),[0,1])
        self.assertTrue(received.is_set(),'a separate batch returned its real first outcome to the run-loop future')
        self.assertEqual(stored,[1],'UncertainRetry discarded the already received independent batch instead of draining/storing it before stopping')

if __name__=='__main__':unittest.main()

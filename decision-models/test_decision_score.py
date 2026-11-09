"""Tests of the Decision Score (AA formula) on English reading runs: export_results.decision_score and the English
page's cells. Run: python3 -m unittest test_decision_score"""

import math
import unittest

import export_results as er
from sitebuild import english_view as ev


def run(choices, correct, probabilities, number=1):
    return {"run": number, "choice": choices, "correct": correct, "probabilities": probabilities}


class DecisionScoreTests(unittest.TestCase):
    def test_sure_and_right_scores_100(self) -> None:
        found = er.decision_score(run(["A"], [1], [{"A": 1.0, "B": 0.0}]), [0])
        self.assertEqual(found["score"], 100)
        self.assertEqual((found["accuracy"], found["brier"], found["n"]), (1, 0, 1))

    def test_sure_and_wrong_scores_0(self) -> None:
        found = er.decision_score(run(["A"], [0], [{"A": 1.0, "B": 0.0}]), [0])
        self.assertEqual(found["score"], 0)
        self.assertEqual(found["brier"], 1)

    def test_half_sure_and_right_scores_87_5(self) -> None:
        found = er.decision_score(run(["A"], [1], [{"A": 0.5, "B": 0.5}]), [0])
        self.assertEqual(found["score"], 87.5)

    def test_score_is_the_identity_over_a_run(self) -> None:
        probabilities = [{"A": 0.9, "B": 0.1}, {"A": 0.3, "B": 0.7}, {"A": 0.6, "B": 0.4}, None]
        found = er.decision_score(run(["A", "B", "A", None], [1, 0, 0, None], probabilities, 7), [0, 1, 2])
        brier = (0.1 ** 2 + 0.7 ** 2 + 0.6 ** 2) / 3
        self.assertAlmostEqual(found["brier"], brier, places=12)
        self.assertAlmostEqual(found["score"], 50 * (1 + 1 / 3 - brier), places=12)
        self.assertEqual((found["n"], found["run"]), (3, 7))

    def test_missing_probability_makes_the_run_unavailable(self) -> None:
        for choices, probabilities in ((["A", "A"], [{"A": 0.9}, None]),        # no probabilities at all
                                       (["A", "B"], [{"A": 0.9}, {"A": 0.9}]),  # none for the chosen answer
                                       (["A", None], [{"A": 0.9}, {"A": 0.9}])):  # no chosen answer
            found = er.decision_score(run(choices, [1, 0], probabilities), [0, 1])
            self.assertEqual(found, {"unavailable": "1 of 2 answers without a probability for the chosen answer"})

    def test_invalid_probability_makes_the_run_unavailable(self) -> None:
        for bad in (math.nan, math.inf, -0.1, 1.5, "0.9", True):
            found = er.decision_score(run(["A", "A"], [1, 1], [{"A": 0.9}, {"A": bad}]), [0, 1])
            self.assertIn("unavailable", found, bad)
            self.assertIn("not a finite number in [0, 1]", found["unavailable"])

    def test_unasked_questions_are_not_scored(self) -> None:
        found = er.decision_score(run(["A", None], [1, None], [{"A": 1.0}, None]), [0])
        self.assertEqual(found["score"], 100)


class CellTests(unittest.TestCase):
    def test_cells(self) -> None:
        scored = {"decision_score": {"score": 93.75249, "accuracy": 0.925, "brier": 0.05, "n": 547, "run": 829}}
        self.assertTrue(ev.score_cell(scored).startswith("93.75<"))
        self.assertIn('title="2 of 547', ev.score_cell({"decision_score_unavailable": "2 of 547 answers"}))
        self.assertIn("not applicable", ev.score_cell({}))


if __name__ == "__main__":
    unittest.main()

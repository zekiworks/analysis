import unittest

import benchmark_metrics as bm


class RankingTests(unittest.TestCase):
    def test_auroc_counts_tied_scores_as_half(self) -> None:
        # Right answers at 0.9 and 0.5, wrong ones at 0.9 and 0.1: pairs score 0.5 + 1 + 0 + 1 of 4.
        scored = [(0.9, 1), (0.9, 0), (0.5, 1), (0.1, 0)]
        self.assertAlmostEqual(bm.auroc(scored), 0.625)

    def test_auroc_needs_right_and_wrong_answers(self) -> None:
        self.assertIsNone(bm.auroc([(0.9, 1), (0.4, 1)]))

    def test_coverage_splits_a_tie_by_its_accuracy(self) -> None:
        groups = bm.tie_groups([(0.9, 1), (0.9, 0), (0.5, 1), (0.5, 1)])
        self.assertAlmostEqual(bm.accuracy_at_coverage(groups, 0.25), 0.5)
        self.assertAlmostEqual(bm.accuracy_at_coverage(groups, 0.75), 2 / 3)

    def test_aurc_averages_the_error_rate_over_every_cutoff(self) -> None:
        area, curve = bm.risk_coverage(bm.tie_groups([(0.9, 1), (0.1, 0)]))
        self.assertAlmostEqual(area, 0.25)
        self.assertEqual(curve[-1], [1.0, 0.5])


class CalibrationTests(unittest.TestCase):
    def test_score_of_one_falls_in_the_top_bin(self) -> None:
        result = bm.calibration([(1.0, 1), (0.0, 0)])
        self.assertAlmostEqual(result["ece"], 0.0)
        self.assertAlmostEqual(result["brier"], 0.0)
        self.assertEqual(result["reliability"][-1]["questions"], 1)

    def test_ece_weights_each_bin_gap_by_its_answers(self) -> None:
        # Bin 0.9–1.0: three answers at 0.95, two right (gap 0.95 - 2/3); bin 0.2–0.3: one at 0.25, wrong.
        result = bm.calibration([(0.95, 1), (0.95, 1), (0.95, 0), (0.25, 0)])
        self.assertAlmostEqual(result["ece"], 0.75 * (0.95 - 2 / 3) + 0.25 * 0.25)


class PairedComparisonTests(unittest.TestCase):
    def test_exact_mcnemar_on_the_discordant_questions(self) -> None:
        result = bm.paired_comparison([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        self.assertEqual((result["first_only"], result["second_only"]), (0, 5))
        self.assertAlmostEqual(result["difference"], -0.5)
        self.assertAlmostEqual(result["p"], 0.0625)

    def test_identical_runs_differ_by_nothing(self) -> None:
        result = bm.paired_comparison([1, 0, 1], [1, 0, 1])
        self.assertEqual((result["difference"], result["low"], result["high"], result["p"]), (0.0, 0.0, 0.0, 1.0))


class RankCorrelationTests(unittest.TestCase):
    def test_tied_values_share_their_average_rank(self) -> None:
        # Ranks [1, 2.5, 2.5, 4] against [1, 3, 2, 4]: covariance 4.5, variances 4.5 and 5.
        result = bm.spearman([1, 2, 2, 3], [1, 3, 2, 4], ["unit"] * 4, shuffles=0)
        self.assertAlmostEqual(result["rho"], 4.5 / (4.5 * 5) ** 0.5)

    def test_a_correlation_that_only_separates_groups_fails_the_shuffle(self) -> None:
        # Easy unit: low uncertainty, no mistakes; hard unit: high uncertainty, all mistakes. Within each
        # unit there is nothing to rank, so every within-unit shuffle reaches the observed correlation.
        result = bm.spearman([0.1, 0.2, 0.3, 0.7, 0.8, 0.9], [0, 0, 0, 1, 1, 1], ["easy"] * 3 + ["hard"] * 3, shuffles=50)
        self.assertGreater(result["rho"], 0.8)
        self.assertEqual(result["p"], 1.0)

    def test_a_constant_sequence_has_no_correlation(self) -> None:
        self.assertEqual(bm.spearman([0.1, 0.5, 0.9], [2, 2, 2], ["unit"] * 3), {"rho": None, "p": None})


class VersionChangeTests(unittest.TestCase):
    def test_counts_changed_answers_and_mistakes_repeated_letter_for_letter(self) -> None:
        # Question 1: same wrong option twice. 2: right, then wrong. 3: wrong, then a different wrong option.
        older = {1: (0, "q1", "A"), 2: (1, "q2", "B"), 3: (0, "q3", "C")}
        newer = {1: (0, "q1", "A"), 2: (0, "q2", "C"), 3: (0, "q3", "D")}
        unchanged = bm.version_change(older, newer)["unchanged"]
        self.assertEqual(unchanged["flipped"], 1)
        self.assertEqual(unchanged["changed_answer"], 2)
        self.assertEqual((unchanged["repeated_mistakes"], unchanged["newer_wrong"]), (1, 3))


class IntervalTests(unittest.TestCase):
    def test_wilson_interval(self) -> None:
        self.assertIsNone(bm.wilson_interval(0, 0))
        low, high = bm.wilson_interval(21, 21)
        self.assertAlmostEqual(low, 21 / (21 + 1.96**2))  # all right: the lower bound is n / (n + z²)
        self.assertAlmostEqual(high, 1.0)

    def test_holm_keeps_adjusted_values_monotone(self) -> None:
        # Sorted: 0.01 × 3 = 0.03, 0.03 × 2 = 0.06, then 0.04 × 1 = 0.04 is raised to 0.06.
        self.assertEqual([round(p, 6) for p in bm.holm([0.01, 0.04, 0.03])], [0.03, 0.06, 0.06])

    def test_tied_groups_give_a_bridging_run_both_letters(self) -> None:
        # Runs 0–1 and 1–2 are tied, 0 and 2 are told apart; run 3 is told apart from all.
        apart = {(0, 2), (0, 3), (1, 3), (2, 3)}
        letters = bm.tied_groups(4, lambda i, j: (min(i, j), max(i, j)) in apart)
        self.assertEqual(letters, ["a", "ab", "b", "c"])

    def test_bootstrap_counts_ties_as_half(self) -> None:
        scored = [(0.5, index % 2) for index in range(40)]
        result = bm.bootstrap_ranking(scored, range(40), resamples=50)
        self.assertEqual(result["auroc"], [0.5, 0.5])

    def test_bootstrap_draws_a_cluster_whole(self) -> None:
        # Two tied clusters, one all right and one all wrong. Drawn whole, a resample is all right, all
        # wrong or half and half; drawn answer by answer, accuracy stays near 50%.
        scored = [(0.9, 1)] * 10 + [(0.9, 0)] * 10
        clustered = bm.bootstrap_ranking(scored, ["a"] * 10 + ["b"] * 10, resamples=200)["coverage_accuracy"]["0.50"]
        separate = bm.bootstrap_ranking(scored, range(20), resamples=200)["coverage_accuracy"]["0.50"]
        self.assertEqual(clustered, [0.0, 1.0])
        self.assertTrue(0.0 < separate[0] < 0.5 < separate[1] < 1.0)


class RepeatStabilityTests(unittest.TestCase):
    def test_separates_changed_answers_from_mistakes_every_run_repeats(self) -> None:
        # Question 1: right every time. 2: right, wrong, right. 3: the same wrong option every time.
        # 4: wrong every time, but with different options. 5: answered by only two of the runs.
        runs = [
            {1: (1, "A", 0.9), 2: (1, "B", 0.6), 3: (0, "C", 0.995), 4: (0, "D", 0.5), 5: (1, "A", 0.7)},
            {1: (1, "A", 0.9), 2: (0, "C", 0.4), 3: (0, "C", 0.991), 4: (0, "E", 0.5), 5: (1, "A", 0.7)},
            {1: (1, "A", 0.9), 2: (1, "B", 0.7), 3: (0, "C", 0.999), 4: (0, "D", 0.5)},
        ]
        result = bm.repeat_stability(runs)
        self.assertEqual(result["questions"], 4)
        self.assertEqual(result["changed_answer"], 2)
        self.assertEqual((result["wrong_every_run_same"], result["wrong_any"]), (1, 3))
        self.assertEqual(result["sure_wrong"], [1, 1, 1])
        self.assertEqual(result["sure_wrong_every_run"], 1)
        self.assertEqual(result["score_identical"], 2)


class CascadeTests(unittest.TestCase):
    def test_stops_above_the_first_level_that_loses_accuracy_for_good(self) -> None:
        # The decision model misses the 0.8 question the frontier run gets right, and never makes it up.
        result = bm.cascade([0.9, 0.8, 0.7, 0.6], [1, 0, 1, 1], [1, 1, 1, 1], splits=10)
        self.assertEqual(result["in_sample"]["threshold"], 0.9)
        self.assertAlmostEqual(result["in_sample"]["answered"], 0.25)
        self.assertAlmostEqual(result["in_sample"]["accuracy"], 1.0)

    def test_a_loss_made_up_further_down_still_counts(self) -> None:
        result = bm.cascade([0.9, 0.8, 0.7, 0.6], [1, 1, 0, 1], [1, 0, 1, 1], splits=10)
        self.assertEqual(result["in_sample"]["threshold"], 0.6)
        self.assertAlmostEqual(result["in_sample"]["answered"], 1.0)
        self.assertAlmostEqual(result["in_sample"]["accuracy"], 0.75)

    def test_tied_scores_are_answered_together(self) -> None:
        # Taking the 0.9 tie costs a question; only the 0.5 question wins it back.
        result = bm.cascade([0.9, 0.9, 0.5], [1, 0, 1], [1, 1, 0], splits=10)
        self.assertEqual(result["in_sample"]["threshold"], 0.5)
        self.assertEqual(result["curve"][1], [round(2 / 3, 4), round(1 / 3, 4)])

    def test_no_threshold_when_the_decision_model_is_always_worse(self) -> None:
        result = bm.cascade([0.9, 0.5], [0, 0], [1, 1], splits=10)
        self.assertIsNone(result["in_sample"]["threshold"])
        self.assertEqual(result["in_sample"]["answered"], 0.0)
        self.assertEqual(result["held_out"]["answered"], 0.0)


if __name__ == "__main__":
    unittest.main()

import copy
import json
import math
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmark_ollama import (
    PRICES,
    Option,
    Question,
    answer_problems,
    answer_usage,
    harness_commit,
    letter_probabilities,
    option_probabilities,
    parse_ollama_content,
    probability_problems,
    regrade,
    replace_key_text,
    run_requests,
    shuffle_options,
)


class RegradeTests(unittest.TestCase):
    ANSWER = {"question_id": 7, "expected_answer": "A", "predicted_answer": "C", "correct": 0, "status": None}

    def test_a_question_excluded_since_the_run_drops_out(self) -> None:
        now = {"key": "A", "status": "excluded"}
        self.assertIsNone(regrade(self.ANSWER, now))
        self.assertEqual(regrade(self.ANSWER, now, keep_excluded=True)["status"], "excluded")

    def test_a_corrected_key_regrades_the_answer(self) -> None:
        graded = regrade(self.ANSWER, {"key": "C", "status": "verified"})
        self.assertEqual((graded["expected_answer"], graded["correct"], graded["status"]), ("C", 1, "verified"))

    def test_an_unchanged_question_keeps_its_grade(self) -> None:
        self.assertEqual(regrade(self.ANSWER, {"key": "A", "status": None}), self.ANSWER)


class ParseOllamaContentTests(unittest.TestCase):
    def test_accepts_valid_json(self) -> None:
        self.assertEqual(
            parse_ollama_content('{"answers": {"1": "B"}}'),
            {"answers": {"1": "B"}},
        )

    def test_accepts_ollama_eot_suffix(self) -> None:
        self.assertEqual(
            parse_ollama_content('  {"answers": {"1": "B"}} <|eot|>\n'),
            {"answers": {"1": "B"}},
        )

    def test_rejects_unrecognized_trailing_content(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            parse_ollama_content('{"answers": {"1": "B"}} explanation')


def token(text: str, logprob: float, alternatives: list[tuple[str, float]] | None = None) -> dict:
    top = [{"token": other, "logprob": value} for other, value in (alternatives or [(text, logprob)])]
    return {"token": text, "logprob": logprob, "top_logprobs": top}


def question(question_id: int, labels: str = "ABCDE") -> Question:
    options = tuple(Option(label, label.lower()) for label in labels)
    return Question(question_id, "1. Unit", "1", "Unit", "", "", "", "1", "prompt", options, labels[0], 1, False, None)


class LetterProbabilitiesTests(unittest.TestCase):
    def test_reads_each_answer_letter_after_the_thinking(self) -> None:
        # The thinking also writes "1": "C"; only the reply, the end of the tokens, counts.
        tokens = [
            token('thinking "1": "', -0.1), token("C", -0.2), token('" done', -0.1),
            token('{"answers": {"1": "', 0.0),
            token("B", math.log(0.6), [("B", math.log(0.6)), ("D", math.log(0.2)), ("A", math.log(0.1)), (" B", -1.0)]),
            token('", "2": "', 0.0),
            # The letter can share its token with the quote; an alternative counts only if it differs in the letter.
            token('E"', math.log(0.5), [('E"', math.log(0.5)), ('C"', math.log(0.25)), ("C", math.log(0.2))]),
            token("}}", 0.0),
        ]
        reply = '{"answers": {"1": "B", "2": "E"}}'
        found = letter_probabilities({"choices": [{"logprobs": {"content": tokens}}]}, reply, [question(1), question(2, "CE")])
        self.assertAlmostEqual(found[1]["B"], 0.6 / 0.9)
        self.assertAlmostEqual(found[1]["D"], 0.2 / 0.9)
        self.assertEqual(found[1]["C"], 0.0)
        self.assertEqual(found[2], {"C": 1 / 3, "E": 2 / 3})

    def test_a_reply_missing_from_the_tokens_gives_nothing(self) -> None:
        result = {"choices": [{"logprobs": {"content": [token("x", 0.0)]}}]}
        self.assertEqual(letter_probabilities(result, '{"answers": {"1": "A"}}', [question(1)]), {})


class OpenAIDecisionsTests(unittest.TestCase):
    @staticmethod
    def stored(answers: list[dict]) -> str:
        return json.dumps({"request_id": None, "response": {"answers": answers, "usage": {"input_tokens": 120, "output_tokens": 0}}})

    def test_score_is_the_chosen_options_listed_probability(self) -> None:
        # The API lists probabilities as {value, probability}; its own confidence field is not the score.
        raw = self.stored(
            [
                {"type": "predicate", "name": "other", "probability": 0.9},
                {
                    "type": "choice",
                    "name": "answer",
                    "choice": "B",
                    "probabilities": [{"value": "A", "probability": 0.25}, {"value": "B", "probability": 0.75}],
                    "confidence": 0.5,
                },
            ]
        )
        self.assertEqual(answer_usage("openai-decisions", 1, raw), ({"input_tokens": 120, "output_tokens": 0}, 0.75))
        self.assertEqual(option_probabilities("openai-decisions", raw), {"A": 0.25, "B": 0.75})

    def test_a_refusal_has_no_score(self) -> None:
        raw = self.stored([{"type": "refusal", "name": "answer"}])
        self.assertIsNone(answer_usage("openai-decisions", 1, raw)[1])
        self.assertIsNone(option_probabilities("openai-decisions", raw))


class StatedConfidenceTests(unittest.TestCase):
    def test_vllm_stated_reads_each_questions_confidence_and_the_requests_tokens(self) -> None:
        # ask_vllm_stated stores the chat API's response with the answers read from it, keyed by question ID.
        raw = json.dumps(
            {
                "answers": {"7": {"answer": "B", "confidence": 0.85}, "8": {"answer": None, "confidence": None}},
                "response": {"usage": {"prompt_tokens": 4161, "completion_tokens": 298}},
            }
        )
        self.assertEqual(answer_usage("vllm-stated", 7, raw), ({"input_tokens": 4161, "output_tokens": 298}, 0.85))
        self.assertIsNone(answer_usage("vllm-stated", 8, raw)[1])
        self.assertIsNone(option_probabilities("vllm-stated", raw, 7))


class ClaudeCostTests(unittest.TestCase):
    def test_cache_reads_and_writes_cost_their_own_rates(self) -> None:
        # One Sonnet 5.5 request as Claude Code reported it: 2 uncached prompt tokens, 6,759 written to the 1-hour
        # cache, 2,181 read from the cache and 2,362 output tokens.
        usage = {
            "input_tokens": 2,
            "cache_creation_input_tokens": 6759,
            "cache_read_input_tokens": 2181,
            "cache_creation": {"ephemeral_1h_input_tokens": 6759, "ephemeral_5m_input_tokens": 0},
            "output_tokens": 2362,
        }
        raw = json.dumps({"answers": {"1": {"confidence": 0.9}}, "output": {"usage": usage}})
        tokens, score = answer_usage("claude", 1, raw)
        self.assertEqual(
            tokens,
            {
                "input_tokens": 8942,
                "output_tokens": 2362,
                "cached_input_tokens": 2181,
                "cache_write_input_tokens": 0,
                "cache_write_1h_input_tokens": 6759,
            },
        )
        self.assertEqual(score, 0.9)
        # $2 per 1M uncached input, $4 per 1M 1-hour cache writes, $0.10 per 1M cache reads, $10 per 1M output.
        expected = (2 * 2.00 + 6759 * 4.00 + 2181 * 0.10 + 2362 * 10.00) / 1_000_000
        self.assertTrue(math.isclose(PRICES["claude", "claude-sonnet-5-5"].cost(tokens), expected, rel_tol=1e-12))


class MakerPriceTests(unittest.TestCase):
    def test_perplexity_bills_three_input_tokens_per_request_beyond_our_count(self) -> None:
        # Our server counted 846,752 input tokens over Decider v1.2's 2,198 requests (run 217); Perplexity's API billed
        # 853,346 for Decider v1.1 on the same questions (run 145), 3 more per request.
        price = PRICES["pplx-decider", "pplx-decider-v1.2"]
        self.assertTrue(math.isclose(price.cost({"input_tokens": 846_752}, requests=2198), 853_346 * 0.02 / 1_000_000, rel_tol=1e-12))


class ShuffleOptionsTests(unittest.TestCase):
    def test_maps_every_shown_letter_back_to_the_same_option(self) -> None:
        original = tuple(Option(label, f"option {label}") for label in "ABCDE")
        texts = {option.label: option.text for option in original}
        for question_id in range(20):
            shown, answer, original_labels = shuffle_options(original, "C", 1, question_id)
            question = Question(
                question_id, "1. Unit", "1", "Unit", "", "", "", "1", "prompt", shown, answer, 1, False, None,
                original_labels=original_labels,
            )
            self.assertEqual([option.label for option in shown], list("ABCDE"))
            for option in shown:
                self.assertEqual(texts[question.original_label(option.label)], option.text)
            self.assertEqual(question.original_label(question.answer), "C")

    def test_unshuffled_letters_stay_the_same(self) -> None:
        options = (Option("A", "a"), Option("B", "b"))
        question = Question(1, "1. Unit", "1", "Unit", "", "", "", "1", "prompt", options, "B", 1, False, None)
        self.assertEqual(question.original_label("B"), "B")
        self.assertIsNone(question.original_label(None))


class ReplaceKeyTextTests(unittest.TestCase):
    def test_only_the_key_changes_and_it_copies_a_wrong_option(self) -> None:
        original = tuple(Option(label, f"option {label}") for label in "ABCDE")
        twins = set()
        for question_id in range(40):
            shown, twin = replace_key_text(original, "C", 1, question_id)
            twins.add(twin)
            self.assertNotEqual(twin, "C")
            self.assertEqual(shown[2], Option("C", f"option {twin}"))
            self.assertEqual([o for o in shown if o.label != "C"], [o for o in original if o.label != "C"])
            self.assertEqual(replace_key_text(original, "C", 1, question_id), (shown, twin))
        self.assertEqual(twins, {"A", "B", "D", "E"})


class RunRequestsTests(unittest.TestCase):
    SAME = '{"request_id":null,"response":{"answers":{"answer":{"choice":"B"}},"usage":{"input_tokens":300}}}'

    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("CREATE TABLE answers (run_id INTEGER, question_id INTEGER, raw_response TEXT, request_seconds REAL)")
        self.connection.executemany(
            "INSERT INTO answers VALUES (?, ?, ?, ?)",
            [(1, 10, self.SAME, 0.4), (1, 11, self.SAME, 0.5), (2, 10, '{"batch":1}', 3.0), (2, 11, '{"batch":1}', 3.0)],
        )

    def test_one_question_per_request_counts_matching_responses_apart(self) -> None:
        self.assertEqual([row["request_seconds"] for row in run_requests(self.connection, 1, 1)], [0.4, 0.5])

    def test_a_batch_counts_its_shared_response_once(self) -> None:
        self.assertEqual([row["request_seconds"] for row in run_requests(self.connection, 2, 16)], [3.0])


class ProbabilityAcceptanceTests(unittest.TestCase):
    LABELS = ["A", "B", "C", "D", "E"]
    # A real answer of the Drex Max server: full-precision floats, normalized by Nace's own answer().
    FULL = {"A": 0.757489677011093, "B": 0.11097449002242932, "C": 0.0184028836801487, "D": 0.049592580369156335,
            "E": 0.06354036891717257}
    OPTIONS = json.dumps([{"label": label, "text": f"option {label}"} for label in LABELS])

    def stored(self, answer: dict) -> str:
        return json.dumps({"request_id": "r1", "response": {"model": "drex-max-v1.1", "answers": {"answer": answer}}})

    def test_full_precision_probabilities_that_sum_to_one_pass(self) -> None:
        self.assertEqual(probability_problems(self.FULL, self.LABELS), [])

    def test_the_sum_must_equal_one_to_seven_decimal_places_as_nace_tests_it(self) -> None:
        self.assertEqual(probability_problems({"A": 0.5, "B": 0.50000004}, ["A", "B"]), [])
        self.assertRegex(probability_problems({"A": 0.5, "B": 0.5000001}, ["A", "B"])[0], "not 1 to 7 decimal places")
        # Values rounded to four places that miss 1 fail too: rounding is not a reason to pass.
        self.assertRegex(
            probability_problems({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.1999}, self.LABELS)[0], r"sum to 0\.9999"
        )

    def test_a_map_that_does_not_sum_to_one_fails(self) -> None:
        self.assertRegex(probability_problems({"A": 0.62, "B": 0.48}, ["A", "B"])[0], "sum to 1.1")
        doubled = {label: 2 * value for label, value in self.FULL.items() if label != "A"} | {"A": 0.0}
        self.assertEqual(len(probability_problems(doubled, self.LABELS)), 1)

    def test_missing_and_unoffered_options_fail(self) -> None:
        self.assertEqual(probability_problems({"A": 0.5, "B": 0.5}, self.LABELS), ["no probability for C, D, E"])
        self.assertEqual(
            probability_problems({"A": 0.5, "B": 0.25, "F": 0.25}, ["A", "B"]), ["a probability for options not offered: F"]
        )

    def test_values_that_are_not_finite_numbers_from_zero_to_one_fail(self) -> None:
        for value in (math.nan, math.inf, -0.1, 1.5, "0.5", True, None):
            with self.subTest(value=value):
                problems = probability_problems({"A": value, "B": 1.0}, ["A", "B"])
                self.assertEqual(problems, [f"an invalid probability for A: {value!r}"])

    def test_the_values_are_checked_as_reported_never_normalized(self) -> None:
        unnormalized = {"A": 0.5, "B": 0.25, "C": 0.125, "D": 0.0625, "E": 0.03125}
        kept = copy.deepcopy(unnormalized)
        self.assertEqual(len(probability_problems(unnormalized, self.LABELS)), 1)
        self.assertEqual(unnormalized, kept)

    def test_a_valid_choice_alone_is_not_a_pass(self) -> None:
        good = {"type": "choice", "choice": "A", "probabilities": self.FULL}
        self.assertEqual(answer_problems("nace", self.OPTIONS, self.stored(good)), [])
        self.assertEqual(answer_problems("nace", self.OPTIONS, self.stored({"type": "choice", "choice": "A"})),
                         ["no probability map"])
        self.assertEqual(
            answer_problems("nace", self.OPTIONS, self.stored({"choice": "A", "probabilities": {"A": 1.0}})),
            ["no probability for B, C, D, E"],
        )

    def test_a_missing_or_unoffered_choice_fails_even_with_good_probabilities(self) -> None:
        for choice in (None, "F"):
            with self.subTest(choice=choice):
                stored = self.stored({"choice": choice, "probabilities": self.FULL})
                self.assertEqual(answer_problems("nace", self.OPTIONS, stored), [f"no valid choice ({choice!r})"])
        self.assertEqual(answer_problems("nace", self.OPTIONS, None), ["no stored response"])


def git(cwd: Path, *arguments: str) -> str:
    """A git command in `cwd` with a fixed identity and no signing, independent of the user's configuration."""
    completed = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
         "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null", *arguments],
        cwd=cwd, check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


class HarnessCommitTests(unittest.TestCase):
    """A run's runner must be published: pushed, so that a remote-tracking branch holds the commit, on every path."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        git(self.root, "init", "--bare", "remote.git")
        git(self.root, "clone", "remote.git", "work")
        self.work = self.root / "work"
        self.runner = self.work / "decision-models" / "runner" / "benchmark_ollama.py"
        self.runner.parent.mkdir(parents=True)
        self.runner.write_text("print('runner')\n")
        git(self.work, "add", ".")
        git(self.work, "commit", "-m", "runner")
        self.head = git(self.work, "rev-parse", "HEAD")
        self.outside = self.root / "outside" / "benchmark_ollama.py"  # a copy outside any checkout
        self.outside.parent.mkdir()
        self.outside.write_bytes(self.runner.read_bytes())

    def test_an_unpushed_checkout_is_refused_and_a_pushed_one_gives_its_head(self) -> None:
        with mock.patch.dict(os.environ, {"HARNESS_REPO": ""}):
            with self.assertRaisesRegex(ValueError, f"commit {self.head[:12]} .* is not pushed"):
                harness_commit(self.runner)
            git(self.work, "push", "origin", "HEAD:main")
            self.assertEqual(harness_commit(self.runner), self.head)

    def test_a_copy_outside_git_needs_a_pushed_commit_in_harness_repo(self) -> None:
        with mock.patch.dict(os.environ, {"HARNESS_REPO": str(self.work)}):
            with self.assertRaisesRegex(ValueError, "is not pushed"):
                harness_commit(self.outside)
            git(self.work, "push", "origin", "HEAD:main")
            self.assertEqual(harness_commit(self.outside), self.head)

    def test_a_changed_copy_has_no_published_commit(self) -> None:
        git(self.work, "push", "origin", "HEAD:main")
        self.outside.write_text("print('changed')\n")
        with mock.patch.dict(os.environ, {"HARNESS_REPO": str(self.work)}):
            with self.assertRaisesRegex(ValueError, "no published commit holds"):
                harness_commit(self.outside)



if __name__ == "__main__":
    unittest.main()

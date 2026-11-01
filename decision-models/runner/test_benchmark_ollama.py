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
    DONT_KNOW_OPTION,
    PRICES,
    Option,
    Question,
    answer_problems,
    answer_usage,
    derived_abstention,
    harness_commit,
    in_main_tables,
    letter_probabilities,
    load_questions,
    mark_run,
    open_result_database,
    option_probabilities,
    parse_args,
    parse_ollama_content,
    probability_problems,
    regrade,
    replace_key_text,
    run_metrics,
    run_repeats,
    run_requests,
    shuffle_options,
    start_run,
    store_answers,
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


class DontKnowTests(unittest.TestCase):
    """The "I don't know" variant: one more option the key never names, kept out of the main tables."""

    def bank(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        path = root / "bank.sqlite"
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE q (question_id INTEGER, unit_number TEXT, unit_title TEXT, section_title TEXT, test_type TEXT, "
            "test_number TEXT, question_number TEXT, question TEXT, choices_json TEXT, answer TEXT, complete INTEGER, "
            "status TEXT, source_page_start INTEGER, passage_text TEXT, passage_description TEXT, passage_markdown TEXT, "
            "visuals_json TEXT)"
        )
        connection.execute("CREATE TABLE questions (id INTEGER, printed_number TEXT, passage_id INTEGER, answer TEXT)")
        for question_id, answer in ((1, "B"), (2, "E"), (3, "C")):
            connection.execute("INSERT INTO questions VALUES (?, ?, NULL, ?)", (question_id, str(question_id), answer))
            choices = json.dumps([{"label": label, "text": f"option {label}"} for label in "ABCDE"])
            connection.execute(
                "INSERT INTO q VALUES (?, '1', 'Unit', '', '', '', ?, ?, ?, ?, 1, NULL, 1, NULL, NULL, NULL, '[]')",
                (question_id, str(question_id), f"Question {question_id}?", choices, answer),
            )
        connection.execute("CREATE VIEW benchmark_questions AS SELECT * FROM q")
        connection.commit()
        connection.close()
        return path

    def test_every_question_ends_with_the_option_and_keeps_its_key(self) -> None:
        path = self.bank()
        plain = load_questions(path, None, None, None, 0).questions
        variant = load_questions(path, None, None, None, 0, dont_know=True).questions
        for before, after in zip(plain, variant, strict=True):
            self.assertEqual(after.options, (*before.options, Option("F", DONT_KNOW_OPTION)))
            self.assertEqual(after.answer, before.answer)
            self.assertTrue(after.prompt.endswith(f"E. option E\nF. {DONT_KNOW_OPTION}"))

    @staticmethod
    def spread(choice: str, p: float, labels: str) -> dict[str, float]:
        rest = (1 - p) / (len(labels) - 1)
        return {label: p if label == choice else rest for label in labels}

    @staticmethod
    def store_run(connection: sqlite3.Connection, path: Path, dont_know: bool,
                  answers: dict[int, tuple[str, dict[str, float]]], repeat: int | None = None) -> dict:
        """A completed run of model "m" through subq with these answers, as its report record."""
        selection = load_questions(path, None, None, None, 0, dont_know=dont_know)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "subq", "http://localhost", 0, 1, False, None, False,
                                 None, None, dont_know, repeat, False)
        for ordinal, question in enumerate(selection.questions):
            choice, probabilities = answers[question.question_id]
            raw = json.dumps({"request_id": None, "response": {
                "answers": {"answer": {"choice": choice, "probabilities": probabilities}}, "usage": {"input_tokens": 10}}})
            store_answers(connection, identity.run_id, [(ordinal, question)], [choice], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        return {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path), "provider": "subq", "model": "m",
                "thinking": "off", "batch_size": 1, "evaluated": 3, "eligible_total": 3,
                "selection_sha256": identity.selection_sha256, "repeat": repeat, "dont_know": dont_know or None}

    def test_the_report_counts_its_answers_and_derives_them_from_the_first_run_without_it(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        spread = self.spread
        # The keys are B, E and C. Without the option: right at 0.6, wrong at 0.9, right at 0.8.
        self.store_run(connection, path, False, {1: ("B", spread("B", 0.6, "ABCDE")), 2: ("A", spread("A", 0.9, "ABCDE")),
                                                 3: ("C", spread("C", 0.8, "ABCDE"))})
        with_option = self.store_run(connection, path, True, {1: ("F", spread("F", 0.7, "ABCDEF")),
                                                              2: ("A", spread("A", 0.5, "ABCDEF")),
                                                              3: ("C", spread("C", 0.75, "ABCDEF"))})
        data = run_metrics(connection, with_option["run_key"], path.parent)["dont_know_answers"]
        self.assertEqual((data["right"], data["wrong"], data["dont_know"], data["invalid"]), (1, 1, 1, 0))
        self.assertEqual((data["attempt_rate"], data["non_hallucination"]), (2 / 3, 1 / 2))
        self.assertAlmostEqual(data["mean_option_probability"], (0.7 + 0.1 + 0.05) / 3)
        # Two attempts in three without the option: the cut-off 0.8 keeps the wrong 0.9 and the right 0.8.
        derived = data["derived"]
        self.assertEqual((derived["cut_off"], derived["right"], derived["wrong"], derived["abstained"]), (0.8, 1, 1, 1))

    def test_its_repeats_never_join_the_repeats_of_the_main_runs(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        plain = {1: ("B", self.spread("B", 0.6, "ABCDE")), 2: ("A", self.spread("A", 0.9, "ABCDE")),
                 3: ("C", self.spread("C", 0.8, "ABCDE"))}
        variant = {1: ("F", self.spread("F", 0.7, "ABCDEF")), 2: ("A", self.spread("A", 0.5, "ABCDEF")),
                   3: ("C", self.spread("C", 0.75, "ABCDEF"))}
        records = [self.store_run(connection, path, False, plain), self.store_run(connection, path, False, plain, 2),
                   self.store_run(connection, path, True, variant), self.store_run(connection, path, True, variant, 2)]
        sets = run_repeats(connection, {record["run_key"]: record for record in records}, path.parent)
        self.assertEqual(sorted(item["run_keys"] for item in sets),
                         sorted([[records[0]["run_key"], records[1]["run_key"]], [records[2]["run_key"], records[3]["run_key"]]]))
        # Each set compares all three questions: none is asked differently inside a set.
        self.assertEqual([item["questions"] for item in sets], [3, 3])

    def test_the_cut_off_meets_the_attempt_rate_and_the_higher_one_wins_a_tie(self) -> None:
        answers = [(0.9, 1), (0.8, 0), (0.7, 1), (0.6, 0)]
        half = derived_abstention(answers, 0.5)
        self.assertEqual((half["cut_off"], half["right"], half["wrong"], half["abstained"]), (0.8, 1, 1, 2))
        self.assertEqual(half["non_hallucination"], 2 / 3)
        # 3/8 lies as far from one attempt in four as from two: the higher cut-off, fewer attempts, wins.
        self.assertEqual(derived_abstention(answers, 0.375)["cut_off"], 0.9)
        none = derived_abstention(answers, 0.0)
        self.assertEqual((none["cut_off"], none["abstained"], none["non_hallucination"]), (None, 4, 1.0))

    def test_a_cut_off_admits_every_answer_with_its_score_and_never_an_unscored_one(self) -> None:
        answers = [(0.9, 1), (0.9, 0), (0.5, 1), (None, 1)]
        one = derived_abstention(answers, 0.4)
        self.assertEqual((one["cut_off"], one["right"], one["wrong"]), (0.9, 1, 1))
        everything = derived_abstention(answers, 1.0)
        self.assertEqual((everything["cut_off"], everything["abstained"], everything["attempt_rate"]), (0.5, 1, 0.75))

    def test_its_runs_stay_out_of_the_main_tables(self) -> None:
        run = {"replace_key_text": None, "repeat": None, "evaluated": 2198, "eligible_total": 2198}
        self.assertTrue(in_main_tables(run))
        self.assertFalse(in_main_tables({**run, "dont_know": True}))

    def test_only_system_one_providers_take_it(self) -> None:
        with mock.patch("sys.argv", ["benchmark_ollama.py", "llama3", "--provider", "ollama", "--dont-know"]), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args()
        with mock.patch("sys.argv", ["benchmark_ollama.py", "subq-snap-1.1", "--provider", "subq", "--dont-know"]):
            self.assertTrue(parse_args().dont_know)


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
        # Values rounded to four places that miss 1 fail too, unless the model is listed as rounding (next test).
        self.assertRegex(
            probability_problems({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.1999}, self.LABELS)[0], r"sum to 0\.9999"
        )

    def test_a_model_listed_as_rounding_may_miss_one_by_its_rounding_only(self) -> None:
        # Drex 2.0 reports four decimal places: five values may miss 1 by up to 5 × 0.00005 together, and no more.
        within = {"A": 0.2001, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2001}
        self.assertEqual(probability_problems(within, self.LABELS, rounded_to=4), [])
        self.assertRegex(probability_problems(within, self.LABELS)[0], "not 1 to 7 decimal places")
        beyond = {"A": 0.2002, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2001}
        self.assertRegex(probability_problems(beyond, self.LABELS, rounded_to=4)[0], "within the rounding of 5 values to 4")
        # A value reported with more places than the model rounds to gets the strict test.
        finer = {"A": 0.20001, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2}
        self.assertRegex(probability_problems(finer, self.LABELS, rounded_to=4)[0], "not 1 to 7 decimal places")

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

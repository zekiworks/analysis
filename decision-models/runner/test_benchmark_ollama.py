import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmark_ollama import (
    DONT_KNOW_OPTION,
    DONT_KNOW_PROMPT_VERSION,
    DONT_KNOW_PROMPTS,
    DONT_KNOW_WORD_INSTRUCTIONS,
    DONT_KNOW_WORD_OPTION,
    DONT_KNOW_WORD_PROMPT_VERSION,
    DONT_KNOW_WORD_PROMPTS,
    ENGLISH_DONT_KNOW_INSTRUCTIONS,
    ENGLISH_DONT_KNOW_OPTION,
    ENGLISH_DONT_KNOW_PROMPT_VERSION,
    ENGLISH_DONT_KNOW_PROMPTS,
    ENGLISH_INSTRUCTIONS,
    ENGLISH_PROMPT_VERSION,
    ENGLISH_PROMPTS,
    JEV_INSTRUCTIONS,
    PROMPT_VERSION,
    PRICES,
    Option,
    Question,
    answer_problems,
    answer_usage,
    ask_batch,
    derived_abstention,
    dont_know_lines,
    english_lines,
    english_selection,
    export_answers,
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
    run_label,
    run_metrics,
    run_repeats,
    run_batching,
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
        plain = self.store_run(connection, path, False, {1: ("B", spread("B", 0.6, "ABCDE")),
                                                         2: ("A", spread("A", 0.9, "ABCDE")), 3: ("C", spread("C", 0.8, "ABCDE"))})
        with_option = self.store_run(connection, path, True, {1: ("F", spread("F", 0.7, "ABCDEF")),
                                                              2: ("A", spread("A", 0.5, "ABCDEF")),
                                                              3: ("C", spread("C", 0.75, "ABCDEF"))})
        # The record's flag comes from the run, so a refreshed record keeps the run out of the main tables.
        self.assertNotIn("dont_know", run_metrics(connection, plain["run_key"], path.parent))
        metrics = run_metrics(connection, with_option["run_key"], path.parent)
        self.assertIs(metrics["dont_know"], True)
        data = metrics["dont_know_answers"]
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


class EnglishTests(unittest.TestCase):
    """English reading: the kept questions in English translation, with English instructions, kept out of the main tables."""

    bank = DontKnowTests.bank

    def translations(self, root: Path, records: list[dict]) -> Path:
        path = root / "translations.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    @staticmethod
    def record(question_id: int, labels: str = "ABCDE", **overrides: str) -> dict:
        options = {label: overrides.get(label, f"English {label}") for label in labels}
        return {"question_id": question_id, "turkish": "ignored",
                "english": {"body": overrides.get("body", f"English question {question_id}?"), "options": options}}

    def test_the_questions_get_the_english_prompt_and_options_under_the_bank_letters(self) -> None:
        path = self.bank()
        selection = load_questions(path, None, None, None, 0, question_ids=frozenset({1, 3}))
        english = english_selection(selection, self.translations(path.parent, [self.record(1), self.record(2), self.record(3)]))
        self.assertEqual([question.question_id for question in english.questions], [1, 3])
        for before, after in zip(selection.questions, english.questions, strict=True):
            self.assertEqual(after.options, tuple(Option(label, f"English {label}") for label in "ABCDE"))
            self.assertEqual(after.answer, before.answer)
            self.assertEqual(
                after.prompt,
                f"English question {after.question_id}?\n\nOptions:\nA. English A\nB. English B\nC. English C\n"
                "D. English D\nE. English E",
            )
        self.assertEqual(english.eligible_total, selection.eligible_total)

    def test_other_letters_a_missing_translation_or_an_empty_text_stop_the_run(self) -> None:
        path = self.bank()
        selection = load_questions(path, None, None, None, 0, question_ids=frozenset({1, 2}))
        for records in ([self.record(1), self.record(2, "ABCD")], [self.record(1), self.record(2, "ABCDF")],
                        [self.record(1)], [self.record(1), self.record(2, C=" ")], [self.record(1), self.record(2, body="")],
                        [self.record(1), self.record(1), self.record(2)]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                english_selection(selection, self.translations(path.parent, records))

    def test_its_prompts_have_their_own_version_and_name_english(self) -> None:
        self.assertEqual(ENGLISH_INSTRUCTIONS, "Which option is the correct answer to this English multiple-choice question?")
        self.assertEqual(ENGLISH_INSTRUCTIONS, JEV_INSTRUCTIONS.replace("Turkish", "English"))
        self.assertEqual(len({ENGLISH_PROMPT_VERSION, PROMPT_VERSION, DONT_KNOW_PROMPT_VERSION}), 3)

    def test_the_decision_models_get_the_english_instructions(self) -> None:
        question_ = question(1)
        sent = []

        def post(endpoint, payload, *rest):
            sent.append(payload)
            if endpoint.endswith("/tokenize"):
                raise RuntimeError("stop")
            return {"answers": {"answer": {"choice": "A"}}}, {}

        common = {"model": "m", "timeout": 1, "dont_know": False, "dont_know_word": "turkish", "english": Path("t.jsonl")}
        with mock.patch("benchmark_ollama.post_json", side_effect=post):
            args = argparse.Namespace(provider="subq", jev_url="http://localhost", jev_api_key=None, **common)
            self.assertEqual(ask_batch(args, [question_], False, None)[0], ["A"])
            self.assertEqual(sent[-1]["questions"]["answer"]["instructions"], ENGLISH_INSTRUCTIONS)
            self.assertEqual(sent[-1]["state"], question_.prompt)
            args = argparse.Namespace(provider="vllm-yes-no", vllm_url="http://localhost", yes_no_ids=(1, 2), **common)
            with self.assertRaises(RuntimeError):
                ask_batch(args, [question_], False, None)
            self.assertIn(f"Question: {ENGLISH_INSTRUCTIONS}\n", sent[-1]["messages"][0]["content"])
            # Without --english the Turkish instructions stay.
            args = argparse.Namespace(provider="subq", jev_url="http://localhost", jev_api_key=None, **{**common, "english": None})
            ask_batch(args, [question_], False, None)
            self.assertEqual(sent[-1]["questions"]["answer"]["instructions"], JEV_INSTRUCTIONS)

    def test_its_run_records_its_facts_and_stays_out_of_the_main_tables_and_repeats(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        translations = self.translations(path.parent, [self.record(1), self.record(2), self.record(3)])
        selection = english_selection(load_questions(path, None, None, None, 0), translations)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "subq", "http://localhost", 0, 1, False, None, False,
                                 None, None, False, None, False, english="ab" * 32)
        row = connection.execute("SELECT prompt_version, english FROM runs WHERE id=?", (identity.run_id,)).fetchone()
        self.assertEqual((row["prompt_version"], row["english"]), (ENGLISH_PROMPT_VERSION, "ab" * 32))
        for ordinal, question_ in enumerate(selection.questions):
            raw = json.dumps({"request_id": None, "response": {"answers": {"answer": {"choice": "B"}}, "usage": {"input_tokens": 10}}})
            store_answers(connection, identity.run_id, [(ordinal, question_)], ["B"], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        metrics = run_metrics(connection, identity.run_key, path.parent)
        self.assertEqual(metrics["english"], {"translations_sha256": "ab" * 32, "questions": 3, "prompt_version": ENGLISH_PROMPT_VERSION})
        record = {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path), "provider": "subq", "model": "m",
                  "thinking": "off", "batch_size": 1, "evaluated": 3, "eligible_total": 3, "replace_key_text": None,
                  "repeat": None, "selection_sha256": identity.selection_sha256, "english": metrics["english"]}
        self.assertTrue(in_main_tables({**record, "english": None}))
        self.assertFalse(in_main_tables(record))
        self.assertEqual(run_repeats(connection, {identity.run_key: record, "other": {**record, "run_key": "other"}}, path.parent), [])
        # A repeat is a run of its own, with its number in its identity, and stays out as well.
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            repeat = start_run(connection, selection, "m", path, "subq", "http://localhost", 0, 1, False, None, False,
                               None, None, False, 2, False, english="ab" * 32)
        self.assertNotEqual(repeat.run_key, identity.run_key)
        row = connection.execute("SELECT repeat, prompt_version, english FROM runs WHERE id=?", (repeat.run_id,)).fetchone()
        self.assertEqual(tuple(row), (2, ENGLISH_PROMPT_VERSION, "ab" * 32))
        repeated = {**record, "run_key": repeat.run_key, "run_id": repeat.run_id, "repeat": 2}
        self.assertFalse(in_main_tables(repeated))
        self.assertEqual(run_repeats(connection, {identity.run_key: record, repeat.run_key: repeated}, path.parent), [])
        # Its report lines form a section of their own.
        lines = english_lines([{**record, "correct": 1, "invalid": 0}])
        self.assertIn("## English reading", lines)
        self.assertEqual(lines[-1], f"| subq m, in English, run {identity.run_id} | 3 | 1 | 0 | 33.33% | abababababab | "
                                    f"{ENGLISH_PROMPT_VERSION} |")

    def test_only_decision_models_on_listed_questions_take_it_and_never_with_another_variant(self) -> None:
        base = ["benchmark_ollama.py", "subq-snap-1.1", "--english", "t.jsonl", "--questions", "kept.txt"]
        for argv in ([*base[:2], "--provider", "ollama", *base[2:]], [*base, "--provider", "subq", "--replace-key-text", "1"],
                     [*base, "--provider", "subq", "--shuffle-options", "1"], [*base[:4], "--provider", "subq"],
                     [*base, "--provider", "vllm"], [*base, "--provider", "vllm-yes-no", "--dont-know"]):
            with self.subTest(argv=argv), mock.patch("sys.argv", argv), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                parse_args()
        for provider in ("subq", "vllm-yes-no"):
            with mock.patch("sys.argv", [*base, "--provider", provider]):
                self.assertEqual(parse_args().english, Path("t.jsonl"))
        with mock.patch("sys.argv", [*base, "--provider", "subq", "--repeat", "2"]):
            args = parse_args()
            self.assertEqual((args.english, args.repeat), (Path("t.jsonl"), 2))


class OptionWordTests(unittest.TestCase):
    """The option-word check (--dont-know --dont-know-word english): the Turkish "I don't know" runs with only the
    option word in English, in runs of their own."""

    bank = DontKnowTests.bank
    spread = staticmethod(DontKnowTests.spread)

    def store(self, connection: sqlite3.Connection, path: Path, answers: dict[int, tuple[str, dict[str, float]]], *,
              dont_know: bool = False, word: str | None = None, repeat: int | None = None) -> dict:
        """A completed run of model "m" through subq with these answers, as its report record."""
        selection = load_questions(path, None, None, None, 0, dont_know=dont_know, dont_know_word=word)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "subq", "http://localhost", 0, 1, False, None, False,
                                 None, None, dont_know, repeat, False, dont_know_word=word)
        for ordinal, question_ in enumerate(selection.questions):
            choice, probabilities = answers[question_.question_id]
            raw = json.dumps({"request_id": None, "response": {
                "answers": {"answer": {"choice": choice, "probabilities": probabilities}}, "usage": {"input_tokens": 10}}})
            store_answers(connection, identity.run_id, [(ordinal, question_)], [choice], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        metrics = run_metrics(connection, identity.run_key, path.parent)
        return {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path),
                "dataset_sha256": identity.dataset_sha256, "provider": "subq", "model": "m", "thinking": "off",
                "batch_size": 1, "evaluated": 3, "eligible_total": 3, "selection_sha256": identity.selection_sha256,
                "replace_key_text": None, "repeat": repeat, "dont_know": metrics.get("dont_know"),
                "dont_know_word": metrics.get("dont_know_word"), "metrics": metrics}

    def test_only_the_option_word_changes(self) -> None:
        self.assertEqual(DONT_KNOW_WORD_OPTION, "I don't know")
        self.assertEqual(DONT_KNOW_WORD_INSTRUCTIONS, "Which option is the correct answer to this Turkish multiple-choice "
                                                      "question? If you do not know the answer, choose I don't know.")
        self.assertEqual(DONT_KNOW_WORD_PROMPTS, {**DONT_KNOW_PROMPTS, "system_one_instructions": DONT_KNOW_WORD_INSTRUCTIONS,
                                                  "dont_know_option": DONT_KNOW_WORD_OPTION})
        path = self.bank()
        turkish = load_questions(path, None, None, None, 0, dont_know=True).questions
        english = load_questions(path, None, None, None, 0, dont_know=True, dont_know_word="english").questions
        for before, after in zip(turkish, english, strict=True):
            self.assertEqual(after.options, (*before.options[:-1], Option("F", "I don't know")))
            self.assertEqual(after.prompt, before.prompt.replace("F. Bilmiyorum", "F. I don't know"))
            self.assertIn("Seçenekler:", after.prompt)
            self.assertEqual(after.answer, before.answer)
        self.assertTrue(english[0].prompt.endswith("E. option E\nF. I don't know"))
        sent = []

        def post(endpoint, payload, *rest):
            sent.append(payload)
            return {"answers": {"answer": {"choice": "F"}}}, {}

        args = argparse.Namespace(provider="subq", jev_url="http://localhost", jev_api_key=None, model="m", timeout=1,
                                  dont_know=True, english=None, dont_know_word="english")
        with mock.patch("benchmark_ollama.post_json", side_effect=post):
            self.assertEqual(ask_batch(args, [english[0]], False, None)[0], ["F"])
        self.assertEqual(sent[-1]["questions"]["answer"]["instructions"], DONT_KNOW_WORD_INSTRUCTIONS)
        self.assertEqual(sent[-1]["state"], english[0].prompt)

    def test_its_prompts_have_their_own_version_and_the_others_keep_theirs(self) -> None:
        self.assertEqual(PROMPT_VERSION, "254597b8be16")
        self.assertEqual(DONT_KNOW_PROMPT_VERSION, "1cdd542b597f")
        self.assertEqual(ENGLISH_PROMPT_VERSION, "47f5776e71db")
        self.assertEqual(ENGLISH_DONT_KNOW_PROMPT_VERSION, "413d6775fc58")
        compact = json.dumps(DONT_KNOW_WORD_PROMPTS, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(DONT_KNOW_WORD_PROMPT_VERSION, hashlib.sha256(compact.encode("utf-8")).hexdigest()[:12])
        self.assertEqual(len({DONT_KNOW_WORD_PROMPT_VERSION, PROMPT_VERSION, DONT_KNOW_PROMPT_VERSION,
                              ENGLISH_PROMPT_VERSION, ENGLISH_DONT_KNOW_PROMPT_VERSION}), 5)

    def test_its_runs_are_their_own_record_the_word_and_derive_from_the_first_main_run(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        spread = self.spread
        plain = self.store(connection, path, {1: ("B", spread("B", 0.6, "ABCDE")), 2: ("A", spread("A", 0.9, "ABCDE")),
                                              3: ("C", spread("C", 0.8, "ABCDE"))})
        variant = {1: ("F", spread("F", 0.7, "ABCDEF")), 2: ("A", spread("A", 0.5, "ABCDEF")),
                   3: ("C", spread("C", 0.75, "ABCDEF"))}
        turkish = self.store(connection, path, variant, dont_know=True)
        word = self.store(connection, path, variant, dont_know=True, word="english")
        word_repeat = self.store(connection, path, variant, dont_know=True, word="english", repeat=2)
        self.assertEqual(len({plain["run_key"], turkish["run_key"], word["run_key"], word_repeat["run_key"]}), 4)
        rows = {row["id"]: row for row in connection.execute("SELECT id, prompt_version, dont_know_word FROM runs")}
        self.assertEqual(tuple(rows[turkish["run_id"]])[1:], (DONT_KNOW_PROMPT_VERSION, None))
        self.assertEqual(tuple(rows[word["run_id"]])[1:], (DONT_KNOW_WORD_PROMPT_VERSION, "english"))
        self.assertNotIn("dont_know_word", turkish["metrics"])
        self.assertEqual(word["metrics"]["dont_know_word"], "english")
        # Counted with the English word, and derived from the setup's first full main run.
        data = word["metrics"]["dont_know_answers"]
        self.assertEqual((data["right"], data["wrong"], data["dont_know"]), (1, 1, 1))
        self.assertEqual(data["derived"], turkish["metrics"]["dont_know_answers"]["derived"])
        self.assertIsNotNone(data["derived"])
        self.assertFalse(in_main_tables(word))
        records = [plain, turkish, word, word_repeat]
        self.assertEqual(run_repeats(connection, {record["run_key"]: record for record in records}, path.parent), [])
        self.assertEqual(run_batching(connection, {record["run_key"]: record for record in records}, path.parent), [])
        # Exported with the word, and with its prompts.
        report = path.parent / "report.md"
        report.write_text("".join(f"<!-- benchmark-result: {json.dumps({**record, 'metrics': None})} -->\n"
                                  for record in (plain, word)), encoding="utf-8")
        export_answers(path.parent / "answers.json", report, connection)
        document = json.loads((path.parent / "answers.json").read_text(encoding="utf-8"))
        self.assertEqual(document["dont_know_word_prompts"], DONT_KNOW_WORD_PROMPTS)
        self.assertNotIn("dont_know_prompts", document)
        self.assertEqual([run["dont_know_word"] for run in document["datasets"][0]["runs"]], [None, "english"])

    def test_it_needs_dont_know_and_refuses_english(self) -> None:
        base = ["benchmark_ollama.py", "subq-snap-1.1", "--provider", "subq"]
        with mock.patch("sys.argv", [*base, "--dont-know", "--dont-know-word", "english"]):
            self.assertEqual(parse_args().dont_know_word, "english")
        with mock.patch("sys.argv", [*base, "--dont-know"]):
            self.assertEqual(parse_args().dont_know_word, "turkish")
        for extra in (["--dont-know-word", "english"],
                      ["--dont-know", "--dont-know-word", "english", "--english", "t.jsonl", "--questions", "kept.txt"]):
            with self.subTest(extra=extra), mock.patch("sys.argv", [*base, *extra]), mock.patch("sys.stderr"), \
                    self.assertRaises(SystemExit):
                parse_args()


class RerunTests(unittest.TestCase):
    """A fresh run of an existing setup (--rerun TAG), in a run of its own."""

    bank = DontKnowTests.bank

    def store(self, connection: sqlite3.Connection, path: Path, rerun: str | None = None, repeat: int | None = None,
              batch_size: int = 1) -> dict:
        selection = load_questions(path, None, None, None, 0)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "fastino/GLiDE", path, "fastino", "http://localhost", 0,
                                 batch_size, False, None, False, None, None, False, repeat, False, rerun=rerun)
        for ordinal, question_ in enumerate(selection.questions):
            raw = json.dumps({"request_id": None, "response": {
                "answers": {"answer": {"choice": "B", "probabilities": {label: 0.2 for label in "ABCDE"}}}}})
            store_answers(connection, identity.run_id, [(ordinal, question_)], ["B"], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        metrics = run_metrics(connection, identity.run_key, path.parent)
        return {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path),
                "dataset_sha256": identity.dataset_sha256, "provider": "fastino", "model": "fastino/GLiDE",
                "thinking": "off", "batch_size": batch_size, "evaluated": 3, "eligible_total": 3,
                "selection_sha256": identity.selection_sha256, "replace_key_text": None, "repeat": repeat,
                "rerun": metrics.get("rerun"), "metrics": metrics}

    def test_a_rerun_is_its_own_run_out_of_the_main_tables_repeats_and_batching(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        first = self.store(connection, path)
        repeat = self.store(connection, path, repeat=2)
        fresh = self.store(connection, path, rerun="2026-11")
        other_size = self.store(connection, path, rerun="2026-11-b", batch_size=5)
        self.assertEqual(len({first["run_key"], repeat["run_key"], fresh["run_key"], other_size["run_key"]}), 4)
        self.assertEqual(tuple(connection.execute("SELECT rerun, prompt_version FROM runs WHERE id=?",
                                                  (fresh["run_id"],)).fetchone()), ("2026-11", PROMPT_VERSION))
        self.assertNotIn("rerun", first["metrics"])
        self.assertEqual(fresh["metrics"]["rerun"], "2026-11")
        self.assertTrue(in_main_tables(first))
        self.assertFalse(in_main_tables(fresh))
        records = {record["run_key"]: record for record in (first, repeat, fresh, other_size)}
        sets = run_repeats(connection, records, path.parent)
        self.assertEqual([item["run_keys"] for item in sets], [[first["run_key"], repeat["run_key"]]])
        self.assertEqual(run_batching(connection, records, path.parent), [])
        self.assertIn("rerun 2026-11", run_label(fresh))
        report = path.parent / "report.md"
        report.write_text("".join(f"<!-- benchmark-result: {json.dumps({**record, 'metrics': None})} -->\n"
                                  for record in (first, fresh)), encoding="utf-8")
        export_answers(path.parent / "answers.json", report, connection)
        document = json.loads((path.parent / "answers.json").read_text(encoding="utf-8"))
        self.assertEqual([run["rerun"] for run in document["datasets"][0]["runs"]], [None, "2026-11"])

    def test_rerun_takes_a_tag_and_never_a_repeat(self) -> None:
        base = ["benchmark_ollama.py", "fastino/GLiDE", "--provider", "fastino"]
        with mock.patch("sys.argv", [*base, "--rerun", "2026-11"]):
            self.assertEqual(parse_args().rerun, "2026-11")
        for extra in (["--rerun", " "], ["--rerun", "x", "--repeat", "2"]):
            with self.subTest(extra=extra), mock.patch("sys.argv", [*base, *extra]), mock.patch("sys.stderr"), \
                    self.assertRaises(SystemExit):
                parse_args()



class EnglishDontKnowTests(unittest.TestCase):
    """English "I don't know": the English reading questions with the option "I don't know", kept out of the main tables."""

    bank = DontKnowTests.bank
    translations = EnglishTests.translations
    record = staticmethod(EnglishTests.record)
    spread = staticmethod(DontKnowTests.spread)

    def store(self, connection: sqlite3.Connection, path: Path, answers: dict[int, tuple[str, dict[str, float]]], *,
              dont_know: bool = False, english: str | None = None, ids: frozenset[int] | None = None,
              repeat: int | None = None, question_list: str | None = None) -> dict:
        """A completed run of model "m" through subq with these answers, as its report record."""
        selection = load_questions(path, None, None, None, 0, dont_know=dont_know, question_ids=ids)
        if english is not None:
            records = [self.record(question_id) for question_id in (1, 2, 3)]
            selection = english_selection(selection, self.translations(path.parent, records), dont_know)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "subq", "http://localhost", 0, 1, False, None, False,
                                 None, None, dont_know, repeat, False, english=english)
        for ordinal, question_ in enumerate(selection.questions):
            choice, probabilities = answers[question_.question_id]
            raw = json.dumps({"request_id": None, "response": {
                "answers": {"answer": {"choice": choice, "probabilities": probabilities}}, "usage": {"input_tokens": 10}}})
            store_answers(connection, identity.run_id, [(ordinal, question_)], [choice], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        metrics = run_metrics(connection, identity.run_key, path.parent)
        return {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path), "provider": "subq",
                "model": "m", "thinking": "off", "batch_size": 1, "evaluated": len(selection.questions), "eligible_total": 3,
                "selection_sha256": identity.selection_sha256, "replace_key_text": None, "repeat": repeat,
                "question_list": question_list, "dont_know": metrics.get("dont_know"), "english": metrics.get("english"),
                "metrics": metrics}

    def test_the_prompt_is_the_english_one_with_the_option_last_under_the_english_heading(self) -> None:
        self.assertEqual(ENGLISH_DONT_KNOW_OPTION, "I don't know")
        self.assertEqual(ENGLISH_DONT_KNOW_INSTRUCTIONS, "Which option is the correct answer to this English multiple-choice "
                                                         "question? If you do not know the answer, choose I don't know.")
        path = self.bank()
        translations = self.translations(path.parent, [self.record(1), self.record(2), self.record(3)])
        selection = load_questions(path, None, None, None, 0, dont_know=True, question_ids=frozenset({1, 3}))
        english = english_selection(selection, translations, True)
        for before, after in zip(selection.questions, english.questions, strict=True):
            self.assertEqual(after.options, (*(Option(label, f"English {label}") for label in "ABCDE"),
                                             Option("F", ENGLISH_DONT_KNOW_OPTION)))
            self.assertEqual(after.answer, before.answer)
            self.assertEqual(after.prompt, f"English question {after.question_id}?\n\nOptions:\nA. English A\nB. English B\n"
                                           "C. English C\nD. English D\nE. English E\nF. I don't know")
        # A selection with the option needs the flag here too: its letters are not the translation's.
        with self.assertRaises(ValueError):
            english_selection(selection, translations)
        sent = []

        def post(endpoint, payload, *rest):
            sent.append(payload)
            return {"answers": {"answer": {"choice": "F"}}}, {}

        args = argparse.Namespace(provider="subq", jev_url="http://localhost", jev_api_key=None, model="m", timeout=1,
                                  dont_know=True, english=Path("t.jsonl"))
        with mock.patch("benchmark_ollama.post_json", side_effect=post):
            self.assertEqual(ask_batch(args, [english.questions[0]], False, None)[0], ["F"])
        self.assertEqual(sent[-1]["questions"]["answer"]["instructions"], ENGLISH_DONT_KNOW_INSTRUCTIONS)
        self.assertEqual(sent[-1]["state"], english.questions[0].prompt)

    def test_its_prompts_have_their_own_version_and_the_others_keep_theirs(self) -> None:
        self.assertEqual(DONT_KNOW_PROMPT_VERSION, "1cdd542b597f")
        self.assertEqual(ENGLISH_PROMPT_VERSION, "47f5776e71db")
        self.assertEqual(ENGLISH_DONT_KNOW_PROMPTS, {**ENGLISH_PROMPTS, "system_one_instructions": ENGLISH_DONT_KNOW_INSTRUCTIONS,
                                                     "dont_know_option": ENGLISH_DONT_KNOW_OPTION})
        compact = json.dumps(ENGLISH_DONT_KNOW_PROMPTS, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(ENGLISH_DONT_KNOW_PROMPT_VERSION, hashlib.sha256(compact.encode("utf-8")).hexdigest()[:12])
        self.assertEqual(len({ENGLISH_DONT_KNOW_PROMPT_VERSION, ENGLISH_PROMPT_VERSION, DONT_KNOW_PROMPT_VERSION,
                              PROMPT_VERSION}), 4)

    def test_english_takes_dont_know_and_dont_know_takes_a_question_list(self) -> None:
        base = ["benchmark_ollama.py", "subq-snap-1.1", "--provider", "subq", "--questions", "kept.txt"]
        with mock.patch("sys.argv", [*base, "--english", "t.jsonl", "--dont-know", "--repeat", "2"]):
            args = parse_args()
        self.assertEqual((args.english, args.dont_know, args.repeat), (Path("t.jsonl"), True, 2))
        with mock.patch("sys.argv", [*base, "--dont-know"]):
            args = parse_args()
        self.assertEqual((args.english, args.dont_know, args.questions), (None, True, Path("kept.txt")))
        for extra in (["--dont-know", "--shuffle-options", "1"], ["--dont-know", "--replace-key-text", "1"]):
            with self.subTest(extra=extra), mock.patch("sys.argv", [*base, *extra]), mock.patch("sys.stderr"), \
                    self.assertRaises(SystemExit):
                parse_args()

    def test_its_original_is_the_first_english_reading_run_with_the_same_translations_and_questions(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        spread = self.spread
        # The keys are B, E and C. Without the option: right at 0.6, wrong at 0.9, right at 0.8.
        plain = {1: ("B", spread("B", 0.6, "ABCDE")), 2: ("A", spread("A", 0.9, "ABCDE")), 3: ("C", spread("C", 0.8, "ABCDE"))}
        turkish = self.store(connection, path, plain)
        self.store(connection, path, plain, english="cd" * 32)
        self.store(connection, path, plain, english="ab" * 32, ids=frozenset({1, 2}))
        original = self.store(connection, path, plain, english="ab" * 32)
        self.store(connection, path, plain, english="ab" * 32, repeat=2)
        variant = {1: ("F", spread("F", 0.7, "ABCDEF")), 2: ("A", spread("A", 0.5, "ABCDEF")),
                   3: ("C", spread("C", 0.75, "ABCDEF"))}
        run = self.store(connection, path, variant, dont_know=True, english="ab" * 32, question_list="kept.txt")
        row = connection.execute("SELECT prompt_version FROM runs WHERE id=?", (run["run_id"],)).fetchone()
        self.assertEqual(row["prompt_version"], ENGLISH_DONT_KNOW_PROMPT_VERSION)
        metrics = run["metrics"]
        self.assertIs(metrics["dont_know"], True)
        self.assertEqual(metrics["english"], {"translations_sha256": "ab" * 32, "questions": 3,
                                              "prompt_version": ENGLISH_DONT_KNOW_PROMPT_VERSION})
        data = metrics["dont_know_answers"]
        self.assertEqual((data["right"], data["wrong"], data["dont_know"], data["invalid"]), (1, 1, 1, 0))
        self.assertEqual(data["original_run"], original["run_id"])
        derived = data["derived"]
        self.assertEqual((derived["cut_off"], derived["right"], derived["wrong"], derived["abstained"]), (0.8, 1, 1, 1))
        # A Turkish "I don't know" run still takes the first full Turkish run.
        turkish_variant = self.store(connection, path, variant, dont_know=True)
        self.assertEqual(turkish_variant["metrics"]["dont_know_answers"]["original_run"], turkish["run_id"])
        # Out of the main tables and the repeats, its section is the "I don't know" one, labelled in English.
        self.assertFalse(in_main_tables(run))
        repeat = self.store(connection, path, variant, dont_know=True, english="ab" * 32, repeat=2, question_list="kept.txt")
        self.assertEqual(run_repeats(connection, {item["run_key"]: item for item in (run, repeat)}, path.parent), [])
        lines = dont_know_lines([{**run, "dont_know_answers": data}])
        self.assertTrue(lines[-1].startswith(f'| subq m, questions from kept.txt, "{ENGLISH_DONT_KNOW_OPTION}" option added, '
                                             f"in English, run {run['run_id']} | 3 | 1 | 1 | 1 | 0 |"))

    def test_without_an_english_reading_run_there_is_no_original(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        plain = {1: ("B", self.spread("B", 0.6, "ABCDE")), 2: ("A", self.spread("A", 0.9, "ABCDE")),
                 3: ("C", self.spread("C", 0.8, "ABCDE"))}
        self.store(connection, path, plain)
        variant = {question_id: ("F", self.spread("F", 0.7, "ABCDEF")) for question_id in (1, 2, 3)}
        data = self.store(connection, path, variant, dont_know=True, english="ab" * 32)["metrics"]["dont_know_answers"]
        self.assertEqual((data["dont_know"], data["original_run"], data["derived"]), (3, None, None))

    def test_a_turkish_run_on_listed_questions_stays_out_of_the_main_tables_and_repeats(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        plain = {1: ("B", self.spread("B", 0.6, "ABCDE")), 2: ("A", self.spread("A", 0.9, "ABCDE")),
                 3: ("C", self.spread("C", 0.8, "ABCDE"))}
        full = self.store(connection, path, plain)
        variant = {1: ("F", self.spread("F", 0.7, "ABCDEF")), 3: ("C", self.spread("C", 0.75, "ABCDEF"))}
        kept = frozenset({1, 3})
        runs = [self.store(connection, path, variant, dont_know=True, ids=kept, question_list="kept.txt", repeat=repeat)
                for repeat in (None, 2)]
        row = connection.execute("SELECT prompt_version FROM runs WHERE id=?", (runs[0]["run_id"],)).fetchone()
        self.assertEqual(row["prompt_version"], DONT_KNOW_PROMPT_VERSION)
        data = runs[0]["metrics"]["dont_know_answers"]
        self.assertEqual((data["questions"], data["right"], data["dont_know"], data["original_run"]), (2, 1, 1, full["run_id"]))
        self.assertIsNone(runs[0]["english"])
        for run in runs:
            self.assertFalse(in_main_tables(run))
        self.assertEqual(run_repeats(connection, {run["run_key"]: run for run in runs}, path.parent), [])


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

    def test_a_model_listed_as_32_bit_may_miss_one_by_32_bit_rounding_only(self) -> None:
        # SubQ Snap 1.1 reports exact 32-bit floats: five of them may miss 1 by up to 5 × 2^-23 (6e-7) together, and no
        # more. These miss it by about 2e-7: too much for 7 decimal places, within 32-bit rounding.
        within = {"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2000002}
        within = {key: struct.unpack("f", struct.pack("f", value))[0] for key, value in within.items()}
        self.assertEqual(probability_problems(within, self.LABELS, float32=True), [])
        self.assertRegex(probability_problems(within, self.LABELS)[0], "not 1 to 7 decimal places")
        beyond = dict(within, E=struct.unpack("f", struct.pack("f", 0.200002))[0])
        self.assertRegex(probability_problems(beyond, self.LABELS, float32=True)[0], "within the 32-bit rounding of 5")
        # A value that is not an exact 32-bit float gets the strict test.
        not_float32 = dict(within, E=0.2000002)
        self.assertRegex(probability_problems(not_float32, self.LABELS, float32=True)[0], "not 1 to 7 decimal places")

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

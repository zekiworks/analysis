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
    CHAT_DONT_KNOW_SENTENCE,
    DONT_KNOW_CHAT,
    DONT_KNOW_CHAT_PROMPT_VERSION,
    DONT_KNOW_CHAT_PROMPTS,
    DONT_KNOW_OPTION,
    DONT_KNOW_PROMPT_VERSION,
    DONT_KNOW_PROMPTS,
    DONT_KNOW_WORD_INSTRUCTIONS,
    DONT_KNOW_WORD_OPTION,
    DONT_KNOW_WORD_PROMPT_VERSION,
    DONT_KNOW_WORD_PROMPTS,
    ENGLISH_CHAT,
    ENGLISH_CHAT_PROMPT_VERSION,
    ENGLISH_DONT_KNOW_INSTRUCTIONS,
    ENGLISH_DONT_KNOW_OPTION,
    ENGLISH_DONT_KNOW_CHAT,
    ENGLISH_DONT_KNOW_CHAT_PROMPT_VERSION,
    ENGLISH_DONT_KNOW_CHAT_PROMPTS,
    ENGLISH_DONT_KNOW_PROMPT_VERSION,
    ENGLISH_DONT_KNOW_SENTENCE,
    ENGLISH_DONT_KNOW_PROMPTS,
    ENGLISH_INSTRUCTIONS,
    ENGLISH_PROMPT_VERSION,
    ENGLISH_PROMPTS,
    JEV_INSTRUCTIONS,
    PLAIN_PROMPT_VERSIONS,
    PROMPT_VERSION,
    GPU_RATE,
    SYSTEM_ONE,
    GPU_TIME,
    PRICES,
    WEB_GROUNDING_PRICES,
    TURKISH_CHAT,
    Option,
    Question,
    add_images,
    answer_problems,
    answer_usage,
    ask_batch,
    confidence_answers,
    derived_abstention,
    dont_know_lines,
    empty_reply,
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
    plain_prompt,
    probability_problems,
    regrade,
    rescue_runs,
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


class GlideImagesTests(unittest.TestCase):
    def test_images_go_into_the_state_as_parts_after_the_text(self) -> None:
        # GLiDE's server passes only `state` and `questions` to the model: an image anywhere else never reaches it.
        with tempfile.TemporaryDirectory() as folder:
            crop = Path(folder) / "crop.png"
            crop.write_bytes(b"\x89PNG\r\n\x1a\n")
            payload = {"state": "Passage text", "questions": {}}
            add_images(SYSTEM_ONE["glide"], payload, {}, (crop,))
            empty = {"state": "", "questions": {}}
            add_images(SYSTEM_ONE["glide"], empty, {}, (crop,))
        self.assertEqual(set(payload), {"state", "questions"})
        self.assertEqual(payload["state"][0], {"type": "text", "text": "Passage text"})
        self.assertEqual(payload["state"][1]["type"], "image_url")
        self.assertTrue(payload["state"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual([part["type"] for part in empty["state"]], ["image_url"])


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

    def test_every_provider_but_vllm_yes_no_takes_it(self) -> None:
        with mock.patch("sys.argv", ["benchmark_ollama.py", "m", "--provider", "vllm-yes-no", "--dont-know"]), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args()
        with mock.patch("sys.argv", ["benchmark_ollama.py", "subq-snap-1.1", "--provider", "subq", "--dont-know"]):
            self.assertTrue(parse_args().dont_know)
        with mock.patch("sys.argv", ["benchmark_ollama.py", "llama3", "--provider", "ollama", "--dont-know"]):
            self.assertTrue(parse_args().dont_know)


class ChatDontKnowTests(unittest.TestCase):
    """"I don't know" for the chat models (--dont-know with a chat provider): the option last, and one more sentence
    ending each instruction, in Turkish or English, in runs of their own."""

    bank = DontKnowTests.bank

    def translations(self, root: Path, records: list[dict]) -> Path:
        return EnglishTests.translations(self, root, records)

    @staticmethod
    def record(question_id: int) -> dict:
        return EnglishTests.record(question_id)

    CHAT_PROVIDERS = ("openai", "claude", "gemini", "xai", "antigravity", "openrouter-chat", "vllm", "vllm-stated",
                      "vllm-verbal", "vllm-vote", "ollama")

    @staticmethod
    def texts(value: object) -> list[str]:
        """Every string in a captured request, each object and array in it as JSON, with JSON inside a string read too."""
        if isinstance(value, dict):
            return [json.dumps(value, ensure_ascii=False), *(text for item in value.values() for text in ChatDontKnowTests.texts(item))]
        if isinstance(value, (list, tuple)):
            return [json.dumps(value, ensure_ascii=False, default=str),
                    *(text for item in value for text in ChatDontKnowTests.texts(item))]
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            return [value, *ChatDontKnowTests.texts(parsed)] if isinstance(parsed, (dict, list)) else [value]
        return []

    def request(self, provider: str, batch: list[Question], english: Path | None, dont_know: bool) -> str:
        """Everything one ask_batch request of `provider` sends: payload, command, stdin and the files it names."""
        seen: list[object] = []

        class Stop(Exception):
            pass

        def post(endpoint, payload, *rest, **kw):
            seen.append(payload)
            raise Stop

        def run(command, *rest, **kw):
            seen.extend([command, kw.get("input")])
            for part in map(str, command):
                for name in (part, part.split("=", 1)[-1].strip('"')):
                    try:
                        seen.append(Path(name).read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
            raise Stop

        def urlopen(request, *rest, **kw):
            seen.append(request.data)
            raise Stop

        args = argparse.Namespace(
            provider=provider, model="m", timeout=1, seed=0, english=english, dont_know=dont_know, dont_know_word="turkish",
            codex_bin="codex", claude_bin="claude", gemini_api_key="k", gemini_thinking="low", claude_effort="low",
            xai_reasoning="low", antigravity_thinking="low", openrouter_reasoning="low", openrouter_order="p",
            openrouter_require_parameters=True, openrouter_json_object=False, openrouter_max_tokens=32768,
            openrouter_answer_layout=False, vllm_url="http://localhost",
            ollama_url="http://localhost", num_ctx=None,
        )
        with mock.patch("benchmark_ollama.post_json", side_effect=post), \
                mock.patch("benchmark_ollama.subprocess.run", side_effect=run), \
                mock.patch("benchmark_ollama.urlopen", side_effect=urlopen), \
                mock.patch("benchmark_ollama.omp_token", return_value="t"), \
                mock.patch("benchmark_ollama.omp_login_field", return_value="p"), \
                mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), self.assertRaises(Stop):
            ask_batch(args, batch, False, None)
        return "\n".join(self.texts(seen))

    def test_the_sentences_and_the_option_reach_every_chat_providers_request_in_both_languages(self) -> None:
        self.assertEqual(CHAT_DONT_KNOW_SENTENCE, "Cevabı bilmiyorsanız Bilmiyorum seçeneğini seçin.")
        self.assertEqual(ENGLISH_DONT_KNOW_SENTENCE, "If you do not know the answer, choose I don't know.")
        path = self.bank()
        turkish = load_questions(path, None, None, None, 0, dont_know=True).questions
        translations = self.translations(path.parent, [self.record(1), self.record(2), self.record(3)])
        english = english_selection(load_questions(path, None, None, None, 0, dont_know=True), translations, True).questions
        for provider in self.CHAT_PROVIDERS:
            batch = list(turkish[:1] if provider in ("vllm-verbal", "vllm-vote") else turkish[:2])
            english_batch = list(english[:len(batch)])
            for language, questions, file, prompts, five, option in (
                    ("turkish", batch, None, DONT_KNOW_CHAT, TURKISH_CHAT, f"F. {DONT_KNOW_OPTION}"),
                    ("english", english_batch, Path("t.jsonl"), ENGLISH_DONT_KNOW_CHAT, ENGLISH_CHAT, f"F. {ENGLISH_DONT_KNOW_OPTION}")):
                with self.subTest(provider=provider, language=language):
                    sent = self.request(provider, questions, file, True)
                    instruction = (prompts.verbal_instruction if provider in ("vllm-verbal", "vllm-vote")
                                   else prompts.answer_instruction if provider in ("vllm", "ollama")
                                   else prompts.confidence_instruction)
                    self.assertIn(instruction, sent)
                    self.assertTrue(instruction.endswith(CHAT_DONT_KNOW_SENTENCE if language == "turkish" else ENGLISH_DONT_KNOW_SENTENCE))
                    self.assertIn(option, sent)
                    # The answer schema offers the option's letter with the others.
                    self.assertRegex(sent, r'"enum": ?\[[^\]]*"E", ?"F"\]')
                    # The system prompts and question headers stay those of the five-option runs.
                    self.assertIn(five.question_header.split(" ")[0], sent)
                    self.assertIn(prompts.confidence_system if instruction == prompts.confidence_instruction
                                  else prompts.answer_system if instruction == prompts.answer_instruction
                                  else prompts.verbal_system, sent)
        for field in ("answer_system", "confidence_system", "verbal_system", "question_header", "image_note"):
            self.assertEqual(getattr(DONT_KNOW_CHAT, field), getattr(TURKISH_CHAT, field))
            self.assertEqual(getattr(ENGLISH_DONT_KNOW_CHAT, field), getattr(ENGLISH_CHAT, field))
        self.assertEqual(DONT_KNOW_CHAT.confidence_instruction, f"{TURKISH_CHAT.confidence_instruction} {CHAT_DONT_KNOW_SENTENCE}")

    def test_without_the_flag_the_requests_keep_the_five_option_prompts(self) -> None:
        path = self.bank()
        batch = list(load_questions(path, None, None, None, 0).questions[:2])
        for provider in ("claude", "gemini", "openrouter-chat"):
            with self.subTest(provider=provider):
                sent = self.request(provider, batch, None, False)
                self.assertIn(TURKISH_CHAT.confidence_instruction + "\n\n", sent)
                self.assertNotIn(CHAT_DONT_KNOW_SENTENCE, sent)
                self.assertNotIn(DONT_KNOW_OPTION, sent)

    def test_a_reply_choosing_the_option_is_read(self) -> None:
        batch = list(load_questions(self.bank(), None, None, None, 0, dont_know=True).questions[:2])
        predictions, _ = confidence_answers({"1": {"answer": "F", "confidence": 0.3}, "2": {"answer": "G", "confidence": 1}}, batch)
        self.assertEqual(predictions, ["F", None])

    def test_its_prompts_have_their_own_versions_and_its_runs_their_own_keys(self) -> None:
        for prompts, version, chat, option, sentence in (
                (DONT_KNOW_CHAT_PROMPTS, DONT_KNOW_CHAT_PROMPT_VERSION, DONT_KNOW_CHAT, DONT_KNOW_OPTION, CHAT_DONT_KNOW_SENTENCE),
                (ENGLISH_DONT_KNOW_CHAT_PROMPTS, ENGLISH_DONT_KNOW_CHAT_PROMPT_VERSION, ENGLISH_DONT_KNOW_CHAT,
                 ENGLISH_DONT_KNOW_OPTION, ENGLISH_DONT_KNOW_SENTENCE)):
            compact = json.dumps(prompts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual(version, hashlib.sha256(compact.encode("utf-8")).hexdigest()[:12])
            self.assertEqual((prompts["confidence_instruction"], prompts["dont_know_option"], prompts["dont_know_sentence"]),
                             (chat.confidence_instruction, option, sentence))
        versions = {PROMPT_VERSION, DONT_KNOW_PROMPT_VERSION, ENGLISH_PROMPT_VERSION, ENGLISH_CHAT_PROMPT_VERSION,
                    ENGLISH_DONT_KNOW_PROMPT_VERSION, DONT_KNOW_CHAT_PROMPT_VERSION, ENGLISH_DONT_KNOW_CHAT_PROMPT_VERSION}
        self.assertEqual(len(versions), 7)
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        translations = self.translations(path.parent, [self.record(1), self.record(2), self.record(3)])
        found = {}
        for english in (False, True):
            for dont_know in (False, True):
                selection = load_questions(path, None, None, None, 0, dont_know=dont_know)
                if english:
                    selection = english_selection(selection, translations, dont_know)
                with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
                    identity = start_run(connection, selection, "m", path, "gemini", "http://localhost", 0, 16, "low", None,
                                         False, None, None, dont_know, None, False, english="ab" * 32 if english else None)
                row = connection.execute("SELECT prompt_version, dont_know FROM runs WHERE id=?", (identity.run_id,)).fetchone()
                found[english, dont_know] = (identity.run_key, row["prompt_version"], row["dont_know"])
        self.assertEqual(len({key for key, _, _ in found.values()}), 4)
        self.assertEqual(found[False, False][1:], (PROMPT_VERSION, None))
        self.assertEqual(found[False, True][1:], (DONT_KNOW_CHAT_PROMPT_VERSION, 1))
        self.assertEqual(found[True, False][1:], (ENGLISH_CHAT_PROMPT_VERSION, None))
        self.assertEqual(found[True, True][1:], (ENGLISH_DONT_KNOW_CHAT_PROMPT_VERSION, 1))

    def test_chat_providers_take_it_at_any_request_size_and_not_the_option_word(self) -> None:
        base = ["benchmark_ollama.py", "m", "--batch-size", "16", "--dont-know"]
        for provider in ("claude", "openai", "gemini", "xai", "vllm", "vllm-stated"):
            with self.subTest(provider=provider), mock.patch("sys.argv", [*base, "--provider", provider]):
                self.assertTrue(parse_args().dont_know)
        with mock.patch("sys.argv", [*base, "--provider", "claude", "--english", "t.jsonl", "--questions", "kept.txt"]):
            args = parse_args()
        self.assertEqual((args.dont_know, args.english), (True, Path("t.jsonl")))
        with mock.patch("sys.argv", [*base, "--provider", "claude", "--dont-know-word", "english"]), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args()

    def test_answers_json_carries_the_prompts_of_the_runs_it_holds(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        selection = load_questions(path, None, None, None, 0, dont_know=True)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "gemini", "http://localhost", 0, 16, "low", None, False,
                                 None, None, True, None, False)
        raw = json.dumps({"answers": {str(q.question_id): {"answer": "F", "confidence": 0.5} for q in selection.questions}})
        store_answers(connection, identity.run_id, list(enumerate(selection.questions)), ["F"] * 3, raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        record = {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path),
                  "dataset_sha256": identity.dataset_sha256, "provider": "gemini", "model": "m", "thinking": "low",
                  "batch_size": 16, "evaluated": 3, "eligible_total": 3, "selection_sha256": identity.selection_sha256,
                  "replace_key_text": None, "repeat": None, "dont_know": True, "metrics": None}
        report = path.parent / "report.md"
        report.write_text(f"<!-- benchmark-result: {json.dumps(record)} -->\n", encoding="utf-8")
        export_answers(path.parent / "answers.json", report, connection)
        document = json.loads((path.parent / "answers.json").read_text(encoding="utf-8"))
        self.assertEqual(document["dont_know_chat_prompts"], DONT_KNOW_CHAT_PROMPTS)
        for key in ("dont_know_prompts", "english_dont_know_prompts", "english_dont_know_chat_prompts", "english_chat_prompts"):
            self.assertNotIn(key, document)
        self.assertIn(CHAT_DONT_KNOW_SENTENCE, "\n".join(dont_know_lines([{**record, "run_id": 1, "dont_know_answers": {
            "questions": 3, "right": 0, "wrong": 0, "dont_know": 3, "invalid": 0, "mean_option_probability": None,
            "original_run": None, "derived": None}}])))


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

        common = {"model": "m", "timeout": 1, "dont_know": False, "dont_know_word": "turkish", "english": Path("t.jsonl"),
                  "perplexity_mode": None}
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

    def test_the_chat_models_get_their_turkish_prompts_in_english_and_keep_them_in_turkish_otherwise(self) -> None:
        batch = [question(1), question(2)]
        sent = []

        def post(endpoint, payload, *rest):
            sent.append(payload)
            raise RuntimeError("stop")

        common = {"model": "m", "timeout": 1, "seed": 0, "dont_know": False, "dont_know_word": "turkish", "vllm_url": "http://localhost"}
        with mock.patch("benchmark_ollama.post_json", side_effect=post):
            for english, prompts, header in ((Path("t.jsonl"), ENGLISH_CHAT, "Question 2 (source page"),
                                             (None, TURKISH_CHAT, "Soru 2 (kaynak sayfa")):
                args = argparse.Namespace(provider="vllm-stated", english=english, **common)
                with self.subTest(english=english), self.assertRaises(RuntimeError):
                    ask_batch(args, batch, False, None)
                system, user = sent[-1]["messages"]
                self.assertEqual(system["content"], prompts.confidence_system)
                self.assertTrue(user["content"].startswith(prompts.confidence_instruction + "\n\n"))
                self.assertIn(header, user["content"])
        # The Turkish runs' prompts stay as published: their version is unchanged.
        self.assertEqual(PROMPT_VERSION, "254597b8be16")
        self.assertNotIn("Turkish", ENGLISH_CHAT.confidence_system + ENGLISH_CHAT.answer_system + ENGLISH_CHAT.verbal_system)

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

    def test_listed_questions_take_it_and_never_with_another_variant(self) -> None:
        base = ["benchmark_ollama.py", "subq-snap-1.1", "--english", "t.jsonl", "--questions", "kept.txt"]
        for argv in ([*base, "--provider", "subq", "--replace-key-text", "1"], [*base, "--provider", "subq", "--shuffle-options", "1"],
                     [*base[:4], "--provider", "subq"], [*base, "--provider", "vllm-yes-no", "--dont-know"]):
            with self.subTest(argv=argv), mock.patch("sys.argv", argv), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                parse_args()
        for provider in ("subq", "vllm-yes-no", "vllm", "vllm-stated"):
            with mock.patch("sys.argv", [*base, "--provider", provider]):
                self.assertEqual(parse_args().english, Path("t.jsonl"))
        with mock.patch("sys.argv", [*base, "--provider", "subq", "--repeat", "2"]):
            args = parse_args()
            self.assertEqual((args.english, args.repeat), (Path("t.jsonl"), 2))

    def test_a_chat_models_run_records_the_english_chat_prompts(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        translations = self.translations(path.parent, [self.record(1), self.record(2), self.record(3)])
        selection = english_selection(load_questions(path, None, None, None, 0), translations)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "gemini", "http://localhost", 0, 16, "low", None, False,
                                 None, None, False, None, False, english="ab" * 32)
        row = connection.execute("SELECT prompt_version FROM runs WHERE id=?", (identity.run_id,)).fetchone()
        self.assertEqual(row["prompt_version"], ENGLISH_CHAT_PROMPT_VERSION)
        self.assertEqual(len({ENGLISH_CHAT_PROMPT_VERSION, ENGLISH_PROMPT_VERSION, PROMPT_VERSION}), 3)


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
                                  dont_know=True, english=None, dont_know_word="english", perplexity_mode=None)
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


class WebGroundingTests(unittest.TestCase):
    """Perplexity's web grounding (--perplexity-mode web_grounding): the request's `mode`, in runs of their own."""

    bank = DontKnowTests.bank
    GROUNDED = {"answers": {"answer": {"type": "choice", "choice": "B", "probabilities": {label: 0.2 for label in "ABCDE"}}},
                "usage": {"input_tokens": 1500, "output_tokens": 1},
                "search_results": [{"title": "t", "url": "https://example.com/a", "snippet": "s"}]}

    def store(self, connection: sqlite3.Connection, path: Path, mode: str | None, repeat: int | None = None) -> dict:
        selection = load_questions(path, None, None, None, 0)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "pplx-decider-v1.2", path, "perplexity", "https://api.perplexity.ai", 0,
                                 1, False, None, False, None, None, False, repeat, False, perplexity_mode=mode)
        for ordinal, question_ in enumerate(selection.questions):
            raw = json.dumps({"request_id": None, "response": self.GROUNDED})
            store_answers(connection, identity.run_id, [(ordinal, question_)], ["B"], raw, 0.1, 0.1)
        mark_run(connection, identity.run_id, "completed")
        metrics = run_metrics(connection, identity.run_key, path.parent)
        return {"run_key": identity.run_key, "run_id": identity.run_id, "dataset": str(path),
                "dataset_sha256": identity.dataset_sha256, "provider": "perplexity", "model": "pplx-decider-v1.2",
                "thinking": "off", "batch_size": 1, "evaluated": 3, "eligible_total": 3,
                "selection_sha256": identity.selection_sha256, "replace_key_text": None, "repeat": repeat,
                "perplexity_mode": mode, "metrics": metrics, **{key: metrics[key] for key in ("cost_usd",)}}

    def test_the_mode_goes_in_the_request_only_when_set(self) -> None:
        sent = []

        def post(endpoint, payload, *rest):
            sent.append(payload)
            return self.GROUNDED, {}

        question_ = load_questions(self.bank(), None, None, None, 0).questions[0]
        common = {"provider": "perplexity", "jev_url": "https://api.perplexity.ai", "jev_api_key": "k", "model": "pplx-decider-v1.2",
                  "timeout": 1, "dont_know": False, "dont_know_word": "turkish", "english": None}
        with mock.patch("benchmark_ollama.post_json", side_effect=post):
            for mode in (None, "web_grounding"):
                self.assertEqual(ask_batch(argparse.Namespace(perplexity_mode=mode, **common), [question_], False, None)[0], ["B"])
        self.assertNotIn("mode", sent[0])
        self.assertEqual(sent[1], {**sent[0], "mode": "web_grounding"})

    def test_a_grounded_run_is_its_own_run_with_the_search_fee(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        plain = self.store(connection, path, None)
        grounded = self.store(connection, path, "web_grounding")
        repeat = self.store(connection, path, "web_grounding", repeat=2)
        self.assertEqual(len({plain["run_key"], grounded["run_key"], repeat["run_key"]}), 3)
        self.assertEqual(connection.execute("SELECT perplexity_mode FROM runs WHERE id=?", (grounded["run_id"],)).fetchone()[0],
                         "web_grounding")
        # 3 requests of 1,500 input tokens at $0.02 per 1M, and a $0.001 search each when grounded.
        self.assertTrue(math.isclose(plain["cost_usd"], 4500 * 0.02 / 1_000_000, rel_tol=1e-12))
        self.assertTrue(math.isclose(grounded["cost_usd"], 4500 * 0.02 / 1_000_000 + 0.003, rel_tol=1e-12))
        self.assertEqual(grounded["metrics"]["price"]["per_request"], 0.001)
        self.assertIn("web grounding", run_label(grounded))
        self.assertNotIn("web grounding", run_label(plain))
        # A whole-bank grounded run is a setup of its own in the main tables; its repeat is not.
        self.assertTrue(in_main_tables(plain))
        self.assertTrue(in_main_tables(grounded))
        self.assertFalse(in_main_tables(repeat))
        records = {record["run_key"]: record for record in (plain, grounded, repeat)}
        sets = run_repeats(connection, records, path.parent)
        self.assertEqual([item["run_keys"] for item in sets], [[grounded["run_key"], repeat["run_key"]]])
        report = path.parent / "report.md"
        report.write_text("".join(f"<!-- benchmark-result: {json.dumps({**record, 'metrics': None})} -->\n"
                                  for record in (plain, grounded)), encoding="utf-8")
        export_answers(path.parent / "answers.json", report, connection)
        document = json.loads((path.parent / "answers.json").read_text(encoding="utf-8"))
        self.assertEqual([run["perplexity_mode"] for run in document["datasets"][0]["runs"]], [None, "web_grounding"])

    def test_the_grounded_price_is_perplexitys(self) -> None:
        price = WEB_GROUNDING_PRICES["perplexity", "pplx-decider-v1.2"]
        self.assertEqual((price.input, price.per_request, price.source),
                         (0.02, 0.001, "https://docs.perplexity.ai/docs/getting-started/pricing"))
        self.assertEqual(PRICES["perplexity", "pplx-decider-v1.2"].per_request, 0.0)

    def test_the_mode_needs_the_perplexity_provider(self) -> None:
        base = ["benchmark_ollama.py", "pplx-decider-v1.2", "--perplexity-mode", "web_grounding"]
        with mock.patch("sys.argv", [*base, "--provider", "perplexity"]):
            self.assertEqual(parse_args().perplexity_mode, "web_grounding")
        with mock.patch("sys.argv", ["benchmark_ollama.py", "m", "--provider", "perplexity"]):
            self.assertIsNone(parse_args().perplexity_mode)
        for provider in ("pplx-decider", "subq"):
            with self.subTest(provider=provider), mock.patch("sys.argv", [*base, "--provider", provider]), \
                    mock.patch("sys.stderr"), self.assertRaises(SystemExit):
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
                                  dont_know=True, english=Path("t.jsonl"), perplexity_mode=None)
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


class EmptyAndBrokenReplyTests(unittest.TestCase):
    """The project lead's rule on chat replies (bus #3215): an empty reply is asked once more; a broken reply has its
    clearly readable letters read and the rest stay invalid; --rescue applies both to finished runs."""

    bank = DontKnowTests.bank
    LAYOUT = "https://openrouter.ai/api/v1/chat/completions#provider=deepinfra/fp8;answer_layout;max_tokens=65536"

    @staticmethod
    def reply(content: str | None, finish: str = "stop", prompt: int = 100, completion: int = 50) -> dict:
        return {"choices": [{"finish_reason": finish, "message": {"content": content}}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}

    @staticmethod
    def questions(count: int = 3) -> list[Question]:
        options = tuple(Option(label, f"option {label}") for label in "ABCDE")
        return [Question(i, "1. Unit", "1", "", "", "", "", str(i), f"Question {i}?", options, "B", 1, False, None)
                for i in range(1, count + 1)]

    def ask(self, replies: list[dict], answer_layout: bool = True, json_object: bool = False) -> tuple[list, dict, int]:
        """ask_openrouter_chat through ask_batch with post_json returning `replies` in turn: the predictions, the stored
        record and the number of requests sent."""
        sent = []

        def post(*args, **kwargs):
            sent.append(1)
            return copy.deepcopy(replies[len(sent) - 1]), {}

        args = argparse.Namespace(
            provider="openrouter-chat", model="m", timeout=1, english=None, dont_know=False, openrouter_reasoning="high",
            openrouter_order="p", openrouter_require_parameters=False, openrouter_json_object=json_object,
            openrouter_max_tokens=100, openrouter_answer_layout=answer_layout,
        )
        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), \
                mock.patch("sys.stderr"):
            predictions, raw = ask_batch(args, self.questions(), "high", None)
        return predictions, json.loads(raw), len(sent)

    def test_empty_means_finished_normally_with_nothing_or_an_empty_object(self) -> None:
        self.assertTrue(empty_reply(self.reply("")))
        self.assertTrue(empty_reply(self.reply(None)))
        self.assertTrue(empty_reply(self.reply(" {\n } ")))
        self.assertTrue(empty_reply(self.reply("<think>long thought</think>  ")))
        self.assertFalse(empty_reply(self.reply("", finish="length")))
        self.assertFalse(empty_reply(self.reply('{"answers": {}}')))
        self.assertFalse(empty_reply({"error": {"code": 500}}))

    def test_an_empty_reply_is_asked_once_more_and_both_replies_are_kept(self) -> None:
        good = self.reply('{"answers": {"1": {"answer": "B", "confidence": 0.9}, "2": {"answer": "A", "confidence": 0.5}, '
                          '"3": {"answer": "C", "confidence": 0.7}}}', prompt=120, completion=60)
        predictions, record, sent = self.ask([self.reply("", prompt=100, completion=30), good])
        self.assertEqual((predictions, sent), (["B", "A", "C"], 2))
        self.assertEqual(record["response"], good)
        self.assertEqual(record["empty_first_reply"]["usage"], {"prompt_tokens": 100, "completion_tokens": 30})
        # Both requests' tokens count in the run's cost.
        tokens, _ = answer_usage("openrouter-chat", 1, json.dumps(record))
        self.assertEqual((tokens["input_tokens"], tokens["output_tokens"]), (220, 90))

    def test_a_second_empty_reply_stays_empty_and_a_cut_or_broken_reply_is_never_asked_again(self) -> None:
        predictions, record, sent = self.ask([self.reply(""), self.reply("{}")])
        self.assertEqual((predictions, sent), ([None] * 3, 2))
        self.assertEqual(record["empty_first_reply"]["choices"][0]["message"]["content"], "")
        predictions, record, sent = self.ask([self.reply('{"answers": {"1": {"answer": "B", "conf', finish="length")])
        self.assertEqual((predictions, sent), ([None] * 3, 1))
        self.assertNotIn("empty_first_reply", record)
        predictions, _, sent = self.ask([self.reply("I think the answer to 1 is B.")])
        self.assertEqual((predictions, sent), ([None] * 3, 1))

    def test_a_broken_reply_has_its_clearly_readable_letters_read_and_marked(self) -> None:
        # The closing brace is missing (Inkling Small's broken replies, runs 866 and 868); "3" has "confidence" first.
        text = '{"answers": {"1": {"answer": "B", "confidence": 0.9}, "2": {"answer": "A"}, "3": {"confidence": 0.4, "answer": "D"}}'
        predictions, record, sent = self.ask([self.reply(text)])
        self.assertEqual((predictions, sent), (["B", "A", "D"], 1))
        self.assertEqual(record["answers"], {
            "1": {"answer": "B", "confidence": 0.9, "read_from_broken_reply": True},
            "2": {"answer": "A", "confidence": None, "read_from_broken_reply": True},
            "3": {"answer": "D", "confidence": 0.4, "read_from_broken_reply": True},
        })
        # The same reply through the JSON reader (schema or JSON mode), and without the "answers" object (another layout).
        self.assertEqual(self.ask([self.reply(text)], answer_layout=False)[0], ["B", "A", "D"])
        self.assertEqual(self.ask([self.reply(text[len('{"answers": '):])], answer_layout=False)[0], ["B", "A", "D"])

    def test_nothing_else_is_read_from_a_broken_reply(self) -> None:
        # 1 appears twice, 2's letter is not allowed, 3's letter is only in free text; the thinking before </think> holds
        # entries that are never read.
        text = ('<think>"2": {"answer": "C"} "3": {"answer": "E"}</think>{"answers": {"1": {"answer": "B"}, "1": '
                '{"answer": "C"}, "2": {"answer": "V", "confidence": 0.5}, "3": "I would say E"')
        predictions, record, _ = self.ask([self.reply(text)])
        self.assertEqual(predictions, [None] * 3)
        self.assertFalse(any(entry.get("read_from_broken_reply") for entry in record["answers"].values()))

    def test_a_reply_read_as_a_whole_is_not_broken_but_a_letter_without_its_confidence_is_read(self) -> None:
        # The strict layout reader reads it; "V" (MiniMax, run 864) stays invalid; 3 has no confidence and 4 one out of
        # range: both letters are read with none, marked; 5 has another key and stays invalid.
        text = ('{"answers": {"1": {"answer": "B", "confidence": 0.9}, "2": {"answer": "V", "confidence": 0.5}, '
                '"3": {"answer": "C"}, "4": {"answer": "A", "confidence": 1.5}, "5": {"answer": "D", "why": "x"}}}')
        sent = []

        def post(*args, **kwargs):
            sent.append(1)
            return self.reply(text), {}

        args = argparse.Namespace(
            provider="openrouter-chat", model="m", timeout=1, english=None, dont_know=False, openrouter_reasoning="high",
            openrouter_order="p", openrouter_require_parameters=False, openrouter_json_object=False,
            openrouter_max_tokens=100, openrouter_answer_layout=True,
        )
        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), \
                mock.patch("sys.stderr"):
            predictions, raw = ask_batch(args, self.questions(5), "high", None)
        record = json.loads(raw)
        self.assertEqual((predictions, len(sent)), (["B", None, "C", "A", None], 1))
        self.assertNotIn("read_from_broken_reply", raw)
        self.assertEqual(record["answers"]["3"], {"answer": "C", "confidence": None, "read_without_confidence": True})
        self.assertEqual(record["answers"]["4"], {"answer": "A", "confidence": None, "read_without_confidence": True})
        self.assertEqual(record["answers"]["1"], {"answer": "B", "confidence": 0.9})

    def test_rescue_reads_a_letter_without_its_confidence_and_keeps_the_valid_answers(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        selection = load_questions(path, None, None, None, 0)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, "openrouter-chat", self.LAYOUT, 0, 3, "high", None, False,
                                 None, None, False, None, False)
        text = ('{"answers": {"1": {"answer": "B", "confidence": 0.9}, "2": {"answer": "E", "confidence": "high"}, '
                '"3": {"answer": "V", "confidence": 0.5}}}')
        raw = json.dumps({"answers": {"1": {"answer": "B", "confidence": 0.9}, "2": {"answer": None, "confidence": None},
                                      "3": {"answer": None, "confidence": None}}, "response": self.reply(text)})
        store_answers(connection, identity.run_id, list(enumerate(selection.questions)), ["B", None, None], raw, 1.0, 1.0)
        mark_run(connection, identity.run_id, "completed")
        before = connection.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (identity.run_id,)).fetchall()
        with mock.patch("benchmark_ollama.harness_commit", return_value="1" * 40):
            text_out = "\n".join(rescue_runs(connection, [identity.run_id], 1.0, 1, dry_run=False))
        self.assertIn("answers read without a confidence: 1 (from 1 reply)", text_out)
        self.assertIn("invalid after: 1 (letter not allowed 1)", text_out)
        after = connection.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (identity.run_id,)).fetchall()
        self.assertEqual([row["predicted_answer"] for row in after], ["B", "E", None])
        self.assertEqual([(row["predicted_answer"], row["correct"]) for row in after[:1]],
                         [(row["predicted_answer"], row["correct"]) for row in before[:1]])
        self.assertEqual(len({row["raw_response"] for row in after}), 1)
        self.assertEqual(json.loads(after[0]["raw_response"])["answers"]["2"],
                         {"answer": "E", "confidence": None, "read_without_confidence": True})

    def test_the_vllm_path_reads_its_own_answer_shape(self) -> None:
        sent = []

        def post(*args, **kwargs):
            sent.append(1)
            return self.reply('{"answers": {"1": "B", "2": "Z", "3": "C"') if len(sent) > 1 else self.reply(""), {}

        args = argparse.Namespace(provider="vllm", model="m", timeout=1, english=None, dont_know=False, seed=0,
                                  vllm_url="http://localhost")
        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch("sys.stderr"):
            predictions, raw = ask_batch(args, self.questions(), False, None)
        record = json.loads(raw)
        self.assertEqual((predictions, len(sent)), (["B", None, "C"], 2))
        self.assertEqual(record["answers"]["1"], {"answer": "B", "probabilities": None, "read_from_broken_reply": True})
        self.assertIn("empty_first_reply", record)

    def run_with_replies(self, connection: sqlite3.Connection, path: Path, provider: str = "openrouter-chat") -> int:
        """A finished run of the three bank questions, one per request: question 1 answered, question 2 in a broken
        reply, question 3 in an empty reply."""
        selection = load_questions(path, None, None, None, 0)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            identity = start_run(connection, selection, "m", path, provider, self.LAYOUT, 0, 1, "high", None, False,
                                 None, None, False, None, False)
        replies = [
            ("B", self.reply('{"answers": {"1": {"answer": "B", "confidence": 0.9}}}'), {"answer": "B", "confidence": 0.9}),
            (None, self.reply('{"answers": {"1": {"answer": "E", "confidence": 0.8}}'), {"answer": None, "confidence": None}),
            (None, self.reply(""), {"answer": None, "confidence": None}),
        ]
        for ordinal, (question, (letter, reply, answer)) in enumerate(zip(selection.questions, replies)):
            raw = json.dumps({"answers": {str(question.question_id): answer}, "response": reply}, separators=(",", ":"))
            store_answers(connection, identity.run_id, [(ordinal, question)], [letter], raw, 1.0, 1.0)
        mark_run(connection, identity.run_id, "completed")
        return identity.run_id

    def test_rescue_reads_broken_replies_re_asks_empty_ones_once_and_leaves_valid_answers_alone(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        run_id = self.run_with_replies(connection, path)
        before = connection.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
        lines = rescue_runs(connection, [run_id], 1.0, 1, dry_run=True)
        self.assertIn("empty replies it would re-ask once: 1", "\n".join(lines))
        self.assertIn("answers it would read from broken replies: 1 (from 1 reply)", "\n".join(lines))
        self.assertEqual(connection.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall(), before)
        sent = []

        def post(endpoint, payload, *args, **kwargs):
            sent.append(payload)
            return self.reply('{"answers": {"1": {"answer": "C", "confidence": 0.6}}}', prompt=7, completion=3), {}

        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch("benchmark_ollama.harness_commit", return_value="1" * 40), \
                mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), mock.patch("sys.stderr"):
            lines = rescue_runs(connection, [run_id], 1.0, 1, dry_run=False)
        text = "\n".join(lines)
        self.assertIn("2 invalid answers before", text)
        self.assertIn("empty replies re-asked once: 1; came back with answers: 1 (answers given: 1)", text)
        self.assertIn("invalid after: 0 (none)", text)
        # One request, the run's own: its question with the answer layout, the endpoint pin and the output cap.
        self.assertEqual(len(sent), 1)
        self.assertEqual((sent[0]["provider"]["order"], sent[0]["max_tokens"], sent[0]["reasoning_effort"]), (["deepinfra/fp8"], 65536, "high"))
        self.assertIn("Question 3?", sent[0]["messages"][1]["content"])
        self.assertNotIn("response_format", sent[0])
        after = connection.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
        self.assertEqual(tuple(after[0]), tuple(before[0]))
        self.assertEqual([row["predicted_answer"] for row in after], ["B", "E", "C"])
        self.assertEqual([row["correct"] for row in after], [1, 1, 1])
        broken, retried = json.loads(after[1]["raw_response"]), json.loads(after[2]["raw_response"])
        self.assertEqual(broken["response"], json.loads(before[1]["raw_response"])["response"])
        self.assertEqual(broken["answers"]["2"], {"answer": "E", "confidence": 0.8, "read_from_broken_reply": True})
        self.assertEqual(broken["rescued"]["answers_before"], {"2": {"answer": None, "confidence": None}})
        self.assertEqual(retried["empty_first_reply"], json.loads(before[2]["raw_response"])["response"])
        self.assertEqual(retried["rescued"]["harness_commit"], "1" * 40)
        # Run again, nothing is left to do: a re-asked reply is never asked again.
        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch("benchmark_ollama.harness_commit", return_value="1" * 40):
            rescue_runs(connection, [run_id], 1.0, 1, dry_run=False)
        self.assertEqual(len(sent), 1)
        # The report counts both requests of the re-asked question, and what the rule did.
        metrics = run_metrics(connection, connection.execute("SELECT run_key FROM runs WHERE id=?", (run_id,)).fetchone()[0],
                              path.parent)
        self.assertEqual(metrics["requests"], 4)
        self.assertEqual(metrics["invalid_replies"], {
            "invalid_without_rule": 2, "read_from_broken_replies": 1, "read_without_confidence": 0,
            "empty_replies_asked_again": 1, "asked_again_with_answers": 1, "answers_after_asking_again": 1,
            "invalid_by_kind": {},
        })

    def test_rescue_refuses_a_run_it_cannot_re_ask_before_touching_any(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        good = self.run_with_replies(connection, path)
        other = DontKnowTests.store_run(connection, path, False, {i: ("B", {}) for i in (1, 2, 3)})["run_id"]
        before = connection.execute("SELECT * FROM answers ORDER BY run_id, ordinal").fetchall()
        with self.assertRaisesRegex(ValueError, f"run {other}: --rescue cannot re-ask provider 'subq'"), \
                mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}):
            rescue_runs(connection, [good, other], 1.0, 1, dry_run=False)
        self.assertEqual(connection.execute("SELECT * FROM answers ORDER BY run_id, ordinal").fetchall(), before)
        # Its empty reply cannot be re-asked with prompts other than the run's own; nothing is read either.
        with connection:
            connection.execute("UPDATE runs SET prompt_version='older' WHERE id=?", (good,))
        with self.assertRaisesRegex(ValueError, f"run {good}: cannot re-ask its empty replies: asked with prompt version older"):
            rescue_runs(connection, [good], 1.0, 1, dry_run=False)
        self.assertEqual(connection.execute("SELECT * FROM answers ORDER BY run_id, ordinal").fetchall(), before)


class PlainAnswerLineTests(unittest.TestCase):
    """--provider vllm-plain (Ümit, bus #3446 and #3475): one question per request as a plain user message with logic's
    instruction, only the --request-params settings, and the last ANSWER or CEVAP line's letter."""

    PARAMS = {"temperature": 0.6, "max_tokens": 4096, "chat_template_kwargs": {"enable_thinking": True}}
    reply = staticmethod(EmptyAndBrokenReplyTests.reply)
    bank = DontKnowTests.bank

    @staticmethod
    def question(dont_know: bool = False) -> Question:
        options = tuple(Option(label, f"option {label}") for label in "ABCDE")
        if dont_know:
            options = (*options, Option("F", ENGLISH_DONT_KNOW_OPTION))
        prompt = "Body?\n\nOptions:\n" + "\n".join(f"{option.label}. {option.text}" for option in options)
        return Question(7, "1. Unit", "1", "", "", "", "", "7", prompt, options, "B", 1, False, None)

    def ask(self, replies: list[dict], dont_know: bool = False, retry_empty: bool = True) -> tuple[str | None, dict, list]:
        """ask_vllm_plain through ask_batch with post_json returning `replies` in turn: the answer, the stored record and
        the request bodies sent."""
        sent = []

        def post(endpoint, payload, *args, **kwargs):
            sent.append((endpoint, payload))
            return copy.deepcopy(replies[len(sent) - 1]), {}

        args = argparse.Namespace(provider="vllm-plain", model="m", timeout=1, english=Path("en.jsonl"), dont_know=dont_know,
                                  vllm_url="http://localhost:8000/", request_params=self.PARAMS)
        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch("sys.stderr"):
            predictions, raw = ask_batch(args, [self.question(dont_know)], "on", None, retry_empty)
        return predictions[0], json.loads(raw), sent

    def test_the_request_is_the_model_the_user_message_and_the_given_settings_only(self) -> None:
        _, record, sent = self.ask([self.reply("ANSWER: B")])
        endpoint, payload = sent[0]
        self.assertEqual(endpoint, "http://localhost:8000/v1/chat/completions")
        self.assertEqual(payload, {"model": "m", "messages": [{"role": "user", "content": (
            "Solve the following multiple-choice question. On the last line of your reply write only 'ANSWER: X' "
            "(X = A, B, C, D or E).\n\nBody?\n\nOptions:\nA. option A\nB. option B\nC. option C\nD. option D\nE. option E")}],
            **self.PARAMS})
        self.assertEqual(record, {"response": self.reply("ANSWER: B"), "answers": {"7": {"answer": "B"}}})

    def test_the_instructions_are_logics_and_follow_the_question_letters(self) -> None:
        question = self.question(dont_know=True)
        self.assertEqual(plain_prompt(question, True, True).split("\n\n")[0], (
            "Solve the following multiple-choice question. On the last line of your reply write only 'ANSWER: X' "
            "(X = A, B, C, D, E or F). If you do not know the answer, choose I don't know."))
        self.assertEqual(plain_prompt(question, False, True).split("\n\n")[0], (
            "Aşağıdaki çoktan seçmeli soruyu çöz. Yanıtının son satırına yalnızca 'CEVAP: X' yaz (X = A, B, C, D, E veya F). "
            f"{CHAT_DONT_KNOW_SENTENCE}"))
        four = Question(1, "", "", "", "", "", "", "", "Q", tuple(Option(label, label) for label in "ABCD"), "A", 1, False, None)
        self.assertEqual(plain_prompt(four, False, False),
                         "Aşağıdaki çoktan seçmeli soruyu çöz. Yanıtının son satırına yalnızca 'CEVAP: X' yaz "
                         "(X = A, B, C veya D).\n\nQ")
        # Each variant has a prompt version of its own, none another provider's.
        self.assertEqual(len(set(PLAIN_PROMPT_VERSIONS.values())), 4)
        self.assertTrue(set(PLAIN_PROMPT_VERSIONS.values()).isdisjoint(
            {PROMPT_VERSION, ENGLISH_PROMPT_VERSION, ENGLISH_CHAT_PROMPT_VERSION, ENGLISH_DONT_KNOW_CHAT_PROMPT_VERSION}))

    def test_the_reader_takes_the_last_answer_line_of_the_content_only(self) -> None:
        cases = [
            ("valid last line", self.reply("The passage says so.\nANSWER: C"), False, "C"),
            ("two answer lines, the last wins", self.reply("ANSWER: A\nOn reflection:\nANSWER: D"), False, "D"),
            ("bold", self.reply("ANSWER: **B**"), False, "B"),
            ("parenthesised", self.reply("ANSWER: (C)"), False, "C"),
            ("lower case", self.reply("answer: d"), False, "D"),
            ("Turkish line", self.reply("CEVAP: E"), False, "E"),
            ("cut off with a letter", self.reply("ANSWER: B and then", finish="length"), False, None),
            ("F without I don't know", self.reply("ANSWER: F"), False, None),
            ("F with I don't know", self.reply("ANSWER: F"), True, "F"),
            ("no answer line", self.reply("I think it is B."), False, None),
            ("letter outside the options", self.reply("ANSWER: G"), False, None),
        ]
        for name, reply, dont_know, expected in cases:
            with self.subTest(name):
                answer, record, sent = self.ask([reply], dont_know=dont_know)
                self.assertEqual((answer, len(sent)), (expected, 1))
                self.assertEqual(record["answers"], {"7": {"answer": expected}})
        # A server's separate reasoning field is never searched.
        reasoning = {"choices": [{"finish_reason": "stop", "message": {"content": "no line", "reasoning_content": "ANSWER: B"}}]}
        self.assertIsNone(self.ask([reasoning])[0])

    def test_an_empty_reply_is_asked_once_more(self) -> None:
        answer, record, sent = self.ask([self.reply("  \n", prompt=90, completion=20), self.reply("ANSWER: B")])
        self.assertEqual((answer, len(sent)), ("B", 2))
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(record["empty_first_reply"], self.reply("  \n", prompt=90, completion=20))
        tokens, score = answer_usage("vllm-plain", 7, json.dumps(record))
        self.assertEqual((tokens["input_tokens"], tokens["output_tokens"], score), (190, 70, None))
        answer, record, sent = self.ask([self.reply(""), self.reply("")])
        self.assertEqual((answer, len(sent)), (None, 2))
        self.assertEqual(self.ask([self.reply("")], retry_empty=False)[0], None)

    def test_parse_args_takes_only_the_allowed_settings_with_vllm_plain(self) -> None:
        base = ["benchmark_ollama.py", "m", "--provider", "vllm-plain"]
        with mock.patch("sys.argv", [*base, "--request-params", '{"top_k": 20, "seed": 1}']):
            args = parse_args()
        self.assertEqual((args.request_params, args.seed), ({"top_k": 20, "seed": 1}, 0))
        for extra in ([], ["--request-params", '{"response_format": {}}'], ["--request-params", "[1]"],
                      ["--request-params", "{}", "--seed", "3"], ["--request-params", "{}", "--batch-size", "2"]):
            with self.subTest(extra), mock.patch("sys.argv", [*base, *extra]), mock.patch("sys.stderr"), \
                    self.assertRaises(SystemExit):
                parse_args()
        with mock.patch("sys.argv", ["benchmark_ollama.py", "m", "--provider", "vllm", "--request-params", "{}"]), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args()

    def start(self, connection: sqlite3.Connection, path: Path, params: str):
        selection = load_questions(path, None, None, None, 0)
        with mock.patch("benchmark_ollama.harness_commit", return_value="0" * 40):
            return selection, start_run(connection, selection, "m", path, "vllm-plain", "http://localhost:8000", None, 1,
                                        "default", None, False, None, None, False, None, False, request_params=params)

    def test_the_settings_are_part_of_the_identity_and_an_unfinished_run_keeps_its_own(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        _, first = self.start(connection, path, '{"temperature":0}')
        row = connection.execute("SELECT seed,request_params FROM runs WHERE id=?", (first.run_id,)).fetchone()
        self.assertEqual(tuple(row), (0, '{"temperature":0}'))
        self.assertEqual(self.start(connection, path, '{"temperature":0}')[1], first)
        with self.assertRaisesRegex(ValueError, f"run {first.run_id} of this setup is unfinished"):
            self.start(connection, path, '{"temperature":1}')
        mark_run(connection, first.run_id, "completed")
        self.assertNotEqual(self.start(connection, path, '{"temperature":1}')[1].run_key, first.run_key)

    def test_rescue_re_asks_only_empty_replies_with_the_runs_settings(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        selection, identity = self.start(connection, path, '{"max_tokens":64}')
        replies = [("B", self.reply("ANSWER: B")), (None, self.reply("ANSWER: B and", finish="length")), (None, self.reply(""))]
        for ordinal, (question, (letter, reply)) in enumerate(zip(selection.questions, replies)):
            raw = json.dumps({"response": reply, "answers": {str(question.question_id): {"answer": letter}}})
            store_answers(connection, identity.run_id, [(ordinal, question)], [letter], raw, 1.0, 1.0)
        mark_run(connection, identity.run_id, "completed")
        sent = []

        def post(endpoint, payload, *args, **kwargs):
            sent.append(payload)
            return self.reply("Thinking.\nCEVAP: C"), {}

        with mock.patch("benchmark_ollama.post_json", side_effect=post), mock.patch("benchmark_ollama.harness_commit", return_value="1" * 40):
            text = "\n".join(rescue_runs(connection, [identity.run_id], 1.0, 1, dry_run=False))
        self.assertIn("empty replies re-asked once: 1; came back with answers: 1 (answers given: 1)", text)
        self.assertIn("invalid after: 1 (cut off 1)", text)
        self.assertEqual(sent, [{"model": "m", "messages": [{"role": "user", "content": plain_prompt(selection.questions[2], False, False)}],
                                 "max_tokens": 64}])
        after = connection.execute("SELECT predicted_answer,raw_response FROM answers WHERE run_id=? ORDER BY ordinal",
                                   (identity.run_id,)).fetchall()
        self.assertEqual([row["predicted_answer"] for row in after], ["B", None, "C"])
        self.assertEqual(json.loads(after[2]["raw_response"])["empty_first_reply"], self.reply(""))


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


class LocalCostTests(unittest.TestCase):
    """Every setup on our GPUs is estimated: a list price for the same model or weights, else its GPU time."""

    store = OptionWordTests.store
    bank = DontKnowTests.bank

    def test_a_setup_has_one_source_of_its_cost(self) -> None:
        self.assertEqual(set(GPU_TIME) & set(PRICES), set())
        for price in PRICES.values():
            if price.applies_to == "weights":
                self.assertIn("'s list price for the same weights (", price.basis)

    def test_the_gpu_rate_is_runpods_secure_cloud_price(self) -> None:
        self.assertEqual((GPU_RATE.usd_per_gpu_hour, GPU_RATE.source, GPU_RATE.date), (2.49, "https://www.runpod.io/pricing", "2026-11-05"))
        self.assertTrue(math.isclose(GPU_RATE.cost(1800, 2), 2.49, rel_tol=1e-12))

    def test_a_gpu_time_setup_costs_its_request_time_on_its_gpus(self) -> None:
        path = self.bank()
        connection = open_result_database(path.parent / "results.sqlite")
        self.addCleanup(connection.close)
        answers = {1: ("B", OptionWordTests.spread("B", 0.6, "ABCDE")), 2: ("A", OptionWordTests.spread("A", 0.9, "ABCDE")),
                   3: ("C", OptionWordTests.spread("C", 0.8, "ABCDE"))}
        plain = self.store(connection, path, answers)["metrics"]
        self.assertNotIn("cost_usd", plain)
        with mock.patch.dict("benchmark_ollama.GPU_TIME", {("subq", "m"): 2}):
            metrics = self.store(connection, path, answers, repeat=2)["metrics"]
        # Three requests of 0.1 s each, one after another, on two GPUs.
        self.assertTrue(math.isclose(metrics["timed_seconds"], 0.3, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["cost_usd"], 0.3 / 3600 * 2 * 2.49, rel_tol=1e-9))
        self.assertEqual((metrics["price"]["applies_to"], metrics["price"]["gpus"], metrics["price"]["usd_per_gpu_hour"]), ("gpu", 2, 2.49))
        self.assertNotIn("rates", metrics["price"])



if __name__ == "__main__":
    unittest.main()

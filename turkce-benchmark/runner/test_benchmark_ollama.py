import json
import math
import unittest

from benchmark_ollama import (
    PRICES,
    Option,
    Question,
    answer_usage,
    letter_probabilities,
    option_probabilities,
    parse_ollama_content,
    regrade,
    replace_key_text,
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


if __name__ == "__main__":
    unittest.main()

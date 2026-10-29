# Benchmark runner

The code that ran the published configurations and built the question bank, copied from the benchmark's
working folder by `../sync_runner.sh`. The question bank itself is not here: the questions come from a
commercial book and cannot be shared. Anyone who owns the book can rebuild a bank in the same format
(below) and run every configuration against it.

| File | What it does |
|---|---|
| `benchmark_ollama.py` | The runner: asks the questions, stores every answer, writes the report |
| `benchmark_metrics.py` | The metrics (the same file as `../benchmark_metrics.py`) |
| `cascade_pipeline.py` | Plans a routing (cascade) run from two stored runs |
| `extract_questions_text.py`, `extract_questions.py`, `vision_ocr.py` | Extract a question bank from a PDF |
| `audit_questions.py` | Flags questions with lost markup and disputed keys |
| `repair_questions.py` | Builds the repaired bank and its review pages |
| `osym_bank.py` | Finishes a bank extracted from an ÖSYM exam booklet (the 2026 exam check) |
| `test_benchmark_metrics.py`, `test_benchmark_ollama.py` | Unit tests |
| `run_*.sh` | One script per published configuration; `run_experiments.sh` holds the repeats and routing runs |
| `pipeline/` | The two routing plans the routing runs used (question IDs only) |

Left out: `run_generate_questions.sh` and `extract_pegem.py` (a different book, never benchmarked),
`run_quiz.sh` (an Ollama run that is not published) and `vision_ocr.swift` (macOS OCR for scanned
books, `--ocr-backend vision`, not used for this book). The small servers that put GLiNER, Clef,
Metask-Jev and Laya behind the decision request are not included either; the
[decision servers](#self-hosted-decision-servers) section gives the request they must answer.

## Setup

- **Python 3.10 or newer.** Every script uses only the standard library; there is nothing to install
  with pip. Pillow is optional (the extractor crops answer strips with it, else with `ffmpeg`).
- **Poppler** (`pdftotext`, `pdftoppm`, `pdfinfo`) for extracting and repairing a bank.
- **Work inside this folder.** The scripts read and write next to themselves: the bank
  `questions.sqlite` (as extracted) and `questions-v2.sqlite` (repaired, what the run scripts use), the
  answer store `benchmark-results.sqlite`, the report `benchmark-results.md`, and `repair/`.

```bash
python3 -m unittest test_benchmark_metrics test_benchmark_ollama   # needs no bank
./benchmark_ollama.py --help
```

## The question bank

**Source:** Paraf Yayınları, *TYT IQ Türkçe Soru Kütüphanesi* (ISBN 978-625-7423-18-2; the imprint
gives © 2022 and the code IX-II, no edition number). The bank was built from a 432-page PDF with SHA-256
`0257428afa660352cc7be8285a73eaff31a62d9d47fe30d6c9c8b30460ec11ea`.

**What the runner reads.** A SQLite file with a `benchmark_questions` view (created by the
extractor), read in the order `unit_number`, `source_page_start`, `question_id`:

| Column | Use |
|---|---|
| `question_id` | The question's ID in every stored answer and in `--questions` lists |
| `unit_number`, `unit_title` | Units 1–6 count as reading, 7–20 as grammar; `--unit` selects by either |
| `section_title`, `test_type`, `test_number`, `question_number`, `source_page_start` | Stored with each answer |
| `passage_text`, `passage_description`, `passage_markdown` | A shared passage, shown above the question |
| `question` | The question text (questions without one are skipped) |
| `choices_json` | `[{"label": "A", "text": "…", "visuals": [{"description", "markdown", "dot"}]}, …]`, at least two options |
| `visuals_json` | The question's figures as text: `[{"description", "markdown", "dot"}, …]` |
| `answer` | The key, one of the option letters (questions without one are skipped) |
| `complete` | Questions with `0` are skipped |
| `requires_image`, `image_path` | Questions that need their page image; skipped unless the model reads images |
| `status` | `verified`, `suspect`, `excluded` or empty; `excluded` questions are skipped and not graded |

The report grades every stored answer against the bank as it stands now, from the tables
`questions` (`id`, `printed_number`, `passage_id`, `answer`) and `question_status` (`question_id`,
`status`). A run is tied to its bank by the file's SHA-256, so a rebuilt bank gives new runs.

**Matching the published answers.** `../answers.json` lists every question's ID, unit, page,
printed number, passage and status. A rebuilt bank numbers its questions in extraction order, so match
questions by page and printed number, which are unique.

### Rebuilding the bank from the book

1. **Extract** (text first: deterministic parsing of the PDF's text layer, a text model only for
   ambiguous blocks, then a vision model for questions whose figures or underlining need the page).
   Pages 9 onward hold the questions. Any OpenAI-compatible server works (`--base-url` or
   `LOCAL_LLM_BASE_URL`); the published bank used `gpt-oss:120b` and `qwen3.6:27b` on Ollama:

   ```bash
   ./extract_questions_text.py BOOK.pdf --db questions.sqlite --base-url http://HOST:11434/v1 \
     --text-model gpt-oss:120b --no-vision -v
   ./extract_questions_text.py BOOK.pdf --db questions.sqlite --base-url http://HOST:11434/v1 \
     --vision-model qwen3.6:27b --vision-only -v
   ```

   Both resume where they stopped. `extract_questions.py` is the whole-page vision extractor the
   text-first one builds on; it also has `--replay-stored` to rebuild pages from stored responses.
2. **Reference runs.** The audit marks a key as suspect when GPT-6 Astra (low), Claude Opus 5.5 (low)
   and Claude Sonnet 5.5 (high) agree on another option, so it needs those three complete runs on
   `questions.sqlite` (the commands of `run_openai.sh`, `run_claude_opus.sh` and
   `run_claude_sonnet_high.sh` with `--data questions.sqlite`).
3. **Audit:** `./audit_questions.py` writes `repair/flags.csv`: questions that refer to underlined or
   numbered words without the marking, Roman numerals stuck to words, and the suspect keys.
4. **Repair** into `questions-v2.sqlite` (same question IDs). `transcribe` asks a vision model for a
   corrected transcription of each flagged question from its page crop (default: `gemma-4-31B-it` at
   `REPAIR_ENDPOINT`; `--endpoint`, `--model`). A person then checks every proposal on the review
   page against the book, sets each question's status, and downloads the decisions:

   ```bash
   ./repair_questions.py init                          # copy questions.sqlite to questions-v2.sqlite
   ./repair_questions.py transcribe --propose          # proposals, thinking on
   ./repair_questions.py transcribe --mode direct      # a second transcription to compare
   ./repair_questions.py sheet                         # writes repair/review.html
   ./repair_questions.py apply decisions-questions-v2.json
   ./audit_questions.py --data questions-v2.sqlite --output repair/flags-v2.csv
   ```

   The PDF must sit next to the bank, unchanged. The published bank ends with 493 `verified`, 12
   `suspect` and 12 `excluded` questions; `../answers.json` gives each question's status, so the
   same questions can be marked (`--work DIR sheet --question ID …` builds a page for chosen questions).

## Running the configurations

Each `run_*.sh` script runs one configuration over every eligible question of `questions-v2.sqlite`.
A run resumes when started again (`--restart` discards it). The report is rewritten after each run;
`./benchmark_ollama.py --refresh-report` recomputes it from the stored answers and
`./benchmark_ollama.py --export-answers FILE` writes every run's answers without question text. For a
first test, add `--sample 100 --seed 0` to a script's command.

**Run records.** A new run records the code and the prompts behind it. `prompt_version` is the first 12 hex
digits of the SHA-256 of the prompt templates (`answers.json` `prompts`, as compact JSON with sorted keys).
`harness_commit` is the published commit that holds this exact `benchmark_ollama.py`: the checkout's `HEAD`
when you run from an unchanged checkout of the repository, or else the newest pushed commit of the clone that
`HARNESS_REPO` names with an identical copy of the file. A new run stops when neither exists, so publish a
changed runner before using it. A resumed run keeps its own record and stops when the prompts have changed;
`--restart` answers it again and records the current ones. `answers.json` gives both fields for each run.
This folder holds the current runner, which can be newer than the commit a run recorded: since `0fbd97b08`, the commit
runs 274 to 278 recorded, it has gained GPT-6.1 Terra's list price and takes self-hosted addresses from environment
variables. To repeat a run exactly, check out the commit it names.

**Addresses.** Self-hosted servers have no built-in address. Each one comes from an environment variable (as
`http://HOST:PORT`) or a flag; a run whose server is unset stops before its first request and names both.

| Where | Environment variable | Flag |
|---|---|---|
| `--provider ollama` | `OLLAMA_URL` | `--ollama-url` |
| `--provider vllm`, `vllm-stated`, `vllm-yes-no`, `vllm-verbal`, `vllm-vote` | `VLLM_URL` | `--vllm-url` |
| `--provider open-jev`, `laya`, `gliner`, `clef`, `metask`, `cygnet`, `winnow` | `OPEN_JEV_URL`, `LAYA_URL`, `GLINER_URL`, `CLEF_URL`, `METASK_URL`, `CYGNET_URL`, `WINNOW_URL` | `--jev-url` |
| `--provider strands`, `pplx-decider`, `glide`, `vllm-sr`, `onejev`, `d3-server` | `STRANDS_URL`, `PPLX_DECIDER_URL`, `GLIDE_URL`, `VLLM_SR_URL`, `ONEJEV_URL`, `D3_SERVER_URL` | `--jev-url` |
| `run_clef_flash.sh`, `run_gliner_decide.sh`, `run_laya_multilingual.sh` | `CLEF_FLASH_URL`, `GLINER_DECIDE_URL`, `LAYA_MULTILINGUAL_URL` | |
| `run_pplx_decider_v1_2.sh`, `run_pplx_decider_flash_v1_2.sh`, `run_glide_v1_2.sh` | `PPLX_DECIDER_V1_2_URL`, `GLIDE_V1_2_URL` | |
| `run_gemma.sh`, `run_gemma_one.sh`, `run_deepseek*.sh`, `run_glm*.sh`, `run_erk.sh`, `run_qwen3_14b.sh` | `GEMMA_URL`, `DEEPSEEK_URL`, `GLM_URL`, `ERK_URL`, `QWEN3_14B_URL` | |
| `run_experiments.sh`, `run_fresh.sh` | `GEMMA_URL`, `DEEPSEEK_URL`, `QWEN_URL`, `OPEN_JEV_URL`, `ERK_URL`, `QWEN3_14B_URL` | |
| `run_jev.sh`, `run_jev_114.sh` and the Jev lanes | `JEV_KEY_FILE` (a file holding the key) | |
| `extract_questions*.py` | `LOCAL_LLM_BASE_URL` (default: the local LM Studio or Ollama port) | `--base-url` |
| `repair_questions.py transcribe` | `REPAIR_ENDPOINT` | `--endpoint` |

### Subscription command-line tools

| Script | Configuration |
|---|---|
| `run_openai.sh`, `run_openai_sol.sh`, `run_openai_luna.sh` | GPT-6 Astra, GPT-6.1 Sol, GPT-6 Luna, low reasoning |
| `run_claude_opus.sh`, `run_claude_sonnet.sh`, `run_claude_sonnet_high.sh` | Claude Opus 5.5 low, Sonnet 5.5 low and high effort |
| `run_openai_one.sh`, `run_openai_sol_one.sh`, `run_claude_opus_one.sh`, `run_claude_sonnet_high_one.sh` | GPT-6 Astra and GPT-6.1 Sol low, Claude Opus 5.5 low, Sonnet 5.5 high, one question per request |
| `run_claude_fable_high.sh` | Claude Fable 5.1, high effort |

- **OpenAI** runs through the Codex CLI signed in with ChatGPT (`codex login`); the provider refuses
  API-key sign-in and removes `OPENAI_API_KEY` from Codex's environment. Each request replaces Codex's
  instructions with the benchmark's and turns off web search and every tool it can (each stored answer
  keeps Codex's events, so any tool call shows). The published runs used Codex 0.159.
- **Claude** runs through Claude Code signed in with a Claude subscription (`claude auth login`;
  `claude auth status` must show a claude.ai login). API keys and base-URL overrides are removed from
  its environment; tools, settings and MCP servers are off.

The main runs send 16 questions per request, the `_one` scripts one; each reply is constrained to a letter
and a 0–1 confidence per question. `--codex-bin` and `--claude-bin` point at other executables.

### Hosted APIs

| Script | Configuration | Key |
|---|---|---|
| `run_gemini.sh`, `run_gemini_high.sh`, `run_gemini_one.sh` | Gemini 3.8 Flash (low thinking; high with 4 requests at a time; low with one question per request) | `GEMINI_API_KEY` |
| `run_perplexity.sh` | Perplexity Decider 27B v1 | `PERPLEXITY_API_KEY` |
| `run_perplexity_v1_1.sh` | Perplexity Decider 27B v1.1 (add `--repeat N` for repeats 2–5) | `PERPLEXITY_API_KEY` |
| `run_jev.sh` | TypeSafe Jev 1.13.0 | `JEV_API_KEY` or `TYPESAFE_API_KEY` |
| `run_jev_114.sh` | TypeSafe Jev 1.14.0 (repeats 2–5: the `jev-114` lane of `run_experiments.sh`) | `JEV_API_KEY` |
| `run_liquid_d1.sh` | Liquid AI d1 | `LIQUID_API_KEY` |
| `run_d1_ultra.sh` | Liquid AI d1-ultra (add `--repeat N` for repeats 2–5) | `LIQUID_API_KEY` |
| `run_glide.sh` | Fastino GLiDE, 4 requests at a time (add `--repeat N` for repeats 2–5) | `FASTINO_API_KEY` |
| `run_celeris.sh` | Celeris-1 Decision (`celeris-1-decision`; add `--repeat N` for repeats 2–5) | `CELERIS_API_KEY` |
| `run_subq.sh` | SubQ Snap Preview (`subq-snap-preview`, public preview; add `--repeat N` for repeats 2–5) | `SUBQ_API_KEY` |
| `run_meragpt.sh` | meraGPT Decider 1 (`decider-1`; add `--repeat N` for repeats 2–5) | `MERAGPT_API_KEY` |
| `run_microsoft_decision_1.sh` | Microsoft-Decision-1 via OpenRouter (`microsoft/microsoft-decision-1`; add `--repeat N` for repeats 2–5) | `OPENROUTER_API_KEY` |
| `run_mercury_decide.sh` | Inception Mercury Decide via OpenRouter (`inception/mercury-decide`, the paid listing; add `--repeat N` for repeats 2–5) | `OPENROUTER_API_KEY` |
| `run_openrouter_kimi.sh` | Kimi K3.1 Pro via OpenRouter's chat API, pinned to Moonshot AI's endpoint (`moonshotai/mxfp4`), reasoning_effort none | `OPENROUTER_API_KEY` |
| `run_openrouter_glm.sh` | GLM-5.3 via OpenRouter's chat API, pinned to Fireworks with required parameters, reasoning_effort low | `OPENROUTER_API_KEY` |
| `run_xai_grok_high.sh` | Grok 4.7 through xAI's Responses API with a SuperGrok subscription login, reasoning effort high, 4 requests at a time | OMP's `xai-oauth` login (`omp token xai-oauth`) |
| `run_openai_decisions.sh` | GPT-6 Luna through OpenAI's Decisions API (public beta), 4 requests at a time | `OPENAI_API_KEY` (an API key with billing) |

`run_jev.sh` and `run_jev_114.sh` (and the `jev` and `jev-114` lanes of `run_experiments.sh`) read the key from the
file `JEV_KEY_FILE` names; `run_glide.sh` reads it from `$HOME/.config/fastino/key`, `run_celeris.sh` from
`$HOME/.config/celeris/key`, `run_subq.sh` from `$HOME/.config/subq/key`, `run_d1_ultra.sh` from
`$HOME/.config/liquid/key` and `run_meragpt.sh` from `$HOME/.keys` when their variable is unset; put the key there,
or run the script's command with the variable set. The decision APIs get one question
per request: the question and options as `state`, and one `choice` question with the option letters
as criteria. Rate limits and server errors are retried.

Perplexity's Decisions API now answers requests that name `pplx-decider-v1-27b` or `pplx-decider-v1.1-27b` with v1.2
(its pricing page and changelog, read 17 October 2026), so `run_perplexity.sh` and `run_perplexity_v1_1.sh` no longer
reach those models. Every stored answer of their published runs names the model asked for, and the open weights still
serve both. Decider v1.2 and Decider Flash v1.2 run from their released checkpoints on our GPUs (Self-hosted decision
servers, below). Through OpenRouter (`run_microsoft_decision_1.sh`, `run_mercury_decide.sh`), the request time includes
OpenRouter's own time.

`--provider openrouter-chat` sends the chat models' prompt and answer schema through OpenRouter's chat completions,
pinned to the one provider endpoint the run names (`--openrouter-order`) with fallbacks off, temperature 1.0 and
OpenRouter's usage accounting, which records each request's billed cost.

### vLLM and SGLang

| Script | Configuration | Served model |
|---|---|---|
| `run_gemma.sh`, `run_gemma_one.sh` | Gemma 4 31B, vLLM, FP8 weights and KV cache (16 questions per request; one) | `gemma-4-31B-it` |
| `run_deepseek.sh`, `run_deepseek_thinking.sh` | DeepSeek-V4.1-Flash on SGLang (4 GPUs), thinking off and on | `deepseek-v4.1-flash` |
| `run_glm.sh`, `run_glm_thinking.sh` | GLM-5.3-Flash on TensorFold (4 GPUs), thinking off and on, stated confidence | `glm-5.3-flash` |
| `run_qwen3_14b.sh`, `run_erk.sh` | Qwen3-14B and Erk-14B, vLLM, BF16 | `qwen3-14b`, `erk-14b` |
| `run_qwen_yes_no.sh`, `run_qwen_verbal.sh` | Qwen3.8-27B, vLLM, BF16: yes/no scoring, stated confidence | `qwen38-27b-bf16` |
| `run_qwen_thinking_low.sh` | Qwen3.8-27B, vLLM, BF16: reasoning on at the chat template's low effort (`--vllm-reasoning-effort low`), 16 questions per request, 4 at a time | `qwen38-27b-bf16` |

The model argument must be the served model name. `--provider vllm` sends 16 questions per request
with thinking off, temperature 0 and seed 0, and reads each answer letter's probabilities from the
token log probabilities (`--vllm-thinking` lets the model think first; the published run used
`--concurrency 8` and a 60-minute timeout). SGLang serves the same API. `--provider vllm-stated` sends the same
request with the hosted models' prompt and schema, a letter and a stated confidence per question, for a server
that returns no token probabilities: TensorFold, which serves GLM-5.3-Flash with Mia's AI Lab's EXL3 checkpoint
(revision `78353f1f`; routed experts at 4 bits, dense layers and KV cache converted to FP8 at load). The 14B pair
ran in `vllm/vllm-openai:v0.30.0`, pinned to the benchmarked revisions:

```bash
docker run -d --name qwen3-14b-vllm --network host --ipc host --gpus device=GPU \
  --entrypoint vllm vllm/vllm-openai:v0.30.0 serve Qwen/Qwen3-14B \
  --revision 40c069824f4251a91eefaf281ebe4c544efd3e18 --served-model-name qwen3-14b \
  --host HOST --port PORT --dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.85
# Erk-14B: the same with ecloudtech/Erk-14B, --revision 8584b14a829d5cc803bc227f44e9012e36e8ad04
# and --served-model-name erk-14b
```

### Self-hosted decision servers

| Script | Configuration | Server |
|---|---|---|
| `run_open_jev.sh` | Open-Jev 27B v1.1 | [Open-Jev](https://github.com/Zefan-Cai/Open-Jev)'s `python -m jev.server`, `--batch-size 8` |
| `run_cygnet.sh` | Cygnet | [cygnet-recipe](https://github.com/blockbrain-ai/cygnet-recipe) `shim/decision_server.py` over vLLM 0.30.0 |
| `run_winnow.sh` | Winnow-12B, Q8_0 | [winnow-inference](https://github.com/EldanRing/winnow-inference) Docker image |
| `run_laya.sh`, `run_laya_multilingual.sh` | Laya, Laya multilingual | `servers/laya_server.py` at `/v1/predict`, one server each |
| `run_gliner.sh`, `run_gliner_decide.sh` | GLiNER2.5 Multi (base), GLiNER2.5-multi-Decide | `servers/gliner_server.py`, one server each (`--model-dir` and `--model-name` select the Decide checkpoint) |
| `run_clef.sh` | Clef | `servers/clef_server.py`: Clef's `systemone()` behind a server |
| `run_metask.sh` | Metask-Jev 4B | `servers/metask_server.py`: the vendor's `jev_scorer.score` behind a server |
| `run_clef_flash.sh` | Clef-flash | `servers/clef_flash_server.py`: the Clef server with the Clef-flash release (`Cloudflare/clef-flash` at `fde727a`) |
| `run_strands.sh` | Strands Decider 2B | `servers/strands_server.py`: starts the `strands-decider` package's own System One server (commit `3e94e9d`) with `StrandsAgents/strands-decider-2B-hobson-v21` at `2b52a62` |
| `run_pplx_decider_v1_2.sh`, `run_pplx_decider_flash_v1_2.sh` | Perplexity Decider v1.2, Decider Flash v1.2 (add `--repeat N` for repeats 2–5) | `servers/pplx_decider_server.py`: the `pplx_decider` package the checkpoints ship, on its reference path, one request at a time, with only the checkpoint's `requirements.txt` installed; `perplexity-ai/pplx-decider-v1.2` at `225c913` and `perplexity-ai/pplx-decider-flash-v1.2` at `6d771ad`, one at a time on a DGX Spark (GB10) (the scripts pass `--jev-url`) |
| `run_glide_v1_2.sh` | Fastino GLiDE v1.2 (add `--repeat N` for repeats 2–5) | the server its checkpoint ships (`python -m glide.server`), `fastino/GLiDE` at `a7e4589`, in a `vllm/vllm-openai:v0.30.0` container with `flash-linear-attention==0.5.2`, one request at a time on a DGX Spark (GB10) (the script passes `--jev-url`) |

Cygnet and Winnow were started as their authors describe:

```bash
docker run -d --name cygnet-vllm --network host --ipc host --gpus device=GPU \
  --entrypoint vllm vllm/vllm-openai:v0.30.0 serve google/gemma-4-12B-it \
  --revision 707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7 --served-model-name cygnet \
  --host HOST --port PORT --max-model-len 16384 --gpu-memory-utilization 0.90
SHIM_VLLM=http://HOST:PORT/v1/chat/completions SHIM_MODEL=cygnet SHIM_TEMPERATURE=3.4 \
  CYGNET_PORT=SHIM_PORT python3 shim/decision_server.py      # in the cygnet-recipe checkout (3cf591c)
# image built with the Dockerfile of winnow-inference at d4631fb; models/ holds the Q8_0 GGUF it pins
docker run -d --name winnow --gpus device=GPU -p HOST:PORT:PORT -v "$PWD/models:/models:ro" \
  winnow-inference:d4631fb --target q8 --text-only --context 8192 --decision-context 8192 \
  --decision-parallel 4 --chat-parallel 1 --cache q8_0 --head selected --pipeline optimized \
  --memory auto --alias winnow-12b
```

Every server takes the decision request the hosted decision APIs take, `POST /v1/systemone` (Laya:
`/v1/predict`):

```json
{"model": "…", "state": "question and options",
 "questions": {"answer": {"type": "choice", "instructions": "…", "criteria": {"A": "option text", "…": "…"}}}}
```

and must answer `{"answers": {"answer": {"choice": "A", "probabilities": {"A": 0.7, …}}}, "usage":
{"input_tokens": …, "output_tokens": …}}`. The chosen option's probability is the answer's score.
Open-Jev and Laya get no `model` field. `servers/` holds the seven wrappers used for the published runs,
each copied next to its model's checkpoint and virtual environment (`model/` beside the script, or the checkpoint
given with `--checkpoint`; each file's docstring gives its command). They only translate this request for the
model; the page's Method section describes how each was read out.

### Repeats, routing and the vote share

`run_experiments.sh LANE` runs one lane; lanes can run side by side.

- `gemma-sample`, `astra-sample`, `opus-sample`, `sonnet-high-sample`, `deepseek-sample`,
  `deepseek-thinking-sample`: five runs on one fixed 200-question sample, 16 questions per request.
- `astra-one`, `gemma-one`: the same sample with one question per request.
- `jev`, `decider` (Decider v1), `d1`, `open-jev`, `qwen-yes-no`, `qwen-stated`: repeats 2–5 of the whole-bank
  run. Decider v1.1's, GLiDE's and Celeris-1 Decision's repeats come from `run_perplexity_v1_1.sh`, `run_glide.sh`
  and `run_celeris.sh` with `--repeat N`.
- `qwen-vote`: Qwen3.8-27B's stated-confidence request sampled 10 times per question.
- `astra-passed`, `astra-held-out`, `sonnet-high-passed`, `sonnet-high-held-out`: the routing runs,
  the frontier configuration on the questions Decider v1 passes on and on the whole held-out half,
  from the plans in `pipeline/`. `./cascade_pipeline.py NAME --decision RUN --frontier RUN --seed 1
  --tolerance 0.5` makes a new plan from two stored runs.
- `sol-held-out`, `flash-held-out`: GPT-6.1 Sol and Gemini 3.8 Flash alone on the same held-out half,
  for a cost comparison with the routing runs on the same questions.

`REPEATS="4 5"` limits a lane to some repeats; `RETRIES` and `RETRY_WAIT` restart a failed run.

`run_swap.sh LANE…` runs the swap test: each question's correct option shows the text of a fixed random wrong
option (`--replace-key-text 1`, as GPT-6 Astra's run 56), so no option is right and two letters show the same
text. Each lane is one model with the settings of its run on the book: `d1-ultra`, `jev-1.14`, `glide`,
`decider-v1.2` and `decider-flash-v1.2`. The report counts, by kind of option, the picks of the original letter, of
the twin and of the rest; these runs stay out of the leaderboard.

### The 2026 exam check

`run_fresh.sh LANE…` runs configurations on the 40 Türkçe questions of ÖSYM's 2026 TYT, whose booklet and key ÖSYM
publishes: one per lane, each with the settings of its run on the book (the lanes are listed at the top of the
script). The bank is built like the book's, with `osym_bank.py` to merge the sections,
set the question boxes and read the key page:

```bash
./extract_questions.py fresh/yks_tyt_2026_kitapcik.pdf --db fresh/tyt-2026-extracted.sqlite \
  --base-url http://HOST:PORT/v1 --model gemma-4-31B-it --pages 3-16 -v
./osym_bank.py fresh/tyt-2026-extracted.sqlite --title "2026-TYT Türkçe Testi" --key-page 45 --test TÜRKÇE
./repair_questions.py --v2 fresh/tyt-2026.sqlite --work fresh/review init --v1 fresh/tyt-2026-extracted.sqlite
./repair_questions.py --v2 fresh/tyt-2026.sqlite --work fresh/review transcribe --all --propose --max-tokens 16384
./repair_questions.py --v2 fresh/tyt-2026.sqlite --work fresh/review transcribe --all --mode direct
./repair_questions.py --v2 fresh/tyt-2026.sqlite --work fresh/review sheet
./repair_questions.py --v2 fresh/tyt-2026.sqlite --work fresh/review apply DECISIONS.json
./run_fresh.sh d1-ultra jev-1.14 glide decider-v1.2 decider-flash-v1.2
```

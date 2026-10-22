//! The results page's graphs, drawn with ratatui widgets.
//!
//! Each [`Figure`] draws into a ratatui buffer through a [`TestBackend`] ([`render`]). The buffer's
//! text is the figure's insta snapshot (`tests/snapshots.rs`), and [`svg::buffer_to_svg`] turns the
//! same buffer into the light and dark SVGs the page shows (`src/main.rs`). The sharing images come from `build_page.py`.
//!
//! Every number a figure prints comes from `results.json`, and which runs are decision models from the page's
//! `page_config.json` (the lists its tables and charts read); the code holds only the run lists, the wording and the
//! layout.

pub mod svg;

use std::cmp::Reverse;
use std::collections::HashMap;
use std::error::Error;
use std::path::Path;

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::style::{Color, Stylize};
use ratatui::symbols::Marker;
use ratatui::text::{Line, Span};
use ratatui::widgets::canvas::{Canvas, Context, Line as Segment};
use ratatui::widgets::{Paragraph, Widget};
use serde::Deserialize;

/// The part of the page's `results.json` the figures use.
#[derive(Debug, Deserialize)]
pub struct Results {
    /// The results snapshot's id: the SVGs carry it in their metadata.
    pub results_version: String,
    /// The scored questions: the denominator of every accuracy.
    pub questions: u32,
    /// The page's fixed confidence cutoff ("our rule").
    pub sure_threshold: f64,
    pub units: Vec<Unit>,
    pub runs: Vec<Run>,
    pub paired: Vec<Paired>,
    pub cascades: Vec<Cascade>,
    pub sources: Vec<SourceSet>,
    pub replay: Replay,
    /// Which runs are decision models: the page's lists, from `page_config.json` ([`load`]).
    #[serde(skip)]
    decision_lists: DecisionLists,
}

/// The two lists in the page's `page_config.json` that say which runs are decision models: the providers whose runs
/// are, and the models of those providers that are not. The page's tables and its charts (v3.js) read the same lists,
/// so a run has one type everywhere; `build_site.py` compares each run's type here (`charts --types`) with the tables'.
#[derive(Debug, Default, Deserialize)]
struct DecisionLists {
    decision_model_providers: Vec<String>,
    not_decision_models: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct Unit {
    pub number: u32,
    /// The topic's plain English label.
    pub english: String,
    pub questions: u32,
}

#[derive(Debug, Deserialize)]
pub struct Run {
    pub run: u32,
    pub model: String,
    pub name: String,
    pub variant: Option<String>,
    pub reasoning: Option<String>,
    pub provider: String,
    /// How the run was paid for: "api", "subscription", "free" or "local".
    pub billing: String,
    /// The run's estimated cost in US dollars at the list price `cost_basis` names; None for a run on our hardware
    /// whose maker lists no price for the same model.
    pub api_equivalent_usd: Option<f64>,
    /// Whose list price the cost uses: "api", "subscription", "free tier" or "maker" (the maker's list price for the
    /// same model, for a run on our hardware); None without a cost.
    #[serde(default)]
    pub cost_basis: Option<String>,
    pub answered_questions: u32,
    pub questions_per_request: u32,
    /// Correct answers among the scored questions.
    pub correct: u32,
    pub groups: HashMap<String, Group>,
    pub units: Vec<u32>,
    pub confidence: Option<Confidence>,
    pub latency: Option<Latency>,
    /// A separate test with one question per request.
    pub single_question_latency: Option<SingleLatency>,
    /// A format rerun's setup's first run: the same setup asked another number of questions per request.
    #[serde(default)]
    pub format_of: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct Group {
    pub questions: u32,
    pub correct: u32,
}

#[derive(Debug, Deserialize)]
pub struct Confidence {
    /// The page's name for the confidence source, such as "Option score" or "Written estimate".
    pub label: String,
    /// [coverage, risk]: the error rate of the most confident `coverage` share of the answers.
    pub risk_coverage: Vec<[f64; 2]>,
    pub reliability: Vec<Bin>,
}

#[derive(Debug, Deserialize)]
pub struct Bin {
    pub questions: u32,
    pub mean_confidence: Option<f64>,
    pub accuracy: Option<f64>,
}

/// The time one request took: from the run itself ("run"), from later repeats of the whole
/// question set ("repeats") or from repeat tests on a sample of questions ("sample").
#[derive(Debug, Deserialize)]
pub struct Latency {
    pub source: String,
    pub runs: Vec<u32>,
    pub questions: Option<u32>,
    pub concurrency: u32,
    pub median_request_seconds: f64,
    pub p90_request_seconds: f64,
}

#[derive(Debug, Deserialize)]
pub struct SingleLatency {
    pub questions: u32,
    pub median_request_seconds: f64,
    pub p90_request_seconds: f64,
}

#[derive(Debug, Deserialize)]
pub struct Paired {
    pub first: u32,
    pub second: u32,
    pub difference: f64,
    pub low: f64,
    pub high: f64,
    pub p_holm: f64,
}

#[derive(Debug, Deserialize)]
pub struct Cascade {
    pub decision: u32,
    pub frontier: u32,
    pub frontier_accuracy: f64,
    /// [share answered by the decision model, combined accuracy], highest cutoff first.
    pub curve: Vec<[f64; 2]>,
    pub held_out: HeldOut,
    /// The pair's estimated cost per 1,000 questions at the held-out cutoffs.
    pub usd_per_1000: f64,
}

/// The cutoff chosen on half the questions: chosen on one half, tested on the other, averaged over the splits.
#[derive(Debug, Deserialize)]
pub struct HeldOut {
    pub splits: u32,
    pub answered: f64,
    pub difference: f64,
}

#[derive(Debug, Deserialize)]
pub struct SourceSet {
    pub answers: u32,
    pub questions: u32,
    pub correct: u32,
    pub sources: Vec<Source>,
}

#[derive(Debug, Deserialize)]
pub struct Source {
    pub run: u32,
    /// "stated" (the answering run's own confidence), "probability" or "votes" (share of samples).
    pub kind: String,
    pub auroc: f64,
    pub risk_coverage: Vec<[f64; 2]>,
}

/// Decider v1.1 replayed on every scored question.
#[derive(Debug, Deserialize)]
pub struct Replay {
    pub decision: u32,
    pub questions: u32,
    pub cutoffs: Vec<Cut>,
    pub share: Share,
}

#[derive(Debug, Deserialize)]
pub struct Cut {
    pub cutoff: f64,
    pub kept: u32,
    pub wrong: u32,
}

/// The most confident quarter: the share kept, the confidence where it ends, and its answers.
#[derive(Debug, Deserialize)]
pub struct Share {
    pub share: f64,
    pub cut: f64,
    pub kept: u32,
    pub wrong: u32,
}

/// The page's `results.json` and, from its `page_config.json`, which runs are decision models.
pub fn load(results: &Path, config: &Path) -> Result<Results, Box<dyn Error>> {
    fn parse<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T, Box<dyn Error>> {
        let text = std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
        Ok(serde_json::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))?)
    }
    let mut loaded: Results = parse(results)?;
    loaded.decision_lists = parse(config)?;
    Ok(loaded)
}

/// A run by (provider, model, reasoning setting).
type RunKey = (&'static str, &'static str, Option<&'static str>);

const DECIDER: RunKey = ("perplexity", "pplx-decider-v1.1-27b", None);
const DECIDER_V1: RunKey = ("perplexity", "pplx-decider-v1-27b", None);
const GLIDE: RunKey = ("fastino", "fastino/GLiDE", None);
const LUNA_API: RunKey = ("openai-decisions", "gpt-6-luna", None);
const CELERIS: RunKey = ("celeris", "celeris-1-decision", None);
const SUBQ: RunKey = ("subq", "subq-snap-preview", None);
const JEV: RunKey = ("jev", "jev-1.13.0", None);
const D1: RunKey = ("liquid", "d1:free", None);
const LAYA: RunKey = ("laya", "laya", None);
const GEMMA: RunKey = ("vllm", "gemma-4-31B-it", Some("off"));
const ASTRA: RunKey = ("openai", "gpt-6-astra", Some("low"));
const OPUS: RunKey = ("claude", "claude-opus-5-5", Some("low"));
const SONNET_HIGH: RunKey = ("claude", "claude-sonnet-5-5", Some("high"));
const DEEPSEEK_ON: RunKey = ("vllm", "deepseek-v4.1-flash", Some("on"));
const DEEPSEEK_OFF: RunKey = ("vllm", "deepseek-v4.1-flash", Some("off"));

/// Models that answer near chance on this bank; their runs share a panel in the confidence figures.
const CHANCE_MODELS: [&str; 4] = ["laya", "laya-multilingual", "gliner2.5-multi-v1", "gliner2.5-multi-decide"];
/// Calibration groups with fewer answers than this are too noisy to plot (the page's table keeps them).
const MIN_BIN_ANSWERS: u32 = 20;
/// Calibration groups with at least this many answers get the large dot.
const LARGE_BIN_ANSWERS: u32 = 200;
/// Units 1 to 6 are reading comprehension; the rest are grammatical analysis.
const READING_UNITS: u32 = 6;
/// The most curves one panel shows, so that a reader can follow each of them.
const MAX_SERIES: usize = 6;

const GUIDE: Color = Color::Rgb(0x9c, 0xa3, 0xaf);
const MUTED: Color = Color::Rgb(0x6b, 0x72, 0x80);
const GRIDLINE: Color = Color::Rgb(0xe5, 0xe7, 0xeb);
/// Reading blue and grammar orange, as everywhere on the page (the style sheet's --reading and --grammar).
const READING: Color = Color::Rgb(0x25, 0x63, 0xeb);
const GRAMMAR: Color = Color::Rgb(0xea, 0x58, 0x0c);
const SIGNIFICANT: Color = Color::Rgb(0x25, 0x63, 0xeb);
/// Decider v1.1's accent in every figure; it never means "correct".
const ACCENT: Color = Color::Rgb(0x9a, 0x34, 0x12);
/// Kept and right; kept but wrong (the page's shared palette).
const RIGHT: Color = Color::Rgb(0x15, 0x80, 0x3d);
const WRONG: Color = Color::Rgb(0xb9, 0x1c, 0x1c);
/// The topic chart's colour scale, lowest accuracy first; each step's text stays readable on it.
const HEAT: [Color; 5] = [
    Color::Rgb(0xf0, 0xf9, 0xff),
    Color::Rgb(0xe0, 0xf2, 0xfe),
    Color::Rgb(0xba, 0xe6, 0xfd),
    Color::Rgb(0x7d, 0xd3, 0xfc),
    Color::Rgb(0x38, 0xbd, 0xf8),
];

impl Results {
    fn run(&self, id: u32) -> Option<&Run> {
        self.runs.iter().find(|run| run.run == id)
    }

    /// A setup's first run; a format rerun of it (`format_of`) is a setup of its own.
    fn find(&self, (provider, model, reasoning): RunKey) -> Option<&Run> {
        self.runs.iter().find(|run| {
            run.provider == provider && run.model == model && run.reasoning.as_deref() == reasoning && run.format_of.is_none()
        })
    }

    /// The plain name of a run with its setting in parentheses: its confidence variant, or its
    /// reasoning setting where that is a level ("low reasoning") or where the model has runs with
    /// another setting ("reasoning on"); then its questions per request where the same setup also
    /// ran with another number. For charts that can show both runs of such a setup.
    pub fn label(&self, run: &Run) -> String {
        self.name_with(run, true)
    }

    /// `label` without the questions per request: for charts that show a setup's first run only, or
    /// that name the request size in a group title.
    pub fn setup_label(&self, run: &Run) -> String {
        self.name_with(run, false)
    }

    fn name_with(&self, run: &Run, with_format: bool) -> String {
        let base = match run.model.as_str() {
            "pplx-decider-v1-27b" => "Decider v1",
            "pplx-decider-v1.1-27b" => "Decider v1.1",
            "pplx-decider-v1.2" => "Decider v1.2",
            "pplx-decider-flash-v1.2" => "Decider Flash v1.2",
            "inception/mercury-decide" => "Mercury Decide",
            "jev-1.13.0" => "Jev 1.13",
            "jev-1.14.0" => "Jev 1.14",
            "d1:free" => "Liquid d1",
            "open-jev-27b-v1.1" => "Open Jev",
            "celeris-1-decision" => "Celeris 1",
            "subq-snap-preview" => "SubQ Snap",
            "qwen38-27b-bf16" => "Qwen 3.8 27B",
            "winnow-12b" => "Winnow 12B",
            "clef-flash" => "Clef flash",
            "metask-jev-4b-policy-mix" => "Metask Jev 4B",
            "gpt-6-luna" if run.provider == "openai-decisions" => "GPT-6 Luna, Decisions API",
            _ => run.name.as_str(),
        };
        let sibling = self
            .runs
            .iter()
            .any(|other| other.model == run.model && other.variant == run.variant && other.reasoning != run.reasoning);
        let setting = match (run.variant.as_deref(), run.reasoning.as_deref()) {
            (Some("stated confidence"), _) => Some("written estimate".to_string()),
            (Some("yes/no scoring"), _) => Some("yes/no score".to_string()),
            (Some("vote share"), _) => Some("agreement across ten answers".to_string()),
            (Some(_), _) if run.provider == "openai-decisions" => None,
            (Some(variant), _) => Some(variant.to_string()),
            (None, Some(level @ ("low" | "medium" | "high"))) => Some(format!("{level} reasoning")),
            (None, Some(setting)) if sibling => Some(format!("reasoning {setting}")),
            _ => None,
        };
        let other_format = self.runs.iter().any(|other| {
            other.provider == run.provider
                && other.model == run.model
                && other.variant == run.variant
                && other.reasoning == run.reasoning
                && other.questions_per_request != run.questions_per_request
        });
        let format = (with_format && other_format).then(|| format!("{} per request", run.questions_per_request));
        let parts: Vec<String> = setting.into_iter().chain(format).collect();
        if parts.is_empty() { base.to_string() } else { format!("{base} ({})", parts.join(", ")) }
    }

    /// The reading and grammar question counts, from the units.
    pub fn part_questions(&self) -> (u32, u32) {
        let reading = self.units.iter().filter(|unit| unit.number <= READING_UNITS).map(|unit| unit.questions).sum();
        let grammar = self.units.iter().filter(|unit| unit.number > READING_UNITS).map(|unit| unit.questions).sum();
        (reading, grammar)
    }

    fn is_decider(&self, run: &Run) -> bool {
        self.find(DECIDER).is_some_and(|decider| decider.run == run.run)
    }

    /// A decision model by the page's lists: its provider is one of `decision_model_providers` and its model not one
    /// of `not_decision_models`.
    pub fn is_decision(&self, run: &Run) -> bool {
        let lists = &self.decision_lists;
        lists.decision_model_providers.contains(&run.provider) && !lists.not_decision_models.contains(&run.model)
    }
}

/// A run's estimated cost per 1,000 questions in US dollars, if it has one.
fn cost(run: &Run) -> Option<f64> {
    run.api_equivalent_usd.map(|usd| 1000.0 * usd / f64::from(run.answered_questions))
}

/// Each run's colour, the same in every figure and distinct within each panel. None is red: in the figures red marks
/// kept-but-wrong answers only (WRONG).
fn color(run: &Run) -> Color {
    let rgb = |code: u32| Color::Rgb((code >> 16) as u8, (code >> 8) as u8, code as u8);
    // A format rerun gets its own colour, distinct from its setup's first run in every panel they share.
    if run.format_of.is_some() {
        return match run.model.as_str() {
            "gpt-6-astra" => rgb(0xc2410c),
            "gpt-6.1-sol" => rgb(0x92400e),
            "gemini-3.8-flash" => rgb(0x7e22ce),
            "claude-opus-5-5" => rgb(0x0f766e),
            "claude-sonnet-5-5" => rgb(0xb45309),
            "gemma-4-31B-it" => rgb(0x6b21a8),
            _ => GUIDE,
        };
    }
    match (run.model.as_str(), run.reasoning.as_deref(), run.variant.as_deref()) {
        ("gpt-6-astra", ..) => rgb(0x2563eb),
        ("gpt-6.1-sol", ..) => rgb(0x0891b2),
        ("gpt-6-luna", _, Some(_)) => rgb(0x4338ca),
        ("gpt-6-luna", ..) => rgb(0x60a5fa),
        ("gemini-3.8-flash", Some("high"), _) => rgb(0x3f6212),
        ("gemini-3.8-flash", ..) => rgb(0x65a30d),
        ("erk-14b", ..) => rgb(0x6d28d9),
        ("qwen3-14b", ..) => rgb(0xa78bfa),
        ("claude-opus-5-5", ..) => rgb(0x7c3aed),
        ("claude-sonnet-5-5", Some("high"), _) => rgb(0xdb2777),
        ("claude-sonnet-5-5", ..) => rgb(0xf472b6),
        ("deepseek-v4.1-flash", Some("on"), _) => rgb(0x0e7490),
        ("deepseek-v4.1-flash", ..) => rgb(0x06b6d4),
        ("gemma-4-31B-it", ..) => rgb(0x16a34a),
        ("glm-5.3-flash", Some("on"), _) => rgb(0x713f12),
        ("glm-5.3-flash", ..) => rgb(0x854d0e),
        ("pplx-decider-v1-27b", ..) => rgb(0xea580c),
        ("pplx-decider-v1.1-27b", ..) => rgb(0x9a3412),
        ("jev-1.13.0", ..) => rgb(0x0e7490),
        ("jev-1.14.0", ..) => rgb(0x06b6d4),
        ("d1:free", ..) => rgb(0xca8a04),
        ("d1-ultra", ..) => rgb(0x059669),
        ("open-jev-27b-v1.1", ..) => rgb(0x0d9488),
        ("clef", ..) => rgb(0x9333ea),
        ("clef-flash", ..) => rgb(0xc084fc),
        ("metask-jev-4b-policy-mix", ..) => rgb(0x1e40af),
        ("cygnet", ..) => rgb(0x27272a),
        ("winnow-12b", ..) => rgb(0xa16207),
        ("fastino/GLiDE", ..) => rgb(0x1d4ed8),
        ("glide-v1.2", ..) => rgb(0x3b82f6),
        ("celeris-1-decision", ..) => rgb(0x4d7c0f),
        ("subq-snap-preview", ..) => rgb(0xa21caf),
        ("pplx-decider-v1.2", ..) => rgb(0xfb923c),
        ("pplx-decider-flash-v1.2", ..) => rgb(0x7c2d12),
        ("microsoft/microsoft-decision-1", ..) => rgb(0x155e75),
        ("inception/mercury-decide", ..) => rgb(0x065f46),
        ("strands-decider-2b", ..) => rgb(0xf97316),
        ("qwen38-27b-bf16", _, Some("stated confidence")) => rgb(0x78716c),
        ("qwen38-27b-bf16", _, Some("vote share")) => rgb(0x4f46e5),
        ("qwen38-27b-bf16", ..) => rgb(0x92400e),
        ("laya", ..) => rgb(0xa16207),
        ("laya-multilingual", ..) => rgb(0xf59e0b),
        ("gliner2.5-multi-v1", ..) => rgb(0x475569),
        ("gliner2.5-multi-decide", ..) => rgb(0x2563eb),
        ("decider-1", ..) => rgb(0x047857),
        _ => GUIDE,
    }
}

/// A group's accuracy in percent: its scored correct answers over its scored questions.
fn accuracy(group: &Group) -> f64 {
    100.0 * f64::from(group.correct) / f64::from(group.questions)
}

fn thousands(value: u32) -> String {
    let digits = value.to_string();
    let mut out = String::new();
    for (index, digit) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index) % 3 == 0 {
            out.push(',');
        }
        out.push(digit);
    }
    out
}

/// A confidence or cutoff as a percentage with up to two decimals: 0.999 → "99.9%", 0.9605 → "96.05%".
fn cutoff_text(fraction: f64) -> String {
    let text = format!("{:.2}", 100.0 * fraction);
    format!("{}%", text.trim_end_matches('0').trim_end_matches('.'))
}

/// A share of `total` as a whole percentage: 349 of 2,198 → "16%".
fn whole_percent(part: u32, total: u32) -> String {
    format!("{:.0}%", 100.0 * f64::from(part) / f64::from(total))
}

/// Dollars: cents from $0.10 up and three decimals below, so that $0.0078 does not read as $0.01.
fn usd(value: f64) -> String {
    if value >= 0.1 { format!("${value:.2}") } else { format!("${value:.3}") }
}

/// Seconds with two significant decimals for short times: "0.23 s", "2.09 s", "13.4 s", "365 s".
fn seconds(value: f64) -> String {
    match value {
        value if value < 0.1 => format!("{value:.3} s"),
        value if value < 10.0 => format!("{value:.2} s"),
        value if value < 100.0 => format!("{value:.1} s"),
        value => format!("{value:.0} s"),
    }
}

/// A difference of two shares in percentage points, signed with a true minus: "−0.13 points".
fn points(difference: f64) -> String {
    let value = 100.0 * difference;
    if value.abs() < 0.005 {
        "no change".to_string()
    } else if value < 0.0 {
        format!("−{:.2} points", -value)
    } else {
        format!("+{value:.2} points")
    }
}

/// Items joined with commas and a final "and": "A, B and C".
fn and_list(items: &[String]) -> String {
    match items {
        [] => String::new(),
        [only] => only.clone(),
        [rest @ .., last] => format!("{} and {last}", rest.join(", ")),
    }
}

/// `text` broken at spaces into lines of at most `width` characters.
fn wrap(text: &str, width: usize) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for word in text.split(' ') {
        match lines.last_mut() {
            Some(line) if line.chars().count() + 1 + word.chars().count() <= width => {
                line.push(' ');
                line.push_str(word);
            }
            _ => lines.push(word.to_string()),
        }
    }
    lines
}

/// `text` as muted lines of at most `width` characters.
fn notes(text: &str, width: u16) -> Vec<Line<'static>> {
    wrap(text, usize::from(width)).into_iter().map(muted).collect()
}

/// One graph: drawn into a buffer of `width` × `height` cells by [`render`].
pub struct Figure<'a> {
    /// The SVG's file name without extension, and the snapshot's name.
    pub name: &'static str,
    /// What the figure shows: the SVG's accessible name.
    pub title: String,
    pub width: u16,
    pub height: u16,
    draw: Box<dyn Fn(Rect, &mut Buffer) + 'a>,
}

/// The figure drawn through ratatui's test backend.
pub fn render(figure: &Figure) -> Buffer {
    let mut terminal = Terminal::new(TestBackend::new(figure.width, figure.height)).expect("the test backend never fails");
    terminal
        .draw(|frame| {
            let area = frame.area();
            (figure.draw)(area, frame.buffer_mut());
        })
        .expect("the test backend never fails");
    terminal.backend().buffer().clone()
}

/// The buffer's characters, one line per row, without trailing spaces: the figure's snapshot.
pub fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (area.top()..area.bottom())
        .map(|y| {
            let row: String = (area.left()..area.right()).map(|x| buffer[(x, y)].symbol()).collect();
            row.trim_end().to_string()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Every figure the data allows, in page order.
pub fn figures(results: &Results) -> Vec<Figure<'_>> {
    [
        cutoffs(results),
        handoff(results),
        first_models(results, false),
        first_models(results, true),
        cost_time(results, false),
        cost_time(results, true),
        Some(reading_grammar(results)),
        cascade(results),
        Some(units(results)),
        Some(coverage(results)),
        calibration(results),
        Some(calibration_all(results)),
        sources(results),
        Some(paired(results)),
    ]
    .into_iter()
    .flatten()
    .collect()
}

/// A curve, dots, or both. Only named series get a legend key.
struct Series {
    name: Option<String>,
    color: Color,
    points: Vec<(f64, f64)>,
    line: bool,
    marker: Option<char>,
    /// Drawn over the other curves (Decider v1.1's).
    front: bool,
}

impl Series {
    fn line(name: impl Into<String>, color: Color, points: Vec<(f64, f64)>) -> Self {
        Self { name: Some(name.into()), color, points, line: true, marker: None, front: false }
    }

    /// Points drawn as `marker`, without a legend entry.
    fn dots(color: Color, points: Vec<(f64, f64)>, marker: char) -> Self {
        Self { name: None, color, points, line: false, marker: Some(marker), front: false }
    }

    fn in_front(mut self, front: bool) -> Self {
        self.front = front;
        self
    }
}

/// A percentage axis: its title, its range and the values that get a label.
struct Scale {
    title: String,
    bounds: [f64; 2],
    ticks: Vec<f64>,
}

fn percent_scale(title: impl Into<String>, low: f64, high: f64, step: f64) -> Scale {
    let ticks = (0..).map(|index| low + step * f64::from(index)).take_while(|tick| *tick <= high + 1e-9).collect();
    Scale { title: title.into(), bounds: [low, high], ticks }
}

/// An accuracy axis from 40% to 100%, or from 0% when a curve falls below 40%.
fn accuracy_scale(title: &str, series: &[Series]) -> Scale {
    if series.iter().flat_map(|series| &series.points).all(|&(_, accuracy)| accuracy >= 40.0) {
        percent_scale(title, 40.0, 100.0, 20.0)
    } else {
        percent_scale(title, 0.0, 100.0, 20.0)
    }
}

/// A plot's rows: 15 row steps, so labels every 20% from 0% (5 steps) or from 40% (3 steps) fall on row centres.
const PLOT_ROWS: u16 = 16;

/// The data range of a canvas `cells` long, with `per_cell` braille dots per cell (2 across, 4 down),
/// whose first and last values fall on the centres of its first and last cells. Values then sit on
/// cell centres whenever the axis's steps divide `cells` − 1, so their labels line up with them.
fn centred([low, high]: [f64; 2], cells: u16, per_cell: f64) -> [f64; 2] {
    let margin = (per_cell - 1.0) / 2.0;
    let step = (high - low) / (f64::from(cells) * per_cell - 1.0 - 2.0 * margin);
    [low - margin * step, high + margin * step]
}

fn percent(value: f64) -> String {
    format!("{value}%")
}

/// The named series as legend keys, wrapped into lines of at most `width` cells.
fn legend(series: &[Series], width: u16) -> Vec<Line<'static>> {
    let mut lines = vec![Line::default()];
    for series in series {
        let Some(name) = &series.name else { continue };
        let entry = 3 + name.chars().count() + 3;
        if lines.last().is_some_and(|line| line.width() > 0 && line.width() + entry > usize::from(width)) {
            lines.push(Line::default());
        }
        let line = lines.last_mut().expect("lines starts with one line");
        line.push_span(Span::from("━━ ").fg(series.color));
        let text = Span::from(format!("{name}   "));
        line.push_span(if series.front { text.bold() } else { text });
    }
    lines
}

/// One small chart of a figure: its own title, curves, legend and y axis; the x axis is the figure's.
struct Panel {
    title: String,
    series: Vec<Series>,
    y: Scale,
}

/// Columns between panels side by side.
const PANEL_GAP: u16 = 4;
/// A panel's rows besides its plot and legend: title, y-axis title, x labels, x-axis title, blank row.
const PANEL_FRAME_ROWS: u16 = 5;
/// Columns left of a panel's plot: the y labels ("100%") and a space.
const Y_LABEL_WIDTH: u16 = 5;
/// Columns right of a panel's plot, where the last x label overhangs.
const PLOT_MARGIN: u16 = 2;

/// Panels in a grid of `columns`, each `width / columns` wide; every panel in a row gets the row's
/// tallest legend, so the plots in a row keep the same size and their axes line up.
struct Grid {
    panels: Vec<Panel>,
    columns: usize,
    plot_rows: u16,
    /// Vertical guides across every plot at these x values (the coverage figure's 20%, 50% and 80%).
    marks: Vec<f64>,
}

impl Grid {
    fn new(panels: Vec<Panel>, columns: usize) -> Self {
        Self { panels, columns, plot_rows: PLOT_ROWS, marks: Vec::new() }
    }

    fn panel_width(&self, width: u16) -> u16 {
        let columns = self.columns as u16;
        (width - PANEL_GAP * (columns - 1)) / columns
    }

    fn legend_rows(row: &[Panel], width: u16) -> u16 {
        row.iter().map(|panel| legend(&panel.series, width).len() as u16).max().unwrap_or(0)
    }

    fn height(&self, width: u16) -> u16 {
        let panel_width = self.panel_width(width);
        let rows: Vec<u16> = self
            .panels
            .chunks(self.columns)
            .map(|row| PANEL_FRAME_ROWS + self.plot_rows + Self::legend_rows(row, panel_width))
            .collect();
        rows.iter().sum::<u16>() + rows.len().saturating_sub(1) as u16
    }

    fn render(&self, buf: &mut Buffer, area: Rect, x: &Scale) {
        let width = self.panel_width(area.width);
        let mut top = area.y;
        for row in self.panels.chunks(self.columns) {
            let height = PANEL_FRAME_ROWS + self.plot_rows + Self::legend_rows(row, width);
            for (index, panel) in row.iter().enumerate() {
                let left = area.x + index as u16 * (width + PANEL_GAP);
                draw_panel(buf, Rect::new(left, top, width, height), panel, x, self.plot_rows, &self.marks);
            }
            top += height + 1;
        }
    }
}

fn draw_panel(buf: &mut Buffer, area: Rect, panel: &Panel, x: &Scale, plot_rows: u16, marks: &[f64]) {
    buf.set_line(area.x, area.y, &Line::from(panel.title.clone()).bold(), area.width);
    buf.set_line(area.x, area.y + 1, &muted(panel.y.title.clone()), area.width);
    let plot_area =
        Rect::new(area.x + Y_LABEL_WIDTH, area.y + 2, area.width - Y_LABEL_WIDTH - PLOT_MARGIN, plot_rows);
    let plot = Plot {
        area: plot_area,
        x: centred(x.bounds, plot_area.width, 2.0),
        y: centred(panel.y.bounds, plot_rows, 4.0),
    };
    let ([left, right], [bottom, top]) = (x.bounds, panel.y.bounds);
    // Curves in order, Decider v1.1's last so that it stays on top.
    let lines: Vec<&Series> = panel
        .series
        .iter()
        .filter(|series| series.line && !series.front)
        .chain(panel.series.iter().filter(|series| series.line && series.front))
        .collect();
    plot.canvas(|ctx| {
        for &mark in marks {
            ctx.draw(&segment(mark, bottom, mark, top, GRIDLINE));
        }
        ctx.draw(&segment(left, bottom, right, bottom, GUIDE));
        ctx.draw(&segment(left, bottom, left, top, GUIDE));
        for series in &lines {
            for pair in series.points.windows(2) {
                ctx.draw(&segment(pair[0].0, pair[0].1, pair[1].0, pair[1].1, series.color));
            }
        }
    })
    .render(plot_area, buf);
    for series in &panel.series {
        let Some(marker) = series.marker else { continue };
        for &(px, py) in &series.points {
            plot.text(buf, px, py, Line::from(marker.to_string()).fg(series.color), Alignment::Center);
        }
    }
    for &tick in &panel.y.ticks {
        let (_, row) = plot.cell(left, tick);
        let label = percent(tick);
        let start = plot_area.x - 1 - label.len() as u16;
        buf.set_line(start, row, &muted(label), Y_LABEL_WIDTH);
    }
    let labels = plot_area.bottom();
    for &tick in &x.ticks {
        let (column, _) = plot.cell(tick, bottom);
        let label = percent(tick);
        let start = column.saturating_sub(label.len() as u16 / 2);
        buf.set_line(start, labels, &muted(label), area.right().saturating_sub(start));
    }
    let title = x.title.chars().count() as u16;
    buf.set_line(plot_area.x + plot_area.width.saturating_sub(title) / 2, labels + 1, &muted(x.title.clone()), plot_area.width);
    let keys = labels + 3;
    Paragraph::new(legend(&panel.series, area.width)).render(Rect::new(area.x, keys, area.width, area.bottom() - keys), buf);
}

/// A figure's heading: its title in bold, then its lines, then a blank row; returns the area below.
fn heading(buf: &mut Buffer, area: Rect, title: &str, lines: Vec<Line<'_>>) -> Rect {
    let rows = 2 + lines.len() as u16;
    let [top, rest] = Layout::vertical([Constraint::Length(rows), Constraint::Fill(1)]).areas(area);
    let mut text = vec![Line::from(title.to_string()).bold()];
    text.extend(lines);
    Paragraph::new(text).render(top, buf);
    rest
}

/// Data coordinates mapped onto a canvas the way ratatui's braille grid maps them, so that text
/// placed with [`Plot::text`] lines up with the dots.
struct Plot {
    area: Rect,
    x: [f64; 2],
    y: [f64; 2],
}

impl Plot {
    fn cell(&self, x: f64, y: f64) -> (u16, u16) {
        let columns = f64::from(self.area.width) * 2.0 - 1.0;
        let rows = f64::from(self.area.height) * 4.0 - 1.0;
        let dot_x = ((x - self.x[0]) * columns / (self.x[1] - self.x[0])).round().clamp(0.0, columns) as u16;
        let dot_y = ((self.y[1] - y) * rows / (self.y[1] - self.y[0])).round().clamp(0.0, rows) as u16;
        (self.area.x + dot_x / 2, self.area.y + dot_y / 4)
    }

    /// Text at a data point, kept inside the plot's area.
    fn text(&self, buf: &mut Buffer, x: f64, y: f64, line: Line, alignment: Alignment) {
        let (column, row) = self.cell(x, y);
        self.place(buf, column, row, line, alignment);
    }

    /// Text at a cell, kept inside the plot's columns.
    fn place(&self, buf: &mut Buffer, column: u16, row: u16, line: Line, alignment: Alignment) {
        let width = line.width() as u16;
        let start = match alignment {
            Alignment::Left => column,
            Alignment::Center => column.saturating_sub(width / 2),
            Alignment::Right => column.saturating_sub(width.saturating_sub(1)),
        }
        .min(self.area.right().saturating_sub(width))
        .max(self.area.x);
        buf.set_line(start, row, &line, self.area.right().saturating_sub(start));
    }

    fn canvas<F: Fn(&mut Context)>(&self, paint: F) -> Canvas<'static, F> {
        Canvas::default().marker(Marker::Braille).x_bounds(self.x).y_bounds(self.y).paint(paint)
    }
}

fn muted(text: impl Into<String>) -> Line<'static> {
    Line::from(text.into()).fg(MUTED)
}

fn segment(x1: f64, y1: f64, x2: f64, y2: f64, color: Color) -> Segment {
    Segment { x1, y1, x2, y2, color }
}

/// A horizontal bar of `value` percent of `cells` columns from (`x`, `y`), in eighths of a cell;
/// returns the column after its end.
fn bar(buf: &mut Buffer, x: u16, y: u16, cells: u16, value: f64, color: Color) -> u16 {
    let eighths = (value.clamp(0.0, 100.0) / 100.0 * f64::from(cells) * 8.0).round() as u32;
    let full = (eighths / 8) as u16;
    for column in x..x + full {
        buf[(column, y)].set_char('█').set_fg(color);
    }
    let rest = eighths % 8;
    if rest == 0 {
        return x + full;
    }
    // Left eighths: ▉ (U+2589) is seven eighths, ▏ (U+258F) one.
    let part = char::from_u32(0x2590 - rest).expect("U+2589..U+258F are characters");
    buf[(x + full, y)].set_char(part).set_fg(color);
    x + full + 1
}

/// The lower `eighths` (1 to 8) of a cell: ▁ (U+2581) is one eighth, █ (U+2588) the whole cell.
fn lower(eighths: u16) -> char {
    char::from_u32(0x2580 + u32::from(eighths.clamp(1, 8))).expect("U+2581..U+2588 are characters")
}

/// Labels on a row, each centred on the left edge of the cell at its fraction of `cells` columns from `x`.
fn axis_labels(buf: &mut Buffer, x: u16, y: u16, cells: u16, labels: &[(f64, String)]) {
    for (fraction, label) in labels {
        let edge = x + (fraction * f64::from(cells)).round() as u16;
        let width = label.chars().count() as u16;
        buf.set_line(edge.saturating_sub(width / 2), y, &muted(label.clone()), width);
    }
}

/// Whether a cell holds a letter, digit or sign rather than a blank or a drawn shape (blocks, box
/// lines, braille).
fn is_text(buf: &Buffer, column: u16, row: u16) -> bool {
    let area = buf.area;
    if column < area.left() || column >= area.right() {
        return false;
    }
    buf[(column, row)].symbol().chars().any(|symbol| !symbol.is_whitespace() && !('\u{2500}'..='\u{28FF}').contains(&symbol))
}

/// A gridline mark in a blank cell that does not touch text, so that labels and values keep a clear
/// space around them. Draw gridlines after everything else.
fn grid_mark(buf: &mut Buffer, column: u16, row: u16, mark: char) {
    let clear = buf[(column, row)].symbol() == " "
        && !is_text(buf, column.wrapping_sub(1), row)
        && !is_text(buf, column + 1, row);
    if clear {
        buf[(column, row)].set_char(mark).set_fg(GRIDLINE);
    }
}

/// Light vertical gridlines at `fractions` of `cells` columns from `x`, on rows `rows`, in blank cells only.
fn gridlines(buf: &mut Buffer, x: u16, cells: u16, fractions: impl Iterator<Item = f64>, rows: std::ops::Range<u16>) {
    for fraction in fractions {
        let column = x + (fraction * f64::from(cells)).round() as u16;
        for row in rows.clone() {
            grid_mark(buf, column, row, '▏');
        }
    }
}

/// Text centred in `width` columns from `x`.
fn centre(buf: &mut Buffer, x: u16, y: u16, width: u16, line: Line) {
    let start = x + width.saturating_sub(line.width() as u16) / 2;
    buf.set_line(start, y, &line, width);
}

// ---------------------------------------------------------------------------------------------
// 00 The cutoff trade-off

const CUTOFFS_TITLE: &str = "Lower the cutoff: Decider keeps more, and makes more mistakes";
/// Columns per bar and its gap, and the bar's own width.
const CUT_PITCH: u16 = 7;
const CUT_BAR: u16 = 5;
/// The answers-kept axis steps by this many answers, each step `CUT_STEP_ROWS` rows tall.
const CUT_STEP: u32 = 250;
const CUT_STEP_ROWS: u16 = 5;
/// Columns left of the plot: the axis labels ("1,000") and two spaces.
const CUT_AXIS_WIDTH: u16 = 7;

struct CutBar {
    cutoff: f64,
    kept: u32,
    wrong: u32,
    /// The bar's two-line callout: our rule (shaded) or the most confident quarter, then its answers.
    note: Option<[String; 2]>,
    rule: bool,
}

/// One stacked bar per cutoff of the replay, plus the most confident quarter at its cut, highest cutoff on
/// the left; each bar's height is the answers kept out of all scored questions.
fn cutoffs(results: &Results) -> Option<Figure<'_>> {
    let replay = &results.replay;
    let decider = results.run(replay.decision)?;
    let total = replay.questions;
    let mut bars: Vec<CutBar> = replay
        .cutoffs
        .iter()
        .map(|cut| {
            let rule = (cut.cutoff - results.sure_threshold).abs() < 1e-9;
            CutBar {
                cutoff: cut.cutoff,
                kept: cut.kept,
                wrong: cut.wrong,
                note: rule.then(|| ["Our rule".to_string(), format!("{} kept, {} wrong", thousands(cut.kept), thousands(cut.wrong))]),
                rule,
            }
        })
        .collect();
    let share = &replay.share;
    bars.push(CutBar {
        cutoff: share.cut,
        kept: share.kept,
        wrong: share.wrong,
        note: Some(["Most confident quarter".to_string(), format!("{} kept, {} wrong", thousands(share.kept), thousands(share.wrong))]),
        rule: false,
    });
    bars.sort_by(|first, second| second.cutoff.total_cmp(&first.cutoff));
    let steps = bars.iter().map(|bar| bar.kept).max()?.div_ceil(CUT_STEP).max(1);
    let top = steps * CUT_STEP;
    let rows = steps as u16 * CUT_STEP_ROWS;
    let plot_width = 1 + bars.len() as u16 * CUT_PITCH;
    let width = CUT_AXIS_WIDTH + plot_width + 1;
    let mut lines = notes(
        &format!(
            "{} on the {} questions. We replayed recorded answers. Above each bar: the share of all questions it keeps, and its mistakes.",
            results.label(decider),
            thousands(total)
        ),
        width,
    );
    lines.push(Line::from(vec![
        Span::from("██").fg(RIGHT),
        Span::from(" Kept and right   "),
        Span::from("██").fg(WRONG),
        Span::from(" Kept but wrong   "),
        Span::from("██").fg(GRIDLINE),
        Span::from(format!(" Shaded: our rule, the {} cutoff", cutoff_text(results.sure_threshold))),
    ]));
    let note = wrap(
        "In a replay of recorded answers, the share Decider keeps is roughly the share of the estimated cost we saved. In the live test, the saving was smaller.",
        usize::from(width),
    );
    // Heading, the y-axis title, two rows for the labels over the tallest bar, the plot, the
    // baseline, the cutoff labels, the x-axis title, a blank row and the note.
    let height = 2 + lines.len() as u16 + 1 + 2 + rows + 4 + note.len() as u16;
    let axis_title = format!("Answers kept, out of {}", thousands(total));
    Some(Figure {
        name: "cutoffs",
        title: CUTOFFS_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CUTOFFS_TITLE, lines.clone());
            buf.set_line(body.x, body.y, &muted(axis_title.clone()), body.width);
            let x0 = body.x + CUT_AXIS_WIDTH;
            let plot_top = body.y + 3;
            let bottom = plot_top + rows - 1;
            let left = |index: usize| x0 + 1 + index as u16 * CUT_PITCH;
            // The shaded column behind our rule's bar, from the label rows to the baseline.
            for (index, bar) in bars.iter().enumerate() {
                if bar.rule {
                    for row in plot_top - 2..=bottom {
                        for column in left(index) - 1..left(index) + CUT_BAR + 1 {
                            buf[(column, row)].set_bg(GRIDLINE);
                        }
                    }
                }
            }
            // Labels every step; each step's gridline (drawn last) runs along the bottom of its label's row.
            for step in 0..=steps {
                let row = bottom - step as u16 * CUT_STEP_ROWS;
                let label = thousands(step * CUT_STEP);
                buf.set_line(x0 - 2 - label.len() as u16, row, &muted(label), CUT_AXIS_WIDTH);
            }
            for column in x0..x0 + plot_width {
                buf[(column, bottom + 1)].set_char('▔').set_fg(GUIDE);
            }
            let eighths = |value: u32| (f64::from(value) / f64::from(top) * f64::from(rows) * 8.0).round() as u16;
            // Where each bar's labels start, for the callouts placed after every bar and label.
            let mut label_tops = Vec::with_capacity(bars.len());
            for (index, bar) in bars.iter().enumerate() {
                let x = left(index);
                // Mistakes at the bottom of the bar, at least an eighth of a row tall so that they show.
                let kept = eighths(bar.kept);
                let wrong = if bar.wrong > 0 { eighths(bar.wrong).max(1) } else { 0 };
                for level in 0..kept.div_ceil(8) {
                    let row = bottom - level;
                    let filled = (kept - 8 * level).min(8);
                    let red = wrong.saturating_sub(8 * level).min(8);
                    for column in x..x + CUT_BAR {
                        let cell = &mut buf[(column, row)];
                        if red == 0 {
                            cell.set_char(lower(filled)).set_fg(RIGHT);
                        } else if red >= filled {
                            cell.set_char(lower(filled)).set_fg(WRONG);
                        } else {
                            cell.set_char(lower(red)).set_fg(WRONG).set_bg(RIGHT);
                        }
                    }
                }
                let bar_top = bottom + 1 - kept.div_ceil(8).max(1);
                let centred_at = |line: &Line| x.saturating_add_signed(((i32::from(CUT_BAR) - line.width() as i32) / 2) as i16);
                let style = |line: Line<'static>| if bar.note.is_some() { line.bold() } else { line };
                let labels = [style(Line::from(whole_percent(bar.kept, total))), style(muted(format!("{} wrong", thousands(bar.wrong))))];
                // The two labels sit right above the bar, raised two rows at a time while they would
                // touch a neighbour's labels.
                let touches = |buf: &Buffer, top: u16| {
                    labels.iter().enumerate().any(|(offset, line)| {
                        let start = centred_at(line);
                        (start.saturating_sub(1)..=start + line.width() as u16).any(|column| is_text(buf, column, top + offset as u16))
                    })
                };
                let mut label_top = bar_top - 2;
                while label_top > plot_top + 1 && touches(buf, label_top) {
                    label_top -= 2;
                }
                for (offset, line) in labels.iter().enumerate() {
                    buf.set_line(centred_at(line), label_top + offset as u16, line, line.width() as u16);
                }
                label_tops.push(label_top);
                let cutoff = style(Line::from(cutoff_text(bar.cutoff)));
                buf.set_line(centred_at(&cutoff), bottom + 2, &cutoff, CUT_PITCH);
            }
            // Each callout sits centred over its own bar, a row above the bar's labels, raised while
            // it would touch a bar or other text; a short leader joins it to the labels.
            for (index, bar) in bars.iter().enumerate() {
                let Some(note) = &bar.note else { continue };
                let centre_column = left(index) + CUT_BAR / 2;
                let width = note.iter().map(|line| line.chars().count() as u16).max().unwrap_or(0);
                let start = centre_column.saturating_sub(width / 2).clamp(x0, x0 + plot_width - width);
                // A clear margin around the callout (three columns on each side, a row above and below),
                // so that it never reads as part of a neighbour's label.
                let clear = |buf: &Buffer, top: u16| {
                    (top - 1..top + 3).all(|row| (start.saturating_sub(3)..start + width + 3).all(|column| buf[(column, row)].symbol() == " "))
                };
                let mut top = label_tops[index].saturating_sub(3);
                while top > plot_top - 2 && !clear(buf, top) {
                    top -= 1;
                }
                buf.set_line(start, top, &Line::from(note[0].clone()).bold(), width);
                buf.set_line(start, top + 1, &Line::from(note[1].clone()), width);
                for row in top + 2..label_tops[index] {
                    let cell = &mut buf[(centre_column, row)];
                    if cell.symbol() == " " {
                        cell.set_char('│').set_fg(GUIDE);
                    }
                }
            }
            for step in 1..=steps {
                let row = bottom - step as u16 * CUT_STEP_ROWS;
                for column in x0..x0 + plot_width {
                    grid_mark(buf, column, row, '▁');
                }
            }
            let title = "Cutoff (lowest confidence we keep)";
            centre(buf, x0, bottom + 3, plot_width, muted(title));
            for (index, line) in note.iter().enumerate() {
                buf.set_line(body.x, bottom + 5 + index as u16, &Line::from(line.clone()), body.width);
            }
        }),
    })
}

// ---------------------------------------------------------------------------------------------
// 01 The handoff

const HANDOFF_TITLE: &str = "Decider answers when it is confident; Opus answers the rest";
const HANDOFF_WIDTH: u16 = 70;

/// A box of `width` columns with `lines` centred in it, its border in `color`.
fn draw_box(buf: &mut Buffer, x: u16, y: u16, width: u16, lines: Vec<Line<'static>>, color: Color) -> Rect {
    let height = lines.len() as u16 + 2;
    let (right, bottom) = (x + width - 1, y + height - 1);
    for column in x..=right {
        buf[(column, y)].set_char('─').set_fg(color);
        buf[(column, bottom)].set_char('─').set_fg(color);
    }
    for row in y..=bottom {
        buf[(x, row)].set_char('│').set_fg(color);
        buf[(right, row)].set_char('│').set_fg(color);
    }
    for (column, row, corner) in [(x, y, '┌'), (right, y, '┐'), (x, bottom, '└'), (right, bottom, '┘')] {
        buf[(column, row)].set_char(corner).set_fg(color);
    }
    for (index, line) in lines.into_iter().enumerate() {
        centre(buf, x + 1, y + 1 + index as u16, width - 2, line);
    }
    Rect::new(x, y, width, height)
}

/// An arrow down from under a box's bottom edge at `column`: a tee on the edge and a head below it.
fn arrow_down(buf: &mut Buffer, column: u16, edge: u16, length: u16, color: Color) {
    buf[(column, edge)].set_char('┬').set_fg(color);
    for row in edge + 1..edge + length {
        buf[(column, row)].set_char('│').set_fg(GUIDE);
    }
    buf[(column, edge + length)].set_char('▼').set_fg(GUIDE);
}

/// Question → Decider v1.1 → among its most confident quarter? → keep Decider's answer, or Opus answers.
fn handoff(results: &Results) -> Option<Figure<'_>> {
    let replay = &results.replay;
    let decider = results.run(replay.decision)?;
    let opus = results.find(OPUS)?;
    let share = &replay.share;
    let total = replay.questions;
    let decider_time = decider.latency.as_ref()?.median_request_seconds;
    let opus_time = opus.latency.as_ref()?.median_request_seconds;
    // The other second models Decider v1.1 was tested in front of, in their first format, largest strict share first.
    let mut others: Vec<(&Run, f64)> = results
        .cascades
        .iter()
        .filter(|cascade| cascade.decision == decider.run && cascade.frontier != opus.run)
        .filter_map(|cascade| Some((results.run(cascade.frontier).filter(|run| run.format_of.is_none())?, cascade.held_out.answered)))
        .collect();
    others.sort_by(|first, second| second.1.total_cmp(&first.1));
    let names: Vec<String> = others.iter().map(|(run, _)| run.name.clone()).collect();
    let same = if names.is_empty() {
        Vec::new()
    } else {
        wrap(&format!("The same steps work with {}.", and_list(&names)), usize::from(HANDOFF_WIDTH))
    };
    let subtitle = notes(
        &format!("{} on the {} questions. We replayed recorded answers.", results.label(decider), thousands(total)),
        HANDOFF_WIDTH,
    );
    let decider_name = results.label(decider);
    let opus_name = opus.name.clone();
    let kept_line = format!("{} of questions", whole_percent(share.kept, total));
    let right_line = format!("{} of {} right", thousands(share.kept - share.wrong), thousands(share.kept));
    let rest_line = format!("{} of questions", whole_percent(total - share.kept, total));
    let decider_speed = format!("about {:.2} s per question", decider_time);
    let opus_speed = vec![
        format!("about {:.0} s per request", opus_time),
        format!("of {} questions", opus.questions_per_request),
    ];
    let height = 2 + subtitle.len() as u16 + 22 + same.len().max(1) as u16;
    Some(Figure {
        name: "handoff",
        title: HANDOFF_TITLE.into(),
        width: HANDOFF_WIDTH,
        height,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, HANDOFF_TITLE, subtitle.clone());
            let (x, y) = (body.x, body.y);
            let centre_column = x + 32;
            let question = draw_box(buf, centre_column - 7, y, 15, vec![Line::from("Question")], GUIDE);
            arrow_down(buf, centre_column, question.bottom() - 1, 1, GUIDE);
            let first = draw_box(buf, centre_column - 8, y + 4, 17, vec![Line::from(decider_name.clone()).bold().fg(ACCENT)], ACCENT);
            buf.set_line(first.right() + 2, y + 5, &muted(decider_speed.clone()), HANDOFF_WIDTH);
            arrow_down(buf, centre_column, first.bottom() - 1, 1, ACCENT);
            let ask = draw_box(buf, x + 10, y + 8, 45, vec![Line::from("Among its most confident quarter?").bold()], GUIDE);
            let (yes, no) = (x + 16, x + 48);
            arrow_down(buf, yes, ask.bottom() - 1, 2, GUIDE);
            arrow_down(buf, no, ask.bottom() - 1, 2, GUIDE);
            buf.set_line(yes - 4, y + 11, &Line::from("Yes").bold(), 3);
            buf.set_line(no + 2, y + 11, &Line::from("No").bold(), 2);
            let keep = draw_box(
                buf,
                x + 2,
                y + 13,
                28,
                vec![Line::from("We keep"), Line::from("Decider's answer")],
                ACCENT,
            );
            let rest = draw_box(
                buf,
                x + 34,
                y + 13,
                30,
                vec![Line::from(format!("{opus_name} answers,")), Line::from("and we use Opus's answer")],
                color(opus),
            );
            for (index, line) in [Line::from(kept_line.clone()).bold(), Line::from(right_line.clone())].into_iter().enumerate() {
                centre(buf, keep.x, keep.bottom() + 1 + index as u16, keep.width, line);
            }
            let rest_lines = std::iter::once(Line::from(rest_line.clone()).bold()).chain(opus_speed.iter().map(|line| muted(line.clone())));
            for (index, line) in rest_lines.enumerate() {
                centre(buf, rest.x, rest.bottom() + 1 + index as u16, rest.width, line);
            }
            for (index, line) in same.iter().enumerate() {
                buf.set_line(x, y + 22 + index as u16, &Line::from(line.clone()), body.width);
            }
        }),
    })
}

// ---------------------------------------------------------------------------------------------
// 02 First models before Astra

const FIRST_MODELS_TITLE: &str = "How many questions can each model handle before Astra?";
/// Columns of the share bars; the axis steps by 5% over them.
const FIRST_BAR_CELLS: u16 = 30;
const FIRST_STEP: f64 = 5.0;

/// The held-out share of each first model in front of GPT-6 Astra (low reasoning) with the cutoff chosen on half the questions,
/// decision models first and chat models below; `all` adds the first models we served ourselves.
fn first_models(results: &Results, all: bool) -> Option<Figure<'_>> {
    let astra = results.find(ASTRA)?;
    let mut decision: Vec<(&Run, &Cascade)> = Vec::new();
    let mut chat: Vec<(&Run, &Cascade)> = Vec::new();
    for cascade in results.cascades.iter().filter(|cascade| cascade.frontier == astra.run) {
        let Some(run) = results.run(cascade.decision) else { continue };
        if !results.is_decision(run) {
            chat.push((run, cascade));
        } else if all || matches!(run.billing.as_str(), "api" | "free") {
            decision.push((run, cascade));
        }
    }
    for group in [&mut decision, &mut chat] {
        group.sort_by(|first, second| second.1.held_out.answered.total_cmp(&first.1.held_out.answered));
    }
    let splits = decision.first().or(chat.first())?.1.held_out.splits;
    let highest = decision.iter().chain(&chat).map(|(_, cascade)| 100.0 * cascade.held_out.answered).fold(0.0, f64::max);
    let steps = (highest / FIRST_STEP).ceil().max(1.0) as u16;
    let scale = f64::from(steps) * FIRST_STEP;
    let cells = FIRST_BAR_CELLS / steps * steps;
    let baseline = format!("{} alone", astra.name);
    let label_width = decision
        .iter()
        .chain(&chat)
        .map(|(run, _)| results.setup_label(run).chars().count())
        .chain([baseline.chars().count()])
        .max()? as u16;
    // Indent, labels, a space, the bars, the share ("20.9%"), then the change column.
    let change_x = 2 + label_width + 1 + cells + 8;
    let width = change_x + 16;
    let chat_title = if chat.len() == 1 { "Chat model for comparison" } else { "Chat models for comparison" };
    let subtitle = notes(
        &format!(
            "We replayed recorded answers on the {} questions. The first model answers the questions it is most confident about; {} answers the rest. We choose the cutoff on half the questions and test it on the other half; bars show the average over {} splits.",
            thousands(results.questions),
            results.setup_label(astra),
            thousands(splits)
        ),
        width,
    );
    // Heading, the change column's two header rows, the groups (a title row, then each bar with a
    // blank row under it), the baseline, the axis labels and the axis title.
    let groups = [("Decision models", decision), (chat_title, chat)];
    let group_rows: u16 = groups.iter().filter(|(_, rows)| !rows.is_empty()).map(|(_, rows)| 1 + 2 * rows.len() as u16).sum();
    let height = 2 + subtitle.len() as u16 + 2 + group_rows + 3;
    let name = if all { "first-models-all" } else { "first-models" };
    Some(Figure {
        name,
        title: FIRST_MODELS_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, FIRST_MODELS_TITLE, subtitle.clone());
            let (x, mut y) = (body.x, body.y);
            let bars_x = x + 2 + label_width + 1;
            buf.set_line(x + change_x, y, &muted("Accuracy change"), 16);
            buf.set_line(x + change_x, y + 1, &muted("vs Astra alone"), 16);
            y += 2;
            let fractions = || (0..=steps).map(|step| f64::from(step) / f64::from(steps));
            for (title, rows) in &groups {
                if rows.is_empty() {
                    continue;
                }
                buf.set_line(x, y, &Line::from(*title).bold(), body.width);
                y += 1;
                for (run, cascade) in rows {
                    let label = results.setup_label(run);
                    let decider = results.is_decider(run);
                    let fill = if decider { ACCENT } else if results.is_decision(run) { GUIDE } else { MUTED };
                    let start = x + 2 + label_width - label.chars().count() as u16;
                    let label = if decider { Line::from(label).bold().fg(ACCENT) } else { Line::from(label) };
                    buf.set_line(start, y, &label, label_width);
                    let share = 100.0 * cascade.held_out.answered;
                    let end = bar(buf, bars_x, y, cells, share / scale * 100.0, fill);
                    let value = Line::from(format!("{share:.1}%"));
                    buf.set_line(end + 1, y, &if decider { value.bold() } else { value }, 8);
                    buf.set_line(x + change_x, y, &Line::from(points(cascade.held_out.difference)), 16);
                    gridlines(buf, bars_x, cells, fractions(), y..y + 2);
                    y += 2;
                }
            }
            let start = x + 2 + label_width - baseline.chars().count() as u16;
            buf.set_line(start, y, &Line::from(baseline.clone()), label_width);
            buf.set_line(bars_x, y, &muted("0%: Astra answers every question"), cells + 8);
            buf.set_line(x + change_x, y, &muted("baseline"), 16);
            let labels: Vec<(f64, String)> = (0..=steps)
                .map(|step| (f64::from(step) / f64::from(steps), percent(f64::from(step) * FIRST_STEP)))
                .collect();
            axis_labels(buf, bars_x, y + 1, cells, &labels);
            buf.set_line(x, y + 2, &muted("Share of final answers supplied by the first model"), body.width);
        }),
    })
}

// ---------------------------------------------------------------------------------------------
// 05 Cost and waiting time

const COST_TIME_TITLE: &str = "What does a first answer cost, and how long does it take?";
/// The runs of the short version, in order; GPT-6 Astra's one-question test follows them.
const COST_TIME_RUNS: [RunKey; 5] = [DECIDER, GLIDE, OPUS, SONNET_HIGH, ASTRA];
const COST_TIME_SINGLE_RUNS: [RunKey; 1] = [ASTRA];
/// Columns per tenfold step on the logarithmic axes, and per step on the linear time axis.
const DECADE_CELLS: u16 = 9;
const TIME_STEP_CELLS: u16 = 9;

/// A horizontal axis: where a value falls (0 to 1) and the labelled values.
struct Axis {
    log: bool,
    low: f64,
    high: f64,
    labels: Vec<(f64, String)>,
    cells: u16,
}

impl Axis {
    /// Tenfold steps covering `values`, labelled by `text`.
    fn log(values: impl Iterator<Item = f64> + Clone, text: impl Fn(i32) -> String) -> Self {
        let low = values.clone().fold(f64::INFINITY, f64::min).log10().floor() as i32;
        let high = (values.fold(0.0, f64::max).log10().ceil() as i32).max(low + 1);
        let decades = (high - low) as u16;
        let labels = (low..=high).map(|power| (f64::from(power - low) / f64::from(decades), text(power))).collect();
        Self { log: true, low: f64::from(low), high: f64::from(high), labels, cells: decades * DECADE_CELLS }
    }

    /// Steps of `step` seconds from 0 up to `highest`.
    fn seconds(highest: f64, step: f64) -> Self {
        let steps = (highest / step).ceil().max(1.0) as u16;
        let labels = (0..=steps).map(|index| (f64::from(index) / f64::from(steps), format!("{:.0} s", f64::from(index) * step))).collect();
        Self { log: false, low: 0.0, high: f64::from(steps) * step, labels, cells: steps * TIME_STEP_CELLS }
    }

    fn fraction(&self, value: f64) -> f64 {
        let value = if self.log { value.max(1e-12).log10() } else { value };
        ((value - self.low) / (self.high - self.low)).clamp(0.0, 1.0)
    }
}

/// A power of ten as a dollar amount: −3 → "$0.001", 1 → "$10".
fn usd_power(power: i32) -> String {
    if power < 0 { format!("${:.*}", (-power) as usize, 10f64.powi(power)) } else { format!("${}", thousands(10u32.pow(power as u32))) }
}

/// A power of ten in seconds: −2 → "0.01 s", 3 → "1,000 s".
fn seconds_power(power: i32) -> String {
    if power < 0 { format!("{:.*} s", (-power) as usize, 10f64.powi(power)) } else { format!("{} s", thousands(10u32.pow(power as u32))) }
}

struct CostRow<'a> {
    run: &'a Run,
    /// A row of the separate one-question tests.
    single: bool,
    label: String,
    decider: bool,
    /// The cost per 1,000 questions, or why there is none.
    cost: Result<f64, &'static str>,
    /// The cost is the maker's list price for the same model (a run on our hardware, whose own cost is not measured).
    maker: bool,
    median: f64,
    p90: f64,
    concurrency: u32,
}

/// The rows of a cost panel: groups of runs by questions per request, then the one-question tests.
fn cost_groups<'a>(results: &'a Results, all: bool) -> Vec<(String, Vec<CostRow<'a>>)> {
    let row = |run: &'a Run, latency: &Latency| CostRow {
        run,
        single: false,
        label: results.setup_label(run),
        decider: results.is_decider(run),
        cost: cost(run).ok_or(match run.billing.as_str() {
            "free" => "Free tier used",
            _ => "No dollar estimate",
        }),
        maker: run.cost_basis.as_deref() == Some("maker"),
        median: latency.median_request_seconds,
        p90: latency.p90_request_seconds,
        concurrency: latency.concurrency,
    };
    let runs: Vec<&Run> = if all {
        let mut runs: Vec<&Run> = results.runs.iter().filter(|run| run.latency.is_some()).collect();
        runs.sort_by(|first, second| {
            let key = |run: &Run| (run.questions_per_request, !results.is_decider(run), !results.is_decision(run));
            key(first).cmp(&key(second)).then(
                first.latency.as_ref().map(|latency| latency.median_request_seconds).unwrap_or(0.0).total_cmp(
                    &second.latency.as_ref().map(|latency| latency.median_request_seconds).unwrap_or(0.0),
                ),
            )
        });
        runs
    } else {
        COST_TIME_RUNS.iter().filter_map(|key| results.find(*key)).filter(|run| run.latency.is_some()).collect()
    };
    let mut groups: Vec<(u32, Vec<CostRow>)> = Vec::new();
    for run in runs {
        let Some(latency) = run.latency.as_ref() else { continue };
        match groups.iter_mut().find(|(per_request, _)| *per_request == run.questions_per_request) {
            Some((_, rows)) => rows.push(row(run, latency)),
            None => groups.push((run.questions_per_request, vec![row(run, latency)])),
        }
    }
    let mut named: Vec<(String, Vec<CostRow>)> = groups
        .into_iter()
        .map(|(per_request, rows)| {
            let title = if per_request == 1 { "One question per request".to_string() } else { format!("{per_request} questions per request") };
            (title, rows)
        })
        .collect();
    let singles: Vec<&Run> = if all {
        results.runs.iter().filter(|run| run.single_question_latency.is_some()).collect()
    } else {
        COST_TIME_SINGLE_RUNS.iter().filter_map(|key| results.find(*key)).filter(|run| run.single_question_latency.is_some()).collect()
    };
    if let Some(questions) = singles.first().and_then(|run| run.single_question_latency.as_ref()).map(|single| single.questions) {
        let rows = singles
            .iter()
            .filter_map(|run| {
                let single = run.single_question_latency.as_ref()?;
                Some(CostRow {
                    run,
                    single: true,
                    label: results.setup_label(run),
                    decider: results.is_decider(run),
                    cost: Err("Not measured in this test"),
                    maker: false,
                    median: single.median_request_seconds,
                    p90: single.p90_request_seconds,
                    concurrency: 1,
                })
            })
            .collect();
        named.push((format!("Separate tests: one question per request, on {} questions", thousands(questions)), rows));
    }
    named
}

/// One panel of the cost figure: its title and notes, its axis labels above and below, and a row per run.
struct CostPanel {
    title: String,
    notes: Vec<Line<'static>>,
    axis: Axis,
    /// Draws a run's bar at (x, y) over the axis's cells.
    draw: fn(&mut Buffer, u16, u16, &Axis, &CostRow),
}

fn draw_cost(buf: &mut Buffer, x: u16, y: u16, axis: &Axis, row: &CostRow) {
    match row.cost {
        Ok(value) => {
            let fill = if row.decider { ACCENT } else { GUIDE };
            let end = bar(buf, x, y, axis.cells, 100.0 * axis.fraction(value), fill);
            let text = Line::from(format!(" {}{}", usd(value), if row.maker { " §" } else { "" }));
            buf.set_line(end, y, &if row.decider { text.bold() } else { text }, 11);
        }
        Err(reason) => {
            buf.set_line(x, y, &muted(reason), axis.cells + 20);
        }
    }
}

fn draw_time(buf: &mut Buffer, x: u16, y: u16, axis: &Axis, row: &CostRow) {
    let fill = if row.decider { ACCENT } else { GUIDE };
    let end = bar(buf, x, y, axis.cells, 100.0 * axis.fraction(row.median), fill);
    let whisker = x + (axis.fraction(row.p90) * f64::from(axis.cells)).round() as u16;
    for column in end..whisker {
        buf[(column, y)].set_char('━').set_fg(fill);
    }
    let cap = whisker.max(end);
    buf[(cap, y)].set_char('│').set_fg(fill);
    let mut text = format!("  {} · {}", seconds(row.median), seconds(row.p90));
    if row.concurrency > 1 {
        text.push_str(&format!(", {} requests at a time", row.concurrency));
    }
    let text = Line::from(text);
    buf.set_line(cap + 1, y, &if row.decider { text.bold() } else { text }, 42);
}

/// Estimated cost per 1,000 questions and the waiting time for one request, in two panels with
/// their own units; `all` has every run with a time, the short version the opening's runs.
fn cost_time(results: &Results, all: bool) -> Option<Figure<'_>> {
    let groups = cost_groups(results, all);
    let rows = || groups.iter().flat_map(|(_, rows)| rows);
    let costs = rows().filter_map(|row| row.cost.ok());
    if costs.clone().next().is_none() {
        return None;
    }
    let cost_axis = Axis::log(costs, usd_power);
    let time_axis = if all {
        Axis::log(rows().flat_map(|row| [row.median, row.p90]), seconds_power)
    } else {
        Axis::seconds(rows().map(|row| row.p90).fold(0.0, f64::max), 10.0)
    };
    // The short version stacks each label over its bars so that it stays narrow; the full one
    // puts the labels in a column.
    let stacked = !all;
    let label_width = rows().map(|row| row.label.chars().count() as u16).max()?;
    let bars_x = if stacked { 4 } else { 2 + label_width + 2 };
    let value_width = 38;
    let width = (bars_x + cost_axis.cells.max(time_axis.cells) + 2 + value_width).max(if stacked { label_width + 4 } else { 0 });
    let log_note = "Logarithmic scale: equal steps show equal multiples; each labelled step is 10 times the one before.";
    let mut time_notes = if time_axis.log { notes(log_note, width) } else { Vec::new() };
    time_notes.push(Line::from(vec![Span::from("██").fg(GUIDE), Span::from(" typical time (median)")]));
    time_notes.push(Line::from(vec![Span::from("━━│").fg(GUIDE), Span::from(" 9 in 10 requests finish within this time (90th percentile)")]));
    let panels = [
        CostPanel {
            title: "Estimated cost per 1,000 questions, in US dollars".into(),
            notes: notes(log_note, width),
            axis: cost_axis,
            draw: draw_cost,
        },
        CostPanel { title: "Waiting time for one request".into(), notes: time_notes, axis: time_axis, draw: draw_time },
    ];
    // Where the times come from, when not from the run itself.
    let mut footnotes = Vec::new();
    let named = |source: &str| -> Vec<&Run> {
        groups
            .iter()
            .flat_map(|(_, rows)| rows)
            .filter(|row| !row.single && row.run.latency.as_ref().is_some_and(|latency| latency.source == source))
            .map(|row| row.run)
            .collect()
    };
    let sample = named("sample");
    if let Some(latency) = sample.first().and_then(|run| run.latency.as_ref()) {
        let list: Vec<String> = sample.iter().map(|run| results.label(run)).collect();
        footnotes.extend(notes(
            &format!(
                "Times for {} were measured on a sample ({} questions), over {} repeat runs.",
                and_list(&list),
                thousands(latency.questions.unwrap_or(0)),
                latency.runs.len()
            ),
            width,
        ));
    }
    let repeats = named("repeats");
    if !repeats.is_empty() {
        let list: Vec<String> = repeats.iter().map(|run| results.label(run)).collect();
        footnotes.extend(notes(&format!("Times for {} come from later repeat runs on all questions.", and_list(&list)), width));
    }
    if rows().any(|row| row.maker && row.cost.is_ok()) {
        footnotes.extend(notes("§ Estimated at the maker's list price for the same model; our hardware cost is not measured.", width));
    }
    let subtitle = notes(
        &format!(
            "Recorded runs on the {} questions. Times describe the service and hardware we tested; they are not times for the two-step setup.",
            thousands(results.questions)
        ),
        width,
    );
    let row_height = if stacked { 2 } else { 1 };
    let body_rows: u16 = groups.iter().map(|(_, rows)| 1 + rows.len() as u16 * row_height).sum();
    // Per panel: title, notes, axis labels, the rows, axis labels, a blank row.
    let panel_rows = |panel: &CostPanel| 1 + panel.notes.len() as u16 + 1 + body_rows + 1 + 1;
    let height = 2 + subtitle.len() as u16 + panels.iter().map(panel_rows).sum::<u16>() + footnotes.len() as u16;
    let name = if all { "cost-time-all" } else { "cost-time" };
    Some(Figure {
        name,
        title: COST_TIME_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, COST_TIME_TITLE, subtitle.clone());
            let (x, mut y) = (body.x, body.y);
            for panel in &panels {
                buf.set_line(x, y, &Line::from(panel.title.clone()).bold(), body.width);
                y += 1;
                for line in &panel.notes {
                    buf.set_line(x, y, line, body.width);
                    y += 1;
                }
                axis_labels(buf, x + bars_x, y, panel.axis.cells, &panel.axis.labels);
                y += 1;
                let fractions: Vec<f64> = panel.axis.labels.iter().map(|(fraction, _)| *fraction).collect();
                for (title, rows) in &groups {
                    buf.set_line(x, y, &muted(title.clone()).bold(), body.width);
                    y += 1;
                    for row in rows {
                        let label = if row.decider { Line::from(row.label.clone()).bold().fg(ACCENT) } else { Line::from(row.label.clone()) };
                        buf.set_line(x + 2, y, &label, if stacked { body.width } else { label_width });
                        if stacked {
                            y += 1;
                        }
                        (panel.draw)(buf, x + bars_x, y, &panel.axis, row);
                        gridlines(buf, x + bars_x, panel.axis.cells, fractions.iter().copied(), y..y + 1);
                        y += 1;
                    }
                }
                axis_labels(buf, x + bars_x, y, panel.axis.cells, &panel.axis.labels);
                y += 2;
            }
            for line in &footnotes {
                buf.set_line(x, y, line, body.width);
                y += 1;
            }
        }),
    })
}

// ---------------------------------------------------------------------------------------------
// 04 Reading and grammar

const READING_GRAMMAR_TITLE: &str = "How often do models get reading and grammar questions right?";
/// The bar charts' labelled values; the cells for the bars are a multiple of 4, so each lands on a cell edge.
const BAR_TICKS: [f64; 5] = [0.0, 25.0, 50.0, 75.0, 100.0];
/// The decision models in the page's order, then the chat models below them.
const READING_GRAMMAR_DECISION: [RunKey; 8] = [DECIDER, GLIDE, SUBQ, LUNA_API, CELERIS, DECIDER_V1, JEV, D1];
const READING_GRAMMAR_CHAT: [RunKey; 2] = [GEMMA, ASTRA];

fn reading_grammar(results: &Results) -> Figure<'_> {
    let row = |key: &RunKey| -> Option<(String, f64, f64, bool)> {
        let run = results.find(*key)?;
        Some((results.setup_label(run), accuracy(run.groups.get("reading")?), accuracy(run.groups.get("grammar")?), results.is_decider(run)))
    };
    let groups: Vec<(&str, Vec<(String, f64, f64, bool)>)> = vec![
        ("Decision models", READING_GRAMMAR_DECISION.iter().filter_map(&row).collect()),
        ("Chat models for comparison", READING_GRAMMAR_CHAT.iter().filter_map(&row).collect()),
    ];
    let (reading_questions, grammar_questions) = results.part_questions();
    let label_width = groups.iter().flat_map(|(_, rows)| rows).map(|row| row.0.chars().count()).max().unwrap_or(0) as u16;
    let width = 84;
    // Labels, two spaces, the bars, then room for a value ("100.0%") after the longest bar.
    let cells = (width - label_width - 2 - 8) / 4 * 4;
    let runs: u16 = groups.iter().map(|(_, rows)| rows.len() as u16).sum();
    // The heading's four rows, tick labels above and below, a title row per group, two bars per run
    // with a blank row after each, and the axis title.
    let body_rows = groups.len() as u16 + runs * 3;
    let source = notes(&format!("Recorded answers on the {} questions.", thousands(results.questions)), width);
    let height = 2 + source.len() as u16 + 1 + 1 + body_rows + 1 + 1;
    Figure {
        name: "reading-grammar",
        title: READING_GRAMMAR_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let key = Line::from(vec![
                Span::from("██").fg(READING),
                Span::from(format!(" Reading ({} questions)   ", thousands(reading_questions))),
                Span::from("██").fg(GRAMMAR),
                Span::from(format!(" Grammar ({} questions)", thousands(grammar_questions))),
            ]);
            let mut lines = source.clone();
            lines.push(key);
            let body = heading(buf, area, READING_GRAMMAR_TITLE, lines);
            let x = body.x + label_width + 2;
            let top = body.y;
            let ticks: Vec<(f64, String)> = BAR_TICKS.iter().map(|tick| (tick / 100.0, percent(*tick))).collect();
            axis_labels(buf, x, top, cells, &ticks);
            let mut y = top + 1;
            for (title, rows) in &groups {
                buf.set_line(body.x, y, &Line::from(*title).bold(), body.width);
                y += 1;
                for (label, reading, grammar, decider) in rows {
                    let start = body.x + label_width - label.chars().count() as u16;
                    let text = if *decider { Line::from(label.clone()).bold().fg(ACCENT) } else { Line::from(label.clone()) };
                    buf.set_line(start, y, &text, label_width);
                    for (row, value, color) in [(y, *reading, READING), (y + 1, *grammar, GRAMMAR)] {
                        let end = bar(buf, x, row, cells, value, color);
                        buf.set_line(end + 1, row, &muted(format!("{value:.1}%")), 7);
                    }
                    y += 3;
                }
            }
            // Gridlines at the labelled values, behind the bars and their values.
            gridlines(buf, x, cells, BAR_TICKS.iter().map(|tick| tick / 100.0), top + 1..y);
            axis_labels(buf, x, y, cells, &ticks);
            centre(buf, x, y + 1, cells, muted("Correct answers"));
        }),
    }
}

// ---------------------------------------------------------------------------------------------
// 07 Topics

const UNITS_TITLE: &str = "Which topics cause the most mistakes?";
/// The runs on the topic chart with their column headings, decision models first.
const UNIT_RUNS: [(RunKey, &[&str]); 7] = [
    (DECIDER, &["Decider", "v1.1"]),
    (JEV, &["Jev", "1.13"]),
    (LAYA, &["Laya"]),
    (ASTRA, &["GPT-6", "Astra"]),
    (DEEPSEEK_ON, &["DeepSeek", "reasoning", "on"]),
    (GEMMA, &["Gemma 4", "31B"]),
    (DEEPSEEK_OFF, &["DeepSeek", "reasoning", "off"]),
];
/// Columns per run: a shaded cell and a gap.
const UNIT_COLUMN: u16 = 10;
/// Columns for the topic labels with their question counts.
const UNIT_LABEL: u16 = 38;

/// The colour step of a percentage shown rounded: each 20 points, the top step taking 100%.
fn heat(rounded: f64) -> Color {
    HEAT[((rounded / 20.0).floor() as usize).min(HEAT.len() - 1)]
}

fn units(results: &Results) -> Figure<'_> {
    let columns: Vec<(&Run, &[&str])> = UNIT_RUNS.iter().filter_map(|(key, header)| Some((results.find(*key)?, *header))).collect();
    let decision_columns = columns.iter().filter(|(run, _)| results.is_decision(run)).count() as u16;
    let header_rows = columns.iter().map(|(_, header)| header.len() as u16).max().unwrap_or(1);
    let (reading_questions, grammar_questions) = results.part_questions();
    let sections = [
        (format!("Reading: topics 1–{READING_UNITS}, {} questions", thousands(reading_questions)), 1..=READING_UNITS),
        (
            format!("Grammar: topics {}–{}, {} questions", READING_UNITS + 1, results.units.len(), thousands(grammar_questions)),
            READING_UNITS + 1..=results.units.len() as u32,
        ),
    ];
    // "3.  How a writer explains and" / "    develops ideas (70)": the count stays with the last word.
    let labels: Vec<Vec<String>> = results
        .units
        .iter()
        .map(|unit| {
            let text = format!("{}\u{a0}({})", unit.english, unit.questions);
            wrap(&text, usize::from(UNIT_LABEL - 5))
                .into_iter()
                .enumerate()
                .map(|(index, line)| if index == 0 { format!("{:<4}{line}", format!("{}.", unit.number)) } else { format!("    {line}") })
                .collect()
        })
        .collect();
    let width = UNIT_LABEL + 1 + columns.len() as u16 * UNIT_COLUMN;
    let subtitle = notes(
        &format!(
            "Recorded answers on the {} questions. Correct answers in each topic, as a share of its questions (the count in brackets). Darker cells: more answers right. Each column is one model.",
            thousands(results.questions)
        ),
        width,
    );
    let mut key = vec![Span::from("Correct answers: ").fg(MUTED)];
    for (index, color) in HEAT.iter().enumerate() {
        let low = index * 20;
        let range = if index + 1 == HEAT.len() { format!("{low}–100%   ") } else { format!("{low}–{}%   ", low + 19) };
        key.push(Span::from("██").fg(*color));
        key.push(Span::from(format!(" {range}")));
    }
    let mut lines = subtitle;
    lines.push(Line::from(key));
    let topic_rows: u16 = labels.iter().map(|lines| lines.len() as u16).sum();
    let height = 2 + lines.len() as u16 + 1 + header_rows + sections.len() as u16 + topic_rows;
    Figure {
        name: "units",
        title: UNITS_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, UNITS_TITLE, lines.clone());
            let column_x = |index: usize| body.x + UNIT_LABEL + 1 + index as u16 * UNIT_COLUMN;
            let mut y = body.y;
            buf.set_line(column_x(0), y, &Line::from("Decision models").bold(), decision_columns * UNIT_COLUMN);
            if columns.len() as u16 > decision_columns {
                buf.set_line(column_x(usize::from(decision_columns)), y, &Line::from("Chat models for comparison").bold(), body.width);
            }
            y += 1;
            for (index, (run, header)) in columns.iter().enumerate() {
                for (row, text) in header.iter().enumerate() {
                    let line = if results.is_decider(run) { Line::from(*text).bold().fg(ACCENT) } else { Line::from(*text) };
                    let start = column_x(index) + (UNIT_COLUMN - 1).saturating_sub(line.width() as u16);
                    buf.set_line(start, y + row as u16, &line, UNIT_COLUMN);
                }
            }
            y += header_rows;
            for (title, numbers) in &sections {
                buf.set_line(body.x, y, &Line::from(title.clone()).bold(), body.width);
                y += 1;
                for (unit_index, unit) in results.units.iter().enumerate().filter(|(_, unit)| numbers.contains(&unit.number)) {
                    let rows = labels[unit_index].len() as u16;
                    for (row, text) in labels[unit_index].iter().enumerate() {
                        buf.set_line(body.x, y + row as u16, &Line::from(text.clone()), UNIT_LABEL);
                    }
                    for (index, (run, _)) in columns.iter().enumerate() {
                        let Some(correct) = run.units.get(unit_index) else { continue };
                        let value = (100.0 * f64::from(*correct) / f64::from(unit.questions)).round();
                        for row in y..y + rows {
                            for column in column_x(index)..column_x(index) + UNIT_COLUMN - 1 {
                                buf[(column, row)].set_bg(heat(value));
                            }
                        }
                        let text = format!("{value:.0}%");
                        let start = column_x(index) + UNIT_COLUMN - 2 - text.len() as u16;
                        let line = if results.is_decider(run) { Line::from(text).bold() } else { Line::from(text) };
                        buf.set_line(start, y, &line, UNIT_COLUMN);
                    }
                    y += rows;
                }
            }
        }),
    }
}

// ---------------------------------------------------------------------------------------------
// 08, 09, 10 Confidence

/// `runs` (best first) in the fewest parts of at most `max` runs, as even as possible, each named.
fn split<'a>(name: &str, runs: Vec<&'a Run>, max: usize) -> Vec<(String, Vec<&'a Run>)> {
    if runs.is_empty() {
        return Vec::new();
    }
    let parts = runs.len().div_ceil(max);
    let size = runs.len().div_ceil(parts);
    runs.chunks(size)
        .enumerate()
        .map(|(index, chunk)| {
            let title = match parts {
                1 => name.to_string(),
                _ => format!("{name}, part {} of {parts}", index + 1),
            };
            (title, chunk.to_vec())
        })
        .collect()
}

/// The panels of the confidence figures, decision models first.
const FAMILIES: [&str; 6] = [
    "Decision models",
    "Chat models from OpenAI and Google",
    "Chat models from Anthropic",
    "Open-weight chat models",
    "Qwen 3.8 27B, different confidence sources",
    "Near chance: Laya and GLiNER",
];

/// Which of [`FAMILIES`] a run belongs to.
fn family(results: &Results, run: &Run) -> usize {
    if CHANCE_MODELS.contains(&run.model.as_str()) {
        5
    } else if results.is_decision(run) {
        0
    } else if matches!(run.provider.as_str(), "openai" | "gemini") {
        1
    } else if run.provider == "claude" {
        2
    } else if run.model == "qwen38-27b-bf16" {
        4
    } else {
        3
    }
}

/// The runs with a confidence score in panels of related runs, best first in each with Decider
/// v1.1 first of all; every run lands in exactly one panel. A panel whose runs share a confidence
/// source names it.
fn families(results: &Results) -> Vec<(String, Vec<&Run>)> {
    let mut runs: Vec<&Run> = results.runs.iter().filter(|run| run.confidence.is_some()).collect();
    runs.sort_by_key(|run| (!results.is_decider(run), Reverse(run.correct)));
    FAMILIES
        .iter()
        .enumerate()
        .flat_map(|(index, name)| split(name, runs.iter().copied().filter(|run| family(results, run) == index).collect(), MAX_SERIES))
        .map(|(title, runs)| {
            let sources: Vec<&str> =
                runs.iter().filter_map(|run| run.confidence.as_ref()).map(|confidence| confidence.label.as_str()).collect();
            let source = match sources.first() {
                Some(first) if sources.iter().all(|source| source == first) => format!(" · {first}"),
                _ => String::new(),
            };
            (format!("{title}{source}"), runs)
        })
        .collect()
}

fn coverage_curve(points: &[[f64; 2]]) -> Vec<(f64, f64)> {
    points.iter().map(|&[coverage, risk]| (100.0 * coverage, 100.0 * (1.0 - risk))).collect()
}

const COVERAGE_TITLE: &str = "How accurate are the answers we keep?";
const COVERAGE_X: &str = "Share of answers we keep, most confident first";
const COVERAGE_Y: &str = "Accuracy among the kept answers";
/// The shares of answers the coverage figure marks.
const COVERAGE_MARKS: [f64; 3] = [20.0, 50.0, 80.0];
const CALIBRATION_TITLE: &str = "When a model scores answers at 80%, are about 80% right?";
const CALIBRATION_X: &str = "Average confidence in this group";
const CALIBRATION_Y: &str = "Correct answers in this group";
const DIAGONAL: &str = "Confidence matches accuracy";
const SOURCES_TITLE: &str = "Can different scores help us judge the same answers?";
/// Columns of the confidence figures' panel grids.
const WIDE_WIDTH: u16 = 160;
/// The single-panel calibration figure: a plot of 61 columns, so that every 20% falls on a cell centre.
const NARROW_WIDTH: u16 = Y_LABEL_WIDTH + 61 + PLOT_MARGIN;

fn coverage(results: &Results) -> Figure<'_> {
    let panels = families(results)
        .into_iter()
        .map(|(title, runs)| {
            let series: Vec<Series> = runs
                .iter()
                .filter_map(|run| {
                    let confidence = run.confidence.as_ref()?;
                    Some(
                        Series::line(results.label(run), color(run), coverage_curve(&confidence.risk_coverage))
                            .in_front(results.is_decider(run)),
                    )
                })
                .collect();
            let y = accuracy_scale(COVERAGE_Y, &series);
            Panel { title, series, y }
        })
        .collect();
    let grid = Grid { marks: COVERAGE_MARKS.to_vec(), ..Grid::new(panels, 2) };
    let x = Scale { title: COVERAGE_X.into(), bounds: [0.0, 100.0], ticks: [0.0].into_iter().chain(COVERAGE_MARKS).chain([100.0]).collect() };
    let lines = notes(
        &format!(
            "Recorded answers on the {} questions. Each curve starts with a model's most confident answers and adds less confident ones. The marks at 20%, 50% and 80% are shares of the answers, not confidence scores. Each curve ends at the model's accuracy on all answers. No second model answers the rest here. Panels group related models, decision models first; read each panel's own y axis.",
            thousands(results.questions)
        ),
        WIDE_WIDTH,
    );
    Figure {
        name: "coverage",
        title: COVERAGE_TITLE.into(),
        width: WIDE_WIDTH,
        height: 2 + lines.len() as u16 + grid.height(WIDE_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, COVERAGE_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    }
}

/// A calibration panel: the diagonal, then each run's groups as a line with dots sized by answers,
/// named with their questions per request when `with_format` and their setup also ran with another.
fn calibration_panel(results: &Results, title: String, runs: &[&Run], with_format: bool) -> Panel {
    let mut series = vec![Series::line(DIAGONAL, GUIDE, vec![(0.0, 0.0), (100.0, 100.0)])];
    for run in runs {
        let Some(confidence) = run.confidence.as_ref() else { continue };
        let bins: Vec<(f64, f64, u32)> = confidence
            .reliability
            .iter()
            .filter(|bin| bin.questions >= MIN_BIN_ANSWERS)
            .filter_map(|bin| Some((100.0 * bin.mean_confidence?, 100.0 * bin.accuracy?, bin.questions)))
            .collect();
        let points = |large: bool| -> Vec<(f64, f64)> {
            bins.iter().filter(|bin| (bin.2 >= LARGE_BIN_ANSWERS) == large).map(|bin| (bin.0, bin.1)).collect()
        };
        // The run's name with its confidence source, unless the name already says it.
        let label = results.name_with(run, with_format);
        let name = if label.to_lowercase().contains(&confidence.label.to_lowercase()) {
            label
        } else {
            format!("{label} · {}", confidence.label)
        };
        series.push(Series::line(name, color(run), bins.iter().map(|bin| (bin.0, bin.1)).collect()).in_front(results.is_decider(run)));
        series.push(Series::dots(color(run), points(false), '•'));
        series.push(Series::dots(color(run), points(true), '●'));
    }
    Panel { title, series, y: percent_scale(CALIBRATION_Y, 0.0, 100.0, 20.0) }
}

fn calibration_notes(questions: u32, width: u16) -> Vec<Line<'static>> {
    notes(
        &format!(
            "Recorded answers on the {} questions. Each dot is a group of answers with similar confidence: its average confidence (x) against the share right (y). Above the diagonal, the model was right more often than its confidence says; below it, less often. Dot size: • {MIN_BIN_ANSWERS} to {} answers, ● {LARGE_BIN_ANSWERS} or more. Groups with fewer than {MIN_BIN_ANSWERS} answers are left out of the plot (the table keeps them).",
            thousands(questions),
            LARGE_BIN_ANSWERS - 1
        ),
        width,
    )
}

/// The default calibration view: Decider v1.1 against Claude Opus 5.5.
const CALIBRATION_RUNS: [RunKey; 2] = [DECIDER, OPUS];

fn calibration(results: &Results) -> Option<Figure<'_>> {
    let runs: Vec<&Run> = CALIBRATION_RUNS.iter().filter_map(|key| results.find(*key)).collect();
    if runs.is_empty() {
        return None;
    }
    let names: Vec<String> = runs.iter().map(|run| results.setup_label(run)).collect();
    let grid = Grid::new(vec![calibration_panel(results, names.join(" and "), &runs, false)], 1);
    let x = percent_scale(CALIBRATION_X, 0.0, 100.0, 20.0);
    let lines = calibration_notes(results.questions, NARROW_WIDTH);
    Some(Figure {
        name: "calibration",
        title: CALIBRATION_TITLE.into(),
        width: NARROW_WIDTH,
        height: 2 + lines.len() as u16 + grid.height(NARROW_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CALIBRATION_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    })
}

fn calibration_all(results: &Results) -> Figure<'_> {
    let panels = families(results).into_iter().map(|(title, runs)| calibration_panel(results, title, &runs, true)).collect();
    let grid = Grid::new(panels, 2);
    let x = percent_scale(CALIBRATION_X, 0.0, 100.0, 20.0);
    let lines = calibration_notes(results.questions, WIDE_WIDTH);
    Figure {
        name: "calibration-all",
        title: CALIBRATION_TITLE.into(),
        width: WIDE_WIDTH,
        height: 2 + lines.len() as u16 + grid.height(WIDE_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CALIBRATION_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    }
}

fn sources(results: &Results) -> Option<Figure<'_>> {
    let set = results.sources.first()?;
    let answers = results.run(set.answers)?;
    let family = results.label(answers).split(' ').next().unwrap_or_default().to_string();
    let series: Vec<Series> = set
        .sources
        .iter()
        .filter_map(|source| {
            let run = results.run(source.run)?;
            let method = match source.kind.as_str() {
                "probability" if run.model == answers.model => format!("{family} option score"),
                "probability" => {
                    let name = results.label(run);
                    format!("{name} score (a separately trained scorer)")
                }
                _ => run.confidence.as_ref()?.label.clone(),
            };
            Some(Series::line(format!("{method}: ranking score {:.2}", source.auroc), color(run), coverage_curve(&source.risk_coverage)))
        })
        .collect();
    let y = accuracy_scale(COVERAGE_Y, &series);
    let grid = Grid::new(vec![Panel { title: String::new(), series, y }], 1);
    // A plot 91 columns wide, so that the x labels fall on cell centres (see `centred`).
    let width = 98;
    let lines = notes(
        &format!(
            "The same {} answers from {} in every curve, {} of them right. Only the score that ranks them changes. Ranking score (AUROC): how often a right answer gets a higher score than a wrong one.",
            thousands(set.questions),
            results.label(answers),
            thousands(set.correct)
        ),
        width,
    );
    let x = percent_scale(COVERAGE_X, 0.0, 100.0, 20.0);
    Some(Figure {
        name: "sources",
        title: SOURCES_TITLE.into(),
        width,
        height: 2 + lines.len() as u16 + grid.height(width),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, SOURCES_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    })
}

// ---------------------------------------------------------------------------------------------
// 11 Paired differences

const PAIRED_TITLE: &str = "How large are the accuracy gaps, and how uncertain are they?";

fn paired(results: &Results) -> Figure<'_> {
    let rows: Vec<(String, f64, f64, f64, bool)> = results
        .paired
        .iter()
        .filter_map(|pair| {
            let (first, second) = (results.run(pair.first)?, results.run(pair.second)?);
            Some((
                format!("{} minus {}", results.setup_label(first), results.setup_label(second)),
                100.0 * pair.difference,
                100.0 * pair.low,
                100.0 * pair.high,
                pair.p_holm < 0.05,
            ))
        })
        .collect();
    let lowest = rows.iter().map(|row| row.2).fold(0.0_f64, f64::min);
    let highest = rows.iter().map(|row| row.3).fold(0.0_f64, f64::max);
    let bounds = [(lowest / 5.0).floor() * 5.0, (highest / 5.0).ceil() * 5.0];
    let label_width = rows.iter().map(|row| row.0.chars().count()).max().unwrap_or(0) as u16;
    let count = rows.len() as u16;
    let passing = rows.iter().filter(|row| row.4).count();
    let width = (label_width + 2 + 60 + 7).max(120);
    let lines = notes(
        &format!(
            "Each row is model A minus model B, on the same {} questions. Dots: the observed gap. Lines: its 95% interval. A line that crosses zero did not establish a difference; the colour shows a related but separate test, adjusted across these {} comparisons ({passing} pass).",
            thousands(results.questions),
            rows.len()
        ),
        width,
    );
    let key = Line::from(vec![
        Span::from("━━ ").fg(SIGNIFICANT),
        Span::from(format!("passes the Holm adjustment across these {} comparisons   ", rows.len())),
        Span::from("━━ ").fg(GUIDE),
        Span::from("does not pass"),
    ]);
    let head_rows = 1 + lines.len() as u16 + 1 + 1;
    Figure {
        name: "paired",
        title: PAIRED_TITLE.into(),
        width,
        height: head_rows + count + 2,
        draw: Box::new(move |area, buf| {
            let [head, body, axis] =
                Layout::vertical([Constraint::Length(head_rows), Constraint::Length(count), Constraint::Length(2)]).areas(area);
            let mut text = vec![Line::from(PAIRED_TITLE).bold()];
            text.extend(lines.clone());
            text.push(key.clone());
            Paragraph::new(text).render(head, buf);
            let [labels, _, plot_area, values] = Layout::horizontal([
                Constraint::Length(label_width),
                Constraint::Length(2),
                Constraint::Fill(1),
                Constraint::Length(7),
            ])
            .areas(body);
            Paragraph::new(rows.iter().map(|row| Line::from(row.0.clone())).collect::<Vec<_>>())
                .alignment(Alignment::Right)
                .render(labels, buf);
            let plot = Plot { area: plot_area, x: bounds, y: [0.0, f64::from(count)] };
            plot.canvas(|ctx| {
                ctx.draw(&segment(0.0, 0.0, 0.0, f64::from(count), GUIDE));
                for (index, (_, difference, low, high, significant)) in rows.iter().enumerate() {
                    let y = f64::from(count) - index as f64 - 0.5;
                    let color = if *significant { SIGNIFICANT } else { GUIDE };
                    ctx.draw(&segment(*low, y, *high, y, color));
                    ctx.draw(&segment(*difference, y - 0.3, *difference, y + 0.3, color));
                }
            })
            .render(plot_area, buf);
            Paragraph::new(
                rows.iter()
                    .map(|row| Line::from(format!("{:+.1}", row.1)).fg(if row.4 { SIGNIFICANT } else { MUTED }))
                    .collect::<Vec<_>>(),
            )
            .alignment(Alignment::Right)
            .render(values, buf);
            let ticks = Plot { area: Rect { y: axis.y, height: 1, ..plot_area }, x: bounds, y: [0.0, 1.0] };
            let mut tick = bounds[0];
            while tick <= bounds[1] {
                let label = if tick == 0.0 { "0".to_string() } else { format!("{tick:+}") };
                ticks.text(buf, tick, 0.5, muted(label), Alignment::Center);
                tick += 5.0;
            }
            let caption = Plot { area: Rect { y: axis.y + 1, height: 1, ..plot_area }, x: bounds, y: [0.0, 1.0] };
            caption.text(
                buf,
                (bounds[0] + bounds[1]) / 2.0,
                0.5,
                muted("Accuracy of model A minus model B, in percentage points"),
                Alignment::Center,
            );
        }),
    }
}

// ---------------------------------------------------------------------------------------------
// 06 The two-step curves

const CASCADE_TITLE: &str = "What happens as we keep more answers from the first model?";

/// One panel per second model in its first format and part of the first models (decision models and
/// Gemma 4 31B, best first), each with its curves and the second model's own accuracy; the second models
/// come in order of Decider v1.1's saving in front of them. The savings table shows the format reruns.
fn cascade(results: &Results) -> Option<Figure<'_>> {
    let mut frontiers: Vec<&Run> = Vec::new();
    let mut decisions: Vec<&Run> = Vec::new();
    for cascade in &results.cascades {
        if let Some(run) = results
            .run(cascade.frontier)
            .filter(|run| run.format_of.is_none() && !frontiers.iter().any(|other| other.run == run.run))
        {
            frontiers.push(run);
        }
        if let Some(run) = results.run(cascade.decision).filter(|run| !decisions.iter().any(|other| other.run == run.run)) {
            decisions.push(run);
        }
    }
    let decider = results.find(DECIDER);
    let saving = |frontier: &Run| -> f64 {
        let pair = results.cascades.iter().find(|cascade| Some(cascade.decision) == decider.map(|run| run.run) && cascade.frontier == frontier.run);
        match (pair, cost(frontier)) {
            (Some(pair), Some(alone)) => 1.0 - pair.usd_per_1000 / alone,
            _ => 0.0,
        }
    };
    frontiers.sort_by(|first, second| saving(second).total_cmp(&saving(first)));
    decisions.sort_by_key(|run| (!results.is_decider(run), Reverse(run.correct)));
    // Room for the second model's line next to the first models' curves.
    let parts = split("first models", decisions, MAX_SERIES - 1);
    // Panels side by side, each plot 46 columns wide so that every 20% falls on a cell centre.
    let columns = parts.len().max(1) as u16;
    let width = columns * (Y_LABEL_WIDTH + 46 + PLOT_MARGIN) + (columns - 1) * PANEL_GAP;
    let mut panels = Vec::new();
    for frontier in &frontiers {
        let accuracy = 100.0 * results.cascades.iter().find(|cascade| cascade.frontier == frontier.run)?.frontier_accuracy;
        for (_, runs) in &parts {
            let mut series = Vec::new();
            for decision in runs {
                let Some(cascade) =
                    results.cascades.iter().find(|cascade| cascade.frontier == frontier.run && cascade.decision == decision.run)
                else {
                    continue;
                };
                let points = cascade.curve.iter().map(|&[answered, accuracy]| (100.0 * answered, 100.0 * accuracy)).collect();
                series.push(Series::line(results.setup_label(decision), color(decision), points).in_front(results.is_decider(decision)));
            }
            series.push(Series::line(format!("{} alone", frontier.name), GUIDE, vec![(0.0, accuracy), (100.0, accuracy)]));
            let y = accuracy_scale("Accuracy of the combined answers", &series);
            panels.push(Panel { title: format!("Second model: {}", results.setup_label(frontier)), series, y });
        }
    }
    if panels.is_empty() {
        return None;
    }
    let grid = Grid::new(panels, parts.len().max(1));
    let x = percent_scale("Share of questions answered by the first model", 0.0, 100.0, 20.0);
    let mut lines = vec![Line::from("We choose and test these cutoffs on the same questions.").bold()];
    lines.extend(notes(
        &format!(
            "We replayed recorded answers on the {} questions. Each first model answers the share of questions it is most confident about (x); the second model answers the rest. Grey line: the second model alone. Curves that use the same questions to choose and test can look better than a test on new questions; the main result uses separate halves.",
            thousands(results.questions)
        ),
        width,
    ));
    Some(Figure {
        name: "cascade",
        title: CASCADE_TITLE.into(),
        width,
        height: 2 + lines.len() as u16 + grid.height(width),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CASCADE_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    })
}

//! The results page's graphs, drawn with ratatui widgets.
//!
//! Each [`Figure`] draws into a ratatui buffer through a [`TestBackend`] ([`render`]). The buffer's
//! text is the figure's insta snapshot (`tests/snapshots.rs`), and [`svg::buffer_to_svg`] turns the
//! same buffer into the SVG the page shows (`src/main.rs`).

pub mod svg;

use std::collections::HashMap;
use std::error::Error;
use std::path::Path;

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Style, Stylize};
use ratatui::symbols::Marker;
use ratatui::text::{Line, Span};
use ratatui::widgets::canvas::{Canvas, Context, Line as Segment};
use ratatui::widgets::{Axis, Bar, BarChart, BarGroup, Block, Chart, Dataset, GraphType, Paragraph, Widget};
use serde::Deserialize;

/// The part of the page's `results.json` the figures use.
#[derive(Debug, Deserialize)]
pub struct Results {
    pub units: Vec<Unit>,
    pub runs: Vec<Run>,
    pub paired: Vec<Paired>,
    pub cascades: Vec<Cascade>,
    pub sources: Vec<SourceSet>,
}

#[derive(Debug, Deserialize)]
pub struct Unit {
    pub number: u32,
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
    pub groups: HashMap<String, Group>,
    pub units: Vec<u32>,
    pub confidence: Option<Confidence>,
}

#[derive(Debug, Deserialize)]
pub struct Group {
    pub questions: u32,
    pub correct: u32,
}

#[derive(Debug, Deserialize)]
pub struct Confidence {
    pub source: String,
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
    /// [share answered by the decision model, cascade accuracy], highest threshold first.
    pub curve: Vec<[f64; 2]>,
    pub in_sample: InSample,
}

#[derive(Debug, Deserialize)]
pub struct InSample {
    pub answered: f64,
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
    pub stated: bool,
    pub auroc: f64,
    pub risk_coverage: Vec<[f64; 2]>,
}

pub fn load(path: &Path) -> Result<Results, Box<dyn Error>> {
    Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
}

/// Calibration bins with fewer answers than this are too noisy to plot.
const MIN_BIN_ANSWERS: u32 = 20;

const GUIDE: Color = Color::Rgb(0x9c, 0xa3, 0xaf);
const MUTED: Color = Color::Rgb(0x6b, 0x72, 0x80);
const READING: Color = Color::Rgb(0x25, 0x63, 0xeb);
const GRAMMAR: Color = Color::Rgb(0xea, 0x58, 0x0c);
const SIGNIFICANT: Color = Color::Rgb(0x25, 0x63, 0xeb);

impl Results {
    fn run(&self, id: u32) -> Option<&Run> {
        self.runs.iter().find(|run| run.run == id)
    }

    /// A short name: the model, plus its setting when the model has more than one run or reasons.
    pub fn label(&self, run: &Run) -> String {
        let base = match run.model.as_str() {
            "gpt-6-astra" => "GPT-6 Astra",
            "claude-opus-5-5" => "Opus 5.5",
            "claude-sonnet-5-5" => "Sonnet 5.5",
            "deepseek-v4.1-flash" => "DeepSeek V4.1",
            "gemma-4-31B-it" => "Gemma 4 31B",
            "pplx-decider-v1-27b" => "Decider",
            "jev-1.13.0" => "Jev",
            "d1:free" => "d1",
            "open-jev-27b-v1.1" => "Open-Jev",
            "qwen38-27b-bf16" => "Qwen3.8",
            _ => run.name.as_str(),
        };
        if let Some(variant) = &run.variant {
            let variant = match variant.as_str() {
                "stated confidence" => "stated",
                "yes/no scoring" => "yes/no",
                other => other,
            };
            return format!("{base} {variant}");
        }
        let runs_of_model = self.runs.iter().filter(|other| other.model == run.model).count();
        match run.reasoning.as_deref() {
            Some(reasoning) if runs_of_model > 1 || reasoning != "off" => format!("{base} ({reasoning})"),
            _ => base.to_string(),
        }
    }
}

/// Each run's colour, the same in every figure.
fn color(run: &Run) -> Color {
    let rgb = |code: u32| Color::Rgb((code >> 16) as u8, (code >> 8) as u8, code as u8);
    match (run.model.as_str(), run.reasoning.as_deref(), run.variant.as_deref()) {
        ("gpt-6-astra", ..) => rgb(0x2563eb),
        ("claude-opus-5-5", ..) => rgb(0x7c3aed),
        ("claude-sonnet-5-5", Some("high"), _) => rgb(0xdb2777),
        ("claude-sonnet-5-5", ..) => rgb(0xf472b6),
        ("deepseek-v4.1-flash", Some("on"), _) => rgb(0x0e7490),
        ("deepseek-v4.1-flash", ..) => rgb(0x06b6d4),
        ("gemma-4-31B-it", ..) => rgb(0x16a34a),
        ("pplx-decider-v1-27b", ..) => rgb(0xea580c),
        ("jev-1.13.0", ..) => rgb(0xdc2626),
        ("d1:free", ..) => rgb(0xca8a04),
        ("open-jev-27b-v1.1", ..) => rgb(0x0d9488),
        ("qwen38-27b-bf16", _, Some("stated confidence")) => rgb(0x78716c),
        ("qwen38-27b-bf16", ..) => rgb(0x92400e),
        _ => GUIDE,
    }
}

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
        Some(reading_grammar(results)),
        Some(units(results)),
        Some(coverage(results)),
        Some(calibration(results)),
        sources(results),
        Some(paired(results)),
        cascade(results),
    ]
    .into_iter()
    .flatten()
    .collect()
}

struct Series {
    name: Option<String>,
    color: Color,
    points: Vec<(f64, f64)>,
    graph: GraphType,
    marker: Marker,
}

impl Series {
    fn line(name: impl Into<String>, color: Color, points: Vec<(f64, f64)>) -> Self {
        Self { name: Some(name.into()), color, points, graph: GraphType::Line, marker: Marker::Braille }
    }

    /// Points without a legend entry.
    fn dots(color: Color, points: Vec<(f64, f64)>) -> Self {
        Self { name: None, color, points, graph: GraphType::Scatter, marker: Marker::Dot }
    }
}

struct Scale {
    title: &'static str,
    bounds: [f64; 2],
    labels: Vec<String>,
}

/// A percentage axis from `low` to `high` with `steps` + 1 evenly spaced labels. Ratatui spaces the
/// x-axis labels in equal slots, so only three of them sit exactly on their values.
fn percent_scale(title: &'static str, low: f64, high: f64, steps: u32) -> Scale {
    let labels = (0..=steps).map(|step| format!("{}%", low + (high - low) * f64::from(step) / f64::from(steps))).collect();
    Scale { title, bounds: [low, high], labels }
}

/// A line chart without a legend ([`panel`] puts it below the chart, where it hides no data) and
/// without a y-axis title (the figure's heading names the axes).
fn line_chart<'a>(title: &'a str, series: &'a [Series], x: &'a Scale, y: &'a Scale) -> Chart<'a> {
    let datasets = series
        .iter()
        .map(|series| {
            Dataset::default()
                .marker(series.marker)
                .graph_type(series.graph)
                .style(Style::new().fg(series.color))
                .data(&series.points)
        })
        .collect();
    let labels = |scale: &'a Scale| scale.labels.iter().map(|label| Line::from(label.as_str()).fg(MUTED));
    Chart::new(datasets)
        .block(Block::new().title(Line::from(title).bold()))
        .x_axis(
            Axis::default()
                .title(Line::from(x.title).fg(MUTED))
                .bounds(x.bounds)
                .labels(labels(x))
                .style(Style::new().fg(GUIDE)),
        )
        .y_axis(Axis::default().bounds(y.bounds).labels(labels(y)).style(Style::new().fg(GUIDE)))
        .legend_position(None)
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
        line.push_span(Span::from(format!("{name}   ")));
    }
    lines
}

/// Line charts side by side, each with its legend below it. Every legend gets the height of the
/// tallest, so the charts keep the same size and their axes line up.
fn panels(buf: &mut Buffer, area: Rect, panels: &[(&str, &[Series])], x: &Scale, y: &Scale) {
    let mut constraints = Vec::new();
    for index in 0..panels.len() {
        if index > 0 {
            constraints.push(Constraint::Length(4));
        }
        constraints.push(Constraint::Fill(1));
    }
    let areas: Vec<Rect> = Layout::horizontal(constraints).split(area).iter().copied().step_by(2).collect();
    let keys: Vec<Vec<Line>> = panels.iter().zip(&areas).map(|((_, series), area)| legend(series, area.width)).collect();
    let height = keys.iter().map(Vec::len).max().unwrap_or(0) as u16;
    for (((title, series), keys), area) in panels.iter().zip(keys).zip(areas) {
        let [chart, _, keys_area] =
            Layout::vertical([Constraint::Fill(1), Constraint::Length(1), Constraint::Length(height)]).areas(area);
        line_chart(title, series, x, y).render(chart, buf);
        Paragraph::new(keys).render(keys_area, buf);
    }
}

/// A figure's heading, then a blank row; returns the area below them.
fn heading(buf: &mut Buffer, area: Rect, text: &str) -> Rect {
    let [top, rest] = Layout::vertical([Constraint::Length(2), Constraint::Fill(1)]).areas(area);
    Paragraph::new(Line::from(text.to_string()).bold()).render(top, buf);
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

fn reading_grammar(results: &Results) -> Figure<'_> {
    let rows: Vec<(String, f64, f64)> = results
        .runs
        .iter()
        .filter_map(|run| Some((results.label(run), accuracy(run.groups.get("reading")?), accuracy(run.groups.get("grammar")?))))
        .collect();
    let height = rows.len() as u16 * 3 + 1;
    Figure {
        name: "reading-grammar",
        title: "Each run's accuracy on the reading units (1–6) and on the grammar units (7–20)".into(),
        width: 100,
        height,
        draw: Box::new(move |area, buf| {
            let title = Line::from(vec![
                Span::from("Accuracy on reading and grammar   ").bold(),
                Span::from("██").fg(READING),
                Span::from(" reading (units 1–6)   "),
                Span::from("██").fg(GRAMMAR),
                Span::from(" grammar (units 7–20)"),
            ]);
            let bar = |value: f64, color: Color, label: &str| {
                Bar::new((value * 10.0).round() as u64)
                    .label(Line::from(label.to_string()))
                    .text_value(format!("{value:.1}%"))
                    .style(Style::new().fg(color))
                    .value_style(Style::new().fg(Color::White).bg(color))
            };
            let chart = rows.iter().fold(
                BarChart::default()
                    .block(Block::new().title(title))
                    .direction(Direction::Horizontal)
                    .bar_width(1)
                    .bar_gap(0)
                    .group_gap(1)
                    .max(1000),
                |chart, (name, reading, grammar)| {
                    chart.data(BarGroup::new(vec![bar(*reading, READING, name), bar(*grammar, GRAMMAR, "")]))
                },
            );
            chart.render(area, buf);
        }),
    }
}

/// The runs on the per-unit chart: (model, reasoning setting).
const UNIT_RUNS: [(&str, Option<&str>); 6] = [
    ("gpt-6-astra", Some("low")),
    ("deepseek-v4.1-flash", Some("on")),
    ("gemma-4-31B-it", Some("off")),
    ("deepseek-v4.1-flash", Some("off")),
    ("jev-1.13.0", None),
    ("laya", None),
];

fn units(results: &Results) -> Figure<'_> {
    let lines: Vec<(String, Color, Vec<(f64, f64)>)> = UNIT_RUNS
        .iter()
        .filter_map(|(model, reasoning)| {
            let run = results.runs.iter().find(|run| run.model == *model && run.reasoning.as_deref() == *reasoning)?;
            let points = results
                .units
                .iter()
                .zip(&run.units)
                .map(|(unit, correct)| (f64::from(unit.number), 100.0 * f64::from(*correct) / f64::from(unit.questions)))
                .collect();
            Some((results.label(run), color(run), points))
        })
        .collect();
    let count = results.units.len();
    let (left, right, reading_end) = (0.5, count as f64 + 0.5, 6.5);
    Figure {
        name: "units",
        title: "Accuracy by unit for six runs, with the 20% chance level and the 22.7% level of always answering E".into(),
        width: 120,
        height: 27,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, "Accuracy by unit (y) for six runs, units 1–20 (x)");
            let plot = Plot { area: body, x: [-4.0, right + 5.0], y: [-14.0, 106.0] };
            plot.canvas(|ctx| {
                ctx.draw(&segment(left, 0.0, right, 0.0, GUIDE));
                ctx.draw(&segment(left, 0.0, left, 100.0, GUIDE));
                ctx.draw(&segment(reading_end, 0.0, reading_end, 100.0, GUIDE));
                ctx.draw(&segment(left, 20.0, right, 20.0, GUIDE));
                ctx.draw(&segment(left, 22.7, right, 22.7, GUIDE));
                for (_, color, points) in &lines {
                    for pair in points.windows(2) {
                        ctx.draw(&segment(pair[0].0, pair[0].1, pair[1].0, pair[1].1, *color));
                    }
                }
            })
            .render(body, buf);
            for value in (0..=100).step_by(20) {
                plot.text(buf, left - 0.6, f64::from(value), muted(format!("{value}%")), Alignment::Right);
            }
            for unit in 1..=count {
                plot.text(buf, unit as f64, -7.0, muted(unit.to_string()), Alignment::Center);
            }
            plot.text(buf, right + 0.4, -7.0, muted("unit"), Alignment::Left);
            plot.text(buf, (left + reading_end) / 2.0, 103.0, muted("reading"), Alignment::Center);
            plot.text(buf, (reading_end + right) / 2.0, 103.0, muted("grammar"), Alignment::Center);
            plot.text(buf, right + 0.4, 17.0, muted("chance 20%"), Alignment::Left);
            plot.text(buf, right + 0.4, 27.0, muted("always E 22.7%"), Alignment::Left);
            // The legend sits in the empty space below the reading units' lines, one run per row.
            let (column, top) = plot.cell(left + 0.6, 64.0);
            for (index, (label, color, _)) in lines.iter().enumerate() {
                let key = Line::from(vec![Span::from("━━ ").fg(*color), Span::from(label.clone())]);
                buf.set_line(column, top + index as u16, &key, body.right().saturating_sub(column));
            }
        }),
    }
}

fn coverage_curve(points: &[[f64; 2]]) -> Vec<(f64, f64)> {
    points.iter().map(|&[coverage, risk]| (100.0 * coverage, 100.0 * (1.0 - risk))).collect()
}

fn coverage(results: &Results) -> Figure<'_> {
    let curves = |source: &str| -> Vec<Series> {
        results
            .runs
            .iter()
            .filter_map(|run| {
                let confidence = run.confidence.as_ref()?;
                (confidence.source == source && run.provider != "laya")
                    .then(|| Series::line(results.label(run), color(run), coverage_curve(&confidence.risk_coverage)))
            })
            .collect()
    };
    let (probability, stated) = (curves("probability"), curves("stated"));
    let x = percent_scale("answered", 0.0, 100.0, 2);
    let y = percent_scale("accuracy", 40.0, 100.0, 6);
    Figure {
        name: "coverage",
        title: "Accuracy on the most confident share of the answers, for probabilities and for stated confidence".into(),
        width: 160,
        height: 30,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, "Accuracy (y) on the most confident share of the answers (x)");
            panels(buf, body, &[("Probability of the chosen option", &probability), ("Stated by the model", &stated)], &x, &y);
        }),
    }
}

fn calibration(results: &Results) -> Figure<'_> {
    let bins = |source: &str| -> Vec<Series> {
        let mut series = vec![Series::line("perfect calibration", GUIDE, vec![(0.0, 0.0), (100.0, 100.0)])];
        for run in &results.runs {
            let Some(confidence) = run.confidence.as_ref().filter(|confidence| confidence.source == source) else { continue };
            if run.provider == "laya" {
                continue;
            }
            let points: Vec<(f64, f64)> = confidence
                .reliability
                .iter()
                .filter(|bin| bin.questions >= MIN_BIN_ANSWERS)
                .filter_map(|bin| Some((100.0 * bin.mean_confidence?, 100.0 * bin.accuracy?)))
                .collect();
            series.push(Series::line(results.label(run), color(run), points.clone()));
            series.push(Series::dots(color(run), points));
        }
        series
    };
    let (probability, stated) = (bins("probability"), bins("stated"));
    let x = percent_scale("mean confidence", 0.0, 100.0, 2);
    let y = percent_scale("accuracy", 0.0, 100.0, 4);
    Figure {
        name: "calibration",
        title: format!(
            "Calibration: accuracy against mean confidence in each tenth of the confidence range with at least {MIN_BIN_ANSWERS} answers"
        ),
        width: 160,
        height: 30,
        draw: Box::new(move |area, buf| {
            let text = format!(
                "Accuracy (y) against mean confidence (x), in each tenth of the confidence range with at least {MIN_BIN_ANSWERS} answers"
            );
            let body = heading(buf, area, &text);
            panels(buf, body, &[("Probability of the chosen option", &probability), ("Stated by the model", &stated)], &x, &y);
        }),
    }
}

fn sources(results: &Results) -> Option<Figure<'_>> {
    let set = results.sources.first()?;
    let answers = results.run(set.answers)?;
    let series: Vec<Series> = set
        .sources
        .iter()
        .filter_map(|source| {
            let run = results.run(source.run)?;
            let name = if source.stated {
                format!("stated confidence, AUROC {:.3}", source.auroc)
            } else {
                format!("{} probability, AUROC {:.3}", results.label(run), source.auroc)
            };
            Some(Series::line(name, color(run), coverage_curve(&source.risk_coverage)))
        })
        .collect();
    let title = format!(
        "{}'s own answers ({} of {} right), scored by three confidence sources",
        answers.name,
        thousands(set.correct),
        thousands(set.questions)
    );
    let x = percent_scale("answered", 0.0, 100.0, 2);
    let y = percent_scale("accuracy", 40.0, 100.0, 6);
    Some(Figure {
        name: "sources",
        title: title.clone(),
        width: 100,
        height: 26,
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, &title);
            panels(buf, body, &[("Accuracy (y) on the most confident share (x)", &series)], &x, &y);
        }),
    })
}

fn paired(results: &Results) -> Figure<'_> {
    let rows: Vec<(String, f64, f64, f64, bool)> = results
        .paired
        .iter()
        .filter_map(|pair| {
            let (first, second) = (results.run(pair.first)?, results.run(pair.second)?);
            Some((
                format!("{} vs {}", results.label(first), results.label(second)),
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
    Figure {
        name: "paired",
        title: "Accuracy difference of each paired comparison, in percentage points, with its 95% interval".into(),
        width: 120,
        height: count + 5,
        draw: Box::new(move |area, buf| {
            let [title, body, axis] =
                Layout::vertical([Constraint::Length(3), Constraint::Length(count), Constraint::Length(2)]).areas(area);
            Paragraph::new(vec![
                Line::from("Accuracy difference, first run minus second, in percentage points, with 95% intervals").bold(),
                Line::from(vec![
                    Span::from("━━ ").fg(SIGNIFICANT),
                    Span::from("significant after Holm correction   "),
                    Span::from("━━ ").fg(GUIDE),
                    Span::from("not significant"),
                ]),
            ])
            .render(title, buf);
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
            caption.text(buf, (bounds[0] + bounds[1]) / 2.0, 0.5, muted("percentage points"), Alignment::Center);
        }),
    }
}

/// The frontier runs on the cascade figure: (model, reasoning setting).
const CASCADE_FRONTIERS: [(&str, &str); 2] = [("gpt-6-astra", "low"), ("claude-sonnet-5-5", "high")];

fn cascade(results: &Results) -> Option<Figure<'_>> {
    let mut charts: Vec<(String, Vec<Series>)> = Vec::new();
    for (model, reasoning) in CASCADE_FRONTIERS {
        let frontier = results.runs.iter().find(|run| run.model == model && run.reasoning.as_deref() == Some(reasoning))?;
        let cascades: Vec<&Cascade> = results.cascades.iter().filter(|cascade| cascade.frontier == frontier.run).collect();
        let accuracy = 100.0 * cascades.first()?.frontier_accuracy;
        // Curves first, then the frontier line over them, then the threshold dots: where a curve keeps
        // the frontier's accuracy it is hidden under the line, so each curve shows where it falls away.
        let mut series = Vec::new();
        let mut thresholds = Vec::new();
        for cascade in cascades {
            let Some(decision) = results.run(cascade.decision) else { continue };
            let points = cascade.curve.iter().map(|&[answered, accuracy]| (100.0 * answered, 100.0 * accuracy)).collect();
            series.push(Series::line(results.label(decision), color(decision), points));
            thresholds.push(Series::dots(color(decision), vec![(100.0 * cascade.in_sample.answered, accuracy)]));
        }
        series.push(Series::line(format!("{} alone", results.label(frontier)), GUIDE, vec![(0.0, accuracy), (100.0, accuracy)]));
        series.extend(thresholds);
        charts.push((format!("Before {}", results.label(frontier)), series));
    }
    let x = percent_scale("answered by the decision model", 0.0, 100.0, 2);
    let y = percent_scale("accuracy", 50.0, 100.0, 5);
    Some(Figure {
        name: "cascade",
        title: "Cascade accuracy against the share of questions the decision model answers, before two frontier runs".into(),
        width: 160,
        height: 30,
        draw: Box::new(move |area, buf| {
            let body = heading(
                buf,
                area,
                "Accuracy (y) when a decision model answers its most confident share (x) and a frontier run the rest; dots: in-sample threshold",
            );
            let pairs: Vec<(&str, &[Series])> = charts.iter().map(|(title, series)| (title.as_str(), series.as_slice())).collect();
            panels(buf, body, &pairs, &x, &y);
        }),
    })
}

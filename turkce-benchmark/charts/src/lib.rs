//! The results page's graphs, drawn with ratatui widgets.
//!
//! Each [`Figure`] draws into a ratatui buffer through a [`TestBackend`] ([`render`]). The buffer's
//! text is the figure's insta snapshot (`tests/snapshots.rs`), and [`svg::buffer_to_svg`] turns the
//! same buffer into the SVG the page shows (`src/main.rs`). [`og::og_image`] draws the sharing card.

pub mod og;
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
    /// The scored questions: the denominator of every accuracy.
    pub questions: u32,
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
    /// Correct answers among the scored questions.
    pub correct: u32,
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

/// The threshold chosen and scored on all questions.
#[derive(Debug, Deserialize)]
pub struct InSample {
    pub answered: f64,
    pub accuracy: f64,
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

pub fn load(path: &Path) -> Result<Results, Box<dyn Error>> {
    Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
}

/// Models that answer near chance on this bank; their runs share a panel in the confidence figures.
const NEAR_CHANCE_MODELS: [&str; 4] = ["laya", "laya-multilingual", "gliner2.5-multi-v1", "gliner2.5-multi-decide"];
/// Calibration bins with fewer answers than this are too noisy to plot (the page's table keeps them).
const MIN_BIN_ANSWERS: u32 = 20;
/// Calibration bins with at least this many answers get the large dot.
const LARGE_BIN_ANSWERS: u32 = 200;
/// Units 1 to 6 are reading comprehension; the rest are grammatical analysis.
const READING_UNITS: u32 = 6;
/// The most curves one panel shows, so that a reader can follow each of them.
const MAX_SERIES: usize = 6;

const GUIDE: Color = Color::Rgb(0x9c, 0xa3, 0xaf);
const MUTED: Color = Color::Rgb(0x6b, 0x72, 0x80);
const GRIDLINE: Color = Color::Rgb(0xe5, 0xe7, 0xeb);
const READING: Color = Color::Rgb(0x25, 0x63, 0xeb);
const GRAMMAR: Color = Color::Rgb(0xea, 0x58, 0x0c);
const SIGNIFICANT: Color = Color::Rgb(0x25, 0x63, 0xeb);

impl Results {
    fn run(&self, id: u32) -> Option<&Run> {
        self.runs.iter().find(|run| run.run == id)
    }

    /// A short name with the run's setting: its variant, else its reasoning setting, in parentheses
    /// (merged into a parenthesis the name already ends with, as in "(preview, high)").
    pub fn label(&self, run: &Run) -> String {
        let base = match run.model.as_str() {
            "claude-opus-5-5" => "Opus 5.5",
            "claude-sonnet-5-5" => "Sonnet 5.5",
            "pplx-decider-v1-27b" => "Decider",
            "jev-1.13.0" => "Jev",
            "d1:free" => "d1",
            "open-jev-27b-v1.1" => "Open-Jev",
            _ => run.name.as_str(),
        };
        with_setting(base, run)
    }

    /// The reading and grammar question counts, from the units.
    pub fn part_questions(&self) -> (u32, u32) {
        let reading = self.units.iter().filter(|unit| unit.number <= READING_UNITS).map(|unit| unit.questions).sum();
        let grammar = self.units.iter().filter(|unit| unit.number > READING_UNITS).map(|unit| unit.questions).sum();
        (reading, grammar)
    }
}

/// `base` followed by the run's setting in parentheses, if it has one.
fn with_setting(base: &str, run: &Run) -> String {
    let setting = match (run.variant.as_deref(), run.reasoning.as_deref()) {
        (Some("stated confidence"), _) => "stated",
        (Some("yes/no scoring"), _) => "yes/no",
        (Some(variant), _) => variant,
        (None, Some(reasoning)) => reasoning,
        (None, None) => return base.to_string(),
    };
    match base.strip_suffix(')') {
        Some(open) => format!("{open}, {setting})"),
        None => format!("{base} ({setting})"),
    }
}

/// Each run's colour, the same in every figure and distinct within each panel.
fn color(run: &Run) -> Color {
    let rgb = |code: u32| Color::Rgb((code >> 16) as u8, (code >> 8) as u8, code as u8);
    match (run.model.as_str(), run.reasoning.as_deref(), run.variant.as_deref()) {
        ("gpt-6-astra", ..) => rgb(0x2563eb),
        ("gpt-6.1-sol", ..) => rgb(0x0891b2),
        ("gpt-6-luna", ..) => rgb(0x60a5fa),
        ("gemini-3.8-flash", ..) => rgb(0x65a30d),
        ("erk-14b", ..) => rgb(0xe11d48),
        ("qwen3-14b", ..) => rgb(0xfda4af),
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
        ("clef", ..) => rgb(0x9333ea),
        ("metask-jev-4b-policy-mix", ..) => rgb(0x1e40af),
        ("cygnet", ..) => rgb(0x27272a),
        ("winnow-12b", ..) => rgb(0xbe185d),
        ("fastino/GLiDE", ..) => rgb(0x059669),
        ("qwen38-27b-bf16", _, Some("stated confidence")) => rgb(0x78716c),
        ("qwen38-27b-bf16", _, Some("vote share")) => rgb(0x4f46e5),
        ("qwen38-27b-bf16", ..) => rgb(0x92400e),
        ("laya", ..) => rgb(0xa16207),
        ("laya-multilingual", ..) => rgb(0xf59e0b),
        ("gliner2.5-multi-v1", ..) => rgb(0x475569),
        ("gliner2.5-multi-decide", ..) => rgb(0x2563eb),
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

/// A curve, dots, or both. Only named series get a legend key.
struct Series {
    name: Option<String>,
    color: Color,
    points: Vec<(f64, f64)>,
    line: bool,
    marker: Option<char>,
}

impl Series {
    fn line(name: impl Into<String>, color: Color, points: Vec<(f64, f64)>) -> Self {
        Self { name: Some(name.into()), color, points, line: true, marker: None }
    }

    /// A line without a legend entry.
    fn guide(color: Color, points: Vec<(f64, f64)>) -> Self {
        Self { name: None, color, points, line: true, marker: None }
    }

    /// Points drawn as `marker`, without a legend entry.
    fn dots(color: Color, points: Vec<(f64, f64)>, marker: char) -> Self {
        Self { name: None, color, points, line: false, marker: Some(marker) }
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
        line.push_span(Span::from(format!("{name}   ")));
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
}

impl Grid {
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
                draw_panel(buf, Rect::new(left, top, width, height), panel, x, self.plot_rows);
            }
            top += height + 1;
        }
    }
}

fn draw_panel(buf: &mut Buffer, area: Rect, panel: &Panel, x: &Scale, plot_rows: u16) {
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
    plot.canvas(|ctx| {
        ctx.draw(&segment(left, bottom, right, bottom, GUIDE));
        ctx.draw(&segment(left, bottom, left, top, GUIDE));
        for series in panel.series.iter().filter(|series| series.line) {
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

/// A figure's heading: its title in bold, then its lines in grey, then a blank row; returns the area below.
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

/// Percent labels for `ticks` on a row, centred on the left edges of the cells where those values
/// fall in a bar area of `cells` columns from `x`.
fn bar_ticks(buf: &mut Buffer, x: u16, y: u16, cells: u16, ticks: &[f64]) {
    for &tick in ticks {
        let label = percent(tick);
        let edge = x + (tick / 100.0 * f64::from(cells)).round() as u16;
        buf.set_line(edge.saturating_sub(label.len() as u16 / 2), y, &muted(label), 6);
    }
}

const READING_GRAMMAR_TITLE: &str = "Strong reading performance can coexist with weak grammar performance";
/// The bar charts' labelled values; the cells for the bars are a multiple of 4, so each lands on a cell edge.
const BAR_TICKS: [f64; 5] = [0.0, 25.0, 50.0, 75.0, 100.0];

fn reading_grammar(results: &Results) -> Figure<'_> {
    let rows: Vec<(String, f64, f64)> = results
        .runs
        .iter()
        .filter_map(|run| Some((results.label(run), accuracy(run.groups.get("reading")?), accuracy(run.groups.get("grammar")?))))
        .collect();
    let (reading_questions, grammar_questions) = results.part_questions();
    let label_width = rows.iter().map(|row| row.0.chars().count()).max().unwrap_or(0) as u16;
    let width = 100;
    // Labels, two spaces, the bars, then room for a value ("100.0%") after the longest bar.
    let cells = (width - label_width - 2 - 8) / 4 * 4;
    // The heading's three rows, tick labels above and below, two bars per run with a blank row between runs.
    let height = 3 + 2 + rows.len() as u16 * 3 - 1;
    Figure {
        name: "reading-grammar",
        title: READING_GRAMMAR_TITLE.into(),
        width,
        height,
        draw: Box::new(move |area, buf| {
            let key = Line::from(vec![
                Span::from("██").fg(READING),
                Span::from(format!(" Reading comprehension ({} questions)   ", thousands(reading_questions))),
                Span::from("██").fg(GRAMMAR),
                Span::from(format!(" Grammatical analysis ({} questions)", thousands(grammar_questions))),
            ]);
            let body = heading(buf, area, READING_GRAMMAR_TITLE, vec![key]);
            let x = body.x + label_width + 2;
            let (top, bottom) = (body.y, body.y + rows.len() as u16 * 3);
            bar_ticks(buf, x, top, cells, &BAR_TICKS);
            bar_ticks(buf, x, bottom, cells, &BAR_TICKS);
            for (index, (label, reading, grammar)) in rows.iter().enumerate() {
                let y = top + 1 + index as u16 * 3;
                let start = body.x + label_width - label.chars().count() as u16;
                buf.set_line(start, y, &Line::from(label.clone()), label_width);
                for (row, value, color) in [(y, *reading, READING), (y + 1, *grammar, GRAMMAR)] {
                    let end = bar(buf, x, row, cells, value, color);
                    buf.set_line(end + 1, row, &muted(format!("{value:.1}%")), 7);
                }
            }
            // Gridlines at the labelled values, behind the bars and their values.
            for tick in BAR_TICKS {
                let column = x + (tick / 100.0 * f64::from(cells)).round() as u16;
                for row in top + 1..bottom {
                    let cell = &mut buf[(column, row)];
                    if cell.symbol() == " " {
                        cell.set_char('▏').set_fg(GRIDLINE);
                    }
                }
            }
        }),
    }
}

/// The runs on the per-topic chart: (model, reasoning setting).
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
    let title = format!("Where performance changes across {count} topics");
    let (left, right, reading_end) = (0.5, count as f64 + 0.5, f64::from(READING_UNITS) + 0.5);
    let width = 120;
    let keys = legend(&lines.iter().map(|(label, color, _)| Series::line(label.clone(), *color, Vec::new())).collect::<Vec<_>>(), width);
    // The plot's rows; the topic numbers and question counts follow, then a blank row and the legend.
    const PLOT_HEIGHT: u16 = 25;
    Figure {
        name: "units",
        title: title.clone(),
        width,
        height: 3 + PLOT_HEIGHT + 3 + keys.len() as u16,
        draw: Box::new(move |area, buf| {
            let body = heading(
                buf,
                area,
                &title,
                vec![muted(format!(
                    "Accuracy (y) by topic (x) for {} runs. Topics 1–{READING_UNITS}: reading comprehension; {}–{count}: grammatical analysis.",
                    lines.len(),
                    READING_UNITS + 1
                ))],
            );
            let plot = Plot { area: Rect { height: PLOT_HEIGHT, ..body }, x: [-4.0, right + 6.0], y: [-3.0, 106.0] };
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
            .render(plot.area, buf);
            for value in (0..=100).step_by(20) {
                plot.text(buf, left - 0.6, f64::from(value), muted(format!("{value}%")), Alignment::Right);
            }
            // Below the axis: the topic numbers, then each topic's question count.
            let labels = Plot { area: body, ..plot };
            let numbers = plot.cell(left, 0.0).1 + 1;
            for unit in &results.units {
                let (column, _) = plot.cell(f64::from(unit.number), 0.0);
                labels.place(buf, column, numbers, muted(unit.number.to_string()), Alignment::Center);
                labels.place(buf, column, numbers + 1, muted(unit.questions.to_string()), Alignment::Center);
            }
            let (after, _) = plot.cell(right + 0.4, 0.0);
            labels.place(buf, after, numbers, muted("topic"), Alignment::Left);
            labels.place(buf, after, numbers + 1, muted("questions"), Alignment::Left);
            plot.text(buf, (left + reading_end) / 2.0, 103.0, muted("reading comprehension"), Alignment::Center);
            plot.text(buf, (reading_end + right) / 2.0, 103.0, muted("grammatical analysis"), Alignment::Center);
            plot.text(buf, right + 0.4, 17.0, muted("chance 20%"), Alignment::Left);
            plot.text(buf, right + 0.4, 27.0, muted("always E 22.7%"), Alignment::Left);
            // The legend below the topic numbers and question counts.
            let top = body.y + PLOT_HEIGHT + 3;
            Paragraph::new(keys.clone()).render(Rect::new(body.x, top, body.width, body.bottom() - top), buf);
        }),
    }
}

/// `runs` (best first) in the fewest parts of at most [`MAX_SERIES`] runs, as even as possible, each named.
fn split<'a>(name: &str, runs: Vec<&'a Run>, max: usize) -> Vec<(String, Vec<&'a Run>)> {
    if runs.is_empty() {
        return Vec::new();
    }
    let parts = runs.len().div_ceil(max);
    let size = runs.len().div_ceil(parts);
    runs.chunks(size)
        .enumerate()
        .map(|(index, chunk)| {
            let title = match (parts, index) {
                (1, _) => name.to_string(),
                (2, 0) => format!("{name}, higher scores"),
                (2, _) => format!("{name}, lower scores"),
                _ => format!("{name}, part {} of {parts}", index + 1),
            };
            (title, chunk.to_vec())
        })
        .collect()
}

/// The panels of the confidence figures, in order.
const FAMILIES: [&str; 6] = [
    "Frontier APIs: OpenAI and Google",
    "Frontier APIs: Anthropic",
    "Open-weight generative models",
    "Qwen3.8-27B, different confidence scores",
    "Decision models",
    "Near chance: Laya and GLiNER",
];

/// Which of [`FAMILIES`] a run belongs to.
fn family(run: &Run) -> usize {
    if NEAR_CHANCE_MODELS.contains(&run.model.as_str()) {
        5
    } else if matches!(run.provider.as_str(), "openai" | "gemini") {
        0
    } else if run.provider == "claude" {
        1
    } else if run.model == "qwen38-27b-bf16" {
        3
    } else if run.provider == "vllm" {
        2
    } else {
        4
    }
}

/// The runs with a confidence score in panels of related runs, best first in each; every run
/// lands in exactly one panel. A panel whose runs share a confidence source names it.
fn families(results: &Results) -> Vec<(String, Vec<&Run>)> {
    let mut runs: Vec<&Run> = results.runs.iter().filter(|run| run.confidence.is_some()).collect();
    runs.sort_by_key(|run| Reverse(run.correct));
    FAMILIES
        .iter()
        .enumerate()
        .flat_map(|(index, name)| split(name, runs.iter().copied().filter(|run| family(run) == index).collect(), MAX_SERIES))
        .map(|(title, runs)| {
            let sources: Vec<&str> =
                runs.iter().filter_map(|run| run.confidence.as_ref()).map(|confidence| confidence.source.as_str()).collect();
            let source = match sources.first() {
                Some(first) if sources.iter().all(|source| source == first) => match *first {
                    "stated" => " · stated confidence",
                    "probability" => " · option probability",
                    "votes" => " · share of samples",
                    _ => "",
                },
                _ => "",
            };
            (format!("{title}{source}"), runs)
        })
        .collect()
}

fn coverage_curve(points: &[[f64; 2]]) -> Vec<(f64, f64)> {
    points.iter().map(|&[coverage, risk]| (100.0 * coverage, 100.0 * (1.0 - risk))).collect()
}

const COVERAGE_TITLE: &str = "How accuracy changes when we keep only the most confident answers";
const COVERAGE_X: &str = "Share of answers retained";
const COVERAGE_Y: &str = "Accuracy among retained answers";
const CALIBRATION_TITLE: &str = "Does 0.8 mean 80% right?";
const SOURCES_TITLE: &str = "Different confidence methods, the same Qwen answers";
/// Columns of the confidence figures' panel grids.
const WIDE_WIDTH: u16 = 160;

fn coverage(results: &Results) -> Figure<'_> {
    let panels = families(results)
        .into_iter()
        .map(|(title, runs)| {
            let series: Vec<Series> = runs
                .iter()
                .filter_map(|run| {
                    let confidence = run.confidence.as_ref()?;
                    Some(Series::line(results.label(run), color(run), coverage_curve(&confidence.risk_coverage)))
                })
                .collect();
            let y = accuracy_scale(COVERAGE_Y, &series);
            Panel { title, series, y }
        })
        .collect();
    let grid = Grid { panels, columns: 2, plot_rows: PLOT_ROWS };
    let x = percent_scale(COVERAGE_X, 0.0, 100.0, 20.0);
    let lines = vec![muted(
        "Answers ordered from most to least confident; each curve ends at the run's accuracy on all answers. Panels group related runs; read each panel's own y axis.",
    )];
    Figure {
        name: "coverage",
        title: COVERAGE_TITLE.into(),
        width: WIDE_WIDTH,
        height: 3 + grid.height(WIDE_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, COVERAGE_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    }
}

fn calibration(results: &Results) -> Figure<'_> {
    let panels = families(results)
        .into_iter()
        .map(|(title, runs)| {
            let mut series = vec![Series::guide(GUIDE, vec![(0.0, 0.0), (100.0, 100.0)])];
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
                series.push(Series::line(results.label(run), color(run), bins.iter().map(|bin| (bin.0, bin.1)).collect()));
                series.push(Series::dots(color(run), points(false), '•'));
                series.push(Series::dots(color(run), points(true), '●'));
            }
            Panel { title, series, y: percent_scale("Share of answers right", 0.0, 100.0, 20.0) }
        })
        .collect();
    let grid = Grid { panels, columns: 2, plot_rows: PLOT_ROWS };
    let x = percent_scale("Mean confidence in the range", 0.0, 100.0, 20.0);
    let lines = vec![
        muted("Accuracy (y) against mean confidence (x) in each tenth of the confidence range; grey diagonal: perfect calibration."),
        muted(format!(
            "Dot size shows the answers in a tenth: • {MIN_BIN_ANSWERS} to {}, ● {LARGE_BIN_ANSWERS} or more. Tenths with fewer than {MIN_BIN_ANSWERS} answers are left out of the plot (the table keeps them).",
            LARGE_BIN_ANSWERS - 1
        )),
    ];
    Figure {
        name: "calibration",
        title: CALIBRATION_TITLE.into(),
        width: WIDE_WIDTH,
        height: 4 + grid.height(WIDE_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CALIBRATION_TITLE, lines.clone());
            grid.render(buf, body, &x);
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
            let method = match source.kind.as_str() {
                "stated" => "stated confidence".to_string(),
                "votes" => "share of 10 samples agreeing".to_string(),
                _ => format!("{} probability", results.label(run)),
            };
            Some(Series::line(format!("{method}, AUROC {:.3}", source.auroc), color(run), coverage_curve(&source.risk_coverage)))
        })
        .collect();
    let y = accuracy_scale(COVERAGE_Y, &series);
    let grid = Grid { panels: vec![Panel { title: String::new(), series, y }], columns: 1, plot_rows: PLOT_ROWS };
    let lines = vec![muted(format!(
        "{}'s answers, the same for every method: {} correct of {}",
        answers.name,
        thousands(set.correct),
        thousands(set.questions)
    ))];
    let x = percent_scale(COVERAGE_X, 0.0, 100.0, 20.0);
    // A plot 91 columns wide, so that the x labels fall on cell centres (see `centred`).
    let width = 98;
    Some(Figure {
        name: "sources",
        title: SOURCES_TITLE.into(),
        width,
        height: 3 + grid.height(width),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, SOURCES_TITLE, lines.clone());
            grid.render(buf, body, &x);
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
    // The title counts the gaps that stay significant after the Holm correction, so it follows the data.
    let title = format!("{} of {} gaps are real", rows.iter().filter(|row| row.4).count(), rows.len());
    Figure {
        name: "paired",
        title: title.clone(),
        width: 120,
        height: count + 6,
        draw: Box::new(move |area, buf| {
            let [head, body, axis] =
                Layout::vertical([Constraint::Length(4), Constraint::Length(count), Constraint::Length(2)]).areas(area);
            Paragraph::new(vec![
                Line::from(title.clone()).bold(),
                muted("Accuracy difference, first run minus second, in percentage points, with 95% intervals"),
                Line::from(vec![
                    Span::from("━━ ").fg(SIGNIFICANT),
                    Span::from("significant after Holm correction   "),
                    Span::from("━━ ").fg(GUIDE),
                    Span::from("not significant"),
                ]),
            ])
            .render(head, buf);
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

const CASCADE_TITLE: &str = "How routing accuracy changes as the cheaper model answers more questions";

/// One panel per frontier run and part of the decision models (best first), each with its curves,
/// the frontier run's own accuracy and the in-sample thresholds.
fn cascade(results: &Results) -> Option<Figure<'_>> {
    let mut frontiers: Vec<&Run> = Vec::new();
    let mut decisions: Vec<&Run> = Vec::new();
    for cascade in &results.cascades {
        if let Some(run) = results.run(cascade.frontier).filter(|run| !frontiers.iter().any(|other| other.run == run.run)) {
            frontiers.push(run);
        }
        if let Some(run) = results.run(cascade.decision).filter(|run| !decisions.iter().any(|other| other.run == run.run)) {
            decisions.push(run);
        }
    }
    decisions.sort_by_key(|run| Reverse(run.correct));
    // Room for the frontier line next to the decision models' curves.
    let parts = split("Decision models", decisions, MAX_SERIES - 1);
    let mut panels = Vec::new();
    for frontier in &frontiers {
        let accuracy = 100.0 * results.cascades.iter().find(|cascade| cascade.frontier == frontier.run)?.frontier_accuracy;
        for (part, runs) in &parts {
            // Curves first, then the frontier line over them, then the threshold dots: where a curve keeps
            // the frontier's accuracy it is hidden under the line, so each curve shows where it falls away.
            let mut series = Vec::new();
            let mut thresholds = Vec::new();
            for decision in runs {
                let Some(cascade) =
                    results.cascades.iter().find(|cascade| cascade.frontier == frontier.run && cascade.decision == decision.run)
                else {
                    continue;
                };
                let points = cascade.curve.iter().map(|&[answered, accuracy]| (100.0 * answered, 100.0 * accuracy)).collect();
                series.push(Series::line(results.label(decision), color(decision), points));
                let threshold = (100.0 * cascade.in_sample.answered, 100.0 * cascade.in_sample.accuracy);
                thresholds.push(Series::dots(color(decision), vec![threshold], '●'));
            }
            series.push(Series::line(format!("{} alone", results.label(frontier)), GUIDE, vec![(0.0, accuracy), (100.0, accuracy)]));
            series.extend(thresholds);
            let y = accuracy_scale("Accuracy of the two-model pipeline", &series);
            panels.push(Panel { title: format!("{part} → {}", results.label(frontier)), series, y });
        }
    }
    if panels.is_empty() {
        return None;
    }
    let grid = Grid { panels, columns: parts.len().max(1), plot_rows: PLOT_ROWS };
    let x = percent_scale("Share answered by the cheaper decision model", 0.0, 100.0, 20.0);
    let lines = vec![
        muted("In-sample thresholds (●): chosen and scored on all questions; held-out results in the table below."),
        muted("The decision model answers its most confident share (x) and the frontier run the rest; grey line: the frontier run alone."),
    ];
    Some(Figure {
        name: "cascade",
        title: CASCADE_TITLE.into(),
        width: WIDE_WIDTH,
        height: 4 + grid.height(WIDE_WIDTH),
        draw: Box::new(move |area, buf| {
            let body = heading(buf, area, CASCADE_TITLE, lines.clone());
            grid.render(buf, body, &x);
        }),
    })
}

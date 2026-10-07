//! The page's sharing card: a 1200 × 630 SVG with the page title above reading and grammar
//! accuracy for a few contrasting configurations. `charts/og-image.sh` rasterizes it to the PNG
//! that `og:image` points at.

use std::fmt::Write;

use crate::svg::escape;
use crate::{Results, Run, accuracy, thousands, with_setting};

const WIDTH: f64 = 1200.0;
const HEIGHT: f64 = 630.0;
const MARGIN: f64 = 60.0;
const PAGE_TITLE: &str = "What Does a Correct Answer Tell Us About Understanding?";
const SITE: &str = "zekiworks.github.io/analysis/turkce-benchmark";
const FONT: &str = r#""Helvetica Neue",Arial,"Liberation Sans",sans-serif"#;
const TEXT: &str = "#111827";
const MUTED: &str = "#6b7280";
const GRIDLINE: &str = "#e5e7eb";
const READING: &str = "#2563eb";
const GRAMMAR: &str = "#ea580c";

/// The configurations on the card, in order: (model, reasoning setting).
const SELECTION: [(&str, Option<&str>); 8] = [
    ("gpt-6-astra", Some("low")),
    ("claude-sonnet-5-5", Some("low")),
    ("claude-sonnet-5-5", Some("high")),
    ("deepseek-v4.1-flash", Some("off")),
    ("deepseek-v4.1-flash", Some("on")),
    ("gemma-4-31B-it", Some("off")),
    ("fastino/GLiDE", None),
    ("pplx-decider-v1-27b", None),
];

/// The bars: the right edge of the labels, where 0% and 100% fall, and the rows.
const LABEL_RIGHT: f64 = 410.0;
const BAR_LEFT: f64 = 430.0;
const BAR_RIGHT: f64 = 1080.0;
const ROWS_TOP: f64 = 168.0;
const ROW_HEIGHT: f64 = 48.0;
const BAR_HEIGHT: f64 = 17.0;
const BAR_GAP: f64 = 3.0;

fn find<'a>(results: &'a Results, model: &str, reasoning: Option<&str>) -> Option<&'a Run> {
    results.runs.iter().find(|run| run.model == model && run.reasoning.as_deref() == reasoning && run.variant.is_none())
}

fn x(percent: f64) -> f64 {
    BAR_LEFT + (BAR_RIGHT - BAR_LEFT) * percent / 100.0
}

/// The card as SVG, or the configuration the data lacks.
pub fn og_image(results: &Results) -> Result<String, String> {
    let mut rows = Vec::new();
    for (model, reasoning) in SELECTION {
        let missing = || format!("no run of {model} with reasoning {reasoning:?} and reading and grammar scores");
        let run = find(results, model, reasoning).ok_or_else(missing)?;
        let (reading, grammar) = (run.groups.get("reading").ok_or_else(missing)?, run.groups.get("grammar").ok_or_else(missing)?);
        rows.push((with_setting(&run.name, run), accuracy(reading), accuracy(grammar)));
    }
    let (reading_questions, grammar_questions) = results.part_questions();
    let bottom = ROWS_TOP + ROW_HEIGHT * rows.len() as f64 - (ROW_HEIGHT - 2.0 * BAR_HEIGHT - BAR_GAP);

    let mut svg = format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" role="img" font-family='{FONT}'><title>{title}</title><rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>"##,
        title = escape(PAGE_TITLE),
    );
    let _ = write!(svg, r#"<text x="{MARGIN}" y="84" font-size="34" font-weight="700" fill="{TEXT}">{}</text>"#, escape(PAGE_TITLE));
    // The legend.
    let mut key = MARGIN;
    for (color, text) in [
        (READING, format!("Reading comprehension ({} questions)", thousands(reading_questions))),
        (GRAMMAR, format!("Grammatical analysis ({} questions)", thousands(grammar_questions))),
    ] {
        let _ = write!(svg, r#"<rect x="{key}" y="114" width="18" height="18" rx="2" fill="{color}"/>"#);
        let _ = write!(svg, r#"<text x="{}" y="130" font-size="20" fill="{TEXT}">{}</text>"#, key + 28.0, escape(&text));
        key += 460.0;
    }
    let _ = write!(svg, r#"<text x="{BAR_RIGHT}" y="130" font-size="18" fill="{MUTED}" text-anchor="end">Accuracy</text>"#);
    // Gridlines and their labels under the bars.
    for tick in [0.0, 25.0, 50.0, 75.0, 100.0] {
        let left = x(tick);
        let _ = write!(
            svg,
            r#"<line x1="{left}" y1="{}" x2="{left}" y2="{}" stroke="{GRIDLINE}" stroke-width="1.5"/><text x="{left}" y="{}" font-size="16" fill="{MUTED}" text-anchor="middle">{tick}%</text>"#,
            ROWS_TOP - 10.0,
            bottom + 8.0,
            bottom + 30.0
        );
    }
    for (index, (label, reading, grammar)) in rows.iter().enumerate() {
        let top = ROWS_TOP + ROW_HEIGHT * index as f64;
        let _ = write!(
            svg,
            r#"<text x="{LABEL_RIGHT}" y="{}" font-size="21" fill="{TEXT}" text-anchor="end">{}</text>"#,
            top + BAR_HEIGHT + 8.0,
            escape(label)
        );
        for (offset, value, color) in [(0.0, reading, READING), (BAR_HEIGHT + BAR_GAP, grammar, GRAMMAR)] {
            let y = top + offset;
            let _ = write!(
                svg,
                r#"<rect x="{BAR_LEFT}" y="{y}" width="{:.1}" height="{BAR_HEIGHT}" fill="{color}"/><text x="{:.1}" y="{}" font-size="15" fill="{TEXT}">{value:.1}%</text>"#,
                x(*value) - BAR_LEFT,
                x(*value) + 6.0,
                y + 14.0
            );
        }
    }
    let _ = write!(
        svg,
        r#"<text x="{MARGIN}" y="{}" font-size="17" fill="{MUTED}">Selected configurations from the {}-run benchmark · reasoning setting in parentheses · {SITE}</text>"#,
        HEIGHT - 26.0,
        results.runs.len()
    );
    svg.push_str("</svg>\n");
    Ok(svg)
}

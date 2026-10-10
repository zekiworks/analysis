//! Writes a ratatui buffer as SVG on a fixed grid of cells.
//!
//! Every cell is `CELL_WIDTH` × `CELL_HEIGHT` pixels. Braille, block, box-drawing and dot characters
//! become shapes, so a graph looks the same in any font; other characters become text placed one
//! character per cell.
//!
//! The buffer's colours are the light theme's; [`Theme::Dark`] swaps each for its counterpart in
//! [`DARK`] and paints the dark card behind the graph.

use std::collections::BTreeMap;
use std::fmt::Write as _;

use ratatui::buffer::Buffer;
use ratatui::style::{Color, Modifier};

pub const CELL_WIDTH: f64 = 8.0;
pub const CELL_HEIGHT: f64 = 16.0;
/// Distance from a cell's top to the text baseline, for the 13 px font.
const BASELINE: f64 = 12.0;
const LINE_WIDTH: f64 = 1.2;
/// Braille dots sit 4 px apart; this radius makes neighbouring dots touch, so lines read as solid.
const DOT_RADIUS: f64 = 1.9;
/// The colour of cells that set none.
const TEXT_COLOR: &str = "#1f2937";
const FONT: &str = r#"13px ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono",monospace"#;
/// The dark theme's card (the page's `--card-bg`), painted behind the whole graph.
const DARK_BACKGROUND: &str = "#1f1e1c";
/// Each light colour the figures use and its dark-theme counterpart. Text and series colours keep at
/// least 4.5:1 contrast against [`DARK_BACKGROUND`], guide lines at least 3:1; gridlines stay subtle.
/// A colour missing here stops the dark SVG ([`Theme::Dark`] panics), so none keeps its light shade.
/// Text, guides, gridlines, reading and grammar follow the page's dark tokens.
const DARK: [(&str, &str); 40] = [
    // Text: default, muted (also `Color::Gray`).
    (TEXT_COLOR, "#ebe9e4"),
    ("#6b7280", "#a8a6a0"),
    // Guide lines: axes, diagonals, zero and chance lines, non-significant intervals.
    ("#9ca3af", "#6b6963"),
    // Gridlines.
    ("#e5e7eb", "#34332f"),
    // Reading, significant intervals and a run colour (also `Color::Blue`); grammar and a run colour.
    ("#2563eb", "#86b9f3"),
    ("#ea580c", "#f0a35e"),
    // Run colours (`fn color` in lib.rs), lighter shades of the same hues. Two runs of one hue in a
    // panel keep their distance: the darker light shade becomes a 400 or 500, the lighter one a 100 or 200.
    ("#0891b2", "#22d3ee"),
    ("#0ea5e9", "#7dd3fc"),
    ("#60a5fa", "#dbeafe"),
    ("#3f6212", "#a3e635"),
    ("#65a30d", "#d9f99d"),
    ("#e11d48", "#fb7185"),
    ("#fda4af", "#fecdd3"),
    ("#7c3aed", "#a78bfa"),
    ("#db2777", "#f472b6"),
    ("#f472b6", "#fbcfe8"),
    ("#0e7490", "#06b6d4"),
    ("#06b6d4", "#a5f3fc"),
    ("#16a34a", "#4ade80"),
    ("#9a3412", "#fed7aa"),
    ("#dc2626", "#f87171"),
    ("#ca8a04", "#facc15"),
    ("#0d9488", "#2dd4bf"),
    ("#9333ea", "#c084fc"),
    ("#c084fc", "#d8b4fe"),
    ("#1e40af", "#60a5fa"),
    ("#27272a", "#d6d3cc"),
    ("#be185d", "#f472b6"),
    ("#1d4ed8", "#60a5fa"),
    ("#4d7c0f", "#bef264"),
    ("#f97316", "#fdba74"),
    ("#78716c", "#a8a29e"),
    ("#4f46e5", "#818cf8"),
    ("#92400e", "#fbbf24"),
    ("#a16207", "#fde047"),
    ("#f59e0b", "#f59e0b"),
    ("#475569", "#d6d3cc"),
    // Named colours of `hex` not covered above.
    ("#000000", "#ebe9e4"),
    ("#ffffff", "#ffffff"),
    ("#c026d3", "#e879f9"),
];

/// The dark counterpart of a light colour in [`DARK`].
fn dark(light: &str) -> Option<&'static str> {
    DARK.iter().find(|(from, _)| *from == light).map(|(_, to)| *to)
}

/// The page theme an SVG is drawn for.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Theme {
    Light,
    Dark,
}

impl Theme {
    pub const ALL: [Theme; 2] = [Theme::Light, Theme::Dark];

    /// What follows the figure's name in its file name: `<name><suffix>.svg`.
    pub fn suffix(self) -> &'static str {
        match self {
            Theme::Light => "",
            Theme::Dark => "-dark",
        }
    }

    /// The theme's shade of a light colour.
    ///
    /// # Panics
    /// In the dark theme, for a colour without a counterpart in [`DARK`].
    fn paint(self, mut light: String) -> String {
        if self == Theme::Dark {
            let shade = dark(&light).unwrap_or_else(|| panic!("{light} has no dark counterpart: add it to DARK in src/svg.rs"));
            light.clear();
            light.push_str(shade);
        }
        light
    }

    /// The SVG fill of a cell colour, or None for the default.
    fn color(self, color: Color) -> Option<String> {
        hex(color).map(|light| self.paint(light))
    }
}

/// Braille dots for bits 0–7 of a pattern (U+2800 + bits), as (column, row) in the 2 × 4 dot grid.
const BRAILLE_DOTS: [(f64, f64); 8] =
    [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (1.0, 0.0), (1.0, 1.0), (1.0, 2.0), (0.0, 3.0), (1.0, 3.0)];

/// The centres of a braille character's dots within its cell, in pixels; None for other characters.
pub fn braille_dots(symbol: char) -> Option<Vec<(f64, f64)>> {
    let bits = (symbol as u32).checked_sub(0x2800).filter(|bits| *bits <= 0xff)?;
    Some(
        BRAILLE_DOTS
            .iter()
            .enumerate()
            .filter(|(bit, _)| bits & (1 << bit) != 0)
            .map(|(_, &(column, row))| ((column + 0.5) * CELL_WIDTH / 2.0, (row + 0.5) * CELL_HEIGHT / 4.0))
            .collect(),
    )
}

/// The arms of a box-drawing character: up, down, left, right.
fn box_arms(symbol: char) -> Option<[bool; 4]> {
    Some(match symbol {
        '─' => [false, false, true, true],
        '│' => [true, true, false, false],
        '┌' => [false, true, false, true],
        '┐' => [false, true, true, false],
        '└' => [true, false, false, true],
        '┘' => [true, false, true, false],
        '├' => [true, true, false, true],
        '┤' => [true, true, true, false],
        '┬' => [false, true, true, true],
        '┴' => [true, false, true, true],
        '┼' => [true, true, true, true],
        _ => return None,
    })
}

/// The part of the cell a block character fills: left, top, right, bottom as fractions of the cell.
fn block_part(symbol: char) -> Option<(f64, f64, f64, f64)> {
    Some(match symbol {
        '█' => (0.0, 0.0, 1.0, 1.0),
        '▀' => (0.0, 0.0, 1.0, 0.5),
        '▐' => (0.5, 0.0, 1.0, 1.0),
        // A heavy horizontal line, used for legend keys: a bar 3 px thick across the cell's middle.
        '━' => (0.0, 0.5 - 1.5 / CELL_HEIGHT, 1.0, 0.5 + 1.5 / CELL_HEIGHT),
        // Lower eighths: ▁ (U+2581) is one eighth, ▇ (U+2587) seven.
        '\u{2581}'..='\u{2587}' => (0.0, 1.0 - f64::from(symbol as u32 - 0x2580) / 8.0, 1.0, 1.0),
        // Left eighths: ▉ (U+2589) is seven eighths, ▏ (U+258F) one.
        '\u{2589}'..='\u{258F}' => (0.0, 0.0, f64::from(0x2590 - symbol as u32) / 8.0, 1.0),
        _ => return None,
    })
}

fn dot_radius(symbol: char) -> Option<f64> {
    match symbol {
        '•' => Some(2.4),
        '●' => Some(3.2),
        _ => None,
    }
}

/// Filled shapes grouped by colour, written as one path per colour.
#[derive(Default)]
struct Paths(BTreeMap<String, String>);

impl Paths {
    fn rect(&mut self, color: &str, left: f64, top: f64, width: f64, height: f64) {
        let path = self.0.entry(color.to_string()).or_default();
        let _ = write!(path, "M{}{}h{}v{}h{}z", number(left), signed(top), number(width), number(height), signed(-width));
    }

    fn dot(&mut self, color: &str, x: f64, y: f64, radius: f64) {
        let path = self.0.entry(color.to_string()).or_default();
        let (r, d) = (number(radius), number(2.0 * radius));
        let _ = write!(path, "M{}{}a{r} {r} 0 1 0 {d} 0a{r} {r} 0 1 0 -{d} 0", number(x - radius), signed(y));
    }

    fn write(&self, svg: &mut String) {
        for (color, path) in &self.0 {
            let _ = write!(svg, r#"<path fill="{color}" d="{path}"/>"#);
        }
    }
}

fn number(value: f64) -> String {
    let text = format!("{value:.2}");
    let text = text.trim_end_matches('0').trim_end_matches('.');
    if text == "-0" { "0".to_string() } else { text.to_string() }
}

/// A number that can follow another in path data: a space before it unless it starts with a minus.
fn signed(value: f64) -> String {
    let text = number(value);
    if text.starts_with('-') { text } else { format!(" {text}") }
}

fn hex(color: Color) -> Option<String> {
    let named = |code: &str| Some(code.to_string());
    match color {
        Color::Reset | Color::Indexed(_) => None,
        Color::Rgb(r, g, b) => Some(format!("#{r:02x}{g:02x}{b:02x}")),
        Color::Black => named("#000000"),
        Color::White => named("#ffffff"),
        Color::Gray | Color::DarkGray => named("#6b7280"),
        Color::Red | Color::LightRed => named("#dc2626"),
        Color::Green | Color::LightGreen => named("#16a34a"),
        Color::Yellow | Color::LightYellow => named("#ca8a04"),
        Color::Blue | Color::LightBlue => named("#2563eb"),
        Color::Magenta | Color::LightMagenta => named("#c026d3"),
        Color::Cyan | Color::LightCyan => named("#0891b2"),
    }
}

pub(crate) fn escape(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

/// Consecutive text cells in one row with the same colour and weight.
struct TextRun {
    color: String,
    bold: bool,
    glyphs: Vec<(f64, String)>,
}

fn flush(texts: &mut String, run: &mut Option<TextRun>, baseline: f64) {
    if let Some(run) = run.take() {
        let positions: Vec<String> = run.glyphs.iter().map(|(x, _)| number(*x)).collect();
        let content: String = run.glyphs.iter().map(|(_, glyph)| escape(glyph)).collect();
        let weight = if run.bold { r#" font-weight="600""# } else { "" };
        let _ = write!(
            texts,
            r#"<text x="{}" y="{}" fill="{}"{weight}>{content}</text>"#,
            positions.join(" "),
            number(baseline),
            run.color
        );
    }
}

/// The buffer as an SVG image in `theme` with `title` as its accessible name.
pub fn buffer_to_svg(buffer: &Buffer, title: &str, theme: Theme) -> String {
    let area = buffer.area;
    let text_color = theme.paint(TEXT_COLOR.to_string());
    let mut backgrounds = Paths::default();
    let mut shapes = Paths::default();
    let mut texts = String::new();
    for y in area.top()..area.bottom() {
        let top = f64::from(y - area.y) * CELL_HEIGHT;
        let mut run: Option<TextRun> = None;
        for x in area.left()..area.right() {
            let cell = &buffer[(x, y)];
            let left = f64::from(x - area.x) * CELL_WIDTH;
            if let Some(background) = theme.color(cell.bg) {
                backgrounds.rect(&background, left, top, CELL_WIDTH, CELL_HEIGHT);
            }
            let color = theme.color(cell.fg).unwrap_or_else(|| text_color.clone());
            let symbol = cell.symbol();
            let mut chars = symbol.chars();
            let single = match (chars.next(), chars.next()) {
                (Some(first), None) => Some(first),
                _ => None,
            };
            let drawn = single.is_some_and(|symbol| {
                if let Some(dots) = braille_dots(symbol) {
                    for (dx, dy) in dots {
                        shapes.dot(&color, left + dx, top + dy, DOT_RADIUS);
                    }
                } else if let Some([up, down, west, east]) = box_arms(symbol) {
                    let (cx, cy, half) = (left + CELL_WIDTH / 2.0, top + CELL_HEIGHT / 2.0, LINE_WIDTH / 2.0);
                    if up {
                        shapes.rect(&color, cx - half, top, LINE_WIDTH, CELL_HEIGHT / 2.0 + half);
                    }
                    if down {
                        shapes.rect(&color, cx - half, cy - half, LINE_WIDTH, CELL_HEIGHT / 2.0 + half);
                    }
                    if west {
                        shapes.rect(&color, left, cy - half, CELL_WIDTH / 2.0 + half, LINE_WIDTH);
                    }
                    if east {
                        shapes.rect(&color, cx - half, cy - half, CELL_WIDTH / 2.0 + half, LINE_WIDTH);
                    }
                } else if let Some((x0, y0, x1, y1)) = block_part(symbol) {
                    shapes.rect(
                        &color,
                        left + x0 * CELL_WIDTH,
                        top + y0 * CELL_HEIGHT,
                        (x1 - x0) * CELL_WIDTH,
                        (y1 - y0) * CELL_HEIGHT,
                    );
                } else if let Some(radius) = dot_radius(symbol) {
                    shapes.dot(&color, left + CELL_WIDTH / 2.0, top + CELL_HEIGHT / 2.0, radius);
                } else {
                    return false;
                }
                true
            });
            if drawn || symbol.trim().is_empty() {
                flush(&mut texts, &mut run, top + BASELINE);
                continue;
            }
            let bold = cell.modifier.contains(Modifier::BOLD);
            match &mut run {
                Some(current) if current.color == color && current.bold == bold => {
                    current.glyphs.push((left, symbol.to_string()));
                }
                _ => {
                    flush(&mut texts, &mut run, top + BASELINE);
                    run = Some(TextRun { color, bold, glyphs: vec![(left, symbol.to_string())] });
                }
            }
        }
        flush(&mut texts, &mut run, top + BASELINE);
    }
    let (width, height) = (f64::from(area.width) * CELL_WIDTH, f64::from(area.height) * CELL_HEIGHT);
    let mut svg = format!(
        r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img"><title>{title}</title><style>text{{font:{FONT};white-space:pre}}</style>"#,
        w = number(width),
        h = number(height),
        title = escape(title),
    );
    if theme == Theme::Dark {
        let _ = write!(svg, r#"<rect width="{}" height="{}" fill="{DARK_BACKGROUND}"/>"#, number(width), number(height));
    }
    backgrounds.write(&mut svg);
    shapes.write(&mut svg);
    svg.push_str(&texts);
    svg.push_str("</svg>\n");
    svg
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn braille_bits_map_to_their_dots() {
        // Dot 1 (bit 0) is the top-left dot and dot 8 (bit 7) the bottom-right one.
        assert_eq!(braille_dots('⠁'), Some(vec![(2.0, 2.0)]));
        assert_eq!(braille_dots('⢀'), Some(vec![(6.0, 14.0)]));
        // Dots 7 and 8 sit below dots 3 and 6.
        assert_eq!(braille_dots('⡄'), Some(vec![(2.0, 10.0), (2.0, 14.0)]));
        assert_eq!(braille_dots('⣿').map(|dots| dots.len()), Some(8));
        assert_eq!(braille_dots('a'), None);
    }

    #[test]
    fn eighth_blocks_fill_their_share_of_the_cell() {
        assert_eq!(block_part('▁'), Some((0.0, 0.875, 1.0, 1.0)));
        assert_eq!(block_part('▄'), Some((0.0, 0.5, 1.0, 1.0)));
        assert_eq!(block_part('▏'), Some((0.0, 0.0, 0.125, 1.0)));
        assert_eq!(block_part('▌'), Some((0.0, 0.0, 0.5, 1.0)));
    }

    /// WCAG 2 relative luminance of a "#rrggbb" colour.
    fn luminance(color: &str) -> f64 {
        let channel = |start: usize| {
            let value = f64::from(u8::from_str_radix(&color[start..start + 2], 16).expect("a #rrggbb colour")) / 255.0;
            if value <= 0.03928 { value / 12.92 } else { ((value + 0.055) / 1.055).powf(2.4) }
        };
        0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
    }

    fn contrast(first: &str, second: &str) -> f64 {
        let (first, second) = (luminance(first), luminance(second));
        (first.max(second) + 0.05) / (first.min(second) + 0.05)
    }

    #[test]
    fn dark_colours_keep_their_contrast_on_the_dark_card() {
        for (index, (light, shade)) in DARK.iter().enumerate() {
            assert!(DARK[..index].iter().all(|(other, _)| other != light), "{light} is in DARK twice");
            let minimum = match *light {
                // Gridlines: visible but subtle.
                "#e5e7eb" => 1.3,
                // Guide lines.
                "#9ca3af" => 3.0,
                _ => 4.5,
            };
            let ratio = contrast(shade, DARK_BACKGROUND);
            assert!(ratio >= minimum, "{light} → {shade}: {ratio:.2}:1 against {DARK_BACKGROUND}, below {minimum}:1");
        }
    }

    #[test]
    fn every_named_and_figure_colour_has_a_dark_counterpart() {
        let named = [
            Color::Black,
            Color::White,
            Color::Gray,
            Color::DarkGray,
            Color::Red,
            Color::LightRed,
            Color::Green,
            Color::LightGreen,
            Color::Yellow,
            Color::LightYellow,
            Color::Blue,
            Color::LightBlue,
            Color::Magenta,
            Color::LightMagenta,
            Color::Cyan,
            Color::LightCyan,
        ];
        let mut lights: Vec<String> = named.into_iter().map(|color| hex(color).expect("named colours have a hex")).collect();
        // Every colour lib.rs writes, as `rgb(0xrrggbb)` (the run colours) or `Color::Rgb(0xrr, 0xgg, 0xbb)`.
        let source = include_str!("lib.rs");
        for (start, pattern) in source.match_indices("rgb(0x") {
            let digits = &source[start + pattern.len()..start + pattern.len() + 6];
            lights.push(format!("#{}", digits.to_ascii_lowercase()));
        }
        for (start, pattern) in source.match_indices("Color::Rgb(0x") {
            let rest = &source[start + pattern.len() - 2..];
            let channels = &rest[..rest.find(')').expect("Color::Rgb closes")];
            let digits: String = channels.split(',').map(|channel| channel.trim().trim_start_matches("0x")).collect();
            lights.push(format!("#{}", digits.to_ascii_lowercase()));
        }
        assert!(lights.len() > 40, "the scan of lib.rs found its colours");
        for light in lights {
            assert!(dark(&light).is_some(), "{light} has no dark counterpart in DARK");
        }
    }

    #[test]
    #[should_panic(expected = "no dark counterpart")]
    fn a_colour_without_a_dark_counterpart_stops_the_dark_svg() {
        assert_eq!(Theme::Light.color(Color::Rgb(0x12, 0x34, 0x56)).as_deref(), Some("#123456"));
        Theme::Dark.color(Color::Rgb(0x12, 0x34, 0x56));
    }
}

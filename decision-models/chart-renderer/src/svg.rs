//! Writes a ratatui buffer as SVG on a fixed grid of cells.
//!
//! Every cell is `CELL_WIDTH` × `CELL_HEIGHT` pixels. Braille, block, box-drawing and dot characters
//! become shapes, so a graph looks the same in any font; other characters become text placed one
//! character per cell.

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

/// The buffer as an SVG image with `title` as its accessible name.
pub fn buffer_to_svg(buffer: &Buffer, title: &str) -> String {
    let area = buffer.area;
    let mut backgrounds = Paths::default();
    let mut shapes = Paths::default();
    let mut texts = String::new();
    for y in area.top()..area.bottom() {
        let top = f64::from(y - area.y) * CELL_HEIGHT;
        let mut run: Option<TextRun> = None;
        for x in area.left()..area.right() {
            let cell = &buffer[(x, y)];
            let left = f64::from(x - area.x) * CELL_WIDTH;
            if let Some(background) = hex(cell.bg) {
                backgrounds.rect(&background, left, top, CELL_WIDTH, CELL_HEIGHT);
            }
            let color = hex(cell.fg).unwrap_or_else(|| TEXT_COLOR.to_string());
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
}

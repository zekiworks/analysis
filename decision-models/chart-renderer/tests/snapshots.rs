//! Each figure, drawn from the page's results.json, against its text snapshot. A failure shows how a
//! graph changed; accept the change with `cargo insta review` or `INSTA_UPDATE=always cargo test`.

use std::path::Path;

fn results() -> charts::Results {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../results.json");
    charts::load(&path).expect("results.json loads")
}

#[test]
fn figures_match_their_snapshots() {
    let results = results();
    let figures = charts::figures(&results);
    assert_eq!(figures.len(), 7, "every figure has its data");
    for figure in figures {
        insta::assert_snapshot!(figure.name, charts::buffer_text(&charts::render(&figure)));
    }
}

/// Every colour a figure uses has a dark counterpart (`buffer_to_svg` panics otherwise), and each dark
/// SVG paints its own card.
#[test]
fn figures_draw_in_the_dark_theme() {
    let results = results();
    for figure in charts::figures(&results) {
        let svg = charts::svg::buffer_to_svg(&charts::render(&figure), &figure.title, charts::svg::Theme::Dark);
        assert!(svg.contains(r##"</style><rect width=""##) && svg.contains(r##"fill="#1f1e1c"/>"##), "{} paints the dark card first", figure.name);
        assert!(svg.contains(r##"fill="#ebe9e4""##), "{} draws default text in the dark text colour", figure.name);
    }
}

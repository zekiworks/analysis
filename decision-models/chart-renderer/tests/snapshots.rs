//! Each figure, drawn from the page's results.json, against its text snapshot. A failure shows how a
//! graph changed; accept the change with `cargo insta review` or `INSTA_UPDATE=always cargo test`.

use std::path::Path;

fn results() -> charts::Results {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    charts::load(&root.join("results.json"), &root.join("page_config.json")).expect("results.json and page_config.json load")
}

#[test]
fn figures_match_their_snapshots() {
    let results = results();
    let figures = charts::figures(&results);
    assert_eq!(figures.len(), 14, "every figure has its data");
    for figure in figures {
        insta::assert_snapshot!(figure.name, charts::buffer_text(&charts::render(&figure)));
    }
}

/// Every colour a figure uses has a dark counterpart (`buffer_to_svg` panics otherwise), each dark
/// SVG paints its own card, and every SVG is an image named by its title with the results version.
#[test]
fn figures_draw_in_the_dark_theme() {
    let results = results();
    for figure in charts::figures(&results) {
        let buffer = charts::render(&figure);
        let svg = charts::svg::buffer_to_svg(&buffer, &figure.title, &results.results_version, charts::svg::Theme::Dark);
        assert!(svg.contains(r##"</style><rect width=""##) && svg.contains(r##"fill="#1f1e1c"/>"##), "{} paints the dark card first", figure.name);
        assert!(svg.contains(r##"fill="#ebe9e4""##), "{} draws default text in the dark text colour", figure.name);
        let light = charts::svg::buffer_to_svg(&buffer, &figure.title, &results.results_version, charts::svg::Theme::Light);
        assert!(light.contains(&format!(r#"role="img"><title>{}</title>"#, figure.title)), "{} names its image", figure.name);
        assert!(light.contains(&format!("<metadata>results {}</metadata>", results.results_version)), "{} carries the results version", figure.name);
    }
}

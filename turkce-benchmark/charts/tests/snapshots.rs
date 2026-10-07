//! Each figure, drawn from the page's results.json, against its text snapshot. A failure shows how a
//! graph changed; accept the change with `cargo insta review` or `INSTA_UPDATE=always cargo test`.

use std::path::Path;

fn results() -> charts::Results {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../docs/results.json");
    charts::load(&path).expect("docs/results.json loads")
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

#[test]
fn og_image_matches_its_snapshot() {
    let svg = charts::og::og_image(&results()).expect("every selected configuration is in results.json");
    assert!(svg.contains(r#"width="1200" height="630""#), "the card is 1200 × 630");
    insta::assert_snapshot!("og-image", svg);
}

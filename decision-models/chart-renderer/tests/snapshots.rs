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

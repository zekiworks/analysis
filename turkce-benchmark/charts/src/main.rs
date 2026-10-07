//! Writes the results page's graphs as SVG: `charts <results.json> <output directory>`, or the
//! sharing card: `charts og-image <results.json> <output.svg>`.

use std::path::Path;
use std::process::ExitCode;

const USAGE: &str = "usage: charts <results.json> <output directory>\n       charts og-image <results.json> <output.svg>";

fn load(results: &str) -> Option<charts::Results> {
    match charts::load(Path::new(results)) {
        Ok(results) => Some(results),
        Err(error) => {
            eprintln!("error: {results}: {error}");
            None
        }
    }
}

fn write(path: &Path, content: &str) -> bool {
    match std::fs::write(path, content) {
        Ok(()) => {
            println!("Wrote {}", path.display());
            true
        }
        Err(error) => {
            eprintln!("error: {}: {error}", path.display());
            false
        }
    }
}

fn figures(results: &str, output: &str) -> ExitCode {
    let Some(results) = load(results) else { return ExitCode::FAILURE };
    let output = Path::new(output);
    if let Err(error) = std::fs::create_dir_all(output) {
        eprintln!("error: {}: {error}", output.display());
        return ExitCode::FAILURE;
    }
    for figure in charts::figures(&results) {
        let svg = charts::svg::buffer_to_svg(&charts::render(&figure), &figure.title);
        if !write(&output.join(format!("{}.svg", figure.name)), &svg) {
            return ExitCode::FAILURE;
        }
    }
    ExitCode::SUCCESS
}

fn og_image(results: &str, output: &str) -> ExitCode {
    let Some(results) = load(results) else { return ExitCode::FAILURE };
    match charts::og::og_image(&results) {
        Ok(svg) if write(Path::new(output), &svg) => ExitCode::SUCCESS,
        Ok(_) => ExitCode::FAILURE,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    match args.as_slice() {
        [_, command, results, output] if command == "og-image" => og_image(results, output),
        [_, results, output] => figures(results, output),
        _ => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

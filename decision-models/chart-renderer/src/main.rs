//! Writes the results page's graphs as SVG: `charts <results.json> <output directory>`. Each figure
//! gets `<name>.svg` for the light theme and `<name>-dark.svg` for the dark one.

use std::path::Path;
use std::process::ExitCode;

const USAGE: &str = "usage: charts <results.json> <output directory>";

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
    let results = match charts::load(Path::new(results)) {
        Ok(results) => results,
        Err(error) => {
            eprintln!("error: {results}: {error}");
            return ExitCode::FAILURE;
        }
    };
    let output = Path::new(output);
    if let Err(error) = std::fs::create_dir_all(output) {
        eprintln!("error: {}: {error}", output.display());
        return ExitCode::FAILURE;
    }
    for figure in charts::figures(&results) {
        let buffer = charts::render(&figure);
        for theme in charts::svg::Theme::ALL {
            let svg = charts::svg::buffer_to_svg(&buffer, &figure.title, theme);
            if !write(&output.join(format!("{}{}.svg", figure.name, theme.suffix())), &svg) {
                return ExitCode::FAILURE;
            }
        }
    }
    ExitCode::SUCCESS
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    match args.as_slice() {
        [_, results, output] => figures(results, output),
        _ => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

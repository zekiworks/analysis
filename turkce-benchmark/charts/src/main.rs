//! Writes the results page's graphs as SVG: `charts <results.json> <output directory>`.

use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    let [_, results, output] = args.as_slice() else {
        eprintln!("usage: charts <results.json> <output directory>");
        return ExitCode::from(2);
    };
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
        let path = output.join(format!("{}.svg", figure.name));
        let svg = charts::svg::buffer_to_svg(&charts::render(&figure), &figure.title);
        if let Err(error) = std::fs::write(&path, svg) {
            eprintln!("error: {}: {error}", path.display());
            return ExitCode::FAILURE;
        }
        println!("Wrote {}", path.display());
    }
    ExitCode::SUCCESS
}

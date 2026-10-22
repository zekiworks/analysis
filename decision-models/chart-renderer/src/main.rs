//! Writes the results page's graphs as SVG: `charts <results.json> <page_config.json> <output directory>`. Each figure
//! gets `<name>.svg` for the light theme and `<name>-dark.svg` for the dark one. `charts --types <results.json>
//! <page_config.json>` prints each run's type in the figures as JSON by run id, "decision" or "chat"; `build_site.py`
//! stops when a table gives a run another type.

use std::collections::BTreeMap;
use std::path::Path;
use std::process::ExitCode;

const USAGE: &str =
    "usage: charts <results.json> <page_config.json> <output directory>\n       charts --types <results.json> <page_config.json>";

fn load(results: &str, config: &str) -> Option<charts::Results> {
    match charts::load(Path::new(results), Path::new(config)) {
        Ok(results) => Some(results),
        Err(error) => {
            eprintln!("error: {error}");
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

fn figures(results: &charts::Results, output: &str) -> ExitCode {
    let output = Path::new(output);
    if let Err(error) = std::fs::create_dir_all(output) {
        eprintln!("error: {}: {error}", output.display());
        return ExitCode::FAILURE;
    }
    for figure in charts::figures(results) {
        let buffer = charts::render(&figure);
        for theme in charts::svg::Theme::ALL {
            let svg = charts::svg::buffer_to_svg(&buffer, &figure.title, &results.results_version, theme);
            if !write(&output.join(format!("{}{}.svg", figure.name, theme.suffix())), &svg) {
                return ExitCode::FAILURE;
            }
        }
    }
    ExitCode::SUCCESS
}

fn types(results: &charts::Results) -> ExitCode {
    let types: BTreeMap<u32, &str> =
        results.runs.iter().map(|run| (run.run, if results.is_decision(run) { "decision" } else { "chat" })).collect();
    match serde_json::to_string(&types) {
        Ok(json) => {
            println!("{json}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    match args.as_slice() {
        [_, flag, results, config] if flag == "--types" => load(results, config).map_or(ExitCode::FAILURE, |results| types(&results)),
        [_, results, config, output] => load(results, config).map_or(ExitCode::FAILURE, |results| figures(&results, output)),
        _ => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

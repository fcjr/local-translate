// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{convert::Infallible, env::var, error::Error, path::PathBuf};

use pyo3::wrap_pymodule;
use pytauri::standalone::{
    dunce::simplified, PythonInterpreterBuilder, PythonInterpreterEnv, PythonScript,
};
use tauri::utils::platform::resource_dir;

use local_translate_lib::{ext_mod, tauri_generate_context};

/// Find the site-packages directory inside a venv (e.g. `.venv/lib/python3.12/site-packages`).
fn find_site_packages(venv_dir: &std::path::Path) -> Option<PathBuf> {
    let lib_dir = venv_dir.join("lib");
    if let Ok(entries) = std::fs::read_dir(&lib_dir) {
        for entry in entries.flatten() {
            let name = entry.file_name();
            if name.to_string_lossy().starts_with("python") {
                let sp = entry.path().join("site-packages");
                if sp.exists() {
                    return Some(sp);
                }
            }
        }
    }
    None
}

fn main() -> Result<Infallible, Box<dyn Error>> {
    let py_env = if cfg!(dev) {
        let venv_dir = var("VIRTUAL_ENV").map(PathBuf::from).unwrap_or_else(|_| {
            let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("src-tauri should have a parent directory")
                .to_owned();
            project_root.join(".venv")
        });
        if !venv_dir.exists() {
            return Err(format!(
                "No virtual environment found at {}. Run `uv sync` first.",
                venv_dir.display()
            )
            .into());
        }

        // The embedded PyO3 interpreter doesn't process .pth files or
        // activate the venv (symlink resolution defeats pyvenv.cfg lookup).
        // Explicitly add our source dir and the venv's site-packages to PYTHONPATH.
        let src_python = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src-python");
        let mut paths = vec![src_python.to_string_lossy().into_owned()];
        if let Some(sp) = find_site_packages(&venv_dir) {
            paths.push(sp.to_string_lossy().into_owned());
        }
        std::env::set_var("PYTHONPATH", paths.join(":"));

        PythonInterpreterEnv::Venv(venv_dir.into())
    } else {
        let context = tauri_generate_context();
        let resource_dir = resource_dir(context.package_info(), &tauri::Env::default())
            .map_err(|err| format!("failed to get resource dir: {err}"))?;
        let resource_dir = simplified(&resource_dir).to_owned();
        PythonInterpreterEnv::Standalone(resource_dir.into())
    };

    let py_script = PythonScript::Module("local_translate".into());
    let builder =
        PythonInterpreterBuilder::new(py_env, py_script, |py| wrap_pymodule!(ext_mod)(py));
    let interpreter = builder.build()?;

    let exit_code = interpreter.run();
    std::process::exit(exit_code);
}

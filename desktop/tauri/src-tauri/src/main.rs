#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{fs, path::PathBuf};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::ShellExt;

fn preferences(app: &AppHandle) -> Result<PathBuf, String> {
    let directory = app
        .path()
        .app_config_dir()
        .map_err(|_| "preferences unavailable")?;
    fs::create_dir_all(&directory).map_err(|_| "preferences unavailable")?;
    Ok(directory.join("data-location.json"))
}

fn saved_location(app: &AppHandle) -> Option<String> {
    let path = preferences(app).ok()?;
    let value: Value = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    value.get("data_dir")?.as_str().map(str::to_owned)
}

async fn invoke_runtime(
    app: &AppHandle,
    action: &str,
    data_dir: Option<String>,
    pack: Option<String>,
) -> Result<Value, String> {
    let shell = app.shell();
    let mut command = shell
        .sidecar("sayelf-runtime")
        .map_err(|_| "runtime unavailable")?
        .arg(action);
    if let Some(directory) = data_dir.as_ref() {
        command = command.arg("--data-dir").arg(directory);
    }
    if let Some(pack) = pack.as_ref() {
        command = command.arg("--pack").arg(pack);
    }
    let output = command.output().await.map_err(|_| "runtime unavailable")?;
    let mut response: Value =
        serde_json::from_slice(&output.stdout).map_err(|_| "runtime response invalid")?;
    if response.get("code").and_then(Value::as_i64)
        != Some(output.status.code().unwrap_or(-1) as i64)
    {
        return Err("runtime response invalid".into());
    }
    if output.status.success() && action == "initialize" {
        let destination = preferences(app)?;
        let data = response.get("data").ok_or("runtime response invalid")?;
        let canonical = data
            .get("data_dir")
            .and_then(Value::as_str)
            .ok_or("runtime response invalid")?;
        fs::write(
            &destination,
            serde_json::to_vec(&json!({"data_dir": canonical}))
                .map_err(|_| "preferences unavailable")?,
        )
        .map_err(|_| "preferences unavailable")?;
    }
    if !output.status.success() && response.get("code").and_then(Value::as_i64) == Some(0) {
        response["code"] = json!(output.status.code().unwrap_or(1));
        response["msg"] = json!("本机环境检查未通过。");
    }
    Ok(response)
}

#[tauri::command]
async fn check_environment(app: AppHandle, data_dir: Option<String>) -> Result<Value, String> {
    let location = data_dir.or_else(|| saved_location(&app));
    invoke_runtime(&app, "health", location, None).await
}

#[tauri::command]
async fn initialize_workspace(
    app: AppHandle,
    pack: String,
    data_dir: Option<String>,
) -> Result<Value, String> {
    if !["media", "engineering"].contains(&pack.as_str()) {
        return Err("invalid setup selection".into());
    }
    invoke_runtime(
        &app,
        "initialize",
        data_dir.or_else(|| saved_location(&app)),
        Some(pack),
    )
    .await
}

#[tauri::command]
async fn choose_data_directory(app: AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .set_title("选择 Sayelf 数据保存位置")
            .blocking_pick_folder()
            .map(|path| {
                path.into_path()
                    .map(|path| path.to_string_lossy().into_owned())
                    .map_err(|_| "invalid folder".to_string())
            })
            .transpose()
    })
    .await
    .map_err(|_| "folder picker unavailable")?
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            check_environment,
            initialize_workspace,
            choose_data_directory
        ])
        .run(tauri::generate_context!())
        .expect("Sayelf Agent Ops desktop failed to start");
}

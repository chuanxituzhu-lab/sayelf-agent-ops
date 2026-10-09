#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::ShellExt;

const MAX_FILE_BYTES: u64 = 15 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 30 * 1024 * 1024;
const MAX_FILES: usize = 5;
const MAX_EXTRACTED_CHARS_PER_FILE: usize = 30_000;
const MAX_TOTAL_EXTRACTED_CHARS: usize = 60_000;
static NEXT_WORKITEM: AtomicU64 = AtomicU64::new(1);

#[derive(Default)]
struct PickedFiles(Mutex<HashSet<PathBuf>>);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SelectedEvidence {
    path: String,
    name: String,
    size: u64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExtractedEvidence {
    path: String,
    extracted_text: String,
    extraction_status: String,
}

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

fn require_workspace(app: &AppHandle) -> Result<String, String> {
    saved_location(app).ok_or_else(|| "workspace not initialized".to_string())
}

async fn invoke_runtime(
    app: &AppHandle,
    action: &str,
    data_dir: Option<String>,
    pack: Option<String>,
    extra_args: Vec<String>,
) -> Result<Value, String> {
    invoke_runtime_with_key(app, action, data_dir, pack, extra_args, None).await
}

async fn invoke_runtime_with_key(
    app: &AppHandle,
    action: &str,
    data_dir: Option<String>,
    pack: Option<String>,
    extra_args: Vec<String>,
    api_key: Option<String>,
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
    for argument in extra_args {
        command = command.arg(argument);
    }
    if let Some(api_key) = api_key.as_ref() {
        command = command.env("SAYELF_MODEL_API_KEY", api_key);
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
    invoke_runtime(&app, "health", location, None, Vec::new()).await
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
        Vec::new(),
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

fn allowed_extension(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| {
            matches!(
                extension.to_ascii_lowercase().as_str(),
                "txt" | "md" | "pdf" | "png" | "jpg" | "jpeg" | "webp" | "bmp"
            )
        })
        .unwrap_or(false)
}

fn checked_source(path: &str) -> Result<PathBuf, String> {
    let source = PathBuf::from(path)
        .canonicalize()
        .map_err(|_| "selected file unavailable".to_string())?;
    if !allowed_extension(&source) || !source.is_file() {
        return Err("unsupported file type".into());
    }
    let metadata = fs::metadata(&source).map_err(|_| "selected file unavailable")?;
    if metadata.len() > MAX_FILE_BYTES {
        return Err("file is larger than 15 MiB".into());
    }
    Ok(source)
}

#[tauri::command]
async fn choose_evidence_files(
    app: AppHandle,
    picked_files: State<'_, PickedFiles>,
) -> Result<Vec<SelectedEvidence>, String> {
    let result = tauri::async_runtime::spawn_blocking(move || {
        let paths = app
            .dialog()
            .file()
            .set_title("添加本地需求材料")
            .add_filter(
                "文本、PDF 或图片",
                &["txt", "md", "pdf", "png", "jpg", "jpeg", "webp", "bmp"],
            )
            .blocking_pick_files();
        let Some(paths) = paths else {
            return Ok(Vec::new());
        };
        if paths.len() > MAX_FILES {
            return Err("一次最多选择 5 个文件".to_string());
        }
        let mut total = 0_u64;
        let mut selected = Vec::new();
        for file_path in paths {
            let original = file_path
                .into_path()
                .map_err(|_| "selected file unavailable".to_string())?;
            let path = checked_source(&original.to_string_lossy())?;
            let size = fs::metadata(&path)
                .map_err(|_| "selected file unavailable")?
                .len();
            total += size;
            if total > MAX_TOTAL_BYTES {
                return Err("附件总大小不能超过 30 MiB".into());
            }
            let name = path
                .file_name()
                .and_then(|name| name.to_str())
                .ok_or_else(|| "invalid file name".to_string())?
                .to_string();
            selected.push(SelectedEvidence {
                path: path.to_string_lossy().into_owned(),
                name,
                size,
            });
        }
        Ok(selected)
    })
    .await
    .map_err(|_| "file picker unavailable")??;
    let paths = result
        .iter()
        .map(|file| PathBuf::from(&file.path))
        .collect::<Vec<_>>();
    let mut allowed = picked_files
        .0
        .lock()
        .map_err(|_| "file selection unavailable")?;
    allowed.extend(paths);
    Ok(result)
}

#[tauri::command]
async fn read_selected_evidence(
    path: String,
    picked_files: State<'_, PickedFiles>,
) -> Result<tauri::ipc::Response, String> {
    let source = checked_source(&path)?;
    {
        let allowed = picked_files
            .0
            .lock()
            .map_err(|_| "file selection unavailable")?;
        if !allowed.contains(&source) {
            return Err("请通过文件选择窗口重新添加附件。".into());
        }
    }
    let bytes = fs::read(&source).map_err(|_| "selected file unavailable")?;
    if bytes.len() as u64 > MAX_FILE_BYTES {
        return Err("file is larger than 15 MiB".into());
    }
    Ok(tauri::ipc::Response::new(bytes))
}

fn next_workitem_id() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let sequence = NEXT_WORKITEM.fetch_add(1, Ordering::Relaxed);
    format!("WI-{millis}-{sequence}")
}

fn validate_workitem_input(request: &str, attachments: &[ExtractedEvidence]) -> Result<(), String> {
    if request.trim().is_empty()
        || request.chars().count() > 20_000
        || attachments.len() > MAX_FILES
    {
        return Err("请填写需求，并限制在 5 个以内的附件。".into());
    }
    let mut total_chars = 0;
    for attachment in attachments {
        let chars = attachment.extracted_text.chars().count();
        if chars > MAX_EXTRACTED_CHARS_PER_FILE {
            return Err("单个附件识别文字超过 30,000 字，请减少或拆分材料。".into());
        }
        total_chars += chars;
        if total_chars > MAX_TOTAL_EXTRACTED_CHARS {
            return Err("附件识别文字总量超过 60,000 字，请减少附件或缩短文字。".into());
        }
    }
    Ok(())
}

fn read_selected_file(path: &Path) -> Result<Vec<u8>, String> {
    let file = fs::File::open(path).map_err(|_| "selected file unavailable")?;
    let mut bytes = Vec::new();
    file.take(MAX_FILE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "selected file unavailable")?;
    if bytes.len() as u64 > MAX_FILE_BYTES {
        return Err("附件大小超过限制，请重新选择较小文件。".into());
    }
    Ok(bytes)
}

fn write_new_file(
    path: &Path,
    bytes: &[u8],
    created_files: &mut Vec<PathBuf>,
) -> Result<(), String> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| "cannot save work item")?;
    created_files.push(path.to_path_buf());
    file.write_all(bytes).map_err(|_| "cannot save work item")?;
    Ok(())
}

fn persist_workitem_input(
    root: &Path,
    workitem_id: &str,
    request: &str,
    channel: &str,
    attachments: &[ExtractedEvidence],
    paths: &[PathBuf],
    file_contents: &[Vec<u8>],
) -> Result<PathBuf, String> {
    if attachments.len() != paths.len() || attachments.len() != file_contents.len() {
        return Err("cannot save work item".into());
    }
    let workitem_dir = root.join("workitems").join(workitem_id);
    let evidence_dir = root.join("evidence").join(workitem_id);
    fs::create_dir(&workitem_dir).map_err(|_| "cannot create work item")?;
    let has_evidence = !attachments.is_empty();
    if has_evidence && fs::create_dir(&evidence_dir).is_err() {
        let _ = fs::remove_dir(&workitem_dir);
        return Err("cannot create evidence folder".into());
    }

    let mut created_files = Vec::new();
    let result = (|| {
        let mut request_attachments = Vec::with_capacity(attachments.len());
        for (index, ((attachment, source), bytes)) in
            attachments.iter().zip(paths).zip(file_contents).enumerate()
        {
            let original_name = source
                .file_name()
                .and_then(|name| name.to_str())
                .ok_or_else(|| "invalid file name".to_string())?;
            let name = if index == 0 {
                original_name.to_string()
            } else {
                format!("{}-{original_name}", index + 1)
            };
            let destination = evidence_dir.join(&name);
            write_new_file(&destination, bytes, &mut created_files)?;
            request_attachments.push(json!({
                "name": name,
                "relative_path": format!("evidence/{workitem_id}/{name}"),
                "extracted_text": attachment.extracted_text.as_str(),
                "extraction_status": attachment.extraction_status,
            }));
        }
        let payload = json!({
            "id": workitem_id,
            "request": request.trim(),
            "channel": channel,
            "attachments": request_attachments,
        });
        let request_path = workitem_dir.join("request.json");
        let request_bytes =
            serde_json::to_vec_pretty(&payload).map_err(|_| "cannot save request".to_string())?;
        write_new_file(&request_path, &request_bytes, &mut created_files)?;
        Ok(request_path)
    })();

    if result.is_err() {
        for path in created_files.into_iter().rev() {
            let _ = fs::remove_file(path);
        }
        if has_evidence {
            let _ = fs::remove_dir(&evidence_dir);
        }
        let _ = fs::remove_dir(&workitem_dir);
    }
    result
}

#[tauri::command]
async fn create_workitem(
    app: AppHandle,
    picked_files: State<'_, PickedFiles>,
    request: String,
    channel: String,
    attachments: Vec<ExtractedEvidence>,
) -> Result<Value, String> {
    validate_workitem_input(&request, &attachments)?;
    let data_dir = require_workspace(&app)?;
    let health = invoke_runtime(&app, "health", Some(data_dir.clone()), None, Vec::new()).await?;
    if health.get("code").and_then(Value::as_i64) != Some(0) {
        return Ok(health);
    }

    let paths = attachments
        .iter()
        .map(|attachment| checked_source(&attachment.path))
        .collect::<Result<Vec<_>, _>>()?;
    {
        let allowed = picked_files
            .0
            .lock()
            .map_err(|_| "file selection unavailable")?;
        if paths.iter().any(|path| !allowed.contains(path)) {
            return Err("请通过文件选择窗口重新添加附件。".into());
        }
    }
    let mut file_contents = Vec::with_capacity(paths.len());
    let mut total = 0_u64;
    for source in &paths {
        let bytes = read_selected_file(source)?;
        total += bytes.len() as u64;
        if total > MAX_TOTAL_BYTES {
            return Err("附件总大小不能超过 30 MiB。".into());
        }
        file_contents.push(bytes);
    }
    let root = PathBuf::from(&data_dir)
        .canonicalize()
        .map_err(|_| "workspace unavailable")?;
    let workitem_id = next_workitem_id();
    let request_path = persist_workitem_input(
        &root,
        &workitem_id,
        &request,
        &channel,
        &attachments,
        &paths,
        &file_contents,
    )?
    .to_string_lossy()
    .into_owned();
    invoke_runtime(
        &app,
        "plan",
        Some(data_dir),
        None,
        vec!["--request-file".into(), request_path],
    )
    .await
}

#[tauri::command]
async fn build_workplan(app: AppHandle, workitem_id: String) -> Result<Value, String> {
    if !workitem_id.starts_with("WI-")
        || !workitem_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_')
    {
        return Err("invalid work item".into());
    }
    let data_dir = require_workspace(&app)?;
    let request_path = PathBuf::from(&data_dir)
        .join("workitems")
        .join(&workitem_id)
        .join("request.json");
    if !request_path.is_file() || request_path.is_symlink() {
        return Err("work item unavailable".into());
    }
    invoke_runtime(
        &app,
        "plan",
        Some(data_dir),
        None,
        vec![
            "--request-file".into(),
            request_path.to_string_lossy().into_owned(),
        ],
    )
    .await
}

#[tauri::command]
async fn set_role_active(app: AppHandle, role_id: String, active: bool) -> Result<Value, String> {
    let data_dir = require_workspace(&app)?;
    invoke_runtime(
        &app,
        "set-role",
        Some(data_dir),
        None,
        vec![
            "--role-id".into(),
            role_id,
            "--active".into(),
            active.to_string(),
        ],
    )
    .await
}

fn provider_credential() -> Result<keyring::Entry, String> {
    keyring::Entry::new("sayelf.agent-ops", "model-provider-api-key")
        .map_err(|_| "无法访问系统安全凭据库。".to_string())
}

fn valid_provider_endpoint(endpoint: &str) -> bool {
    if endpoint.len() > 2048
        || endpoint.contains(['@', '?', '#', '\\', '\n', '\r', ' '])
        || endpoint.ends_with('/')
    {
        return false;
    }
    let lower = endpoint.to_ascii_lowercase();
    if lower.starts_with("https://") {
        return endpoint[8..]
            .split('/')
            .next()
            .is_some_and(|host| !host.is_empty());
    }
    ["http://localhost", "http://127.0.0.1", "http://[::1]"]
        .iter()
        .any(|prefix| lower.starts_with(&format!("{prefix}:")) || lower == *prefix)
}

#[tauri::command]
async fn configure_ai_provider(
    app: AppHandle,
    endpoint: String,
    model: String,
    api_key: String,
) -> Result<Value, String> {
    if !valid_provider_endpoint(&endpoint)
        || model.trim().is_empty()
        || model.chars().count() > 200
        || api_key.trim().is_empty()
        || api_key.len() > 4096
        || api_key.contains(['\0', '\n', '\r'])
    {
        return Err("请检查服务地址、模型名称和密钥。远程服务必须使用 HTTPS。".into());
    }
    let data_dir = require_workspace(&app)?;
    let entry = provider_credential()?;
    let previous_key = entry.get_password().ok();
    entry
        .set_password(api_key.trim())
        .map_err(|_| "无法将密钥保存到系统安全凭据库。".to_string())?;
    let configured = invoke_runtime(
        &app,
        "provider-config",
        Some(data_dir),
        None,
        vec!["--endpoint".into(), endpoint, "--model".into(), model],
    )
    .await;
    match configured {
        Ok(response) if response.get("code").and_then(Value::as_i64) == Some(0) => Ok(response),
        Ok(response) => {
            restore_provider_key(&entry, previous_key);
            Err(response
                .get("msg")
                .and_then(Value::as_str)
                .unwrap_or("AI 服务设置失败。")
                .to_string())
        }
        Err(error) => {
            restore_provider_key(&entry, previous_key);
            Err(error)
        }
    }
}

fn restore_provider_key(entry: &keyring::Entry, previous: Option<String>) {
    match previous {
        Some(value) => {
            let _ = entry.set_password(&value);
        }
        None => {
            let _ = entry.delete_credential();
        }
    }
}

#[tauri::command]
async fn ai_provider_status(app: AppHandle) -> Result<Value, String> {
    let data_dir = require_workspace(&app)?;
    let mut response =
        invoke_runtime(&app, "provider-status", Some(data_dir), None, Vec::new()).await?;
    if let Some(data) = response.get_mut("data") {
        data["credential_available"] = json!(provider_credential()
            .and_then(|entry| entry
                .get_password()
                .map_err(|_| "credential unavailable".to_string()))
            .is_ok());
    }
    Ok(response)
}

#[tauri::command]
async fn clear_ai_provider(app: AppHandle) -> Result<Value, String> {
    let data_dir = require_workspace(&app)?;
    let entry = provider_credential()?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => {}
        Err(_) => return Err("无法从系统安全凭据库清除密钥。".into()),
    }
    let response = invoke_runtime(&app, "provider-clear", Some(data_dir), None, Vec::new()).await?;
    if response.get("code").and_then(Value::as_i64) != Some(0) {
        return Err(response
            .get("msg")
            .and_then(Value::as_str)
            .unwrap_or("AI 服务设置清除失败。")
            .to_string());
    }
    Ok(response)
}

#[tauri::command]
async fn test_ai_provider(app: AppHandle) -> Result<Value, String> {
    let data_dir = require_workspace(&app)?;
    let api_key = provider_credential()?
        .get_password()
        .map_err(|_| "请先保存 AI 服务密钥。".to_string())?;
    invoke_runtime_with_key(
        &app,
        "provider-test",
        Some(data_dir),
        None,
        Vec::new(),
        Some(api_key),
    )
    .await
}

#[tauri::command]
async fn execute_media_workflow(
    app: AppHandle,
    workitem_id: String,
    consent_to_provider: bool,
    resume_run_id: Option<String>,
) -> Result<Value, String> {
    if !valid_workitem_id(&workitem_id) {
        return Err("工作单编号无效。".into());
    }
    let data_dir = require_workspace(&app)?;
    let api_key = provider_credential()?
        .get_password()
        .map_err(|_| "请先保存 AI 服务密钥。".to_string())?;
    let mut arguments = vec!["--workitem-id".into(), workitem_id];
    if consent_to_provider {
        arguments.push("--allow-external".into());
    }
    if let Some(run_id) = resume_run_id {
        arguments.push("--resume-run-id".into());
        arguments.push(run_id);
    }
    invoke_runtime_with_key(
        &app,
        "execute-media",
        Some(data_dir),
        None,
        arguments,
        Some(api_key),
    )
    .await
}

#[tauri::command]
async fn list_recent_media_workflows(app: AppHandle) -> Result<Value, String> {
    let data_dir = require_workspace(&app)?;
    invoke_runtime(&app, "recent-workflows", Some(data_dir), None, Vec::new()).await
}

#[tauri::command]
async fn load_saved_media_result(
    app: AppHandle,
    workitem_id: String,
    run_id: String,
) -> Result<Value, String> {
    if !valid_workitem_id(&workitem_id) || !valid_workflow_id(&run_id) {
        return Err("本机任务编号无效。".into());
    }
    let data_dir = require_workspace(&app)?;
    invoke_runtime(
        &app,
        "saved-media-result",
        Some(data_dir),
        None,
        vec![
            "--workitem-id".into(),
            workitem_id,
            "--run-id".into(),
            run_id,
        ],
    )
    .await
}

#[tauri::command]
async fn approve_and_export_media_package(
    app: AppHandle,
    workitem_id: String,
    version: u64,
    content: String,
) -> Result<Value, String> {
    if !valid_workitem_id(&workitem_id)
        || version == 0
        || content.trim().is_empty()
        || content.len() > 1_000_000
    {
        return Err("成果内容为空、过大或工作单编号无效。".into());
    }
    let data_dir = require_workspace(&app)?;
    let workitem_dir = PathBuf::from(&data_dir)
        .join("workitems")
        .join(&workitem_id);
    if !workitem_dir.is_dir() || workitem_dir.is_symlink() {
        return Err("本机工作单不可用。".into());
    }
    let content_path = workitem_dir.join("review-current.md");
    if content_path.is_symlink() {
        return Err("本机审核文件不可用。".into());
    }
    fs::write(&content_path, content).map_err(|_| "无法保存待审核成果。".to_string())?;
    invoke_runtime(
        &app,
        "approve-export",
        Some(data_dir),
        None,
        vec![
            "--workitem-id".into(),
            workitem_id,
            "--version".into(),
            version.to_string(),
            "--content-file".into(),
            content_path.to_string_lossy().into_owned(),
        ],
    )
    .await
}

#[tauri::command]
async fn record_media_performance(
    app: AppHandle,
    workitem_id: String,
    metrics: Value,
) -> Result<Value, String> {
    if !valid_workitem_id(&workitem_id) {
        return Err("工作单编号无效。".into());
    }
    let data_dir = require_workspace(&app)?;
    let workitem_dir = PathBuf::from(&data_dir)
        .join("workitems")
        .join(&workitem_id);
    if !workitem_dir.is_dir() || workitem_dir.is_symlink() {
        return Err("本机工作单不可用。".into());
    }
    let metrics_path = workitem_dir.join("performance-current.json");
    if metrics_path.is_symlink() {
        return Err("本机复盘文件不可用。".into());
    }
    let serialized = serde_json::to_vec(&metrics).map_err(|_| "复盘数据格式无效。".to_string())?;
    if serialized.len() > 16_384 {
        return Err("复盘数据超出允许大小。".into());
    }
    fs::write(&metrics_path, serialized).map_err(|_| "无法保存本机复盘数据。".to_string())?;
    let result = invoke_runtime(
        &app,
        "performance-review",
        Some(data_dir),
        None,
        vec![
            "--workitem-id".into(),
            workitem_id,
            "--metrics-file".into(),
            metrics_path.to_string_lossy().into_owned(),
        ],
    )
    .await;
    let _ = fs::remove_file(metrics_path);
    result
}

fn valid_workitem_id(workitem_id: &str) -> bool {
    workitem_id.starts_with("WI-")
        && workitem_id.len() <= 68
        && workitem_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_')
}

fn valid_workflow_id(run_id: &str) -> bool {
    run_id.starts_with("RUN-")
        && (5..=84).contains(&run_id.len())
        && run_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_')
}

#[tauri::command]
async fn save_workitem_result(
    app: AppHandle,
    workitem_id: String,
    content: String,
) -> Result<String, String> {
    if !valid_workitem_id(&workitem_id) || content.len() > 1_000_000 {
        return Err("result is too large or invalid".into());
    }
    let data_dir = require_workspace(&app)?;
    let health = invoke_runtime(&app, "health", Some(data_dir.clone()), None, Vec::new()).await?;
    if health.get("code").and_then(Value::as_i64) != Some(0) {
        return Err("workspace unavailable".into());
    }
    let output_dir = PathBuf::from(data_dir).join("outputs");
    if !output_dir.is_dir() || output_dir.is_symlink() {
        return Err("output folder unavailable".into());
    }
    let destination = output_dir.join(format!("{workitem_id}.md"));
    if destination.is_symlink() {
        return Err("output file unavailable".into());
    }
    fs::write(destination, content).map_err(|_| "cannot save result".to_string())?;
    Ok("已保存到本机成果目录。".into())
}

#[tauri::command]
async fn export_workitem_result(
    app: AppHandle,
    workitem_id: String,
    content: String,
) -> Result<Option<String>, String> {
    if !valid_workitem_id(&workitem_id) || content.len() > 1_000_000 {
        return Err("result is too large or invalid".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("导出 Sayelf 工作成果")
            .set_file_name(format!("{workitem_id}.md"))
            .add_filter("Markdown", &["md"])
            .blocking_save_file();
        let Some(selected) = selected else {
            return Ok(None);
        };
        let destination = selected
            .into_path()
            .map_err(|_| "invalid output path".to_string())?;
        fs::write(&destination, content).map_err(|_| "cannot export result".to_string())?;
        Ok(Some(destination.to_string_lossy().into_owned()))
    })
    .await
    .map_err(|_| "save dialog unavailable")?
}

fn main() {
    tauri::Builder::default()
        .manage(PickedFiles::default())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            check_environment,
            initialize_workspace,
            choose_data_directory,
            choose_evidence_files,
            read_selected_evidence,
            create_workitem,
            build_workplan,
            set_role_active,
            configure_ai_provider,
            ai_provider_status,
            clear_ai_provider,
            test_ai_provider,
            execute_media_workflow,
            list_recent_media_workflows,
            load_saved_media_result,
            approve_and_export_media_package,
            record_media_performance,
            save_workitem_result,
            export_workitem_result
        ])
        .run(tauri::generate_context!())
        .expect("Sayelf Agent Ops desktop failed to start");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evidence(text: String) -> ExtractedEvidence {
        ExtractedEvidence {
            path: String::new(),
            extracted_text: text,
            extraction_status: String::new(),
        }
    }

    fn temporary_root() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root =
            std::env::temp_dir().join(format!("sayelf-intake-{}-{stamp}", std::process::id()));
        fs::create_dir(&root).unwrap();
        root
    }

    #[test]
    fn extracted_text_limits_match_the_runtime_contract() {
        let exact_limit = vec![
            evidence("中".repeat(MAX_EXTRACTED_CHARS_PER_FILE)),
            evidence("字".repeat(MAX_EXTRACTED_CHARS_PER_FILE)),
        ];
        assert!(validate_workitem_input("需求", &exact_limit).is_ok());

        let over_total = vec![
            evidence("中".repeat(MAX_EXTRACTED_CHARS_PER_FILE)),
            evidence("字".repeat(MAX_EXTRACTED_CHARS_PER_FILE)),
            evidence("超".to_string()),
        ];
        assert_eq!(
            validate_workitem_input("需求", &over_total),
            Err("附件识别文字总量超过 60,000 字，请减少附件或缩短文字。".into())
        );

        let over_file = vec![evidence("字".repeat(MAX_EXTRACTED_CHARS_PER_FILE + 1))];
        assert_eq!(
            validate_workitem_input("需求", &over_file),
            Err("单个附件识别文字超过 30,000 字，请减少或拆分材料。".into())
        );
    }

    #[test]
    fn workflow_ids_are_bounded_and_path_safe() {
        assert!(valid_workflow_id("RUN-0123456789abcdef"));
        assert!(!valid_workflow_id("RUN-"));
        assert!(!valid_workflow_id("RUN-../escape"));
        assert!(!valid_workflow_id(&format!("RUN-{}", "a".repeat(81))));
    }

    #[test]
    fn failed_evidence_directory_creation_removes_only_the_new_workitem_folder() {
        let root = temporary_root();
        let workitems = root.join("workitems");
        let evidence_root = root.join("evidence");
        fs::create_dir(&workitems).unwrap();
        fs::create_dir_all(evidence_root.join("WI-COLLISION")).unwrap();
        let sentinel = evidence_root.join("WI-COLLISION").join("keep.txt");
        fs::write(&sentinel, b"existing data").unwrap();

        let result = persist_workitem_input(
            &root,
            "WI-COLLISION",
            "request",
            "channel",
            &[evidence("text".into())],
            &[PathBuf::from("source.txt")],
            &[vec![1]],
        );

        assert_eq!(result, Err("cannot create evidence folder".into()));
        assert!(!workitems.join("WI-COLLISION").exists());
        assert_eq!(fs::read(&sentinel).unwrap(), b"existing data");
        fs::remove_dir_all(root).unwrap();
    }
}

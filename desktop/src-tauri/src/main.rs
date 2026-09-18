use serde::Deserialize;
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

struct Sidecar(Mutex<Option<Child>>);

#[derive(Deserialize)]
struct Session {
    port: u16,
    token: String,
}

fn shared_state_dir() -> Result<PathBuf, String> {
    if let Some(path) = std::env::var_os("CSI_STATE_DIR") {
        return Ok(PathBuf::from(path));
    }
    let home = std::env::var_os("HOME").ok_or("无法读取用户目录")?;
    Ok(PathBuf::from(home)
        .join("Library")
        .join("Application Support")
        .join("Creator Source Importer"))
}

fn session_url(session: &Session) -> Option<String> {
    let address = SocketAddr::from(([127, 0, 0, 1], session.port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(500)).ok()?;
    stream.set_read_timeout(Some(Duration::from_millis(500))).ok()?;
    let request = format!(
        "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-Importer-Token: {}\r\nConnection: close\r\n\r\n",
        session.port, session.token
    );
    stream.write_all(request.as_bytes()).ok()?;
    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    let (_, body) = response.split_once("\r\n\r\n")?;
    let health: serde_json::Value = serde_json::from_str(body).ok()?;
    if health.get("version")?.as_str()? != "0.7.1" {
        return None;
    }
    Some(format!(
        "http://127.0.0.1:{}/#token={}",
        session.port, session.token
    ))
}

fn packaged_path(app: &tauri::AppHandle, relative: &str) -> Result<PathBuf, String> {
    let bundled = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?
        .join(relative);
    Ok(bundled)
}

fn launch_backend(app: &tauri::AppHandle) -> Result<(Option<Child>, String), String> {
    let state = shared_state_dir()?;
    fs::create_dir_all(&state).map_err(|error| error.to_string())?;
    let session_path = state.join("session.json");
    if let Ok(raw) = fs::read_to_string(&session_path) {
        if let Ok(session) = serde_json::from_str::<Session>(&raw) {
            if let Some(url) = session_url(&session) {
                return Ok((None, url));
            }
        }
    }
    let _ = fs::remove_file(&session_path);

    let sidecar = packaged_path(app, "resources/sidecar/creator-source-importer-sidecar")?;
    let runtime = packaged_path(app, "resources/runtime")?;
    if !sidecar.is_file() {
        return Err(format!("应用运行组件缺失：{}", sidecar.display()));
    }
    let log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(state.join("server.log"))
        .map_err(|error| error.to_string())?;
    let err_log = log.try_clone().map_err(|error| error.to_string())?;
    let mut command = Command::new(sidecar);
    command
        .args(["--port", "0"])
        .env("CSI_STATE_DIR", &state)
        .env("CSI_FFMPEG", runtime.join("bin/ffmpeg"))
        .env("CSI_FFPROBE", runtime.join("bin/ffprobe"))
        .env("CSI_JS_RUNTIME", runtime.join("bin/deno"))
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(err_log));
    let child = command.spawn().map_err(|error| error.to_string())?;

    let deadline = Instant::now() + Duration::from_secs(45);
    while Instant::now() < deadline {
        if let Ok(raw) = fs::read_to_string(&session_path) {
            if let Ok(session) = serde_json::from_str::<Session>(&raw) {
                let url = format!(
                    "http://127.0.0.1:{}/#token={}",
                    session.port, session.token
                );
                return Ok((Some(child), url));
            }
        }
        thread::sleep(Duration::from_millis(150));
    }
    Err("本地服务未能在 45 秒内启动。".to_string())
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let (child, url) = launch_backend(app.handle())?;
            app.manage(Sidecar(Mutex::new(child)));
            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(url.parse().map_err(|error| format!("{error}"))?),
            )
            .title("Creator Source Importer")
            .inner_size(1040.0, 800.0)
            .min_inner_size(760.0, 620.0)
            .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build application");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
            if let Some(sidecar) = app_handle.try_state::<Sidecar>() {
                if let Ok(mut child) = sidecar.0.lock() {
                    if let Some(process) = child.as_mut() {
                        let _ = process.kill();
                        let _ = process.wait();
                    }
                    *child = None;
                }
            }
        }
    });
}

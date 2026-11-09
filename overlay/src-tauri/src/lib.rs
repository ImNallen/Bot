use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, State, WebviewWindow};

/// The bot's circle in window points. Clicks inside it reach the page; everywhere else passes through.
#[derive(Clone, Copy, Default)]
struct HitRegion {
    x: f64,
    y: f64,
    r: f64,
}

#[derive(Default)]
struct Hit(Mutex<HitRegion>);

#[derive(Clone, Serialize)]
struct Pointer {
    x: f64,
    y: f64,
}

#[tauri::command]
fn set_hit_region(hit: State<Hit>, x: f64, y: f64, r: f64) {
    *hit.0.lock().unwrap() = HitRegion { x, y, r };
}

/// Whether the cursor moved enough to be worth sending. The first position is always sent.
fn moved_enough(last_sent: Option<(f64, f64)>, x: f64, y: f64) -> bool {
    last_sent.is_none_or(|(lx, ly)| (x - lx).abs() > 0.5 || (y - ly).abs() > 0.5)
}

fn place_bottom_right(win: &WebviewWindow) -> tauri::Result<()> {
    let Some(monitor) = win.primary_monitor()? else { return Ok(()) };
    let area = monitor.work_area();
    let size = win.outer_size()?;
    let x = area.position.x + area.size.width as i32 - size.width as i32;
    let y = area.position.y + area.size.height as i32 - size.height as i32;
    win.set_position(PhysicalPosition::new(x, y))
}

/// Tauri can only make a whole window click-through, so this polls the cursor and turns
/// click-through off while it is over the bot. The same position drives the eyes.
fn track_pointer(app: AppHandle, win: WebviewWindow) {
    thread::spawn(move || {
        let mut over_bot = None;
        let mut last_sent: Option<(f64, f64)> = None;
        loop {
            thread::sleep(Duration::from_millis(16));
            let (Ok(cursor), Ok(origin), Ok(scale)) = (app.cursor_position(), win.outer_position(), win.scale_factor()) else {
                continue;
            };
            let x = (cursor.x - origin.x as f64) / scale;
            let y = (cursor.y - origin.y as f64) / scale;
            let hit = *app.state::<Hit>().0.lock().unwrap();
            let inside = (x - hit.x).hypot(y - hit.y) <= hit.r;
            if over_bot != Some(inside) {
                let _ = win.set_ignore_cursor_events(!inside);
                over_bot = Some(inside);
            }
            if moved_enough(last_sent, x, y) {
                last_sent = Some((x, y));
                let _ = win.emit("pointer", Pointer { x, y });
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Hit::default())
        .invoke_handler(tauri::generate_handler![set_hit_region])
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            let win = app.get_webview_window("main").expect("main window is declared in tauri.conf.json");
            place_bottom_right(&win)?;
            track_pointer(app.handle().clone(), win);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("companion overlay failed to start");
}

#[cfg(test)]
mod tests {
    use super::moved_enough;

    #[test]
    fn first_position_is_always_sent() {
        assert!(moved_enough(None, 10.0, 20.0));
    }

    #[test]
    fn only_real_movement_is_sent_after_that() {
        assert!(!moved_enough(Some((10.0, 20.0)), 10.3, 20.2));
        assert!(moved_enough(Some((10.0, 20.0)), 11.0, 20.0));
        assert!(moved_enough(Some((10.0, 20.0)), 10.0, 19.0));
    }
}

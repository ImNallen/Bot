mod settings;
mod watch;

use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::image::Image;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, Rect, State, WebviewWindow, WindowEvent};

use settings::{get_settings, update_settings, SettingsStore};
use watch::HideReason;

/// Areas of the overlay window, in window points, that take clicks. Everything else passes through.
#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
enum Region {
    Circle { x: f64, y: f64, r: f64 },
    Rect { x: f64, y: f64, w: f64, h: f64 },
}

impl Region {
    fn contains(&self, px: f64, py: f64) -> bool {
        match *self {
            Region::Circle { x, y, r } => (px - x).hypot(py - y) <= r,
            Region::Rect { x, y, w, h } => px >= x && px <= x + w && py >= y && py <= y + h,
        }
    }
}

#[derive(Default)]
struct HitRegions(Mutex<Vec<Region>>);

#[derive(Default)]
struct PopoverClosedAt(Mutex<Option<Instant>>);

#[derive(Clone, Serialize)]
struct Pointer {
    x: f64,
    y: f64,
}

#[tauri::command]
fn set_hit_regions(regions: State<HitRegions>, list: Vec<Region>) {
    *regions.0.lock().unwrap() = list;
}

#[tauri::command]
fn fit_popover(app: AppHandle, height: f64) {
    if let Some(popover) = app.get_webview_window("settings") {
        let _ = popover.set_size(LogicalSize::new(320.0, height.clamp(200.0, 900.0)));
    }
}

#[tauri::command]
fn open_transcript(app: AppHandle) {
    if let Some(popover) = app.get_webview_window("settings") {
        let _ = popover.hide();
    }
    let _ = app.emit("open-transcript", ());
}

#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

/// Whether the cursor moved enough to be worth sending. The first position is always sent.
fn moved_enough(last_sent: Option<(f64, f64)>, x: f64, y: f64) -> bool {
    last_sent.is_none_or(|(lx, ly)| (x - lx).abs() > 0.5 || (y - ly).abs() > 0.5)
}

fn home_position(win: &WebviewWindow) -> tauri::Result<PhysicalPosition<i32>> {
    let size = win.outer_size()?;
    let Some(monitor) = win.primary_monitor()? else { return win.outer_position() };
    let area = monitor.work_area();
    Ok(PhysicalPosition::new(
        area.position.x + area.size.width as i32 - size.width as i32,
        area.position.y + area.size.height as i32 - size.height as i32,
    ))
}

/// Sidesteps along the bottom edge when the cursor hangs around next to the bot without touching it.
/// A quick approach to click the bot never triggers it, and it drifts home once the cursor is gone.
struct Dodge {
    offset: f64,
    target: f64,
    near_since: Option<Instant>,
    far_since: Option<Instant>,
}

impl Dodge {
    const DISTANCE: f64 = 240.0;
    const NEAR_BAND: f64 = 90.0;
    const FAR: f64 = 220.0;
    const LINGER: Duration = Duration::from_millis(1200);
    const RETURN_AFTER: Duration = Duration::from_secs(4);

    fn update(&mut self, allowed: bool, gap: f64, now: Instant) {
        if !allowed {
            self.target = 0.0;
            self.near_since = None;
            return;
        }
        if gap <= 0.0 {
            self.near_since = None;
        } else if gap < Self::NEAR_BAND {
            self.far_since = None;
            let since = *self.near_since.get_or_insert(now);
            if now - since > Self::LINGER {
                self.target = if self.target == 0.0 { -Self::DISTANCE } else { 0.0 };
                self.near_since = None;
            }
        } else if gap > Self::FAR {
            self.near_since = None;
            let since = *self.far_since.get_or_insert(now);
            if now - since > Self::RETURN_AFTER {
                self.target = 0.0;
            }
        }
    }

    /// Eases toward the target; returns true while it is still moving.
    fn step(&mut self) -> bool {
        if (self.offset - self.target).abs() < 0.5 {
            self.offset = self.target;
            return false;
        }
        self.offset += (self.target - self.offset) * 0.18;
        true
    }
}

fn hide_reason(app: &AppHandle, settings: &settings::OverlaySettings) -> Option<HideReason> {
    if settings.hidden {
        return Some(HideReason::Manual);
    }
    if !settings.hide_in_fullscreen {
        return None;
    }
    if watch::fullscreen_app_in_front(app) {
        return Some(HideReason::Fullscreen);
    }
    watch::camera_in_use().then_some(HideReason::Camera)
}

/// One loop for everything driven by the cursor and the screen: eyes, click-through, dodging and hiding.
fn watch_screen(app: AppHandle, win: WebviewWindow) {
    thread::spawn(move || {
        let home = home_position(&win).unwrap_or(PhysicalPosition::new(0, 0));
        let mut over_bot = None;
        let mut last_sent = None;
        let mut dodge = Dodge { offset: 0.0, target: 0.0, near_since: None, far_since: None };
        let mut hidden: Option<Option<HideReason>> = None;
        for frame in 0u64.. {
            thread::sleep(Duration::from_millis(16));
            let settings = app.state::<SettingsStore>().get();
            if frame % 30 == 0 {
                let reason = hide_reason(&app, &settings);
                if hidden != Some(reason) {
                    let _ = if reason.is_some() { win.hide() } else { win.show() };
                    let _ = app.emit("visibility", reason);
                    hidden = Some(reason);
                }
            }
            let (Ok(cursor), Ok(origin), Ok(scale)) = (app.cursor_position(), win.outer_position(), win.scale_factor()) else {
                continue;
            };
            let x = (cursor.x - origin.x as f64) / scale;
            let y = (cursor.y - origin.y as f64) / scale;
            let regions = app.state::<HitRegions>().0.lock().unwrap().clone();
            let inside = regions.iter().any(|r| r.contains(x, y));
            if over_bot != Some(inside) {
                let _ = win.set_ignore_cursor_events(!inside);
                over_bot = Some(inside);
            }
            if moved_enough(last_sent, x, y) {
                last_sent = Some((x, y));
                let _ = win.emit("pointer", Pointer { x, y });
            }
            if let Some(&Region::Circle { x: cx, y: cy, r }) = regions.first() {
                dodge.update(settings.keep_away && !settings.stay_put, (x - cx).hypot(y - cy) - r, Instant::now());
            }
            if dodge.step() {
                let _ = win.set_position(PhysicalPosition::new(home.x + (dodge.offset * scale) as i32, home.y));
            }
        }
    });
}

fn toggle_popover(app: &AppHandle, icon: Rect) {
    let Some(popover) = app.get_webview_window("settings") else { return };
    if popover.is_visible().unwrap_or(false) {
        let _ = popover.hide();
        return;
    }
    let just_closed = app.state::<PopoverClosedAt>().0.lock().unwrap().is_some_and(|at| at.elapsed() < Duration::from_millis(300));
    if just_closed {
        return;
    }
    let scale = popover.scale_factor().unwrap_or(1.0);
    let at = icon.position.to_physical::<f64>(scale);
    let size = icon.size.to_physical::<f64>(scale);
    let width = popover.outer_size().map(|s| s.width as f64).unwrap_or(320.0 * scale);
    let _ = popover.set_position(PhysicalPosition::new((at.x + size.width / 2.0 - width / 2.0) as i32, (at.y + size.height + 6.0) as i32));
    let _ = popover.show();
    let _ = popover.set_focus();
}

/// For working on the popover: COMPANION_OPEN_SETTINGS=1 shows it at launch, top right, without a click.
fn open_settings_in_corner(win: &WebviewWindow) -> tauri::Result<()> {
    let (Some(popover), Some(monitor)) = (win.app_handle().get_webview_window("settings"), win.primary_monitor()?) else { return Ok(()) };
    let area = monitor.work_area();
    let width = popover.outer_size()?.width as i32;
    popover.set_position(PhysicalPosition::new(area.position.x + area.size.width as i32 - width - 12, area.position.y + 6))?;
    popover.show()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(HitRegions::default())
        .manage(PopoverClosedAt::default())
        .invoke_handler(tauri::generate_handler![set_hit_regions, get_settings, update_settings, fit_popover, open_transcript, quit])
        .on_window_event(|window, event| {
            if window.label() == "settings" && matches!(event, WindowEvent::Focused(false)) {
                let _ = window.hide();
                *window.app_handle().state::<PopoverClosedAt>().0.lock().unwrap() = Some(Instant::now());
            }
        })
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            let config_dir = app.path().app_config_dir()?;
            app.manage(SettingsStore::load(config_dir.join("overlay-settings.json")));

            TrayIconBuilder::with_id("main")
                .icon(Image::from_bytes(include_bytes!("../icons/tray.png"))?)
                .icon_as_template(true)
                .tooltip("Companion")
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { rect, button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        toggle_popover(tray.app_handle(), rect);
                    }
                })
                .build(app)?;

            let win = app.get_webview_window("main").expect("main window is declared in tauri.conf.json");
            win.set_position(home_position(&win)?)?;
            if std::env::var_os("COMPANION_OPEN_SETTINGS").is_some() {
                open_settings_in_corner(&win)?;
            }
            watch_screen(app.handle().clone(), win);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("companion overlay failed to start");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_position_is_always_sent() {
        assert!(moved_enough(None, 10.0, 20.0));
    }

    #[test]
    fn only_real_movement_is_sent_after_that() {
        assert!(!moved_enough(Some((10.0, 20.0)), 10.3, 20.2));
        assert!(moved_enough(Some((10.0, 20.0)), 11.0, 20.0));
    }

    fn fresh() -> Dodge {
        Dodge { offset: 0.0, target: 0.0, near_since: None, far_since: None }
    }

    #[test]
    fn lingering_next_to_the_bot_makes_it_step_aside() {
        let mut d = fresh();
        let t0 = Instant::now();
        d.update(true, 40.0, t0);
        d.update(true, 40.0, t0 + Duration::from_millis(600));
        assert_eq!(d.target, 0.0, "a quick pass does nothing");
        d.update(true, 40.0, t0 + Duration::from_millis(1300));
        assert_eq!(d.target, -Dodge::DISTANCE);
    }

    #[test]
    fn reaching_for_the_bot_never_triggers_a_dodge() {
        let mut d = fresh();
        let t0 = Instant::now();
        d.update(true, 40.0, t0);
        d.update(true, -5.0, t0 + Duration::from_millis(300));
        d.update(true, -5.0, t0 + Duration::from_millis(3000));
        assert_eq!(d.target, 0.0);
    }

    #[test]
    fn it_comes_home_once_the_cursor_has_been_away() {
        let mut d = Dodge { target: -Dodge::DISTANCE, ..fresh() };
        let t0 = Instant::now();
        d.update(true, 400.0, t0);
        d.update(true, 400.0, t0 + Duration::from_secs(5));
        assert_eq!(d.target, 0.0);
    }

    #[test]
    fn stay_put_cancels_any_dodge() {
        let mut d = Dodge { target: -Dodge::DISTANCE, ..fresh() };
        d.update(false, 40.0, Instant::now());
        assert_eq!(d.target, 0.0);
    }

    #[test]
    fn regions_hit_test_circles_and_rectangles() {
        assert!(Region::Circle { x: 0.0, y: 0.0, r: 10.0 }.contains(6.0, 6.0));
        assert!(!Region::Circle { x: 0.0, y: 0.0, r: 10.0 }.contains(8.0, 8.0));
        assert!(Region::Rect { x: 0.0, y: 0.0, w: 10.0, h: 5.0 }.contains(10.0, 5.0));
    }
}

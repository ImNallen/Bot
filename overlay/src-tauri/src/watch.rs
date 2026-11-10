//! What is going on on screen that should make the bot step aside.

use std::sync::mpsc;

use tauri::AppHandle;

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub enum HideReason {
    Manual,
    Fullscreen,
    Camera,
}

/// A fullscreen app hides the menu bar, which is the one signal every app shares, games and video included.
pub fn fullscreen_app_in_front(app: &AppHandle) -> bool {
    let (tx, rx) = mpsc::channel();
    let _ = app.run_on_main_thread(move || {
        #[cfg(target_os = "macos")]
        {
            use objc2_foundation::MainThreadMarker;
            let visible = MainThreadMarker::new().map(objc2_app_kit::NSMenu::menuBarVisible).unwrap_or(true);
            let _ = tx.send(!visible);
        }
        #[cfg(not(target_os = "macos"))]
        let _ = tx.send(false);
    });
    rx.recv().unwrap_or(false)
}

/// Another app is using the camera, which almost always means a video call.
pub fn camera_in_use() -> bool {
    #[cfg(target_os = "macos")]
    unsafe {
        use objc2_av_foundation::{AVCaptureDevice, AVMediaTypeVideo};
        let Some(video) = AVMediaTypeVideo else { return false };
        return AVCaptureDevice::defaultDeviceWithMediaType(video).is_some_and(|device| device.isInUseByAnotherApplication());
    }
    #[allow(unreachable_code)]
    false
}

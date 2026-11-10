use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Emitter, State};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Theme {
    System,
    Light,
    Dark,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Size {
    S,
    M,
    L,
}

/// Everything the overlay itself decides. The Rust side owns it, saves it, and broadcasts every
/// change to both windows, so the popover and the bot can never disagree.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct OverlaySettings {
    pub theme: Theme,
    pub size: Size,
    pub keep_away: bool,
    pub hide_in_fullscreen: bool,
    pub stay_put: bool,
    pub hidden: bool,
}

impl Default for OverlaySettings {
    fn default() -> Self {
        Self { theme: Theme::System, size: Size::M, keep_away: true, hide_in_fullscreen: true, stay_put: false, hidden: false }
    }
}

impl OverlaySettings {
    /// Applies a partial update. Unknown keys and wrong types are rejected as a whole.
    pub fn merged(&self, patch: &Value) -> Result<Self, String> {
        let mut value = serde_json::to_value(self).map_err(|e| e.to_string())?;
        let (Value::Object(target), Value::Object(changes)) = (&mut value, patch) else {
            return Err("settings patch must be an object".into());
        };
        for (key, change) in changes {
            if !target.contains_key(key) {
                return Err(format!("unknown setting {key}"));
            }
            target.insert(key.clone(), change.clone());
        }
        serde_json::from_value(value).map_err(|e| e.to_string())
    }
}

pub struct SettingsStore {
    path: PathBuf,
    pub current: Mutex<OverlaySettings>,
}

impl SettingsStore {
    pub fn load(path: PathBuf) -> Self {
        let current = fs::read_to_string(&path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default();
        Self { path, current: Mutex::new(current) }
    }

    pub fn get(&self) -> OverlaySettings {
        self.current.lock().unwrap().clone()
    }

    fn save(&self, settings: &OverlaySettings) {
        if let Some(dir) = self.path.parent() {
            let _ = fs::create_dir_all(dir);
        }
        if let Ok(text) = serde_json::to_string_pretty(settings) {
            let _ = fs::write(&self.path, text);
        }
    }
}

#[tauri::command]
pub fn get_settings(store: State<SettingsStore>) -> OverlaySettings {
    store.get()
}

#[tauri::command]
pub fn update_settings(app: AppHandle, store: State<SettingsStore>, patch: Value) -> Result<OverlaySettings, String> {
    let next = store.get().merged(&patch)?;
    *store.current.lock().unwrap() = next.clone();
    store.save(&next);
    let _ = app.emit("settings", &next);
    Ok(next)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_patch_changes_only_what_it_names() {
        let next = OverlaySettings::default().merged(&json!({"stayPut": true, "size": "l"})).unwrap();
        assert_eq!(next, OverlaySettings { stay_put: true, size: Size::L, ..OverlaySettings::default() });
    }

    #[test]
    fn bad_patches_are_rejected_whole() {
        let base = OverlaySettings::default();
        assert!(base.merged(&json!({"size": "xl"})).is_err());
        assert!(base.merged(&json!({"stayPut": true, "teleport": true})).is_err());
        assert!(base.merged(&json!(["not", "an", "object"])).is_err());
    }

    #[test]
    fn missing_fields_in_a_saved_file_fall_back_to_defaults() {
        let loaded: OverlaySettings = serde_json::from_str(r#"{"theme":"dark"}"#).unwrap();
        assert_eq!(loaded, OverlaySettings { theme: Theme::Dark, ..OverlaySettings::default() });
    }
}

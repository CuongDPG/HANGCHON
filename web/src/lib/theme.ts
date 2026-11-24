/**
 * Giao diện sáng/tối. Mặc định theo máy; chọn tay thì lưu vào localStorage và đặt `data-theme` trên <html>.
 * THEME_SCRIPT chạy trước khi trang hiện (trong <head>) để không bị nháy màu.
 */
export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "hc-theme";

export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch(e){}})();`;

export function readThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const t = window.localStorage.getItem(THEME_STORAGE_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(pref: ThemePreference) {
  const root = document.documentElement;
  try {
    if (pref === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    /* chế độ riêng tư: bỏ qua */
  }
  if (pref === "system") delete root.dataset.theme;
  else root.dataset.theme = pref;
}

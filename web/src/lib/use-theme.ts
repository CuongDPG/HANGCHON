"use client";

import { useCallback, useSyncExternalStore } from "react";
import { applyThemePreference, readThemePreference, type ThemePreference } from "./theme";

const EVENT = "hc-theme-change";

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** Giao diện đang chọn + hàm đổi (dùng ở Cài đặt, trang /desk/kit). */
export function useThemePreference(): [ThemePreference, (pref: ThemePreference) => void] {
  const pref = useSyncExternalStore(subscribe, readThemePreference, () => "system" as ThemePreference);
  const set = useCallback((next: ThemePreference) => {
    applyThemePreference(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [pref, set];
}

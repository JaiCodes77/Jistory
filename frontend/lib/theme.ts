export const THEME_STORAGE_KEY = "jistory-theme"
export const THEME_EVENT = "jistory-theme"

export type Theme = "dark" | "light"

export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light")document.documentElement.classList.remove("dark");else document.documentElement.classList.add("dark");}catch(e){}})();`

export function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === "dark") {
    root.classList.add("dark")
  } else {
    root.classList.remove("dark")
  }
  localStorage.setItem(THEME_STORAGE_KEY, theme)
  window.dispatchEvent(new Event(THEME_EVENT))
}

export function getStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === "light" || stored === "dark") {
      return stored
    }
  } catch {
    // Ignore quota / privacy-mode failures and keep the default.
  }
  return "dark"
}

export function subscribeTheme(onStoreChange: () => void) {
  window.addEventListener(THEME_EVENT, onStoreChange)
  window.addEventListener("storage", onStoreChange)
  return () => {
    window.removeEventListener(THEME_EVENT, onStoreChange)
    window.removeEventListener("storage", onStoreChange)
  }
}

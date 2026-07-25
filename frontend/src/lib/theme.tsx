/**
 * Theme state for the light/dark token sets in `styles.css`.
 *
 * Three settings, not two: "system" is the default and tracks the OS, so an
 * analyst who runs their machine dark gets a dark console without configuring
 * anything. Choosing light or dark explicitly pins it and survives reloads.
 *
 * The `.dark` class on <html> is what the CSS actually keys off. It is applied
 * before first paint by THEME_INIT_SCRIPT (see `__root.tsx`) — this provider
 * only keeps it in sync afterwards.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "erakshak.theme";

/**
 * Runs blocking in <head> so the correct token set is in place before the first
 * paint. Without it the page renders light, then snaps to dark a frame later.
 * Kept dependency-free and stringified because it must execute before the
 * bundle loads.
 */
export const THEME_INIT_SCRIPT = `(function(){try{
var s=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
var m=window.matchMedia("(prefers-color-scheme: dark)").matches;
var d=s==="dark"||((!s||s==="system")&&m);
document.documentElement.classList.toggle("dark",d);
document.documentElement.style.colorScheme=d?"dark":"light";
}catch(e){}})();`;

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* private mode / storage disabled — fall through to the system default */
  }
  return "system";
}

function applyTheme(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

type ThemeContextValue = {
  /** What the user chose — may be "system". */
  theme: Theme;
  /** What is actually on screen once "system" is resolved. */
  resolvedTheme: ResolvedTheme;
  setTheme: (next: Theme) => void;
  /** Flip to the opposite of what is currently rendered. */
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Server-render assumes "system"; the init script has already corrected the
  // DOM by the time this mounts, and the effect below re-syncs from storage.
  const [theme, setThemeState] = useState<Theme>("system");
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    setThemeState(readStoredTheme());
    setSystemDark(systemPrefersDark());
  }, []);

  // Track OS changes so "system" stays live rather than sampled once.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const resolvedTheme: ResolvedTheme =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    applyTheme(resolvedTheme);
  }, [resolvedTheme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* preference just won't persist */
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(resolvedTheme === "dark" ? "light" : "dark");
  }, [resolvedTheme, setTheme]);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme }),
    [theme, resolvedTheme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}

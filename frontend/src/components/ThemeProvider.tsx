import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];

const STORAGE_KEY = "theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  /** What "system" currently resolves to, so a control can show the real state. */
  resolved: "light" | "dark";
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const stored = (): Theme => {
  const value = localStorage.getItem(STORAGE_KEY);
  return THEMES.includes(value as Theme) ? (value as Theme) : "system";
};

const prefersDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(stored);
  const [systemDark, setSystemDark] = useState(prefersDark);

  // Only matters while the choice is "system", but the listener is cheap and
  // unsubscribing on every toggle is more code than leaving it attached.
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
    document.documentElement.style.colorScheme = resolved;
  }, [resolved]);

  const setTheme = (next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolved }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useTheme was called outside ThemeProvider");
  }
  return value;
}

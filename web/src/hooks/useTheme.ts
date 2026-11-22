import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "annu-theme";
const darkQuery = "(prefers-color-scheme: dark)";

function readSaved(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.(darkQuery).matches ? "dark" : "light";
}

/**
 * The page follows the operating system until the person makes a choice;
 * after that their choice wins and is remembered on this device.
 */
export function useTheme() {
  const [saved, setSaved] = useState<Theme | null>(readSaved);
  const [system, setSystem] = useState<Theme>(systemTheme);

  useEffect(() => {
    const media = window.matchMedia?.(darkQuery);
    if (!media) return;
    const onChange = () => setSystem(media.matches ? "dark" : "light");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (saved) root.dataset.theme = saved;
    else delete root.dataset.theme;
  }, [saved]);

  const theme = saved ?? system;

  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setSaved(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable: the choice lasts for this visit only */
    }
  }, [theme]);

  return { theme, toggle };
}

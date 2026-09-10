import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try { const saved = localStorage.getItem("memstara-theme"); return saved !== "light"; } catch { return true; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("memstara-theme", dark ? "dark" : "light"); } catch { /* Storage unavailable. */ }
  }, [dark]);
  return <button className="theme-toggle" onClick={() => setDark(!dark)} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}>
    {dark ? <Sun size={17} /> : <Moon size={17} />}
  </button>;
}

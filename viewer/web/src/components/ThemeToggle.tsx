import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (new URLSearchParams(window.location.search).get('demo') === '1') return false;
    try { const saved = localStorage.getItem("memstara-theme-v2"); return saved === "dark"; } catch { return false; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("memstara-theme-v2", dark ? "dark" : "light"); localStorage.setItem("memstara-theme", dark ? "dark" : "light"); } catch { /* Storage unavailable. */ }
  }, [dark]);
  return <button className="theme-toggle" onClick={() => setDark(!dark)} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}>
    {dark ? <Sun size={17} /> : <Moon size={17} />}
  </button>;
}

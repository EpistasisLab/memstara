/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // One colour per stage, used for the character, its card and its lines, so a
        // task keeps the same identity as it moves between places.
        stage: {
          curator: "rgb(var(--stage-curator) / <alpha-value>)",
          hypothesis: "rgb(var(--stage-hypothesis) / <alpha-value>)",
          data: "rgb(var(--stage-data) / <alpha-value>)",
          ml: "rgb(var(--stage-ml) / <alpha-value>)",
          interpreter: "rgb(var(--stage-interpreter) / <alpha-value>)",
          report: "rgb(var(--stage-report) / <alpha-value>)",
        },
        accent: { DEFAULT: "rgb(var(--accent) / <alpha-value>)", contrast: "rgb(var(--accent-contrast) / <alpha-value>)" },
        ink: { DEFAULT: "rgb(var(--ink) / <alpha-value>)", soft: "rgb(var(--ink-soft) / <alpha-value>)", faint: "rgb(var(--ink-faint) / <alpha-value>)" },
        paper: { DEFAULT: "rgb(var(--paper) / <alpha-value>)", panel: "rgb(var(--panel) / <alpha-value>)", line: "rgb(var(--line) / <alpha-value>)" },
      },
      fontFamily: {
        sans: ['"Apple SD Gothic Neo"', '"Noto Sans KR"', "system-ui", "sans-serif"],
        mono: ['"SF Mono"', "Menlo", "monospace"],
      },
      keyframes: {
        // A tool call lights its line briefly, then fades. Distinct from a steady state
        // so a glance tells "something just happened" from "something is happening".
        flash: { "0%": { opacity: "0" }, "15%": { opacity: "1" }, "100%": { opacity: "0" } },
        breathe: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
      },
      animation: {
        flash: "flash 1.6s ease-out",
        breathe: "breathe 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

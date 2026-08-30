/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // One colour per stage, used for the character, its card and its lines, so a
        // task keeps the same identity as it moves between places.
        stage: {
          hypothesis: "#2f6b47",
          data: "#2a5f8f",
          ml: "#8a5f12",
          interpreter: "#6b3f8f",
          report: "#8f2f4f",
        },
        ink: { DEFAULT: "#17171a", soft: "#52514e", faint: "#8a8880" },
        paper: { DEFAULT: "#faf9f6", panel: "#ffffff", line: "#dcdbd4" },
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

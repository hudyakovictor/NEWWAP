/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a1523",
          panel: "#0d1b2d",
          deep: "#061019",
        },
        line: "#1a2b44",
        axis: "#233657",
        ok: "#22c55e",
        warn: "#f59e0b",
        danger: "#ef4444",
        info: "#38bdf8",
        accent: "#a855f7",
        muted: "#6b7a90",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

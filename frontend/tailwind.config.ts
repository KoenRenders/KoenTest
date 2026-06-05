import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#1d4ed8", light: "#3b82f6", dark: "#1e3a8a" },
        accent: { DEFAULT: "#16a34a", light: "#22c55e" },
        "ocean-blue": "#0051a4",
        "golden-yellow": "#ffce00",
        "pumpkin-orange": "#f16532",
        "cool-green": "#3aba9b",
        "dark-green": "#005d29",
        "hot-pink": "#f17fb2",
        "watermelon-red": "#ee3a37",
        indigo: "#460359",
      },
      fontFamily: {
        primary: ["var(--font-radio-canada-big)", "Radio Canada Big", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;

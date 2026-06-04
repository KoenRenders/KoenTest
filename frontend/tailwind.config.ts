import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#1d4ed8", light: "#3b82f6", dark: "#1e3a8a" },
        accent: { DEFAULT: "#16a34a", light: "#22c55e" },
      },
    },
  },
  plugins: [],
};
export default config;

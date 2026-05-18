import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        webb: {
          deep: "#05060f",
          ink: "#0b0d1a",
          star: "#e7e9ff",
          accent: "#7aa2ff",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;

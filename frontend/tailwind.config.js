/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F4F6F5",
        ink: "#17211E",
        "ink-soft": "#4A5551",
        own: "#0C6B58",
        "own-tint": "#E3F0EC",
        invariant: "#AE4326",
        "invariant-tint": "#F7E9E3",
        hairline: "#C9D1CE",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

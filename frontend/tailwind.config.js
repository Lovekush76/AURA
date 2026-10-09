/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        aura: {
          bg: "#08080C",
          cyan: "#00F0FF",
          border: "rgba(255, 255, 255, 0.08)",
          card: "rgba(255, 255, 255, 0.03)"
        }
      }
    },
  },
  plugins: [],
}

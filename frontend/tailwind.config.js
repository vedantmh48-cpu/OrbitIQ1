/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        space: {
          950: "#060a14",
          900: "#0a1220",
          850: "#0d1729",
          800: "#111c33",
          700: "#1a2a47",
          600: "#243a61"
        },
        accent: {
          DEFAULT: "#22d3ee",
          soft: "#67e8f9",
          deep: "#0891b2"
        }
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"]
      },
      animation: {
        "fade-in": "fadeIn .35s ease-out",
        "slide-up": "slideUp .3s ease-out",
        "pulse-slow": "pulse 2.5s cubic-bezier(.4,0,.6,1) infinite"
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } }
      }
    }
  },
  plugins: []
};
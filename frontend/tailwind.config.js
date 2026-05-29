/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg-main)",
        foreground: "var(--text-main)",
        card: "var(--bg-card)",
        "card-foreground": "var(--text-main)",
        primary: "var(--primary)",
        "primary-foreground": "#ffffff",
        secondary: "var(--bg-hover)",
        "secondary-foreground": "var(--text-main)",
        muted: "var(--bg-hover)",
        "muted-foreground": "var(--text-muted)",
        accent: "var(--primary-light)",
        "accent-foreground": "var(--primary)",
        border: "var(--border)",
        input: "var(--border)",
      }
    },
  },
  corePlugins: {
    preflight: false,
  },
  plugins: [],
}

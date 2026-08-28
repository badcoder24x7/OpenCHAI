/** @type {import('tailwindcss').Config} */
export default {

  darkMode: 'class',

  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  theme: {
    extend: {
      colors: {
        chai: {
          50:  '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          900: '#0c4a6e',
        },
        // Brand header/nav palette — fixed across Light & Dark mode by design
        // (same pattern as Azure Portal / Cisco Intersight's persistent top
        // bar). Centralized here so the 4 previously-hardcoded hex values
        // in Navbar.jsx / Login.jsx become a single source of truth.
        brand: {
          DEFAULT: '#0F4C81', // header bar background
          dark:    '#0d3f6b', // header bar hover / active
          panel:   '#0A3B63', // icon buttons / chips on the header
          panelHover: '#144F7F',
        },
      },
    },
  },

  plugins: [
    require('@tailwindcss/typography'),
  ],
}

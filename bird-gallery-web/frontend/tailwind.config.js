/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 兼容旧 primary-* 引用，逐步迁移到 apple-*
        primary: {
          50:  '#f0f7ff',
          100: '#e0efff',
          200: '#b9dcff',
          300: '#7abfff',
          400: '#2997ff',
          500: '#0071e3',
          600: '#0071e3',
          700: '#0066cc',
          800: '#004d99',
          900: '#003366',
        },
        apple: {
          blue: '#0071e3',
          'link-light': '#0066cc',
          'link-dark': '#2997ff',
        },
        surface: {
          white: '#ffffff',
          light: '#f5f5f7',
          dark: '#000000',
          'card-dark': '#272729',
        },
        text: {
          primary: '#1d1d1f',
          secondary: 'rgba(0,0,0,0.8)',
          tertiary: 'rgba(0,0,0,0.48)',
          'on-dark': '#ffffff',
          'on-dark-secondary': 'rgba(255,255,255,0.8)',
          'on-dark-tertiary': 'rgba(255,255,255,0.48)',
        },
      },
      fontFamily: {
        display: ['"SF Pro Display"', '-apple-system', '"PingFang SC"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        text: ['"SF Pro Text"', '-apple-system', '"PingFang SC"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        'pill': '980px',
      },
      backdropBlur: {
        'apple': '20px',
      },
      boxShadow: {
        'apple': 'rgba(0, 0, 0, 0.22) 3px 5px 30px 0px',
      },
    },
  },
  plugins: [],
}

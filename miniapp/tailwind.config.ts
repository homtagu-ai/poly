import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0b1520',
          secondary: '#101c28',
          card: '#142230',
          'card-hover': '#1a2d3d',
          input: '#1a2d3d',
          tertiary: '#1a2d3d',
        },
        border: {
          DEFAULT: '#243848',
          subtle: '#1c3040',
        },
        accent: {
          blue: '#3ba5b5',
          cyan: '#0dd3ce',
          teal: '#3edbd5',
          green: '#10b981',
          red: '#ef4444',
          yellow: '#f59e0b',
        },
        text: {
          primary: '#e4eef6',
          secondary: '#8ba8be',
          muted: '#507080',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'gradient-shift': 'gradientShift 3s ease-in-out infinite',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
        'blur-fade': 'blurFadeIn 0.5s ease-out forwards',
      },
      keyframes: {
        gradientShift: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        blurFadeIn: {
          '0%': { opacity: '0', filter: 'blur(8px)', transform: 'translateY(12px)' },
          '100%': { opacity: '1', filter: 'blur(0)', transform: 'translateY(0)' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(59,165,181,0.15)' },
          '50%': { boxShadow: '0 0 24px rgba(59,165,181,0.35)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config

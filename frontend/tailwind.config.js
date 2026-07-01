/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: '#080c14',
          panel: '#0d1420',
          border: '#1a2540',
          cyan: '#00f5ff',
          'cyan-dim': '#005f66',
          gold: '#ffd700',
          red: '#ff3366',
          purple: '#9d00ff',
          green: '#00ff88',
          text: '#c8d8f0',
          'text-dim': '#5a7090',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"Orbitron"', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-cyan': 'glowCyan 2s ease-in-out infinite alternate',
        'glow-red': 'glowRed 1.5s ease-in-out infinite alternate',
        'scan-line': 'scanLine 4s linear infinite',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.5s ease-out',
        'count-up': 'countUp 0.5s ease-out',
        float: 'float 6s ease-in-out infinite',
      },
      keyframes: {
        glowCyan: {
          '0%': { boxShadow: '0 0 5px #00f5ff40, 0 0 10px #00f5ff20' },
          '100%': { boxShadow: '0 0 15px #00f5ff80, 0 0 30px #00f5ff40' },
        },
        glowRed: {
          '0%': { boxShadow: '0 0 5px #ff336640, 0 0 10px #ff336620' },
          '100%': { boxShadow: '0 0 20px #ff336680, 0 0 40px #ff336640' },
        },
        scanLine: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
      backgroundImage: {
        'grid-cyber': `linear-gradient(rgba(0,245,255,0.03) 1px, transparent 1px),
                       linear-gradient(90deg, rgba(0,245,255,0.03) 1px, transparent 1px)`,
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
      backgroundSize: {
        'grid-40': '40px 40px',
      },
      boxShadow: {
        'glow-cyan': '0 0 15px rgba(0,245,255,0.5)',
        'glow-red': '0 0 15px rgba(255,51,102,0.5)',
        'glow-purple': '0 0 15px rgba(157,0,255,0.5)',
        'glow-gold': '0 0 15px rgba(255,215,0,0.5)',
        'glow-green': '0 0 15px rgba(0,255,136,0.5)',
        'panel': '0 0 0 1px rgba(0,245,255,0.1), 0 4px 24px rgba(0,0,0,0.5)',
      },
    },
  },
  plugins: [],
}

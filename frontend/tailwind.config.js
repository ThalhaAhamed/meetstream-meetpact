/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Soft & pastel neo-brutalism: hard offset shadows in a deep plum-ink
      // instead of black, rounder corners, pastel fills.
      boxShadow: {
        card: '4px 4px 0 0 #2B2540',
        lift: '6px 6px 0 0 #2B2540',
        press: '2px 2px 0 0 #2B2540',
      },
      borderRadius: {
        DEFAULT: '0.5rem',
        md: '0.75rem',
        lg: '1rem',
        xl: '1.25rem',
      },
      keyframes: {
        'fade-up': { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: { 'fade-up': 'fade-up 280ms cubic-bezier(0.2, 0.8, 0.2, 1) both', shimmer: 'shimmer 1.6s linear infinite' },
      colors: {
        ink: { 50: '#FBF8FF', 100: '#F1ECFA', 200: '#E2DBF0', 300: '#C8BFDB', 400: '#9D93B5', 500: '#756B8E', 600: '#5B5274', 700: '#463E5D', 800: '#363049', 900: '#2E2842', 950: '#2B2540' },
        brand: { 50: '#F3F0FF', 100: '#E6E0FF', 200: '#CEC3FF', 300: '#B3A3FB', 400: '#9A86F5', 500: '#8470EC', 600: '#6F5AD6', 700: '#5B47B5', 800: '#4A3B91', 900: '#3D3274' },
        pop: { yellow: '#FFE38F', pink: '#FFC6DA', mint: '#BFEBD3', sky: '#C4E1FF', orange: '#FFD5B3', lilac: '#DCCFFF', red: '#FFB5B0' },
      },
    },
  },
  plugins: [],
}

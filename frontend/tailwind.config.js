/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Neubrutalism: hard, offset, solid-black shadows.
      boxShadow: {
        card: '4px 4px 0 0 #111111',
        lift: '6px 6px 0 0 #111111',
        press: '2px 2px 0 0 #111111',
      },
      keyframes: {
        'fade-up': { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: { 'fade-up': 'fade-up 280ms cubic-bezier(0.2, 0.8, 0.2, 1) both', shimmer: 'shimmer 1.6s linear infinite' },
      colors: {
        ink: { 50: '#FFF8E7', 100: '#F6EDD5', 200: '#E6DCC0', 300: '#C9BFA4', 400: '#9A917A', 500: '#6E6756', 600: '#55503F', 700: '#3E3A2E', 800: '#2A2720', 900: '#1A1814', 950: '#111111' },
        brand: { 50: '#E8EDFF', 100: '#D3DCFF', 200: '#AFBEFF', 300: '#8299FF', 400: '#5A76FF', 500: '#3B5BFF', 600: '#2F4BE6', 700: '#2238C2', 800: '#1C2E99', 900: '#18287A' },
        pop: { yellow: '#FFD23F', pink: '#FF8FB1', mint: '#7CE3A1', sky: '#8CC8FF', orange: '#FFA552', lilac: '#C3A6FF', red: '#FF6B6B' },
      },
    },
  },
  plugins: [],
}

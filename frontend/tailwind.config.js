/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Soft Swiss-grid neo-brutalism ("Butter and charcoal"): hard offset shadows in
      // warm charcoal ink, rounded corners, pastel fills, strict grid.
      boxShadow: {
        card: '4px 4px 0 0 #22201B',
        lift: '6px 6px 0 0 #22201B',
        press: '2px 2px 0 0 #22201B',
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
        ink: { 50: '#FAF7EE', 100: '#F2EEE3', 200: '#E3DDCD', 300: '#C9C1AD', 400: '#9E9684', 500: '#776F5F', 600: '#5C5548', 700: '#463F35', 800: '#332E27', 900: '#29251F', 950: '#22201B' },
        brand: { 50: '#FFFBEB', 100: '#FFF3C4', 200: '#FFE89A', 300: '#FFD95C', 400: '#F5C633', 500: '#D9A50F', 600: '#B3850A', 700: '#8A650B', 800: '#6B4F0E', 900: '#58420F' },
        // One brand colour (accent: butter). Every other pastel has one meaning.
        // The names are roles, not hues: "yellow" is the warning role (blocked /
        // needs attention, peach here so it never looks like the brand) and
        // "orange" the keeps-slipping role (lilac); red = overdue / failed,
        // mint = done, sky = in progress / info.
        accent: { DEFAULT: '#FFD95C', soft: '#F6ECC4' },
        pop: { yellow: '#FFC59E', pink: '#FFC6DA', mint: '#BFEBD3', sky: '#C4E1FF', orange: '#DCCFFF', lilac: '#DCCFFF', red: '#FFB5B0' },
        // Readable text versions of the signal colours.
        signal: { red: '#B3261E', amber: '#8A5A00' },
      },
    },
  },
  plugins: [],
}

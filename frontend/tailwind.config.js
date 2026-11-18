/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Soft Swiss-grid neo-brutalism ("Cobalt mist"): hard offset shadows in
      // deep navy ink, rounded corners, pastel fills, strict grid.
      boxShadow: {
        card: '4px 4px 0 0 #151C2E',
        lift: '6px 6px 0 0 #151C2E',
        press: '2px 2px 0 0 #151C2E',
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
        ink: { 50: '#F4F6FA', 100: '#E8EDF5', 200: '#D5DDEA', 300: '#B7C3D6', 400: '#8B98AF', 500: '#66738B', 600: '#4D5970', 700: '#3A4559', 800: '#283247', 900: '#1C2438', 950: '#151C2E' },
        brand: { 50: '#EEF4FF', 100: '#E1EAFB', 200: '#C7DAFF', 300: '#9EC1FF', 400: '#77A6F7', 500: '#4F86E8', 600: '#3A6ACB', 700: '#2E54A3', 800: '#26447F', 900: '#1F3662' },
        // One brand colour (accent: cobalt). Every other pastel has one meaning:
        // yellow = blocked / needs attention, red = overdue / failed, mint = done,
        // sky = in progress / info, orange (peach) = keeps slipping.
        accent: { DEFAULT: '#9EC1FF', soft: '#E1EAFB' },
        pop: { yellow: '#FFE38F', pink: '#FFC6DA', mint: '#BFEBD3', sky: '#C4E1FF', orange: '#FFD0A8', lilac: '#DCCFFF', red: '#FFB5B0' },
        // Readable text versions of the signal colours.
        signal: { red: '#B3261E', amber: '#8A5A00' },
      },
    },
  },
  plugins: [],
}

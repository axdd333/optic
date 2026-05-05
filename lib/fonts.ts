import { Playfair_Display, DM_Sans } from 'next/font/google';

export const editorialFont = Playfair_Display({
  subsets: ['latin'],
  variable: '--font-editorial',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
});

export const sansFont = DM_Sans({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
});

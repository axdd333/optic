import Hero from '@/components/sections/Hero';
import MarqueeBar from '@/components/sections/MarqueeBar';
import HowItWorks from '@/components/sections/HowItWorks';
import Wedge from '@/components/sections/Wedge';
import Features from '@/components/sections/Features';
import Moat from '@/components/sections/Moat';
import Expansion from '@/components/sections/Expansion';
import Faq from '@/components/sections/Faq';
import Cta from '@/components/sections/Cta';

export default function Home() {
  return (
    <main>
      <Hero />
      <MarqueeBar />
      <HowItWorks />
      <Wedge />
      <Features />
      <Moat />
      <Expansion />
      <Faq />
      <Cta />
    </main>
  );
}

import { Hero } from "@/components/marketing/hero";
import { HowItWorks } from "@/components/marketing/how-it-works";
import { FeaturesSection } from "@/components/marketing/features-section";
import { StatsSection } from "@/components/marketing/stats-section";
import { CtaSection } from "@/components/marketing/cta-section";

export default function LandingPage() {
  return (
    <>
      <Hero />
      <HowItWorks />
      <FeaturesSection />
      <StatsSection />
      <CtaSection />
    </>
  );
}

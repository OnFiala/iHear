import Link from "next/link";
import Image from "next/image";
import { ArrowRight, AudioLines, FileText, ScanLine } from "lucide-react";
import { Header, Footer } from "@/components/shared";

export default function Landing() {
  return (
    <>
      <Header />
      <main tabIndex={-1} id="main">
        <section className="hero page-width">
          <div className="hero-copy">
            <h1>A simple<br />listening log.</h1>
            <p className="lead">Capture everyday listening. Give your audiologist a clearer picture at your next visit.</p>
            <div className="hero-actions">
              <Link className="button" href="/app">Patient app <ArrowRight size={19} /></Link>
              <Link className="button secondary" href="/clinic">Clinician demo <ArrowRight size={19} /></Link>
            </div>
            <p className="hero-note">Illustrative demo</p>
          </div>
          <div className="hero-art">
            <Image src="/listening-ear.webp" alt="A blue ear with two sound waves — the iHear listening symbol" fill preload unoptimized sizes="(max-width: 760px) 100vw, 55vw" />
          </div>
        </section>
        <section id="how-it-works" className="landing-steps page-width" aria-label="How it works">
          <article><ScanLine size={24} /><h2>Pair your phone</h2><p>Open the QR code from your clinician.</p></article>
          <article><AudioLines size={24} /><h2>Save a moment</h2><p>Choose “I understand” or “I don’t understand”.</p></article>
          <article><FileText size={24} /><h2>Review together</h2><p>Bring your listening log to your next visit.</p></article>
        </section>
        <details className="landing-about page-width">
          <summary>About this demo</summary>
          <p>Use synthetic profiles only. With your microphone enabled, iHear saves a short phone sample and extracts acoustic features. Raw audio is deleted after processing. No speech is transcribed.</p>
          <p>Phone audio is not a hearing test or a measurement at your hearing aid. iHear does not diagnose conditions or prescribe hearing-aid settings. Automated interpretation is off.</p>
        </details>
      </main>
      <Footer />
    </>
  );
}

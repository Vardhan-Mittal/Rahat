import type { Metadata } from "next";
import { Archivo, JetBrains_Mono, Mukta, Tiro_Devanagari_Hindi } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });
const mukta = Mukta({ subsets: ["devanagari", "latin"], weight: ["400", "600", "700"], variable: "--font-mukta" });
const tiro = Tiro_Devanagari_Hindi({ subsets: ["devanagari", "latin"], weight: "400", variable: "--font-tiro" });

export const metadata: Metadata = {
  title: "RAHAT Command Centre",
  description: "From alert to I'm safe: live hazard levels, safe routes and multilingual alerts for India.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${mono.variable} ${mukta.variable} ${tiro.variable}`}>
      <body>{children}</body>
    </html>
  );
}

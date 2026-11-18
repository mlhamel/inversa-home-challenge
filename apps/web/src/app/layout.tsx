import "maplibre-gl/dist/maplibre-gl.css";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inversa — Wildfire Air-Quality Explorer",
  description:
    "Real-time and 7-day view of how active wildfires and wind degrade downwind air quality.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";
import Navigation from "@/components/Navigation";

export const metadata: Metadata = {
  title: "ROXY AI — Autonomous Personal AI Assistant",
  description: "Autonomous personal AI assistant for intelligence, automation, finance, and creative workflows.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-[#f8faf9] text-[#1e292b] antialiased">
        <Navigation />
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./fonts.css";
import "./globals.css";
import "./identity.css";
import "./review-studio.css";
import "./document-integrity.css";
import { AuthProvider } from "../components/auth-provider";

export const metadata: Metadata = {
  title: "Forma — бюро мысли",
  description: "Оригинал, свидетельства и критерии — рядом. ИИ помогает понять работу, преподаватель принимает решение.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body className="fs-exclude ph-no-capture rr-block" data-private="true" data-hj-suppress="true" data-clarity-mask="true">  <AuthProvider>{children}</AuthProvider></body></html>;
}

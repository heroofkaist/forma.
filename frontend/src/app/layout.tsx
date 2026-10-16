import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./fonts.css";
import "./globals.css";
import "./identity.css";
import "./review-studio.css";
import "./teaching-workflow.css";
import "./document-integrity.css";
import "./product-design.css";
import "./motion-public.css";
import { AuthProvider } from "../components/auth-provider";

export const metadata: Metadata = {
  title: { default: "Forma — курсы, работы и проверка с ИИ", template: "%s · Forma" },
  description: "Учебные курсы, работы студентов и проверка по критериям. ИИ предлагает баллы, преподаватель принимает решение.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body className="fs-exclude ph-no-capture rr-block" data-private="true" data-hj-suppress="true" data-clarity-mask="true">  <AuthProvider>{children}</AuthProvider></body></html>;
}

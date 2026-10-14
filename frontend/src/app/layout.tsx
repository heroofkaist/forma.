import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import { AuthProvider } from "../components/auth-provider";

export const metadata: Metadata = {
  title: "Forma — проверка письменных работ",
  description: "Рабочее пространство учителя для проверки решений по физике и математике",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>  <AuthProvider>{children}</AuthProvider></body></html>;
}

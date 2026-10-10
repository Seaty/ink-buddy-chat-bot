import type { Metadata } from "next";
import { AuthProvider } from "@/features/auth/provider";
import "./globals.css";
export const metadata: Metadata = {
  title: "Ink Buddy",
  referrer: "no-referrer",
  description: "พื้นที่แชตสำหรับค้นหาและเลือกเครื่องเขียน",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

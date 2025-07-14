import "./globals.css";
import { ReactNode } from "react";
import Navbar from "@/components/navbar";
import Script from "next/script";
import '@fortawesome/fontawesome-free/css/all.min.css';

export const metadata = {
  title: "Stockr",
  description: "",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Additional head elements if needed */}
      </head>
      <body className="h-screen overflow-x-hidden">
        <div className="h-full flex flex-col">
          <Navbar />
          <div className="flex-1 overflow-y-auto">
            <div className="container h-full">{children}</div>
          </div>
        </div>

        <Script
          src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.6/dist/umd/popper.min.js"
          strategy="afterInteractive"
        />
        <Script
          src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.min.js"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}

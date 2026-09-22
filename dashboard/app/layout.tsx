import "./globals.css";

export const metadata = {
  title: "Aishu Dashboard",
  description: "Private Aishu Bot community dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

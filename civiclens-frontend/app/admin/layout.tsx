import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CivicLens Admin",
  description: "CivicLens administrator console",
  robots: { index: false, follow: false },
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}

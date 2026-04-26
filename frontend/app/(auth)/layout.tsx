import Link from "next/link";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 bg-background">
      <Link href="/" className="mb-8 font-serif text-3xl tracking-tight text-foreground hover:opacity-80 transition-opacity">
        Clarus
      </Link>
      {children}
    </div>
  );
}

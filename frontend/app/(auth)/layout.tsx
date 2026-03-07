import Link from "next/link";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <Link href="/" className="mb-8 font-serif text-3xl tracking-tight">
        Clarus
      </Link>
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8">
        {children}
      </div>
    </div>
  );
}

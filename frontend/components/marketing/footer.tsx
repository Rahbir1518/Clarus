import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto max-w-7xl px-6 py-14">
        <div className="flex flex-col justify-between gap-10 md:flex-row">
          {/* Left */}
          <div>
            <span className="font-serif text-xl tracking-tight">Clarus</span>
            <p className="mt-3 text-sm text-muted-foreground">
              Intelligent clinical workflow automation
            </p>
          </div>

          {/* Right — link columns */}
          <div className="flex gap-16">
            <div>
              <p className="text-sm font-medium">Product</p>
              <div className="mt-3 flex flex-col gap-2">
                <Link
                  href="/features"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Features
                </Link>
                <Link
                  href="/pricing"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Pricing
                </Link>
                <Link
                  href="/contact"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Contact
                </Link>
              </div>
            </div>
            <div>
              <p className="text-sm font-medium">Legal</p>
              <div className="mt-3 flex flex-col gap-2">
                <Link
                  href="#"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Privacy
                </Link>
                <Link
                  href="#"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Terms
                </Link>
                <Link
                  href="#"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  HIPAA
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-12 border-t border-border pt-6 text-xs text-muted-foreground/60">
          &copy; {new Date().getFullYear()} Clarus Inc.
        </div>
      </div>
    </footer>
  );
}

"use client";

import Link from "next/link";
import Image from "next/image";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Menu, X, ArrowUpRight } from "lucide-react";

const navLinks = [
  { href: "/about", label: "About" },
  { href: "/features", label: "Product" },
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Contact" },
];

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY >= 50);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const collapsed = scrolled;

  return (
    <header
      className={`fixed top-0 z-50 w-full transition-all duration-500 ${
        collapsed
          ? "bg-background/80 backdrop-blur-xl md:bg-transparent md:backdrop-blur-none"
          : "bg-background/80 backdrop-blur-xl"
      }`}
    >
      {/* Single morphing nav */}
      <nav
        className={`mx-auto flex items-center justify-between border border-transparent transition-all duration-500 h-20 max-w-7xl rounded-none px-6 ${
          collapsed
            ? "md:max-w-2xl md:h-12 md:rounded-full md:px-4 md:border-border/50 md:bg-background/90 md:shadow-lg md:backdrop-blur-xl md:mt-3"
            : "md:bg-transparent md:shadow-none md:backdrop-blur-none md:mt-0"
        }`}
      >
        {/* Logo — always visible, shrinks when collapsed */}
        <Link
          href="/"
          className={`flex items-center gap-2 font-serif tracking-tight text-foreground transition-all duration-500 text-2xl ${collapsed ? "md:text-lg" : ""}`}
        >
          <Image
            src="/assets/Clarus.png"
            alt="Clarus"
            width={36}
            height={36}
            className={`transition-all duration-500 h-9 w-9 ${collapsed ? "md:h-6 md:w-6" : ""}`}
          />
          Clarus
        </Link>

        {/* Desktop nav links */}
        <div
          className={`hidden items-center md:flex transition-all duration-500 ${
            collapsed ? "gap-1" : "gap-8"
          }`}
        >
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm transition-all duration-500 ${
                collapsed
                  ? pathname === link.href
                    ? "rounded-full bg-foreground px-4 py-1.5 text-background"
                    : "rounded-full px-4 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {link.label}
            </Link>
          ))}

          <Link
            href="/signIn"
            className="inline-flex items-center gap-1.5 rounded-full bg-foreground px-4 py-1.5 text-sm font-medium text-background transition-opacity hover:opacity-80"
          >
            Log In
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        {/* Mobile menu button */}
        <button
          className="inline-flex items-center justify-center rounded-lg p-2 text-foreground md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? (
            <X className="h-5 w-5" />
          ) : (
            <Menu className="h-5 w-5" />
          )}
        </button>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-border bg-background px-6 pb-6 pt-4 md:hidden">
          <div className="flex flex-col gap-4">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-2 border-t border-border pt-4">
              <Link
                href="/signIn"
                className="inline-flex items-center gap-1.5 rounded-full bg-foreground px-4 py-2 text-sm font-medium text-background"
                onClick={() => setMobileOpen(false)}
              >
                Log In
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

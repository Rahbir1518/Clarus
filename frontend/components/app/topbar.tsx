"use client";

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-xl">
      <div />
      <div className="flex items-center gap-4">
        <div className="h-8 w-8 rounded-full bg-muted" />
      </div>
    </header>
  );
}

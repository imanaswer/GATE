/**
 * The desktop shell every page wears.
 *
 * The product is one macOS desk: a menu bar across the top, content sitting in
 * windows with traffic lights and a caption underneath. Extracted from the
 * landing page so the rest of the product cannot drift away from it.
 *
 * Windows do NOT drag by default. The landing scatters them and invites you to
 * pick them up; anywhere else a card that slides out from under the cursor is a
 * defect, so `drag` is opt-in and only the landing passes it.
 */
import Image from "next/image";
import type { ReactNode } from "react";

/** The GATE wordmark, sized by the caller. Menu bars want it small; the hero wants it huge. */
export function Wordmark({ className = "h-5 w-auto" }: { className?: string }) {
  return <Image src="/gate-wordmark.png" alt="GATE" width={904} height={293} priority className={className} />;
}

/** macOS menu bar. Functional pages put their own controls in `right`. */
export function MenuBar({
  left,
  center,
  right,
}: {
  left?: ReactNode;
  center?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <nav className="relative z-30 flex items-center justify-between gap-4 border-b border-line/70 bg-surface/70 px-4 py-2 text-sm backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-center gap-4">{left}</div>
      {center && (
        <div className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 sm:block">
          {center}
        </div>
      )}
      <div className="flex shrink-0 items-center gap-3 text-muted">{right}</div>
    </nav>
  );
}

/** The three traffic lights. Decorative — they close nothing. */
export function TrafficLights() {
  return (
    <div className="flex items-center gap-1.5 border-b border-line/70 px-3 py-2">
      <span className="size-2.5 rounded-full bg-[#ff5f57]" />
      <span className="size-2.5 rounded-full bg-[#febc2e]" />
      <span className="size-2.5 rounded-full bg-[#28c840]" />
      <span className="ml-auto text-[10px] text-muted" aria-hidden="true">
        ×
      </span>
    </div>
  );
}

/**
 * A window: chrome, content, and the filename caption that sits under it on the
 * desk. `caption` is decorative labelling, so it is hidden from screen readers
 * unless it carries meaning the content does not.
 */
export function Win({
  caption,
  children,
  className = "",
  bodyClassName = "",
}: {
  caption?: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div className={className}>
      <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-[0_20px_50px_-24px_#00000040]">
        <TrafficLights />
        <div className={bodyClassName}>{children}</div>
      </div>
      {caption && (
        <p className="mt-2 text-center font-mono text-xs text-muted" aria-hidden="true">
          {caption}
        </p>
      )}
    </div>
  );
}

/**
 * Page shell: menu bar, then centred content. Deliberately does NOT add its own
 * min-height flex layer — `body` is already `min-h-full flex flex-col`, and a
 * second full-height flex ancestor stops the arena's sticky header sticking.
 */
export function Desk({
  children,
  width = "max-w-lg",
  right,
}: {
  children: ReactNode;
  width?: string;
  right?: ReactNode;
}) {
  return (
    <>
      <MenuBar
        left={<Wordmark />}
        center={
          <span aria-hidden="true" className="font-mono text-base text-muted">
            ^ω^
          </span>
        }
        right={right ?? <span className="hidden sm:inline">by G-TEC EDUCATION</span>}
      />
      <main className="flex flex-1 justify-center px-4 py-10 sm:px-6 sm:py-14">
        <div className={`w-full ${width}`}>{children}</div>
      </main>
    </>
  );
}

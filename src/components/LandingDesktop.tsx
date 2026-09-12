"use client";

import { useRef, useState } from "react";
import { GoogleSignIn } from "@/components/GoogleSignIn";
import Image from "next/image";
import { MenuBar, TrafficLights, Wordmark } from "@/components/desk";

/**
 * The landing page as a desktop: the exam's real moments (a challenge, the
 * timer, a certificate) scattered as draggable windows around one wordmark.
 * Everything is positioned in percentages so it scales with the viewport, and
 * the windows are hidden below md where there is no room for a desktop.
 */
export function LandingDesktop({ next }: { next: string }) {
  return (
    <div className="desk relative flex min-h-svh flex-col overflow-hidden text-ink">
      <MenuBar
        left={<Wordmark />}
        center={<span aria-hidden="true" className="font-mono text-base text-muted">^ω^</span>}
        right={<span>by G-TEC EDUCATION</span>}
      />

      {/* The scattered desktop. Decorative and draggable, never load-bearing. */}
      {/* Above the hero (z-20) so a window dragged over the wordmark stays on top;
          the layer itself passes pointer events through, only windows catch them.
          Windows sit in the four corners and leave the middle third to the wordmark. */}
      <div className="pointer-events-none absolute inset-0 z-20 hidden md:block" aria-hidden="true">
        <Window left="4%" top="12%" width={300} caption="challenge-04.png" bob={7} rotate={-1.5}>
          <div className="p-4">
            <p className="text-[10px] text-[#8a8a86]">4 of 20 / foundation / easy</p>
            <p className="mt-1 text-sm font-semibold">What does this print?</p>
            <pre className="mt-2 rounded-md bg-[#f1f1ee] p-2 font-mono text-[11px] leading-snug">
              {"const a = [1, 2, 3]\nconst b = a\nb.push(4)\nconsole.log(a.length)"}
            </pre>
            <ul className="mt-2 space-y-1 text-xs">
              {["4", "3", "It throws", "undefined"].map((o, i) => (
                <li
                  key={o}
                  className={`flex items-center gap-2 rounded-md px-2 py-1 ${
                    i === 0 ? "bg-[#004282] text-white" : "bg-surface-2"
                  }`}
                >
                  <span className="font-mono text-[10px]">{"ABCD"[i]}</span> {o}
                </li>
              ))}
            </ul>
          </div>
        </Window>

        <Window left="10%" top="64%" width={230} caption="timer.app" bob={5} rotate={1}>
          <div className="p-4 text-center">
            <p className="font-mono text-4xl font-bold tracking-tight">12:22</p>
            <div className="mt-3 flex gap-1">
              {[100, 60, 0].map((w, i) => (
                <div key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-[#ececea]">
                  <div className="h-full bg-[#004282]" style={{ width: `${w}%` }} />
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] text-[#8a8a86]">problem solver · 11 of 20</p>
          </div>
        </Window>

        <Window left="74%" top="10%" width={320} caption="certificate.pdf" bob={8} rotate={1.5}>
          <div className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-[10px] tracking-widest text-accent-soft">CERTIFICATE</p>
                <p className="mt-1 text-lg font-bold leading-tight">GATE 2026</p>
                <p className="mt-1 text-xs text-muted">Mathematics · 17 / 20</p>
              </div>
              <span className="text-3xl">🎓</span>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-dashed border-line pt-3">
              <span className="font-mono text-[10px] text-[#8a8a86]">GT26-8F3K-2Q</span>
              <span className="rounded-full bg-[#e6f7ec] px-2 py-0.5 text-[10px] font-medium text-[#137a3a]">
                ✓ verified
              </span>
            </div>
          </div>
        </Window>

        <Window left="79%" top="58%" width={220} caption="result.png" bob={9} rotate={-1}>
          <div className="p-4">
            <p className="text-[10px] text-[#8a8a86]">your score</p>
            <p className="mt-1 text-5xl font-bold tracking-tighter">
              17<span className="text-lg text-[#8a8a86]">/20</span>
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#ececea]">
              <div className="h-full w-[86%] bg-[#e8000f]" />
            </div>
            <p className="mt-2 text-[10px] text-[#8a8a86]">top 12% this week</p>
          </div>
        </Window>

        <Window left="73%" top="36%" width={210} caption="verify.html" bob={6} rotate={-1}>
          <div className="flex items-center gap-3 p-4">
            <Qr />
            <div className="min-w-0">
              <span className="rounded-full bg-[#e6f7ec] px-2 py-0.5 text-[10px] font-medium text-[#137a3a]">
                ✓ verified
              </span>
              <p className="mt-1.5 truncate text-xs font-semibold">A. Student</p>
              <p className="text-[10px] text-[#8a8a86]">Mathematics · 2026</p>
            </div>
          </div>
        </Window>

        <Note left="45%" top="8%" rotate={3}>
          <p className="font-bold">exam day ✓</p>
          <ul className="mt-1 list-disc pl-3">
            <li>60s a question</li>
            <li>answers autosave</li>
            <li>no going back</li>
          </ul>
        </Note>

        {/* Stickers and kaomoji. The "HELLO" tag is the brand red. */}
        <Sticker left="89%" top="47%" rotate={-7} />
        <Sticker left="26%" top="6%" rotate={5} navy />
        {[
          ["¯\\_(ツ)_/¯", "60%", "8%"],
          ["(¬_¬)", "30%", "82%"],
          ["{ ^-^ }", "68%", "86%"],
          ["( •̀ᴗ•́ )و", "62%", "77%"],
        ].map(([face, left, top]) => (
          <span key={face} className="absolute font-mono text-lg text-ink" style={{ left, top }}>
            {face}
          </span>
        ))}
        {[
          ["📁", "37%", "12%"],
          ["🗑️", "5%", "50%"],
          ["💾", "27%", "30%"],
          ["📱", "3%", "73%"],
          ["✏️", "21%", "55%"],
        ].map(([icon, left, top]) => (
          <span key={icon} className="absolute text-3xl" style={{ left, top }}>
            {icon}
          </span>
        ))}
      </div>

      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 pt-16 pb-28 text-center md:pb-36">
        <p className="mb-4 font-mono text-sm text-muted md:hidden" aria-hidden="true">
          ^ω^ &nbsp; ¯\_(ツ)_/¯
        </p>
        <h1 className="rise">
          <Image
            src="/gate-logo.png"
            alt="GATE — G-TEC Aptitude Test for Excellence"
            width={916}
            height={362}
            priority
            className="w-[min(88vw,560px)]"
          />
        </h1>
        <p className="rise mt-4 text-lg text-ink sm:text-2xl" style={{ animationDelay: "80ms" }}>
          20 challenges. 20 minutes. a certificate anyone can verify.
        </p>

        <div className="rise mt-8" style={{ animationDelay: "160ms" }}>
          <GoogleSignIn next={next} bare className="pill pill-primary" />
        </div>

        <ul
          className="rise mt-6 flex flex-wrap items-center justify-center gap-2 font-mono text-[11px] tracking-wide text-muted"
          style={{ animationDelay: "240ms" }}
        >
          {["100% free", "one attempt", "7 arenas", "server-timed", "verifiable"].map((t) => (
            <li key={t} className="rounded-full border border-line bg-surface/70 px-3 py-1">
              {t}
            </li>
          ))}
        </ul>
      </main>

      <Dock />
    </div>
  );
}

/** A post-it. Yellow is the one colour off-palette, because that is what a
 *  sticky note is. */
function Note({
  left,
  top,
  rotate,
  children,
}: {
  left: string;
  top: string;
  rotate: number;
  children: React.ReactNode;
}) {
  return (
    <div
      className="absolute w-44 bg-[#fff2a8] p-3 font-mono text-[11px] leading-relaxed text-ink shadow-[0_12px_28px_-14px_#00000066]"
      style={{ left, top, rotate: `${rotate}deg` }}
    >
      {children}
    </div>
  );
}

/** A QR code that scans as nothing. Finder squares in three corners are all
 *  it takes for the eye to read it as one. */
function Qr() {
  const rows = [
    "111111101", "100000101", "101110100", "101110111", "101110101",
    "100000110", "111111101", "000000011", "110101101",
  ];
  return (
    <div className="grid shrink-0 grid-cols-9 gap-px" style={{ width: 54 }}>
      {rows.join("").split("").map((bit, i) => (
        <span key={i} className={`aspect-square ${bit === "1" ? "bg-ink" : "bg-transparent"}`} />
      ))}
    </div>
  );
}

/** The seven arenas as a macOS dock. Purely a signpost: the real choice is made
 *  after sign-in, so nothing here is a link. */
function Dock() {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-6 z-20 hidden justify-center md:flex" aria-hidden="true">
      <ul className="pointer-events-auto flex items-end gap-1 rounded-2xl border border-line bg-surface/70 px-3 py-2 shadow-[0_20px_50px_-24px_#00000066] backdrop-blur">
        {[
          ["🧭", "General"],
          ["➗", "Math"],
          ["🔬", "Science"],
          ["📈", "Commerce"],
          ["💻", "Tech"],
          ["📊", "Data"],
          ["🎯", "Combined"],
        ].map(([icon, name]) => (
          <li key={name} className="group relative">
            <span className="block rounded-xl px-2 py-1 text-3xl transition-transform duration-200 group-hover:-translate-y-2 group-hover:scale-125">
              {icon}
            </span>
            <span className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-0.5 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100">
              {name}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A mac-style window you can pick up and move. Pointer capture means the
 *  drag keeps working when the cursor outruns the window. */
function Window({
  left,
  top,
  width,
  caption,
  bob,
  rotate = 0,
  children,
}: {
  left: string;
  top: string;
  width: number;
  caption: string;
  bob: number;
  rotate?: number;
  children: React.ReactNode;
}) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const origin = useRef({ x: 0, y: 0, px: 0, py: 0 });

  return (
    <div
      className={`pointer-events-auto absolute select-none ${dragging ? "z-30" : "z-0"}`}
      style={{ left, top, width, translate: `${pos.x}px ${pos.y}px`, rotate: `${rotate}deg`, touchAction: "none" }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        origin.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y };
        setDragging(true);
      }}
      onPointerMove={(e) => {
        if (!dragging) return;
        const o = origin.current;
        setPos({ x: o.px + e.clientX - o.x, y: o.py + e.clientY - o.y });
      }}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
    >
      <div
        className={`bob overflow-hidden rounded-xl border border-line bg-surface shadow-[0_20px_50px_-24px_#00000066] transition-[transform,box-shadow] duration-200 ${
          dragging
            ? "cursor-grabbing scale-[1.03] shadow-[0_30px_60px_-20px_#00000080]"
            : "cursor-grab hover:scale-[1.02]"
        }`}
        style={{ animationDuration: `${bob}s` }}
      >
        <TrafficLights />
        {children}
      </div>
      <p className="mt-2 text-center text-xs text-[#8a8a86]">{caption}</p>
    </div>
  );
}

function Sticker({
  left,
  top,
  rotate,
  navy,
}: {
  left: string;
  top: string;
  rotate: number;
  navy?: boolean;
}) {
  const bg = navy ? "#004282" : "#e8000f";
  return (
    <div
      className="absolute w-28 overflow-hidden rounded-md bg-surface text-center shadow-[0_10px_24px_-12px_#00000066]"
      style={{ left, top, rotate: `${rotate}deg` }}
    >
      <div className="px-2 pt-1.5 pb-1 text-[9px] font-bold tracking-wide text-white" style={{ background: bg }}>
        HELLO
        <span className="block text-[6px] font-normal">my name is</span>
      </div>
      <p className="py-2 font-mono text-sm tracking-tight">GATE</p>
      <div className="h-1.5" style={{ background: bg }} />
    </div>
  );
}

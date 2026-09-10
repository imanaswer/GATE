"use client";

import { useRef, useState } from "react";
import { GoogleSignIn } from "@/components/GoogleSignIn";

/**
 * The landing page as a desktop: the exam's real moments (a challenge, the
 * timer, a certificate) scattered as draggable windows around one wordmark.
 * Everything is positioned in percentages so it scales with the viewport, and
 * the windows are hidden below md where there is no room for a desktop.
 */
export function LandingDesktop({ next }: { next: string }) {
  return (
    <div className="desk relative flex min-h-svh flex-col overflow-hidden text-[#121212]">
      <nav className="relative z-20 flex items-center justify-between px-5 py-4 text-sm sm:px-8">
        <span className="font-semibold">tech arena</span>
        <span aria-hidden="true" className="hidden font-mono text-lg sm:block">
          ^ω^
        </span>
        <span className="text-[#6b6b68]">by G-TEC Education</span>
      </nav>

      {/* The scattered desktop. Decorative and draggable, never load-bearing. */}
      {/* Above the hero (z-20) so a window dragged over the wordmark stays on top;
          the layer itself passes pointer events through, only windows catch them. */}
      <div className="pointer-events-none absolute inset-0 z-20 hidden md:block" aria-hidden="true">
        <Window left="3%" top="16%" width={300} caption="challenge-04.png" bob={7}>
          <div className="p-4">
            <p className="text-[10px] text-[#8a8a86]">4 of 15 / foundation / easy</p>
            <p className="mt-1 text-sm font-semibold">What does this print?</p>
            <pre className="mt-2 rounded-md bg-[#f1f1ee] p-2 font-mono text-[11px] leading-snug">
              {"const a = [1, 2, 3]\nconst b = a\nb.push(4)\nconsole.log(a.length)"}
            </pre>
            <ul className="mt-2 space-y-1 text-xs">
              {["4", "3", "It throws", "undefined"].map((o, i) => (
                <li
                  key={o}
                  className={`flex items-center gap-2 rounded-md px-2 py-1 ${
                    i === 0 ? "bg-[#004282] text-white" : "bg-[#f7f7f5]"
                  }`}
                >
                  <span className="font-mono text-[10px]">{"ABCD"[i]}</span> {o}
                </li>
              ))}
            </ul>
          </div>
        </Window>

        <Window left="36%" top="5%" width={230} caption="timer.app" bob={5}>
          <div className="p-4 text-center">
            <p className="font-mono text-4xl font-bold tracking-tight">12:22</p>
            <div className="mt-3 flex gap-1">
              {[100, 60, 0].map((w, i) => (
                <div key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-[#ececea]">
                  <div className="h-full bg-[#004282]" style={{ width: `${w}%` }} />
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] text-[#8a8a86]">problem solver · 8 of 15</p>
          </div>
        </Window>

        <Window left="72%" top="14%" width={320} caption="certificate.pdf" bob={8}>
          <div className="p-5">
            <p className="font-mono text-[10px] tracking-widest text-[#e8000f]">CERTIFICATE</p>
            <p className="mt-1 text-lg font-bold leading-tight">Tech Arena 2026</p>
            <p className="mt-1 text-xs text-[#6b6b68]">Mathematics · 13 / 15</p>
            <div className="mt-4 flex items-center justify-between border-t border-dashed border-[#d9d9d6] pt-3">
              <span className="font-mono text-[10px] text-[#8a8a86]">TA26-8F3K-2Q</span>
              <span className="rounded-full bg-[#e6f7ec] px-2 py-0.5 text-[10px] font-medium text-[#137a3a]">
                ✓ verified
              </span>
            </div>
          </div>
        </Window>

        <Window left="6%" top="62%" width={270} caption="arenas.txt" bob={6}>
          <ul className="grid grid-cols-2 gap-1.5 p-3 text-xs">
            {[
              ["🧭", "General"],
              ["➗", "Math"],
              ["🔬", "Science"],
              ["📈", "Commerce"],
              ["💻", "Tech"],
              ["📊", "Data"],
              ["🎯", "Combined"],
            ].map(([icon, name]) => (
              <li key={name} className="flex items-center gap-2 rounded-md bg-[#f7f7f5] px-2 py-1.5">
                <span>{icon}</span> {name}
              </li>
            ))}
          </ul>
        </Window>

        <Window left="78%" top="60%" width={220} caption="result.png" bob={9}>
          <div className="p-4">
            <p className="text-[10px] text-[#8a8a86]">your score</p>
            <p className="mt-1 text-5xl font-bold tracking-tighter">
              13<span className="text-lg text-[#8a8a86]">/15</span>
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#ececea]">
              <div className="h-full w-[86%] bg-[#e8000f]" />
            </div>
          </div>
        </Window>

        {/* Stickers and kaomoji. The "HELLO" tag is the brand red. */}
        <Sticker left="86%" top="40%" rotate={-7} />
        <Sticker left="24%" top="7%" rotate={5} navy />
        {[
          ["¯\\_(ツ)_/¯", "56%", "22%"],
          ["(¬_¬)", "27%", "70%"],
          ["{ ^-^ }", "84%", "82%"],
          ["( •̀ᴗ•́ )و", "30%", "56%"],
        ].map(([face, left, top]) => (
          <span
            key={face}
            className="absolute font-mono text-lg text-[#333]"
            style={{ left, top }}
          >
            {face}
          </span>
        ))}
        {[
          ["📁", "31%", "24%"],
          ["🗑️", "26%", "48%"],
          ["💾", "60%", "9%"],
          ["📱", "15%", "88%"],
          ["🎓", "70%", "6%"],
        ].map(([icon, left, top]) => (
          <span key={icon} className="absolute text-3xl" style={{ left, top }}>
            {icon}
          </span>
        ))}
      </div>

      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 pt-20 pb-16 text-center">
        <p className="mb-4 font-mono text-sm text-[#6b6b68] md:hidden" aria-hidden="true">
          ^ω^ &nbsp; ¯\_(ツ)_/¯
        </p>
        <h1 className="rise text-6xl font-bold tracking-[-0.05em] sm:text-8xl">tech arena</h1>
        <p className="rise mt-3 text-lg text-[#333] sm:text-2xl" style={{ animationDelay: "80ms" }}>
          15 challenges. 20 minutes. a certificate anyone can verify.
        </p>

        <div
          className="rise mt-8 flex flex-col items-center gap-3 sm:flex-row"
          style={{ animationDelay: "160ms" }}
        >
          <GoogleSignIn next={next} bare className="pill pill-primary" />
          <a href="#how" className="pill pill-secondary">
            how it works
          </a>
        </div>
        <p className="rise mt-4 text-sm text-[#8a8a86]" style={{ animationDelay: "240ms" }}>
          100% free. one attempt per person.
        </p>
      </main>

      <section
        id="how"
        className="relative z-10 mx-auto mb-16 w-full max-w-3xl px-6"
      >
        <ol className="grid gap-3 rounded-3xl border border-[#e2e2df] bg-white p-4 shadow-[0_24px_60px_-30px_#00000040] sm:grid-cols-4">
          {[
            ["01", "sign in", "Google, one tap"],
            ["02", "pick an arena", "the domain you know best"],
            ["03", "15 challenges", "server timer, autosave"],
            ["04", "certificate", "issued the moment you finish"],
          ].map(([n, title, sub]) => (
            <li key={n} className="rounded-2xl bg-[#f7f7f5] p-4 transition-transform duration-200 hover:-translate-y-1">
              <span className="font-mono text-[10px] text-[#e8000f]">{n}</span>
              <p className="mt-1 font-semibold">{title}</p>
              <p className="text-xs text-[#6b6b68]">{sub}</p>
            </li>
          ))}
        </ol>
      </section>
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
  children,
}: {
  left: string;
  top: string;
  width: number;
  caption: string;
  bob: number;
  children: React.ReactNode;
}) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const origin = useRef({ x: 0, y: 0, px: 0, py: 0 });

  return (
    <div
      className={`pointer-events-auto absolute select-none ${dragging ? "z-30" : "z-0"}`}
      style={{ left, top, width, translate: `${pos.x}px ${pos.y}px`, touchAction: "none" }}
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
        className={`bob rounded-xl border border-[#d9d9d6] bg-white shadow-[0_20px_50px_-24px_#00000066] transition-[transform,box-shadow] duration-200 ${
          dragging
            ? "cursor-grabbing scale-[1.03] shadow-[0_30px_60px_-20px_#00000080]"
            : "cursor-grab hover:scale-[1.02]"
        }`}
        style={{ animationDuration: `${bob}s` }}
      >
        <div className="flex items-center gap-1.5 border-b border-[#ececea] px-3 py-2">
          <span className="size-2.5 rounded-full bg-[#ff5f57]" />
          <span className="size-2.5 rounded-full bg-[#febc2e]" />
          <span className="size-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-auto text-[10px] text-[#b5b5b1]">×</span>
        </div>
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
      className="absolute w-28 overflow-hidden rounded-md bg-white text-center shadow-[0_10px_24px_-12px_#00000066]"
      style={{ left, top, rotate: `${rotate}deg` }}
    >
      <div className="px-2 pt-1.5 pb-1 text-[9px] font-bold tracking-wide text-white" style={{ background: bg }}>
        HELLO
        <span className="block text-[6px] font-normal">my name is</span>
      </div>
      <p className="py-2 font-mono text-sm tracking-tight">tech arena</p>
      <div className="h-1.5" style={{ background: bg }} />
    </div>
  );
}

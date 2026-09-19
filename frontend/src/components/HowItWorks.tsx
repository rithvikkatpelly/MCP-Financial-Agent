import type { ReactNode } from "react";

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const STEPS: { title: string; text: string; icon: ReactNode }[] = [
  {
    title: "Search in plain words",
    text: "Type “core inflation” or “jobless rate”. We match it to the right data series — no IDs to memorise.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4.5 4.5" />
      </svg>
    ),
  },
  {
    title: "Chart it",
    text: "Pick a time range and see the trend, the latest reading and how far it has moved.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M4 19V5M4 19h16" />
        <path d="m8 15 3-4 3 2 4-6" />
      </svg>
    ),
  },
  {
    title: "Compare",
    text: "Overlay up to four indicators. Different units? We rebase them to 100 so the shapes line up.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M3 16c3-8 6-8 9-2s6 2 9-6" />
        <path d="M3 9c3 6 6 6 9 1s6-1 9 5" opacity=".55" />
      </svg>
    ),
  },
  {
    title: "Trust what you see",
    text: "Inputs are validated, responses are size-capped, and provider notes are shown as quotes — never as instructions.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z" />
        <path d="m9 12 2.2 2.2L15.5 10" />
      </svg>
    ),
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="section" aria-labelledby="how-title">
      <h2 id="how-title" className="section-title center">
        From question to chart in <em>four steps</em>
      </h2>
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <div className="step-icon">{s.icon}</div>
            <span className="mono muted">STEP {i + 1}</span>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

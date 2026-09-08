function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function today(): string {
  return iso(new Date());
}

export function yearsAgo(n: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - n);
  return iso(d);
}

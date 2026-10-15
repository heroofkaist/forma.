export type AgeBand = "under_13" | "13_to_17" | "18_or_over";
export function ageBand(age: string): AgeBand | null {
  if (!/^\d{1,3}$/.test(age)) return null;
  const value = Number(age);
  if (!Number.isSafeInteger(value) || value < 0 || value > 120) return null;
  return value < 13 ? "under_13" : value < 18 ? "13_to_17" : "18_or_over";
}
export function ageLabel(age: string): string {
  if (ageBand(age) === null) return "Выберите возраст";
  const number = Number(age), last = number % 10, tens = number % 100;
  return `${number} ${tens >= 11 && tens <= 14 ? "лет" : last === 1 ? "год" : last >= 2 && last <= 4 ? "года" : "лет"}`;
}

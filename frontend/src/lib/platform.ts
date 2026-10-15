import { requestError } from "./presentation";
import { API_URL, authenticatedFetch } from "./api";
export class PlatformError extends Error {
  constructor(public status: number, public detail: unknown) { super(requestError(status, detail)); this.name = "PlatformError"; }
}
export async function platformRequest<T = { message: string }>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await authenticatedFetch(`${API_URL}${path}`, body === undefined ? { method: method ?? "GET" } : {
    method: method ?? "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new PlatformError(response.status, detail);
  }
  return data as T;
}

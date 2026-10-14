import { API_URL, authenticatedFetch } from "./api";
export async function platformRequest<T = { message: string }>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await authenticatedFetch(`${API_URL}${path}`, body === undefined ? { method: method ?? "GET" } : {
    method: method ?? "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item: {msg?: string}) => item.msg).join("; ") : `Request failed (${response.status}).`);
  }
  return data as T;
}

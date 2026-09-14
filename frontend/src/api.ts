export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: { "X-Brainifly-Local": "1", ...init.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((issue: {loc?:string[];msg?:string})=>`${issue.loc?.slice(1).join(".") || "Settings"}: ${issue.msg || "Invalid value"}`).join("\n") : `HTTP ${response.status}`);
  }
  return response.json();
}
export const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

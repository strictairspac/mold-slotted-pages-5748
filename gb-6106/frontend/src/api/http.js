import { clearSession, session } from "../stores/session.js";

export async function request(path, {method = "GET", data, raw = false, signal, headers: extraHeaders} = {}) {
  const headers = new Headers(extraHeaders || {});
  const current = session();
  if (current) headers.set("Authorization", `Bearer ${current.token}`);
  if (data !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {method, headers, signal, body: JSON.stringify(data)});
  if (response.ok) return raw ? response : response.json();
  const error = await response.json().catch(() => ({}));
  if (response.status === 401 && current) {
    clearSession();
    window.dispatchEvent(new Event("sessionchange"));
  }
  let detail = error.detail;
  if (Array.isArray(detail)) detail = detail.map(entry => entry.msg).join("；");
  else if (detail && typeof detail === "object") detail = detail.message || JSON.stringify(detail);
  else if (error.message) detail = error.message;
  const failure = new Error(detail || `请求失败（${response.status}）`);
  failure.status = response.status;
  failure.body = error;
  for (const [key, value] of Object.entries(error)) {
    if (key !== "detail" && key !== "message") failure[key] = value;
  }
  throw failure;
}

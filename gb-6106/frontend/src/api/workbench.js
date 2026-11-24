import { request } from "./http.js";

export const api = {
  config: () => request("/workbench"),
  login: data => request("/auth/login", {method: "POST", data}),
  cases: () => request("/cases"),
  createCase: data => request("/cases", {method: "POST", data}),
  runs: () => request("/runs"),
  run: (id, signal) => request(`/runs/${id}`, {signal}),
  enqueue: (id, data) => request(`/cases/${id}/runs`, {method: "POST", data}),
  continuations: () => request("/continuations"),
  continuation: id => request(`/continuations/${id}`),
  retryContinuation: id => request(`/continuations/${id}/retry`, {method: "POST"}),
  continueRun: (id, data, idempotencyKey) => request(`/runs/${id}/continuations`, {
    method: "POST",
    data,
    headers: idempotencyKey ? {"Idempotency-Key": idempotencyKey} : undefined,
  }),
  continueDraft: (id, data, idempotencyKey) => request(`/drafts/${id}/continuations`, {
    method: "POST",
    data,
    headers: idempotencyKey ? {"Idempotency-Key": idempotencyKey} : undefined,
  }),
  continuationExport: id => request(`/continuations/${id}/export`, {raw: true}),
  review: id => request(`/runs/${id}/review`),
  submitReview: (id, data) => request(`/runs/${id}/review`, {method: "POST", data}),
  export: id => request(`/runs/${id}/export`, {raw: true}),
  audit: () => request("/audit", {signal: AbortSignal.timeout(5000)}),
};

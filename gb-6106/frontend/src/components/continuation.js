import { api } from "../api/workbench.js";
import { errorText, field } from "./common/fields.js";
import { section } from "./common/panel.js";
import { status } from "./common/status.js";
import { submit } from "../hooks/submit.js";
import { el } from "../utils/dom.js";
import { download } from "../utils/format.js";

function winnerLink(run) {
  const winner = run.winner_run_id || run.continuation?.winner_run_id;
  if (!winner) return null;
  return el("p", {class: "continuation-collision", role: "alert", "data-testid": "collision-winner"},
    `撞单：已报出接班批次 #${winner}。`,
    el("a", {href: `#evidence/${winner}`}, "查看接班批次"));
}

function continuationState(run) {
  if (!run) return el("p", {class: "empty"}, "续单提交后在此显示接班、退回或撞单结果。");
  const winner = run.winner_run_id || run.continuation?.winner_run_id;
  const children = [
    el("div", {class: "run-state-line"}, status(run.status), el("strong", {}, `续单批次 #${run.id}`)),
  ];
  if (run.status === "queued") {
    children.push(el("p", {"data-testid": "continuation-working"}, "续单正在整单写入；中断恢复后会从原批次继续，不会重复认领底稿。"));
  } else if (run.status === "done") {
    children.push(el("p", {}, run.result?.summary || "续单已整单写成。"));
    children.push(el("div", {class: "actions"},
      el("a", {class: "button", href: `#evidence/${run.id}`}, "查看续单证据"),
      el("button", {
        type: "button",
        "data-testid": "download-new-credential",
        onclick: async event => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            await download(await api.export(run.id), `continuation-${run.id}.json`);
          } finally {
            button.disabled = false;
          }
        },
      }, "下载新凭据")));
  } else if (run.status === "rejected" || run.status === "failed") {
    children.push(el("p", {role: "alert"}, run.failure || "有记录装不下，整单已退回；底稿和原凭据未改变。"));
    const retryError = el("p", {role: "alert"});
    const retry = el("button", {type: "button", "data-testid": "retry-continuation"}, "重试续单");
    retry.addEventListener("click", async () => {
      retry.disabled = true;
      retryError.textContent = "";
      try {
        const next = await api.retryContinuation(run.id);
        node.replaceWith(continuationState(next));
      } catch (error) {
        retry.disabled = false;
        retryError.textContent = error.message;
      }
    });
    children.push(el("div", {class: "actions"}, retry, retryError));
  } else if (run.status === "conflict") {
    children.push(el("p", {role: "alert"}, run.failure || "该底稿已有先做成的接班批次。"));
    if (winner) children.push(el("a", {class: "button", href: `#evidence/${winner}`}, `查看接班批次 #${winner}`));
  } else if (run.failure) {
    children.push(el("p", {role: "alert"}, run.failure));
  }
  const node = el("div", {class: "continuation-result", "data-run": run.id}, ...children);
  if (run.status === "queued") {
    const timer = setInterval(async () => {
      clearInterval(timer);
      try {
        const next = await api.run(run.id);
        node.replaceWith(continuationState(next));
      } catch {
        // The next manual refresh/retry can recover a transient polling error.
      }
    }, 800);
  }
  return node;
}

export function continuationSection(baseRun, user) {
  if (user?.role !== "operator") return null;
  const capacity = baseRun.parameter;
  const free = baseRun.result?.metrics?.["剩余字节"];
  const keyValue = `night-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
  const state = el("div", {class: "stack continuation-state"});
  const collision = el("div", {});
  const feedback = errorText();
  const originalButton = el("button", {type: "button", class: "quiet", "data-testid": "download-original-credential"}, "下载原交班凭据");
  originalButton.addEventListener("click", async () => {
    originalButton.disabled = true;
    feedback.textContent = "";
    try {
      await download(await api.export(baseRun.id), `handover-${baseRun.id}.json`);
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      originalButton.disabled = false;
    }
  });
  const form = el("form", {class: "continuation-form", "data-testid": "continuation-form"},
    el("p", {class: "help"}, `续单沿用底稿页容量 ${capacity} 字节${Number.isFinite(free) ? `，交班后剩余 ${free} 字节` : ""}。压实后活记录槽号照旧；撤销槽号保留且不会分配给其他履历。任一笔装不下都会整单退回。`),
    field("续单幂等键（重试不重复认领底稿）", el("input", {
      name: "idempotency_key", value: keyValue, maxlength: 128, autocomplete: "off",
    }), "同一键重试返回原续单批次；两张不同续单会在同一底稿上撞单。"),
    field("续单操作 JSON", el("textarea", {
      name: "operations", rows: 10, spellcheck: "false", required: true,
    }, JSON.stringify([
      {op: "update", key: "GM-073", note: "22:10 夜班复检合格"},
      {op: "insert", key: "GM-N01", note: "合格"},
    ], null, 2)), "默认示例适配 C4#03 的 192 字节页：先缩短补记，再压实并追加新槽；可自行改成装不下的长备注验证整单退回。"),
    collision,
    el("div", {class: "actions"},
      el("button", {type: "submit"}, "提交续单"),
      originalButton),
    feedback);

  submit(form, async values => {
    collision.replaceChildren();
    let parsed;
    try {
      parsed = JSON.parse(values.get("operations"));
    } catch {
      throw new Error("续单 JSON 无法解析，请检查括号、引号和逗号");
    }
    const payload = Array.isArray(parsed) ? {operations: parsed} : parsed;
    const key = values.get("idempotency_key")?.trim() || undefined;
    try {
      const run = await api.continueRun(baseRun.id, payload, key);
      state.replaceChildren(continuationState(run));
    } catch (error) {
      if (error.winner_run_id) collision.replaceChildren(winnerLink(error));
      throw error;
    }
  });

  return section("夜班续单 · 接续本底稿", form, state);
}

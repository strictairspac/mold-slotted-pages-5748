import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { resultTable } from "../components/common/table.js";
import { status } from "../components/common/status.js";
import { submit } from "../hooks/submit.js";
import { poll } from "../hooks/poll.js";
import { continuationSection } from "../components/continuation.js";
import { el } from "../utils/dom.js";
import { cell, download, time } from "../utils/format.js";

function reviewForm(id, saved) {
  const form = el("form", {id: "review-form"},
    field("复核意见", el("textarea", {name: "note", required: true, minlength: 3, maxlength: 500, rows: 3})),
    errorText(), el("button", {type: "submit"}, "签署复核"));
  submit(form, async values => saved(await api.submitReview(id, {note: values.get("note")})));
  return form;
}

function signature(review) {
  return el("div", {"data-testid": "reviewed", class: "signature"},
    el("strong", {}, `已签署 · ${review.actor}`), el("p", {}, review.note), el("time", {}, time(review.created_at)));
}

export async function evidencePage(config, user, route) {
  const runs = (await api.runs()).filter(item => item.status === "done");
  const run = route.id ? await api.run(route.id) : runs[0];
  if (run?.status !== "done" || !run?.result) {
    if (run && ["queued", "failed", "rejected", "conflict"].includes(run.status)) {
      const controller = new AbortController();
      if (run.status === "queued") {
        poll(async () => {
          const next = await api.run(run.id, controller.signal);
          if (next.status === "done") {
            location.reload();
            return false;
          }
          return next.status === "queued";
        }, controller.signal);
      }
      return el("div", {class: "page"},
        pageHeading(config.modules[3], run.case_title),
        section("凭据尚未开放下载",
          el("div", {class: "stack"},
            el("div", {}, status(run.status), el("strong", {}, `批次 #${run.id}`)),
            el("p", {role: run.status === "queued" ? null : "alert"},
              run.status === "queued" ? "整单写成后才会开放新凭据下载，页面会自动刷新。" : (run.failure || "该批次未完成。")),
            run.winner_run_id ? el("a", {class: "button", href: `#evidence/${run.winner_run_id}`}, `查看接班批次 #${run.winner_run_id}`) : null,
            run.base_run_id ? el("a", {href: `#evidence/${run.base_run_id}`}, "返回原交班凭据") : el("a", {href: "#evidence"}, "返回证据列表"))));
    }
    return el("div", {class: "page"},
      pageHeading(config.modules[3], null), empty("成功执行一个批次后可以查看、签核和下载证据。"),
      el("a", {href: "#runs"}, config.modules[2]));
  }

  const review = await api.review(run.id);
  const issue = errorText();
  const button = el("button", {type: "button", onclick: async () => {
    button.disabled = true;
    issue.textContent = "";
    try {
      await download(await api.export(run.id), `evidence-${run.id}.json`);
    } catch (error) {
      issue.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }}, "导出证据");
  const signing = el("div", {});
  signing.append(review ? signature(review) : user.role === "reviewer" ?
    reviewForm(run.id, data => signing.replaceChildren(signature(data))) : empty("待复核员签署。"));
  const options = el("select", {"aria-label": "选择已完成的批次", onchange: event => {
    location.hash = `evidence/${event.target.value}`;
  }}, runs.map(item => el("option", {value: item.id, selected: item.id === run.id}, `#${item.id} ${item.case_title}`)));
  return el("div", {class: "page evidence"},
    pageHeading(config.modules[3], run.case_title, button),
    issue, options,
    el("section", {class: "feature evidence-summary"}, el("div", {}, el("h2", {}, "批次判定"), el("p", {}, run.result.summary)),
      el("details", {}, el("summary", {}, "证据摘要"), el("code", {}, run.digest))),
    el("dl", {class: "metrics"}, Object.entries(run.result.metrics).map(([label, value]) =>
      el("div", {}, el("dt", {}, label), el("dd", {}, cell(value))))),
    continuationSection(run, user),
    section("业务结果明细", run.result.rows.length ? resultTable(run.result.rows) : empty("此批次无明细。")),
    section("复核签署", signing));
}

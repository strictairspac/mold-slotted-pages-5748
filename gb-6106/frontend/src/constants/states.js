export const States = Object.freeze({
  queued: "等待执行", done: "已完成", failed: "执行失败", rejected: "整单退回", conflict: "撞单",
});

export const Actions = Object.freeze({
  create_case: "登记资料", enqueue: "提交执行", done: "执行完成", failed: "执行失败", review: "复核签署",
  enqueue_continuation: "提交续单", rejected: "整单退回", conflict: "撞单报接班批次",
});

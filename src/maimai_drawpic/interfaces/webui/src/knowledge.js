(() => {
  "use strict";
  const U = window.DrawpicUI,
    { state, $, e, icon, call, buttonAction, toast } = U;
  const STATUS = { ok: "已查到", not_found: "未查到", error: "检索出错", manual: "手工词条" };
  const FIELDS = {
    name: "名称",
    aliases: "别名",
    kind: "种类",
    franchise: "所属作品",
    look: "外观",
    draw_hint: "绘图提示",
    facts: "近期事实",
  };
  let generation = 0,
    entries = new Map(),
    kinds = [],
    uploadTarget = null;
  const current = (token) => state.view === "knowledge" && token === generation;
  const split = (text, pattern) =>
    text.split(pattern).map((item) => item.trim()).filter(Boolean);
  function host(url) {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }
  function card(item) {
    const status = item.disabled
      ? '<span class="pill failed">已禁用</span>'
      : `<span class="pill ${["ok", "manual"].includes(item.status) ? "completed" : "pending"}">${e(STATUS[item.status] || item.status)}</span>`;
    const locked = item.locked_fields.length
      ? `<span class="pill" title="自动刷新不会覆盖这些字段">锁定 ${e(item.locked_fields.map((key) => FIELDS[key] || key).join("、"))}</span>`
      : "";
    const refs = item.refs
      .map(
        (ref) =>
          `<div class="source-item" title="${ref.manual ? "手工上传" : e("自动 · " + (ref.source || "网页"))}">${ref.preview ? `<img src="${e(ref.preview)}" alt="${e(item.name)} 参考图">` : ""}<button type="button" class="icon-button" data-action="drop" data-entry="${e(item.id)}" data-file="${e(ref.file)}" aria-label="删除${ref.manual ? "手工" : "自动"}参考图">×</button></div>`,
      )
      .join("");
    const sources = item.sources
      .filter((source) => /^https?:\/\//.test(source.url))
      .map(
        (source) =>
          `<a href="${e(source.url)}" target="_blank" rel="noopener noreferrer">${e(source.title || host(source.url))}</a>`,
      )
      .join(" · ");
    const meta = [
      item.status !== "manual" && item.expires_at && !item.expired ? `有效期至 ${U.date(item.expires_at)}` : "",
      item.use_count ? `用过 ${item.use_count} 次` : "",
      item.auto_image ? "" : "不自动找图",
    ].filter(Boolean);
    return `<article class="panel knowledge-card"><div class="panel-header"><div><h3>${e(item.name)}</h3><p class="hint">${e([item.franchise, item.aliases.join(" / ")].filter(Boolean).join(" · "))}</p></div><div class="actions"><span class="pill">${e(item.kind_label)}</span>${status}${item.expired && !item.disabled ? '<span class="pill pending">已过期</span>' : ""}${locked}</div></div>${item.look ? `<p><strong>外观</strong> ${e(item.look)}</p>` : '<p class="hint">还没有外观描述</p>'}${item.facts.length ? `<ul class="hint knowledge-facts">${item.facts.map((fact) => `<li>${e(fact)}</li>`).join("")}</ul>` : ""}${refs ? `<div class="source-list">${refs}</div>` : ""}${sources ? `<p class="hint">来源：${sources}</p>` : ""}${meta.length ? `<p class="hint">${e(meta.join(" · "))}</p>` : ""}<div class="actions knowledge-actions"><button type="button" class="button secondary compact" data-action="edit" data-entry="${e(item.id)}">编辑</button><button type="button" class="button secondary compact" data-action="image" data-entry="${e(item.id)}">${icon("upload")}上传参考图</button><button type="button" class="button secondary compact" data-action="refresh" data-entry="${e(item.id)}" ${item.disabled ? "disabled" : ""}>${icon("refresh")}重新检索</button><button type="button" class="button ghost compact" data-action="toggle" data-entry="${e(item.id)}">${item.disabled ? "取消禁用" : "这是群梗（禁用）"}</button><button type="button" class="button ghost compact" data-action="delete" data-entry="${e(item.id)}">删除</button></div></article>`;
  }
  function editor(item, token) {
    const value = item || {
      name: "",
      aliases: [],
      kind: "esports_team",
      franchise: "",
      look: "",
      draw_hint: "",
      facts: [],
      auto_image: true,
      locked_fields: [],
    };
    const node = U.modal(
      item ? `编辑词条：${item.name}` : "新建手工词条",
      `<form id="knowledge-form"><div class="field-row"><div class="field"><label for="kw-name">名称</label><input id="kw-name" maxlength="24" required></div><div class="field"><label for="kw-kind">种类</label><select id="kw-kind">${kinds.map((kind) => `<option value="${e(kind.value)}">${e(kind.label)}</option>`).join("")}</select></div></div><div class="field-row"><div class="field"><label for="kw-franchise">所属作品 / 赛区</label><input id="kw-franchise" maxlength="24" placeholder="例如 英雄联盟、原神"></div><div class="field"><label for="kw-aliases">别名</label><input id="kw-aliases" maxlength="300" placeholder="用逗号分隔，最多 8 个"></div></div><div class="field"><label for="kw-look">外观</label><input id="kw-look" maxlength="40" aria-describedby="kw-look-hint"><p class="hint" id="kw-look-hint">最多 40 字，只写看得见的特征：配色、标志、发型、服装。</p></div><div class="field"><label for="kw-hint">绘图提示（英文）</label><textarea id="kw-hint" rows="2" maxlength="200" placeholder="red and black team jersey with the T1 wordmark"></textarea></div><div class="field"><label for="kw-facts">近期事实</label><textarea id="kw-facts" rows="3" aria-describedby="kw-facts-hint"></textarea><p class="hint" id="kw-facts-hint">每行一条，最多 3 条，建议带日期；只用来防止画面或台词说错。</p></div><div class="field"><label class="inline-choice"><input type="checkbox" role="switch" class="toggle" id="kw-auto-image">没有参考图时自动找图</label></div>${item ? `<fieldset class="field"><legend>锁定字段</legend><div class="choice-list">${Object.entries(FIELDS).map(([key, label]) => `<label class="choice-item"><input type="checkbox" data-lock="${key}" ${item.locked_fields.includes(key) ? "checked" : ""}>${label}</label>`).join("")}</div><p class="hint">锁定的字段自动刷新不会覆盖；这次改过的字段保存时会自动锁定。</p></fieldset>` : ""}<div class="modal-footer"><button type="button" class="button secondary" id="kw-cancel">取消</button><button type="submit" class="button" id="kw-save">保存</button></div></form>`,
    );
    $("#kw-name", node).value = value.name;
    $("#kw-kind", node).value = value.kind;
    $("#kw-franchise", node).value = value.franchise;
    $("#kw-aliases", node).value = value.aliases.join("，");
    $("#kw-look", node).value = value.look;
    $("#kw-hint", node).value = value.draw_hint;
    $("#kw-facts", node).value = value.facts.join("\n");
    $("#kw-auto-image", node).checked = value.auto_image;
    $("#kw-cancel", node).onclick = () => U.closeModal(true);
    $("#knowledge-form", node).onsubmit = (event) => {
      event.preventDefault();
      buttonAction($("#kw-save", node), async () => {
        const fields = {
          name: $("#kw-name", node).value.trim(),
          kind: $("#kw-kind", node).value,
          franchise: $("#kw-franchise", node).value.trim(),
          aliases: split($("#kw-aliases", node).value, /[,，、;；\n]+/),
          look: $("#kw-look", node).value.trim(),
          draw_hint: $("#kw-hint", node).value.trim(),
          facts: split($("#kw-facts", node).value, /\n+/),
          auto_image: $("#kw-auto-image", node).checked,
        };
        if (fields.facts.length > 3) throw new Error("近期事实最多 3 条");
        if (item) {
          fields.id = item.id;
          fields.locked_fields = [...node.querySelectorAll("[data-lock]")]
            .filter((box) => box.checked)
            .map((box) => box.dataset.lock);
        }
        await call("action", "knowledge_save", { entry_json: JSON.stringify(fields) });
        await U.closeModal(true);
        toast(item ? "词条已保存，改过的字段已锁定" : "已新建手工词条");
        if (current(token)) await U.views.knowledge();
      });
    };
  }
  async function act(button, token) {
    const { action, entry: id, file } = button.dataset;
    const item = entries.get(id);
    if (!item) return;
    if (action === "edit") return editor(item, token);
    if (action === "image") {
      uploadTarget = id;
      $("#knowledge-file").value = "";
      $("#knowledge-file").click();
      return;
    }
    return buttonAction(button, async () => {
      if (action === "refresh") {
        const result = await call("action", "knowledge_refresh", { entry_id: id });
        toast(result.message);
      } else if (action === "toggle") {
        await call("action", "knowledge_save", {
          entry_json: JSON.stringify({ id, disabled: !item.disabled }),
        });
        toast(item.disabled ? "已取消禁用" : "已禁用：这个词之后不再检索或注入");
      } else if (action === "drop") {
        await call("action", "knowledge_image_drop", { entry_id: id, file_name: file });
        toast("已删除参考图");
      } else if (action === "delete") {
        const result = await call("action", "knowledge_delete", { entry_id: id });
        toast(result.deleted ? "已删除词条" : "词条已不存在");
      }
      if (current(token)) await U.views.knowledge();
    });
  }
  U.views.knowledge = async () => {
    const token = ++generation;
    state.knowledgePage ||= 1;
    state.knowledgeSearch ??= "";
    const result = await call("query", "knowledge", {
      page: state.knowledgePage,
      search: state.knowledgeSearch,
    });
    if (!current(token)) return;
    const pages = Math.max(1, Math.ceil(result.total / result.page_size));
    if (!result.items.length && state.knowledgePage > pages) {
      state.knowledgePage = pages;
      return U.views.knowledge();
    }
    entries = new Map(result.items.map((item) => [item.id, item]));
    kinds = result.kinds;
    $("#workspace-content").innerHTML =
      `<div class="toolbar"><div class="actions"><span class="pill ${result.enabled ? "enabled" : ""}">总开关 ${result.enabled ? "已开启" : "已关闭"}</span><span class="pill ${result.online ? "enabled" : "failed"}">联网检索 ${result.online ? "可用" : "不可用"}</span><span class="pill ${result.verify_enabled ? "enabled" : ""}">画后校验 ${result.verify_enabled ? "已开启" : "已关闭"}</span><button type="button" id="knowledge-settings" class="button ghost compact">世界知识设置 ${icon("arrow")}</button></div><button type="button" id="knowledge-new" class="button compact">${icon("plus")}新建手工词条</button></div><form id="knowledge-search" class="toolbar"><div class="actions"><input id="knowledge-search-text" class="search-input" maxlength="100" placeholder="搜索名称、别名或所属作品" aria-label="搜索词条"><button type="submit" class="button secondary">搜索</button></div><span class="hint">共 ${result.total} 条 · 改过的字段会锁定，自动刷新不覆盖</span></form><input type="file" id="knowledge-file" accept="image/png,image/jpeg,image/webp" hidden><div id="knowledge-list">${result.items.length ? `<div class="card-grid knowledge-grid">${result.items.map(card).join("")}</div>` : U.empty("词条库还是空的", "开启世界知识后，画到游戏角色、战队、新产品等现实对象时会自动建词条；也可以先手工建一条，比如上传战队队标。")}</div><div class="actions pagination"><button type="button" id="knowledge-previous" class="button secondary compact" ${state.knowledgePage <= 1 ? "disabled" : ""}>上一页</button><span class="hint">第 ${state.knowledgePage} / ${pages} 页</span><button type="button" id="knowledge-next" class="button secondary compact" ${state.knowledgePage >= pages ? "disabled" : ""}>下一页</button></div>`;
    $("#knowledge-search-text").value = state.knowledgeSearch;
    U.bindSubmit($("#knowledge-search"));
    $("#knowledge-search").onsubmit = (event) => {
      event.preventDefault();
      state.knowledgeSearch = $("#knowledge-search-text").value.trim();
      state.knowledgePage = 1;
      U.views.knowledge().catch(U.error);
    };
    $("#knowledge-settings").onclick = () => {
      state.settingsSection = "knowledge";
      U.navigate("settings");
    };
    $("#knowledge-new").onclick = () => editor(null, token);
    $("#knowledge-list").onclick = (event) => {
      const button = event.target.closest("[data-action]");
      if (button) Promise.resolve(act(button, token)).catch(U.error);
    };
    $("#knowledge-file").onchange = (event) => {
      const file = event.target.files[0], id = uploadTarget;
      uploadTarget = null;
      if (!file || !id) return;
      call("upload", "knowledge_image", { entry_id: id }, file)
        .then(async () => {
          toast("已设为手工参考图，出图时优先使用");
          if (current(token)) await U.views.knowledge();
        })
        .catch(U.error);
    };
    $("#knowledge-previous").onclick = () => {
      state.knowledgePage--;
      U.views.knowledge().catch(U.error);
    };
    $("#knowledge-next").onclick = () => {
      state.knowledgePage++;
      U.views.knowledge().catch(U.error);
    };
  };
})();

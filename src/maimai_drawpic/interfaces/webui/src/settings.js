(() => {
  "use strict";
  const U = window.DrawpicUI,
    { state, $, call, buttonAction, toast } = U;
  const sections = { general: "通用配置", review: "审核配置", style: "风格预设", knowledge: "世界知识" };
  const sourceSection = (name) => ["review", "knowledge"].includes(name) ? "general" : name;
  // 通用配置里的审核、世界知识字段各自成页，其余留在通用。
  const generalSection = (key) =>
    /^(prompt|image)_review_/.test(key) ? "review" : /^world_knowledge_/.test(key) ? "knowledge" : "general";
  U.views.settings = async () => {
    let selected = Object.hasOwn(sections, state.settingsSection)
      ? state.settingsSection
      : "general";
    const revision = state.data.revision;
    const readers = {};
    const save = $("#save-settings");
    $("#workspace-content").innerHTML =
      `<div class="settings-layout"><div class="settings-tabs" role="tablist" aria-label="配置分类">${Object.entries(
        sections,
      )
        .map(
          ([name, title]) =>
            `<button id="settings-tab-${name}" class="settings-tab" data-section="${name}" role="tab" aria-controls="settings-panel-${name}">${title}</button>`,
        )
        .join(
          "",
        )}</div><section class="panel"><div class="panel-header"><div><h2 id="settings-heading"></h2><p class="hint" id="settings-description"></p></div><button type="button" id="reset-settings" class="button secondary compact">恢复当前分类默认</button></div><form id="settings-form"></form></section></div>`;
    const form = $("#settings-form");
    let requiresRefresh = false;
    function renderSection(name, values) {
      const panel = document.createElement("section");
      panel.id = `settings-panel-${name}`;
      panel.dataset.settingsPanel = name;
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", `settings-tab-${name}`);
      panel.hidden = name !== selected;
      const fields = Object.fromEntries(
        Object.entries(state.data.schema.sections[sourceSection(name)].fields)
          .filter(([key]) => name === "style" || generalSection(key) === name),
      );
      panel.innerHTML = U.forms.html(fields, values);
      const old = $(`#${panel.id}`, form);
      if (old) old.replaceWith(panel);
      else form.append(panel);
      const read = U.forms.bind(panel, fields, values);
      // 通用与审核共享持久化配置，只读取当前分类的字段，避免互相覆盖草稿。
      readers[name] = () => {
        const result = read();
        return Object.fromEntries(Object.keys(fields).map((key) => [key, result[key]]));
      };
    }
    for (const name of Object.keys(sections))
      renderSection(name, structuredClone(state.data.settings[sourceSection(name)]));
    function activate(name) {
      selected = state.settingsSection = name;
      $("#settings-heading").textContent = sections[name];
      $("#settings-description").textContent =
        name === "style"
          ? "把常用风格保存为提示词模板，三个分类的修改可一起保存。"
          : name === "review"
            ? "分别设置提示词审核和生成图片审核，使用 MaiBot 配置的审核模型。切换分类保留草稿。"
          : name === "knowledge"
            ? "画到游戏角色、战队选手、新产品等现实对象时先联网查外观与参考图，可选出图后对照校验。词条在左侧「世界知识」页管理。"
          : "切换分类会保留草稿，点击右上角“保存全部设置”统一保存。";
      for (const tab of document.querySelectorAll("[data-section]")) {
        const active = tab.dataset.section === name;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      }
      for (const panel of form.children)
        panel.hidden = panel.dataset.settingsPanel !== name;
    }
    const tabs = [...document.querySelectorAll("[data-section]")];
    for (const [index, tab] of tabs.entries()) {
      tab.onclick = () => activate(tab.dataset.section);
      tab.onkeydown = (event) => {
        let target;
        if (["ArrowRight", "ArrowDown"].includes(event.key))
          target = (index + 1) % tabs.length;
        else if (["ArrowLeft", "ArrowUp"].includes(event.key))
          target = (index + tabs.length - 1) % tabs.length;
        else if (event.key === "Home") target = 0;
        else if (event.key === "End") target = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[target].focus();
        activate(tabs[target].dataset.section);
      };
    }
    const updateNotice = () => {
      $("#settings-unsaved").hidden = !state.dirty;
    };
    form.addEventListener("input", updateNotice);
    form.addEventListener("click", updateNotice);
    $("#reset-settings").onclick = () => {
      renderSection(selected, structuredClone(state.data.defaults[sourceSection(selected)]));
      state.dirty = true;
      updateNotice();
      toast("已恢复当前分类默认值，其他分类草稿保留，保存后生效");
    };
    const submitAll = () => {
      const invalid = form.querySelector(":invalid");
      if (invalid)
        activate(
          invalid.closest("[data-settings-panel]").dataset.settingsPanel,
        );
      U.submitForm(form);
    };
    save.onclick = submitAll;
    form.addEventListener("keydown", (event) => {
      if (
        event.key === "Enter" &&
        event.target.tagName === "INPUT" &&
        !event.isComposing
      ) {
        event.preventDefault();
        submitAll();
      }
    });
    form.onsubmit = (event) => {
      event.preventDefault();
      if (form.inert || requiresRefresh) return;
      buttonAction(save, async () => {
        const all = {
          general: {
            ...state.data.settings.general, ...readers.general(), ...readers.review(), ...readers.knowledge(),
          },
          style: readers.style(),
        };
        form.inert = true;
        $("#reset-settings").disabled = true;
        try {
          const result = await call("action", "settings_save", {
            config_json: JSON.stringify(all),
            revision,
          });
          if (form.isConnected) {
            state.dirty = false;
            updateNotice();
          }
          let refreshError = null;
          try {
            await U.bootstrap();
            if (form.isConnected && state.view === "settings") await U.render();
          } catch (error) {
            refreshError = error;
            requiresRefresh = true;
          }
          U.savedNotice(result, "全部设置已保存", refreshError);
        } finally {
          if (form.isConnected) {
            form.inert = requiresRefresh;
            $("#reset-settings").disabled = requiresRefresh;
          }
        }
      }).finally(() => {
        if (form.isConnected && requiresRefresh) save.disabled = true;
      });
    };
    activate(selected);
    updateNotice();
  };
})();

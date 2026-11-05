import { View, div, svg, image } from "gpui-kit";
import { h_flex } from "gpui-base";
import { spaces, panes, run, openOverlay, theme, window, shared, layout, settings } from "herdr";

// `color` (#rgb, #rrggbb or #rrggbbaa) at `alpha` (hex 00-ff); any other color as it is.
// The same helper is in bettr-spaces (a mod cannot import another's files).
const tint = (color, alpha) => {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(color)?.[1];
  if (!hex) return color;
  return `#${hex.length === 3 ? [...hex].map(c => c + c).join("") : hex.slice(0, 6)}${alpha}`;
};

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

// The right panel's children, side by side in `panel-body` (a row). Each button shows or
// hides its own. The first open child takes what is left (weight 1) and the others are
// fixed (px), so dragging the panel's outer edge resizes only the first. Each child keeps
// its own width; WIDTH is the width of a child the person never resized.
const PANELS = ["files", "changes", "activity", "context"], WIDTH = 368;
const gap = () => find(layout(), "panel-body")?.gap ?? 0;
const same = (a, b) => a.length === b.length && a.every((id, i) => id === b[i]);

export default class Tabs extends View {
  init() {
    this.pressed = null;
    // Each space's open panels.
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem("panels") ?? "{}") ?? {}; } catch {}
    this.panels = Object.fromEntries(Object.entries(saved).filter(([, v]) => Array.isArray(v)));
    // Each child's last width, px.
    this.widths = {};
    try { this.widths = JSON.parse(localStorage.getItem("panelWidths") ?? "{}") ?? {}; } catch {}
  }

  // The open children, in PANELS order: none while the panel is hidden.
  opened(root, panel) {
    return panel && !panel.hidden ? PANELS.filter(id => { const node = find(root, id); return node && !node.hidden; }) : [];
  }

  // Show exactly `want`, and size the panel to fit them. None hides the panel.
  setOpen(want, now, panel) {
    const between = gap();
    // Record the widths the person left: fixed children have px, the first gets the rest.
    if (now.length && panel?.size?.px) {
      const root = layout();
      let rest = panel.size.px - between * (now.length - 1);
      const shared = [];
      for (const id of now) {
        const px = find(root, id)?.size?.px;
        if (px) { this.widths[id] = Math.max(200, Math.round(px)); rest -= px; } else shared.push(id);
      }
      for (const id of shared) this.widths[id] = Math.max(200, Math.round(rest / shared.length));
      try { localStorage.setItem("panelWidths", JSON.stringify(this.widths)); } catch {}
    }
    for (const id of PANELS) run(want.includes(id) ? "layout.show" : "layout.hide", { id });
    if (!want.length) { run("layout.hide", { id: "panel" }); return; }
    const width = id => this.widths[id] ?? WIDTH;
    want.forEach((id, i) => run("layout.resize", i ? { id, px: width(id) } : { id, weight: 1 }));
    run("layout.resize", { id: "panel", px: want.reduce((sum, id) => sum + width(id), 0) + between * (want.length - 1) });
    run("layout.show", { id: "panel" });
  }

  // The open panels are remembered per space: switching shows that space's choice
  // (closed if it never had one), and opening or closing one records it.
  syncPanel(space, root, panel, enabled) {
    if (!space || !panel) return;
    const now = this.opened(root, panel);
    // A panel turned off in the Layout dialog closes.
    const allowed = now.filter(id => enabled.includes(id));
    if (!same(allowed, now) && !this.pending) {
      this.pending = { want: allowed, until: Date.now() + 1000 };
      this.setOpen(allowed, now, panel);
      return;
    }
    if (space.id !== this.space) {
      const first = this.space === undefined;
      this.space = space.id; this.pending = null;
      if (!(first && !(space.id in this.panels))) {
        const want = PANELS.filter(id => (this.panels[space.id] ?? []).includes(id) && enabled.includes(id));
        if (!same(want, now)) {
          this.pending = { want, until: Date.now() + 1000 };
          this.setOpen(want, now, panel);
          return;
        }
      }
    }
    // Open children from an older layout state can all share the width: fix their sizes.
    // The first open child has no px (it takes the rest); each other one has px.
    if (!this.pending && now.some((id, i) => Boolean(find(root, id)?.size?.px) !== i > 0)) {
      this.pending = { want: now, until: Date.now() + 1000 };
      this.setOpen(now, now, panel);
      return;
    }
    // Until the restore lands (or something else won), the old state isn't a choice.
    if (this.pending) {
      if (!same(this.pending.want, now) && Date.now() < this.pending.until) return;
      this.pending = null;
    }
    if (same(this.panels[space.id] ?? [], now) && space.id in this.panels) return;
    this.panels[space.id] = now;
    try { localStorage.setItem("panels", JSON.stringify(this.panels)); } catch {}
  }

  render() {
    const t = theme();
    const space = spaces().find(p => p.active);
    const shown = space?.tabs ?? [];
    const stop = (_e, cx) => cx.stop_propagation();
    const button = (id, label, action) => div().id(id).size(26).flex_none().flex().items_center().justify_center().rounded(6).text_color(t.dim).hover(s => s.bg(t.hover).text_color(t.foreground))
      .on_mouse_down("left", stop).on_click(action).child(label);
    const ps = panes(); // Read once: each read copies every pane.
    const item = (c, i) => {
      const program = ps.find(p => p.tab === c.id && p.program?.agent)?.program ?? ps.find(p => p.tab === c.id)?.program;
      const name = /^tb\d+$/.test(c.name) ? program?.name ?? "Terminal" : c.name;
      return h_flex().id(`tab-${c.id}`).h(29).px(10).gap(7).rounded(7).items_center().flex_none().text_size(13)
        .border(1).border_color(c.active ? t.input : t.chrome).bg(c.active ? tint(t.raised, "80") : t.chrome).text_color(c.active ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover))
        .on_mouse_down("left", (e, cx) => { cx.stop_propagation(); this.pressed = i; if (e.click_count === 2) run("tab.rename", { id: c.id }); })
        .on_mouse_up("left", () => {
          const from = this.pressed; this.pressed = null;
          if (from !== null && from !== i) run("tab.move", { id: shown[from].id, index: space.tabs.findIndex(x => x.id === c.id) + 1 });
          else run("tab.select", { id: c.id });
        })
        .on_mouse_down("right", (_e, cx) => { cx.stop_propagation(); openOverlay({ mod: "menu", kind: "popup", width: 200, props: { tab: "tab", target: { id: c.id, space: space.id } } }); })
        .when(Boolean(program?.icon), el => el.child(program.tint ? svg(program.icon).size(14).text_color(t.muted) : image(program.icon).size(14)))
        .child(div().max_w(170).truncate().child(c.zoomed ? `${name} Z` : name))
        .when(c.status === "working", el => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)))
        .when(c.status === "blocked" || c.status === "done", el => el.child(div().size(6).rounded(3).bg(t[c.status])))
        .when(c.active, el => el.child(div().id(`close-${c.id}`).text_color(t.dim).on_mouse_down("left", stop).on_click((_e, cx) => { cx.stop_propagation(); run("tab.close", { id: c.id }); }).child(svg("mods/pane/close.svg").size(12))));
    };
    const root = layout(), sidebar = find(root, "sidebar"), w = window();
    // With the sidebar hidden, the tabs start after the macOS window buttons.
    const lightsPadding = w?.platform === "macos" && w.titlebar === "none" && !w.fullscreen && root?.traffic_lights
      ? Math.max(10, (root.traffic_lights[0] + 64) / settings().zoom - (sidebar?.hidden ? 0 : sidebar?.size?.px ?? 0))
      : 10;
    const panel = find(root, "panel");
    // Set in the Layout dialog (bettr-chrome/layout-config.js, same default).
    const enabled = shared("bettr.panels") ?? [...(shared("workspace.panels") ?? ["files", "changes"]), "activity", "context"];
    this.syncPanel(space, root, panel, enabled);
    const open = this.opened(root, panel);
    const panelButton = (id, label, icon) => {
      const on = open.includes(id);
      // Icon only; the name is the tooltip.
      return h_flex().id(`panel-${id}`).size(26).flex_none().items_center().justify_center().rounded(6).border(1).border_color(t.border)
        .tooltip(label).bg(on ? t.selected : t.chrome).text_color(on ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover)).on_mouse_down("left", stop)
        // Each button shows or hides its own panel; the others stay as they are.
        .on_click(() => this.setOpen(on ? open.filter(p => p !== id) : PANELS.filter(p => p === id || open.includes(p)), open, panel))
        .child(svg(icon).size(14));
    };
    return h_flex().size_full().min_w(0).px(10).pl(lightsPadding).pt(8).gap(6).items_center().bg(t.chrome)
      .on_mouse_up("left", () => { this.pressed = null; })
      .on_scroll_wheel(e => { if (Math.abs(e.delta.y) >= 1) run(e.delta.y > 0 ? "tab.prev" : "tab.next"); })
      .child(h_flex().id("tab-scroll").flex_1().min_w(0).h_full().items_center().gap(3).overflow_x_scrollbar().children(shown.map(item)))
      .child(button("tab-new", "+", () => openOverlay({ mod: "new-menu", kind: "popup", width: 250, height: 512 })))
      .when(enabled.includes("files"), el => el.child(panelButton("files", "Files", "mods/bettr-tabs/icons/list-tree.svg")))
      .when(enabled.includes("changes"), el => el.child(panelButton("changes", "Changes", "mods/bettr-tabs/icons/git-compare.svg")))
      .when(enabled.includes("activity"), el => el.child(panelButton("activity", "Activity", "mods/bettr-tabs/icons/activity.svg")))
      .when(enabled.includes("context"), el => el.child(panelButton("context", "Context", "mods/bettr-tabs/icons/gauge.svg")))
      .when(w?.buttons, el => el.child(button("minimize", w.platform === "windows" ? svg("mods/tabs/win-min.svg").size(16) : "−", () => run("window.minimize")))
        .child(button("maximize", w.platform === "windows" ? svg(`mods/tabs/${w.maximized ? "win-restore" : "win-max"}.svg`).size(16) : "□", () => run("window.maximize")))
        .child(button("close-window", w.platform === "windows" ? svg("mods/tabs/win-close.svg").size(16) : svg("mods/pane/close.svg").size(13), () => run("window.close"))));
  }
}

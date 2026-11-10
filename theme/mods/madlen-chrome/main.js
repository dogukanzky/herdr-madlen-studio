import { View, div, image, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { theme, run, props, window, shared, setShared, updates, layout } from "herdr";

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

// The sidebar's rail goes by its width, not a flag: dragging its edge narrows it too.
const narrow = () => (find(layout(), "sidebar")?.size?.px ?? Infinity) < 160;

// To the rail (on macOS wide enough for the traffic lights), or back to the width it had.
function toggleSidebar() {
  const width = find(layout(), "sidebar")?.size?.px;
  if (!narrow()) setShared("sidebar.width", width);
  // Mods edited before the rail went by width still read the flag.
  setShared("sidebar.collapsed", !narrow());
  run("layout.resize", { id: "sidebar", px: narrow() ? (shared("sidebar.width") ?? 268) : window()?.platform === "macos" ? 76 : 44 });
}

export default class WorkspaceChrome extends View {
  button(id, label, action) {
    const t = theme();
    return div().id(id).size(26).flex_none().flex().items_center().justify_center().rounded(6).text_color(t.muted).hover(s => s.bg(t.hover).text_color(t.foreground))
      .tooltip(id === "search" ? "Çalışma alanı ara" : "Kenar çubuğunu daralt / genişlet").on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click(action).child(label);
  }
  render() {
    const t = theme();
    const collapsed = narrow();
    if (props()?.section) return h_flex().size_full().px(22).items_center().bg(t.chrome).font_family("Helvetica Neue").text_size(10).font_semibold().text_color(t.dim)
      .when(!collapsed, el=>el.child(props().section));
    if (props()?.footer) {
      const row = (id, icon, label, dim, action) => h_flex().id(id).h(34).px(12).gap(7).items_center().rounded(8)
        .when(collapsed, el => el.relative().w(32).px(0).justify_center().tooltip(label))
        .text_color(dim ? t.dim : t.muted).hover(s => s.bg(t.hover).text_color(t.foreground)).cursor_pointer()
        .on_click(action).child(svg(`mods/madlen-chrome/${icon}.svg`).size(17))
        .when(!collapsed, el => el.child(label));
      const ready = div().size(6).rounded_full().bg(t.accent);
      return h_flex().size_full().items_center().justify_between().bg(t.chrome).border_t(1).border_color(t.border).px(8).pt(4).pb(8).font_family("Helvetica Neue").text_size(14)
        .when(collapsed, el => el.px(0).gap(0).justify_center())
        .child(row("settings", "settings", "Ayarlar", false, () => run("app.settings"))
          .when(Boolean(updates().app.ready), el => el.child(collapsed ? ready.absolute().top(5).right(6) : ready)))
        .child(row("machine", "plus", "Makine ekle", true, () => run("mod.open", { name: "machine-add" })));
    }
    if (collapsed) return v_flex().size_full().bg(t.chrome).items_center().justify_end().pb(5)
      .child(this.button("sidebar-expand", "»", toggleSidebar));
    return h_flex().size_full().bg(t.chrome).pl(collapsed ? 6 : 14).pr(10).gap(4).items_center().text_size(13.5)
      .when(window()?.platform === "macos" && !window()?.fullscreen && !collapsed, el => el.pl(76))
      .when(!collapsed, el => el.child(h_flex().flex_1().gap(8).items_center().child(image("mods/madlen-chrome/wordmark.svg").w(100).h(24))))

      // On the macOS rail the traffic lights fill the row; the agents list's » unfolds it.
      .when(!(collapsed && window()?.platform === "macos"), el => el.child(h_flex().id("sidebar-toggle").h(30).px(5).gap(5).items_center().rounded(6).font_family("Helvetica Neue").text_size(12).text_color(t.dim).cursor_pointer().hover(s=>s.bg(t.hover)).tooltip("Kenar çubuğunu daralt / genişlet").on_mouse_down("left", (_e,cx)=>cx.stop_propagation()).on_click(toggleSidebar).child(svg("mods/madlen-chrome/chevron-left.svg").size(13)).when(!collapsed,el=>el.child("Daralt"))));
  }
}

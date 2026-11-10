// Live workspace context. All actions use Herdr commands; no parallel state model.
import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";
import { spaces, agents, theme, settings, layout, run, openOverlay } from "herdr";

export default class MadlenHeading extends View {
  render() {
    const t = theme(), space = spaces().find(s => s.active);
    const list = agents().filter(a => a.space === space?.id);
    const indicators = [
      {id:"working", label:"Çalışan agentlar", icon:"spinner", color:t.working},
      {id:"blocked", label:"Yanıt bekleyenler", icon:"clock", color:t.blocked},
      {id:"done", label:"Yeni sonuçlar", icon:"layers", color:t.done},
    ];
    const stop = (_e, cx) => cx.stop_propagation();
    const chosen = layout()?.theme;
    const dark = typeof chosen === "string" ? chosen === "madlen-night" : Boolean(settings().dark);
    return h_flex().id("madlen-heading").size_full().min_w(0).px(12).gap(8).items_center().bg(t.canvas)
      .child(h_flex().gap(4).flex_none().items_center().children(indicators.map(g => {
        const members = list.filter(a => a.status === g.id);
        return h_flex().id(`heading-${g.id}`).h(32).px(7).gap(5).items_center().rounded(8)
          .text_color(members.length ? g.color : t.dim).text_size(12)
          .tooltip(`${g.label}: ${members.length}`)
          .on_mouse_down("left", stop)
          .when(members.length > 0, el => el.cursor_pointer().hover(s => s.bg(t.hover))
            .on_click(() => run("agent.focus", {terminal:members[0].address})))
          .child(svg(`mods/madlen-chrome/${g.icon}.svg`).size(15))
          .child(div().child(String(members.length)));
      })))
      .child(div().id("madlen-appearance").size(32).flex_none().flex().items_center().justify_center().rounded(9)
        .text_size(18).text_color(t.muted).hover(s => s.bg(t.hover)).cursor_pointer()
        .tooltip(dark ? "Açık temaya geç" : "Koyu temaya geç").on_mouse_down("left", stop)
        .on_click(() => run("layout.set", {layout:{...layout(), theme:dark ? "madlen-cream" : "madlen-night"}})).child(dark ? "☀" : "☾"))
      .child(h_flex().id("madlen-new").h(34).px(12).gap(7).flex_none().items_center().rounded(9)
        .bg(t.solid).text_color(t.solid_foreground).text_size(13).font_medium().cursor_pointer()
        .tooltip("Yeni agent veya terminal başlat").on_mouse_down("left", stop)
        .on_click(() => openOverlay({mod:"new-menu", kind:"popup", width:250, height:512}))
        .child(svg("mods/madlen-chrome/plus.svg").size(14)).child("Yeni başlat"));
  }
}

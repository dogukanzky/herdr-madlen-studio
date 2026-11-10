import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { focused, panes, terminals, shared, theme, exec, appHome, props, closeOverlay, nextCommand } from "herdr";

export default class OutputLauncher extends View {
  init(_props, cx) {
    this.target = focused()?.terminal ?? focused()?.agent ?? shared("outputs-browser.target");
    this.error = null;
    this.busy = false;
    cx.spawn(async cx => {
      for (;;) {
        const command = await nextCommand();
        if (command === "open") this.open(cx);
      }
    });
  }
  open(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.spawn(async cx => {
      try {
        const f = focused();
        const target = f?.terminal ?? f?.agent
          ?? panes().find(p => p.tab === f?.tab && p.terminal)?.terminal
          ?? terminals().find(t => t.labels?.["herdr.chat"] === f?.pane)?.address
          ?? this.target;
        if (!target) throw new Error("Önce bir ajan oturumu seç.");
        const result = await exec("python3", [`${appHome()}/mods/outputs-browser/launch.py`, "--terminal", target]);
        if (result.code !== 0) throw new Error(result.stderr || "Dosya penceresi açılamadı.");
        if (props()?.overlay) closeOverlay(props().overlay);
      } catch (error) { this.error = String(error.message ?? error); }
      this.busy = false;
      cx.notify();
    });
  }
  render() {
    const t = theme();
    if (props()?.toolbar) return h_flex().size_full().items_center().justify_center().bg(t.chrome).text_size(12).text_color(t.muted)
      .child(div().id("outputs-launch").px(10).py(6).rounded(6).cursor_pointer().hover(s => s.bg(t.hover).text_color(t.foreground))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => { cx.stop_propagation(); this.open(cx); }).child(this.busy ? "Açılıyor…" : "Çıktılar"));
    return v_flex().size_full().p(28).gap(16).items_center().justify_center().bg(t.surface).text_color(t.foreground)
      .child(div().text_size(17).font_semibold().child("Çıktılar"))
      .child(div().text_size(13).text_color(t.muted).child("Izgara, liste, arama, HTML önizleme ve dosya sürükleme yerel macOS penceresinde açılır."))
      .when(Boolean(this.error), el => el.child(div().text_color(t.blocked).child(this.error)))
      .child(div().id("native-outputs-open").px(16).py(9).rounded(7).bg(t.selected).cursor_pointer()
        .on_click((_e, cx) => this.open(cx)).child(this.busy ? "Açılıyor…" : "Dosya penceresini aç"));
  }
}

// Sidebar quota rings: Claude (5-hour + weekly) and Codex, from `quota-axi --json`.
// Each ring shows the share still LEFT; the text beside it is the time until that window resets.
import { View, div, svg, PathBuilder } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { exec, theme, layout } from "herdr";

const EVERY = 120000;               // ask quota-axi
const TICK = 30000;                 // redraw the countdowns
const PROVIDERS = [["claude", "Claude"], ["codex", "Codex"]];
const RING = 34, STROKE = 4;

// Green while there is plenty, amber when it runs low, red at the end.
const tone = left => (left <= 15 ? "#f2665c" : left <= 40 ? "#f2c14e" : "#5ed49a");

function until(iso, now) {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.parse(iso) - now) / 60000));
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  return h < 24 ? `${h}h ${min % 60}m` : `${Math.floor(h / 24)}d ${h % 24}h`;
}

const tag = w => (w.kind === "session" ? "5h" : w.kind === "weekly" ? "wk" : (w.label ?? w.id).split(" ")[0].slice(0, 5));

// A ring: a full track, then an arc from 12 o'clock clockwise for `left` percent.
function ring(left, color, track) {
  const c = RING / 2, r = (RING - STROKE) / 2;
  const trackPath = PathBuilder.stroke(STROKE).move_to(c, c - r).arc_to(r, r, 0, false, true, c, c + r).arc_to(r, r, 0, false, true, c, c - r).build();
  const p = Math.min(1, Math.max(0, left / 100));
  let arc = null;
  if (p >= 0.999) arc = trackPath;
  else if (p > 0) {
    const a = p * 2 * Math.PI;
    arc = PathBuilder.stroke(STROKE).move_to(c, c - r)
      .arc_to(r, r, 0, a > Math.PI, true, c + r * Math.sin(a), c - r * Math.cos(a)).build();
  }
  return div().relative().size(RING).flex_none()
    .child(window.paint_path(trackPath, track).absolute().top(0).left(0).size_full())
    .when(arc !== null, el => el.child(window.paint_path(arc, color).absolute().top(0).left(0).size_full()));
}

async function load() {
  let r = await exec("quota-axi", ["--provider", "claude,codex", "--json", "--max-age", "1m"]).catch(e => ({ code: -1, stderr: String(e) }));
  // Apps started from the Dock miss PATH entries from the shell's rc file (nvm): ask the person's own shell.
  if (r.code !== 0) r = await exec("sh", ["-c", 'exec "${SHELL:-/bin/sh}" -lic "quota-axi --provider claude,codex --json --max-age 1m" </dev/null']).catch(e => ({ code: -1, stderr: String(e) }));
  if (r.code !== 0) throw new Error((r.stderr || "").trim().split("\n").pop() || `exit ${r.code}`);
  const data = JSON.parse(r.stdout.slice(r.stdout.indexOf("{")));
  const out = {};
  for (const p of data.providers ?? []) {
    out[p.provider] = {
      credits: p.credits && !p.credits.unlimited ? p.credits.remaining : null,
      windows: (p.windows ?? []).filter(w => Number.isFinite(w.percentRemaining) && (w.kind === "session" || w.kind === "weekly"))
        .map(w => ({ id: w.id, kind: w.kind, label: w.label, left: Math.round(w.percentRemaining), resetsAt: w.resetsAt ?? null })),
    };
  }
  return out;
}

export default class MadlenQuota extends View {
  init(_props, cx) {
    this.data = null; this.error = null; this.at = 0;
    this.refresh(cx);
    cx.timer.every(EVERY, cx => this.refresh(cx));
    cx.timer.every(TICK, cx => cx.notify());
  }

  refresh(cx) {
    cx.spawn(async cx => {
      try { this.data = await load(); this.error = null; this.at = Date.now(); }
      catch (e) { this.error = String(e.message ?? e); }
      cx.notify();
    });
  }

  cell(w, now, t) {
    const icon = w.provider === "claude" ? "claude" : "codex";
    return h_flex().gap(5).items_center().flex_none()
      .child(div().relative().size(RING).flex_none()
        .child(ring(w.left, tone(w.left), t.border))
        .child(h_flex().absolute().top(0).left(0).size_full().items_center().justify_center()
          .text_size(10).font_semibold().text_color(t.foreground).child(`${w.left}`)))
      .child(v_flex().gap(1)
        .child(h_flex().gap(3).items_center().text_size(10).text_color(t.dim)
          .child(svg(icon === "claude" ? "icons/claude.svg" : "mods/madlen-quota/codex.svg").size(11).text_color(w.provider === "claude" ? "#d97757" : t.muted))
          .child(tag(w)))
        .child(div().text_size(11).text_color(t.muted).child(until(w.resetsAt, now))));
  }

  render() {
    const t = theme(), now = Date.now();
    const cells = PROVIDERS.flatMap(([id]) => (this.data?.[id]?.windows ?? []).map(w => ({ ...w, provider: id })));
    const find = n => n?.id === "sidebar" ? n : (n?.children ?? []).map(find).find(Boolean);
    if ((find(layout())?.size?.px ?? 320) < 160) {
      const summary = cells.map(w => `${w.provider} ${tag(w)}: %${w.left} kaldı · ${until(w.resetsAt, now)}`).join("\n");
      return h_flex().id("quota-compact").size_full().justify_center().items_center().text_size(11).text_color(t.muted)
        .tooltip(summary || (this.error ? "Kota okunamadı" : "Kota yükleniyor"))
        .child(div().px(8).py(5).rounded(8).bg(t.hover).child("Kota"));
    }
    return h_flex().size_full().px(8).gap(12).items_center().justify_center().overflow_hidden()
      .children(cells.length ? cells.map(w => this.cell(w, now, t))
        : [div().text_size(11).text_color(this.error ? "#f2665c" : t.dim).child(this.error ? "kota okunamadı" : "…")]);
  }
}

/* Offline document renderer. Markdown libraries retain their bundled licenses. */
(() => {
  'use strict';
  const content = document.getElementById('content');
  const tools = document.getElementById('tools');
  const elements = new Map();
  let kind = '', root = null, serial = 0, pending = null;
  const lower = value => String(value).toLocaleLowerCase('tr');
  const el = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; };

  function parseJSON(source) {
    let at = 0, nodes = 0;
    const fail = message => { const before = source.slice(0, at); throw new Error(`${message} · Satır ${before.split('\n').length}, sütun ${at - before.lastIndexOf('\n')}`); };
    const white = () => { while (/[ \t\r\n]/.test(source[at] || '') && at < source.length) at++; };
    function quoted() {
      const start = at++;
      while (at < source.length) {
        if (source[at] === '\\') { at += 2; continue; }
        if (source[at++] === '"') { try { return JSON.parse(source.slice(start, at)); } catch { fail('Geçersiz metin'); } }
      }
      fail('Metin kapatılmamış');
    }
    function value(depth, parents = [], key = null) {
      white(); if (++nodes > 200000 || depth > 200) fail('Belge güvenle gösterilemeyecek kadar büyük');
      const node = { id: ++serial, key, parents, children: [], type: '', value: '' };
      const c = source[at];
      if (c === '{' || c === '[') {
        node.type = c === '{' ? 'object' : 'array'; const end = c === '{' ? '}' : ']'; at++; white();
        if (source[at] !== end) for (;;) {
          white(); let childKey = node.children.length;
          if (node.type === 'object') { if (source[at] !== '"') fail('Alan adı bekleniyor'); childKey = quoted(); white(); if (source[at++] !== ':') fail('İki nokta bekleniyor'); }
          node.children.push(value(depth + 1, [...parents, node.id], childKey)); white();
          if (source[at] === end) break;
          if (source[at++] !== ',') fail('Virgül veya kapanış bekleniyor');
        }
        if (source[at++] !== end) fail('Kapanış bekleniyor');
      } else if (c === '"') { node.type = 'string'; node.value = quoted(); }
      else {
        const token = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(source.slice(at));
        if (!token) fail('Geçerli bir JSON değeri bekleniyor');
        node.value = token[0]; at += token[0].length;
        node.type = token[0] === 'null' ? 'null' : /^(true|false)$/.test(token[0]) ? 'boolean' : 'number';
      }
      return node;
    }
    const result = value(0); white(); if (at !== source.length) fail('JSON sonunda beklenmeyen içerik');
    return result;
  }
  const container = node => node.type === 'object' || node.type === 'array';
  function keyLabel(node) { return node.key === null ? '' : typeof node.key === 'number' ? `[${node.key}]` : JSON.stringify(node.key); }
  function decorate(line, node) {
    if (node.key !== null) { line.append(el('span', 'json-key', keyLabel(node)), document.createTextNode(': ')); }
    if (container(node)) {
      line.append(el('span', 'json-brace', node.type === 'object' ? '{ … }' : '[ … ]'));
      line.append(el('span', 'json-meta', `${node.children.length} ${node.type === 'object' ? 'alan' : 'öğe'}`));
    } else line.append(el('span', `json-${node.type}`, node.type === 'string' ? JSON.stringify(node.value) : node.value));
  }
  function renderNode(node, depth = 0) {
    let view;
    if (container(node)) {
      view = el('details'); const summary = el('summary'); decorate(summary, node); view.append(summary);
      let rendered = false;
      const children = () => { if (rendered) return; rendered = true; node.children.forEach(child => view.append(renderNode(child, depth + 1))); };
      view.addEventListener('toggle', () => { if (view.open) children(); });
      view.ensureChildren = children;
      if (depth < 2) { children(); view.open = true; }
    } else { view = el('div', 'json-line'); decorate(view, node); }
    view.dataset.node = String(node.id); elements.set(node.id, view); return view;
  }
  function walk(node, visit) { visit(node); node.children.forEach(child => walk(child, visit)); }
  function reveal(node) {
    for (const id of node.parents) { const parent = elements.get(id); if (parent) { parent.ensureChildren?.(); parent.open = true; } }
    return elements.get(node.id);
  }
  function expandAll() { if (root) walk(root, node => { const view = reveal(node); if (container(node) && view) { view.ensureChildren?.(); view.open = true; } }); }
  function collapseAll() { content.querySelectorAll('details').forEach(view => { view.open = false; }); }
  function clearMarks() {
    content.querySelectorAll('mark[data-find]').forEach(mark => { const parent = mark.parentNode; mark.replaceWith(document.createTextNode(mark.textContent)); parent.normalize(); });
    content.querySelectorAll('.json-match,.json-active').forEach(node => node.classList.remove('json-match', 'json-active'));
  }
  function markdownFind(query, index) {
    clearMarks(); if (!query) return { count: 0, index: 0 };
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, { acceptNode: node => node.parentElement.closest('button,script,style') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    const nodes = []; let text = '', current;
    while ((current = walker.nextNode())) { nodes.push({ node: current, start: text.length, end: text.length + current.length }); text += current.data; }
    const source = lower(text), needle = lower(query), hits = [];
    for (let at = 0; (at = source.indexOf(needle, at)) !== -1; at += needle.length) hits.push([at, at + needle.length]);
    if (!hits.length) return { count: 0, index: 0 };
    const active = ((index % hits.length) + hits.length) % hits.length;
    for (const { node, start, end } of nodes) {
      const matches = hits.map((hit, i) => ({ from: Math.max(hit[0], start) - start, to: Math.min(hit[1], end) - start, i })).filter(hit => hit.to > hit.from);
      if (!matches.length) continue;
      const fragment = document.createDocumentFragment(); let at = 0;
      for (const hit of matches) { fragment.append(document.createTextNode(node.data.slice(at, hit.from))); const mark = el('mark', hit.i === active ? 'active' : '', node.data.slice(hit.from, hit.to)); mark.dataset.find = String(hit.i); fragment.append(mark); at = hit.to; }
      fragment.append(document.createTextNode(node.data.slice(at))); node.replaceWith(fragment);
    }
    content.querySelector(`mark[data-find="${active}"]`)?.scrollIntoView({ block: 'center' });
    return { count: hits.length, index: active };
  }
  function jsonFind(query, index) {
    clearMarks(); if (!query || !root) return { count: 0, index: 0 };
    const hits = [], needle = lower(query);
    walk(root, node => { if (lower(`${keyLabel(node)} ${container(node) ? '' : node.value}`).includes(needle)) hits.push(node); });
    if (!hits.length) return { count: 0, index: 0 };
    const active = ((index % hits.length) + hits.length) % hits.length;
    const node = hits[active], view = reveal(node), line = container(node) ? view.querySelector('summary') : view;
    line.classList.add('json-active'); line.scrollIntoView({ block: 'center' });
    return { count: hits.length, index: active };
  }
  function load(payload) {
    if (document.readyState === 'loading' || !window.marked || !window.DOMPurify) { pending = payload; return; }
    kind = payload.kind; root = null; serial = 0; elements.clear(); content.replaceChildren(); document.body.dataset.kind = kind; tools.hidden = kind !== 'json';
    try {
      const text = String(payload.text).replace(/^\uFEFF/, '');
      if (kind === 'json') {
        root = parseJSON(text); const tree = el('div', 'json-tree'); tree.append(renderNode(root)); content.append(tree);
        document.getElementById('document-summary').textContent = `${payload.name} · ${root.type === 'object' ? 'Nesne' : root.type === 'array' ? 'Dizi' : 'Değer'}`;
      } else {
        content.innerHTML = DOMPurify.sanitize(marked.parse(text, { gfm: true }), { USE_PROFILES: { html: true } });
        content.querySelectorAll('pre code').forEach(code => { hljs.highlightElement(code); const button = el('button', 'copy-code', 'Kopyala'); button.addEventListener('click', () => window.webkit?.messageHandlers.reader?.postMessage({ action: 'copy', text: code.textContent })); code.parentElement.prepend(button); });
        content.querySelectorAll('img').forEach(img => { const raw = img.getAttribute('src') || ''; if (!/^(https?:|data:)/i.test(raw)) { try { const local = new URL(raw, payload.baseURL); img.src = 'outputs-asset://file' + local.pathname; } catch { img.removeAttribute('src'); } } });
      }
      document.body.dataset.ready = 'true';
    } catch (error) {
      const card = el('section', 'error'); card.append(el('h2', '', 'Belge gösterilemedi'), el('p', '', error.message), el('pre', '', String(payload.text).slice(0, 2400))); content.append(card); document.body.dataset.error = 'true';
    }
  }
  document.getElementById('expand-all').addEventListener('click', expandAll);
  document.getElementById('collapse-all').addEventListener('click', collapseAll);
  window.Reader = { load, parseJSON, find: (query, index = 0) => kind === 'json' ? jsonFind(query.trim(), index) : markdownFind(query.trim(), index), expandAll, collapseAll,
    inspect: () => ({ kind, ready: document.body.dataset.ready === 'true', error: document.body.dataset.error === 'true', collapsed: content.querySelectorAll('details:not([open])').length }) };
  window.addEventListener('DOMContentLoaded', () => { if (pending) { const payload = pending; pending = null; load(payload); } });
  if (window.__readerPayload) load(window.__readerPayload);
})();

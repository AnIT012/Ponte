const $ = id => document.getElementById(id);
const SAMPLES = JSON.parse($("samples").textContent);
const src = $("src"), hl = $("hl"), out = $("out"), state = $("state"), testBtn = $("test"), docBtn = $("doc");
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
const md = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
let py = null, timer = null, seq = 0;
// 共有リンク: #code=… に書いたものを入れる（# の後ろはサーバーに送られない）
const b64 = t => btoa(String.fromCharCode(...new TextEncoder().encode(t))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64 = t => new TextDecoder().decode(Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0)));
let shared = null;
try { const m = location.hash.match(/^#code=([\w-]+)$/); if (m) shared = unb64(m[1]); } catch (e) {}
try { src.value = shared ?? localStorage.getItem("ponte-play") ?? SAMPLES.todo; } catch (e) { src.value = shared ?? SAMPLES.todo; }

// 色分け（highlight.py と同じ決め方。Python の読み込みを待たずに、すぐ色が付く）
const HL = (() => {
  const w = s => new Set(s.split(" "));
  const HEAD = w("thing flow list match rule relate action group tbd scene look part style input words who change connect use shape");
  const CLAUSE = w("of where sort when do why in out example by ask how given at says taps gets expect adds title sub mark button lead heading empty search take top main side bottom over");
  const GUARD = w("never else tbd gone limit confirm");
  const TYPES = w("text number count money percent date monthday duration file image pdf");
  const TOKEN = /"[^"]*"|->|\||>|\[|\]|\d+(?:[:/.]\d+)*(?:\s+(?:days?|hours?|minutes?|seconds?|weeks?))?|[A-Za-z_][\p{L}\p{N}_-]*|\s+|./gu;
  const e = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const span = (c, t) => `<span class="${c}">${e(t)}</span>`;
  function line(src, inFields, states) {
    if (src.trimStart().startsWith("##")) return span("block", src);
    let code = src, comment = "";
    const k = src.indexOf(" #");
    if (k >= 0 && src.slice(0, k).slice(-1) !== '"') { code = src.slice(0, k); comment = src.slice(k + 2); }
    if (src.trimStart().startsWith("#")) return span("c", src);
    const out = []; let first = true, gb = false; const ind = src[0] === " ";
    for (const m of code.matchAll(TOKEN)) {
      const t = m[0]; let c = null;
      if (!t.trim()) { out.push(t); continue; }
      if (first && !ind && HEAD.has(t)) c = GUARD.has(t) ? "guard" : "head";
      else if (first && ind && GUARD.has(t)) c = "guard";
      else if (first && ind && inFields && /^[a-z_][\p{L}\p{N}_]*$/u.test(t)) c = "field";
      else if (first && ind && CLAUSE.has(t)) c = "clause";
      else if (t === "[" && out.length && out[out.length - 1].endsWith(">gone</span>")) { c = "guard"; gb = true; }
      else if (gb) { c = "guard"; gb = t !== "]"; }
      else if (GUARD.has(t) || t === ">") c = "guard";
      else if (["[", "]", "->", "|"].includes(t)) c = "op";
      else if (states.has(t)) c = "val";
      else if (TYPES.has(t)) c = "type";
      else if (t[0] === '"' || /^\d/.test(t)) c = "val";
      else if (/^[A-Z][\p{L}\p{N}_]*$/u.test(t)) c = "name";
      out.push(c ? span(c, t) : e(t)); first = false;
    }
    if (comment) out.push(span("c", " #" + comment));
    return out.join("");
  }
  function statesIn(src) {
    const n = new Set();
    for (const m of src.matchAll(/[\p{L}\p{N}_]+ *\[([^\]]*)\]/gu)) if (!m[0].startsWith("gone[")) m[1].split("|").forEach(x => n.add(x.trim()));
    for (const m of src.matchAll(/^\s+([\p{L}\p{N}_].*->.*)$/gmu)) (m[1].match(/[a-z_][\p{L}\p{N}_]*/gu) || []).forEach(x => n.add(x));
    return n;
  }
  return function highlight(src) {
    const states = statesIn(src), rows = []; let inF = false, rec = null;
    for (const l of src.replace(/\n+$/, "").split("\n")) {
      const ind = l.length - l.replace(/^ +/, "").length;
      if (l && l[0] !== " " && !l.startsWith("#")) inF = ["thing", "input"].includes(l.split(/\s+/)[0]);
      if (rec !== null && l.trim() && ind < rec) rec = null;
      rows.push(line(l, inF || (rec !== null && ind >= rec), states));
      const ws = l.trim().split(/\s+/);
      if (["given", "taps", "expect", "adds"].includes(ws[0]) || (ws[0] === "do" && ws[1] === "create")) rec = ind + 2;
    }
    return rows.join("\n");
  };
})();
function paintPlain() { hl.innerHTML = HL(src.value) + "\n"; }
function sync() { hl.scrollTop = src.scrollTop; hl.scrollLeft = src.scrollLeft; }
function gotoLine(n) {
  const lines = src.value.split("\n"); let pos = 0;
  for (let i = 0; i < n - 1 && i < lines.length; i++) pos += lines[i].length + 1;
  src.focus(); src.setSelectionRange(pos, pos + (lines[n - 1] || "").length);
  const lh = parseFloat(getComputedStyle(src).lineHeight) || 20; src.scrollTop = Math.max(0, (n - 4) * lh); sync();
}
function showCheck(r) {
  const errs = r.findings.filter(f => f[3]), warns = r.findings.filter(f => !f[3]);
  state.className = "state " + (errs.length ? "bad" : "good");
  state.textContent = errs.length ? `エラー ${errs.length}件` : "決めていないことはありません";
  testBtn.disabled = errs.length > 0;
  if (!r.findings.length) { out.innerHTML = '<p class="ok">check が通りました。「test」で example を動かせます。</p>'; return; }
  out.innerHTML = r.findings.map(f => `<button type="button" class="finding ${f[3] ? "err" : "warn"}" data-line="${f[1]}">
    <span class="where"><span class="badge ${f[3] ? "err" : "warn"}">${esc(f[0])}</span> ${f[1]}行目</span>
    <span class="msg">${esc(f[2])}</span>${f[4] ? `<span class="fix">直し方: ${md(f[4])}</span>` : ""}</button>`).join("");
}
async function run() {
  const my = ++seq, text = src.value;
  try { localStorage.setItem("ponte-play", text); } catch (e) {}
  paintPlain();
  if (!py) return;
  const r = JSON.parse(py.globals.get("run_check")(text));
  if (my === seq) showCheck(r);
}
src.addEventListener("input", () => { paintPlain(); clearTimeout(timer); timer = setTimeout(run, 350); });
src.addEventListener("scroll", sync);
// 見出しの行で Enter を押すと、その見出しに必須の部品の名前だけを入れる（中身は書く人が埋める）
const REQUIRED = __SKELETON__;
const PARTS = new Set(Object.values(REQUIRED).flat().map(p => p.split(" ")[0]));
function put(text, caret) {
  const s = src.selectionStart;
  src.focus();
  if (!document.execCommand || !document.execCommand("insertText", false, text)) src.setRangeText(text, s, src.selectionEnd, "end");
  if (caret != null) src.setSelectionRange(s + caret, s + caret);
  src.dispatchEvent(new Event("input"));
}
src.addEventListener("keydown", e => {
  const v = src.value, s = src.selectionStart, e0 = src.selectionEnd;
  const ls = v.lastIndexOf("\n", s - 1) + 1, le = v.indexOf("\n", s) < 0 ? v.length : v.indexOf("\n", s);
  const line = v.slice(ls, le), next = v.slice(le + 1).split("\n")[0] || "";
  if (e.key === "Enter" && !e.shiftKey && s === e0 && s === le && !next.startsWith(" ")) {
    const word = /^[a-z]+ \S/.test(line) ? line.split(" ")[0] : "";
    if (REQUIRED[word]) {
      e.preventDefault();
      const parts = REQUIRED[word].map(p => "  " + p + " ");
      put("\n" + parts.join("\n"), 1 + parts[0].length);
      return;
    }
  }
  if (e.key === "Tab" && !e.shiftKey) {
    e.preventDefault();
    const m = /^  (\S+)\s*$/.exec(next);                        // 次の行がまだ空の部品なら、そこへ移る
    if (s === le && m && (PARTS.has(m[1]) || next.trim() === "else ->")) {
      const to = le + 1 + next.length;
      src.setSelectionRange(to, to);
      return;
    }
    put("  ");
  }
});
out.addEventListener("click", e => { const b = e.target.closest("[data-line]"); if (b) gotoLine(+b.dataset.line); });
$("pick").addEventListener("change", e => { src.value = SAMPLES[e.target.value]; src.scrollTop = 0; src.dispatchEvent(new Event("input")); });
testBtn.addEventListener("click", () => {
  const r = JSON.parse(py.globals.get("run_test")(src.value));
  if (r.error) { out.innerHTML = `<p class="bad">${esc(r.error)}</p>`; return; }
  const ok = r.results.filter(x => x[2]).length, n = r.results.length;
  const head = n === 0
    ? `<p class="info-h">example はまだありません。</p><p class="info">example は書かなくてもアプリは動きます。書くと、それがそのままテストになります。</p>`
    : `<p class="${ok === n ? "ok" : "bad"}">example ${n}件中 ${ok}件通過</p>`;
  out.innerHTML = head +
    r.results.map(x => `<button type="button" class="finding ${x[2] ? "pass" : "err"}" data-line="${x[1]}"><span class="where">${x[2] ? "通過" : "失敗"} ・ ${esc(x[0])}</span>${x[3] ? `<span class="msg">${esc(x[3])}</span>` : ""}</button>`).join("") +
    (r.holes.length ? `<p class="holes">まだ example で確かめていない部分（${r.holes.length}件）</p><p class="info">エラーではありません。ここに example を足すと、この部分も確かめられます。</p>` + r.holes.map(h => `<button type="button" class="finding info-row" data-line="${h[0]}"><span class="where">${h[0]}行目</span><span class="msg">${esc(h[1])}</span></button>`).join("") : "");
});
$("share").addEventListener("click", async () => {
  const url = location.href.split("#")[0] + "#code=" + b64(src.value);
  history.replaceState(null, "", url);
  try { await navigator.clipboard.writeText(url); $("share").textContent = "コピーしました"; }
  catch (e) { $("share").textContent = "URL に入れました"; }
  setTimeout(() => { $("share").textContent = "共有"; }, 1800);
});
docBtn.addEventListener("click", () => {
  const page = py.globals.get("run_doc")(src.value);
  if (!page) { out.innerHTML = '<p class="bad">仕様を読めないため、1枚の HTML を作れません。</p>'; return; }
  const url = URL.createObjectURL(new Blob([page], { type: "text/html" }));
  window.open(url, "_blank", "noopener");
});
paintPlain();
try {
  const base = new URLSearchParams(location.search).get("pyodide") || "__PYODIDE__";
  const { loadPyodide } = await import(base + "pyodide.mjs");
  py = await loadPyodide({ indexURL: base });
  const zip = await (await fetch("ponte.zip")).arrayBuffer();
  py.unpackArchive(zip, "zip");
  py.runPython($("playpy").textContent);
  testBtn.disabled = false; docBtn.disabled = false;
  run();
} catch (e) {
  state.className = "state bad"; state.textContent = "読み込めませんでした";
  out.innerHTML = `<p class="bad">Python を読み込めませんでした: ${esc(e.message || e)}</p>`;
}

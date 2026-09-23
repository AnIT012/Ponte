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

function paintPlain() { hl.textContent = src.value + "\n"; }
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
  state.textContent = errs.length ? `止まります（${errs.length}件）` : "決めてないことなし";
  testBtn.disabled = errs.length > 0;
  if (!r.findings.length) { out.innerHTML = '<p class="ok">check が通りました。「test」で example を動かせます。</p>'; return; }
  out.innerHTML = r.findings.map(f => `<button type="button" class="finding ${f[3] ? "err" : "warn"}" data-line="${f[1]}">
    <span class="where"><span class="badge ${f[3] ? "err" : "warn"}">${esc(f[0])}</span> ${f[1]}行目</span>
    <span class="msg">${esc(f[2])}</span>${f[4] ? `<span class="fix">直し方: ${md(f[4])}</span>` : ""}</button>`).join("");
}
async function run() {
  const my = ++seq, text = src.value;
  try { localStorage.setItem("ponte-play", text); } catch (e) {}
  if (!py) { paintPlain(); return; }
  hl.innerHTML = py.globals.get("run_highlight")(text) + "\n";
  const r = JSON.parse(py.globals.get("run_check")(text));
  if (my === seq) showCheck(r);
}
src.addEventListener("input", () => { paintPlain(); if (py) hl.innerHTML = py.globals.get("run_highlight")(src.value) + "\n"; clearTimeout(timer); timer = setTimeout(run, 350); });
src.addEventListener("scroll", sync);
src.addEventListener("keydown", e => {
  if (e.key === "Tab") { e.preventDefault(); const s = src.selectionStart; src.setRangeText("  ", s, src.selectionEnd, "end"); src.dispatchEvent(new Event("input")); }
});
out.addEventListener("click", e => { const b = e.target.closest("[data-line]"); if (b) gotoLine(+b.dataset.line); });
$("pick").addEventListener("change", e => { src.value = SAMPLES[e.target.value]; src.scrollTop = 0; src.dispatchEvent(new Event("input")); });
testBtn.addEventListener("click", () => {
  const r = JSON.parse(py.globals.get("run_test")(src.value));
  if (r.error) { out.innerHTML = `<p class="bad">${esc(r.error)}</p>`; return; }
  const ok = r.results.filter(x => x[2]).length;
  out.innerHTML = `<p class="${ok === r.results.length ? "ok" : "bad"}">example ${r.results.length}件中 ${ok}件通過</p>` +
    r.results.map(x => `<button type="button" class="finding ${x[2] ? "pass" : "err"}" data-line="${x[1]}"><span class="where">${x[2] ? "通過" : "失敗"} ・ ${esc(x[0])}</span>${x[3] ? `<span class="msg">${esc(x[3])}</span>` : ""}</button>`).join("") +
    (r.holes.length ? `<p class="holes">確かめていない所（${r.holes.length}件）</p>` + r.holes.map(h => `<button type="button" class="finding warn" data-line="${h[0]}"><span class="where">${h[0]}行目</span><span class="msg">${esc(h[1])}</span></button>`).join("") : "");
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
  if (!page) { out.innerHTML = '<p class="bad">読めないので、決めごとの1枚を作れません。</p>'; return; }
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

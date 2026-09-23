// 保存した時に `ponte check --json` を流して、エラーを波線で出す（依存なし。VS Code の API だけ）。
// 設定: ponte.python（既定 "python"）。ワークスペースに ponte/ があれば、そこで動かす。
const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");

function activate(context) {
  const diags = vscode.languages.createDiagnosticCollection("ponte");
  context.subscriptions.push(diags);

  const run = doc => {
    if (doc.languageId !== "ponte" || doc.uri.scheme !== "file") return;
    const py = vscode.workspace.getConfiguration("ponte").get("python") || "python";
    const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
    const cwd = folder ? folder.uri.fsPath : path.dirname(doc.uri.fsPath);
    execFile(py, ["-m", "ponte", "check", "--json", doc.uri.fsPath], { cwd, timeout: 20000 }, (err, stdout) => {
      let out;
      try { out = JSON.parse(stdout); } catch (e) {
        // 読めない（字下げの間違いなど）ときは1行目に出す
        const msg = (stdout || (err && err.message) || "ponte check を動かせませんでした").trim();
        diags.set(doc.uri, [new vscode.Diagnostic(new vscode.Range(0, 0, 0, 1), msg, vscode.DiagnosticSeverity.Error)]);
        return;
      }
      const mine = out.findings.filter(f => path.resolve(cwd, f.file) === path.resolve(doc.uri.fsPath));
      diags.set(doc.uri, mine.map(f => {
        const line = Math.max(0, f.line - 1);
        const text = doc.lineAt(Math.min(line, doc.lineCount - 1));
        const range = new vscode.Range(line, text.firstNonWhitespaceCharacterIndex, line, text.text.length);
        const d = new vscode.Diagnostic(range, f.message + (f.fix ? `\n直し方: ${f.fix}` : ""),
          f.error ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning);
        d.code = f.code;
        d.source = "ponte";
        return d;
      }));
    });
  };

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(run),
    vscode.workspace.onDidOpenTextDocument(run),
    vscode.workspace.onDidCloseTextDocument(doc => diags.delete(doc.uri)),
  );
  vscode.workspace.textDocuments.forEach(run);
}

function deactivate() {}

module.exports = { activate, deactivate };

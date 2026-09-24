"""List every Japanese string in the source that the English catalog (ponte/i18n_en.json) must cover.

    python tools/i18n_keys.py            # print the keys that are missing from the catalog
    python tools/i18n_keys.py --add      # add them to the catalog with an empty value, for translating

server.py and forms.py are left out: what they show belongs to the app's screen, whose language
comes from the viewer (`words`), not from the command line.
"""
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "ponte", "i18n_en.json")
SKIP = {"server.py", "forms.py", "i18n.py"}
JP = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")


def keys() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "ponte", "*.py"))):
        if os.path.basename(path) in SKIP:
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if isinstance(n, ast.JoinedStr):
                t = "".join(str(v.value).replace("{", "{{").replace("}", "}}") if isinstance(v, ast.Constant) else "{}"
                            for v in n.values)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and id(n) not in inner:
                t = n.value.replace("{", "{{").replace("}", "}}")
            else:
                continue
            if JP.search(t):
                out.setdefault(t, []).append(f"{os.path.relpath(path, ROOT)}:{n.lineno}")
    return out


def main() -> int:
    cat = json.load(open(CATALOG, encoding="utf-8")) if os.path.exists(CATALOG) else {}
    missing = {k: v for k, v in keys().items() if k not in cat}
    if "--add" in sys.argv:
        cat.update({k: "" for k in missing})
        json.dump(cat, open(CATALOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        print(f"added {len(missing)}")
    else:
        for k, where in missing.items():
            print(f"{where[0]}\t{k}")
        print(f"missing {len(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

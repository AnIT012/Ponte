import os

# テストは日本語の出力で確かめる（英語の出力は tests/test_i18n.py で確かめる）
os.environ["PONTE_LANG"] = "ja"

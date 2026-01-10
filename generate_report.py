
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import compute
from pdf_report import build_pdf
from sample_payload import build_sample_payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default="", help="payload JSON dosyası yolu (opsiyonel)")
    ap.add_argument("--out", dest="out_path", default="demo_akreditasyon_raporu.pdf", help="çıktı PDF yolu")
    ap.add_argument("--dump-result", dest="dump_result", default="", help="hesap sonucunu JSON olarak kaydet (opsiyonel)")
    args = ap.parse_args()

    if args.in_path:
        payload = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    else:
        payload = build_sample_payload()

    result = compute(payload)
    out = build_pdf(result, args.out_path)

    if args.dump_result:
        Path(args.dump_result).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: PDF üretildi -> {out}")


if __name__ == "__main__":
    main()


"""
PDF Rapor Üretimi (ReportLab + Matplotlib)
- Excel'deki "ders değerlendirme raporu" hissine yakın, bölümlü çıktı üretir.
"""
from __future__ import annotations

import io
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.rl_config import TTFSearchPath

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _register_font() -> str:
    """
    Türkçe karakterler için geniş kapsamlı bir font kaydeder, yoksa varsayılanı döndürür.
    """
    try:
        TTFSearchPath.append("C:\\Windows\\Fonts")
    except Exception:
        pass
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                pdfmetrics.registerFont(TTFont("TurkishSans", str(path)))
                return "TurkishSans"
        except Exception:
            continue
    return "Helvetica"


def _bar_chart(data: List[Tuple[str, float]], title: str, xlabel: str = "", ylabel: str = "% Başarı") -> bytes:
    """
    data: [(label, value_pct), ...]
    PNG bytes döndürür.
    """
    labels = [d[0] for d in data]
    vals = [d[1] for d in data]

    fig = plt.figure(figsize=(7.2, 3.2))
    ax = fig.add_subplot(111)
    ax.bar(labels, vals)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def build_pdf(result: Dict[str, Any], out_path: str) -> str:
    base_font = _register_font()
    course = result.get("course", {})
    computed = result.get("computed", {})
    thresholds = result.get("thresholds", {"met": 70, "partially": 50})

    styles = getSampleStyleSheet()
    styles["Title"].fontName = base_font
    styles["Heading2"].fontName = base_font
    styles["BodyText"].fontName = base_font
    title_style = styles["Title"]
    h_style = styles["Heading2"]
    p_style = styles["BodyText"]

    doc = SimpleDocTemplate(out_path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []

    # Kapak
    story.append(Paragraph("Ders Değerlendirme ve Akreditasyon Raporu (Demo v2)", title_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Üretim zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M')}", p_style))
    story.append(Spacer(1, 14))

    info_rows = [
        ["Ders Kodu", course.get("course_code","")],
        ["Ders Adı", course.get("course_name","")],
        ["Program", course.get("program_name","")],
        ["Dönem", course.get("term","")],
        ["Öğretim Elemanı", course.get("instructor","")],
    ]
    t = Table(info_rows, colWidths=[120, 380])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(1,0), colors.whitesmoke),
        ("GRID", (0,0),(-1,-1), 0.25, colors.grey),
        ("FONTNAME",(0,0),(-1,-1), base_font),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BACKGROUND",(0,0),(0,-1), colors.HexColor("#f3f3f3")),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    overall = computed.get("overall", {})
    story.append(Paragraph("Genel Başarı", h_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Genel başarı (ağırlıklı): <b>%{overall.get('success_pct',0):.1f}</b> — Durum: <b>{overall.get('status','')}</b>"
        f" (Eşikler: Sağlandı≥{thresholds.get('met',70)}, Kısmen≥{thresholds.get('partially',50)})",
        p_style
    ))
    story.append(Spacer(1, 12))

    # Ölçme bileşenleri
    story.append(Paragraph("Ölçme Planı (Bileşenler)", h_style))
    story.append(Spacer(1, 6))
    comp = computed.get("assessments", {})
    comp_rows = [["Bileşen", "Ağırlık", "Ort. Puan", "Toplam Puan", "% Başarı"]]
    for cid, cs in comp.items():
        comp_rows.append([cs.get("name", cid), f"{cs.get('weight',0):.2f}", f"{cs.get('avg_points',0):.2f}",
                          f"{cs.get('max_points',0):.2f}", f"%{cs.get('success_pct',0):.1f}"])
    t = Table(comp_rows, colWidths=[160, 70, 80, 80, 70])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#e8eef7")),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # DÖÇ grafiği + tablo
    docs = computed.get("docs", {})
    doc_data = [(did, float(st.get("success_pct",0))) for did, st in docs.items()]
    doc_data_sorted = sorted(doc_data, key=lambda x: x[0])
    png = _bar_chart(doc_data_sorted, "DÖÇ Başarı Dağılımı", xlabel="DÖÇ")
    story.append(Paragraph("Ders Öğrenme Çıktıları (DÖÇ) Sonuçları", h_style))
    story.append(Spacer(1, 6))
    img = Image(io.BytesIO(png), width=480, height=220)
    story.append(img)
    story.append(Spacer(1, 8))

    doc_rows = [["DÖÇ", "Açıklama", "Ort. Puan", "Toplam Puan", "% Başarı", "Durum"]]
    for did, st in sorted(docs.items(), key=lambda kv: kv[0]):
        doc_rows.append([
            did,
            (st.get("text","")[:70] + "…") if len(st.get("text","")) > 70 else st.get("text",""),
            f"{st.get('avg_points',0):.2f}",
            f"{st.get('max_points',0):.2f}",
            f"%{st.get('success_pct',0):.1f}",
            st.get("status","")
        ])
    t = Table(doc_rows, colWidths=[40, 250, 60, 60, 55, 55])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#e8f7ee")),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),8.5),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    story.append(t)
    story.append(PageBreak())

    # PÖÇ
    pocs = computed.get("pocs", {})
    poc_data = [(pid, float(st.get("success_pct",0))) for pid, st in pocs.items()]
    poc_data_sorted = sorted(poc_data, key=lambda x: x[0])
    png = _bar_chart(poc_data_sorted, "PÖÇ Başarı Dağılımı", xlabel="PÖÇ")
    story.append(Paragraph("Program Öğrenme Çıktıları (PÖÇ) Sonuçları", h_style))
    story.append(Spacer(1, 6))
    story.append(Image(io.BytesIO(png), width=480, height=220))
    story.append(Spacer(1, 8))

    poc_rows = [["PÖÇ", "Açıklama", "% Başarı", "Durum", "Katkı Veren DÖÇ’ler (ağırlık)"]]
    for pid, st in sorted(pocs.items(), key=lambda kv: kv[0]):
        contrib = st.get("contributors", [])
        contrib_txt = ", ".join([f"{c['doc_id']}({int(c['weight'])})" for c in contrib]) if contrib else "—"
        poc_rows.append([
            pid,
            (st.get("text","")[:60] + "…") if len(st.get("text","")) > 60 else st.get("text",""),
            f"%{st.get('success_pct',0):.1f}",
            st.get("status",""),
            contrib_txt
        ])
    t = Table(poc_rows, colWidths=[45, 220, 70, 70, 125])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#fff2cc")),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),8.5),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # Bloom
    bloom = computed.get("bloom", {})
    bloom_data = [(b, float(st.get("success_pct",0))) for b, st in bloom.items()]
    bloom_data_sorted = sorted(bloom_data, key=lambda x: x[0])
    if bloom_data_sorted:
        png = _bar_chart(bloom_data_sorted, "Bloom Düzeyi Başarı Dağılımı", xlabel="Bloom")
        story.append(Paragraph("Bloom Analizi", h_style))
        story.append(Spacer(1, 6))
        story.append(Image(io.BytesIO(png), width=480, height=220))
        story.append(Spacer(1, 8))

        bloom_rows = [["Bloom", "Soru Sayısı", "Ort. Puan", "Toplam Puan", "% Başarı", "Durum"]]
        for b, st in sorted(bloom.items(), key=lambda kv: kv[0]):
            bloom_rows.append([b, str(st.get("questions",0)), f"{st.get('avg_points',0):.2f}",
                               f"{st.get('max_points',0):.2f}", f"%{st.get('success_pct',0):.1f}", st.get("status","")])
        t = Table(bloom_rows, colWidths=[120, 70, 80, 80, 70, 70])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f4cccc")),
            ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
            ("FONTSIZE",(0,0),(-1,-1),9),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
        ]))
        story.append(t)

    # PEA
    peas = computed.get("peas", {})
    if peas:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Program Eğitim Amaçları (PEA) – Dolaylı Katkı", h_style))
        story.append(Spacer(1, 6))
        pea_rows = [["PEA", "Açıklama", "İlgili PÖÇ’ler", "% Özet", "Durum"]]
        for aid, st in sorted(peas.items(), key=lambda kv: kv[0]):
            pea_rows.append([
                aid,
                (st.get("text","")[:60] + "…") if len(st.get("text","")) > 60 else st.get("text",""),
                ", ".join(st.get("pocs", [])) if st.get("pocs") else "—",
                f"%{st.get('success_pct',0):.1f}" if st.get("status","—") != "—" else "—",
                st.get("status","—")
            ])
        t = Table(pea_rows, colWidths=[45, 220, 120, 60, 60])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#d9ead3")),
            ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
            ("FONTSIZE",(0,0),(-1,-1),8.5),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
        ]))
        story.append(t)

    # Otomatik değerlendirme
    narrative = computed.get("narrative", {})
    story.append(Spacer(1, 14))
    story.append(Paragraph("Otomatik Değerlendirme ve İyileştirme Önerileri", h_style))
    story.append(Spacer(1, 6))
    sugg = narrative.get("suggestions", [])
    if not sugg:
        story.append(Paragraph("Öneri üretilemedi (veri yetersiz olabilir).", p_style))
    else:
        for s in sugg:
            story.append(Paragraph("• " + s, p_style))

    doc.build(story)
    return out_path

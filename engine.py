"""
Akreditasyon Demo v2 - Hesap Motoru
-----------------------------------
Bu motor, "ders değerlendirme raporu" mantığına uygun şekilde şunları hesaplar:

1) Not bileşenleri (Vize/Final/Ödev/Quiz/Lab...) ve ağırlıkları
2) Soru bazlı: max puan, öğrenci puanları, başarı yüzdesi
3) DÖÇ başarısı (puan bazlı): DÖÇ'ye bağlı sorulardan alınan puan / alınabilecek puan
4) PÖÇ başarısı: DÖÇ başarılarının DÖÇ→PÖÇ katkı matrisi ile ağırlıklı aktarımı
5) PEA katkısı (dolaylı): PÖÇ→PEA eşlemesi üzerinden özet
6) Bloom dağılımı: soruların Bloom düzeylerine göre puan payı ve başarı

Girdi verisi "payload" JSON formatındadır (web arayüzü ve CLI bunu kullanır).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import statistics


# -----------------------------
# Veri modelleri
# -----------------------------

@dataclass(frozen=True)
class CourseInfo:
    course_code: str
    course_name: str
    program_name: str
    term: str
    instructor: str


@dataclass(frozen=True)
class DOC:
    id: str
    text: str


@dataclass(frozen=True)
class POC:
    id: str
    text: str


@dataclass(frozen=True)
class PEA:
    id: str
    text: str


@dataclass(frozen=True)
class AssessmentComponent:
    id: str
    name: str
    weight: float  # 0..1 (örn 0.4)


@dataclass(frozen=True)
class Question:
    id: str
    component_id: str
    text: str
    doc_id: str
    bloom: str
    max_points: float


@dataclass(frozen=True)
class Student:
    id: str
    name: str


# -----------------------------
# Yardımcılar
# -----------------------------

def _safe_div(num: float, den: float) -> float:
    return (num / den) if den else 0.0


def status_by_threshold(pct, thresholds: Dict[str, float]) -> str:
    """
    thresholds örn:
      {"met": 70, "partially": 50}
    """
    if pct is None:
        pct = 0  # Güvenlik için
    met = thresholds.get("met", 70)
    partially = thresholds.get("partially", 50)
    if pct >= met:
        return "Sağlandı"
    if pct >= partially:
        return "Kısmen"
    return "Sağlanmadı"


def normalize_pct(x: float) -> float:
    """0..1 aralığını 0..100 yapar; 0..100 girdiyse de 0..100 bırakır."""
    if x <= 1.0:
        return x * 100.0
    return x


# -----------------------------
# Ana hesap fonksiyonları
# -----------------------------

def compute(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload şeması (özet):
    {
      "course": {...},
      "docs": [{"id":"D1","text":"..."}],
      "pocs": [{"id":"P1","text":"..."}],
      "peas": [{"id":"A1","text":"..."}],
      "assessments": [{"id":"C1","name":"Vize","weight":0.4}, ...],
      "questions": [{"id":"Q1","component_id":"C1","doc_id":"D1","bloom":"Uygulama","max_points":10, "text":"..."}],
      "students": [{"id":"S1","name":"..."}],
      "scores": { "S1": {"Q1": 7, "Q2": 10, ...}, "S2": {...}},
      "doc_poc_weights": { "D1": {"P1": 2, "P2": 0}, ... },  # 0..3
      "poc_pea_map": { "P1": ["A1","A2"], "P2":["A1"] },
      "thresholds": {"met":70,"partially":50},
      "grading": {"A":90,"B":80,"C":70,"D":60,"F":0}  # opsiyon
    }
    """
    thresholds = payload.get("thresholds", {"met": 70, "partially": 50})
    grading = payload.get("grading")  # opsiyon

    # Indexler
    docs = {d["id"]: d for d in payload.get("docs", [])}
    pocs = {p["id"]: p for p in payload.get("pocs", [])}
    peas = {a["id"]: a for a in payload.get("peas", [])}
    assessments = {c["id"]: c for c in payload.get("assessments", [])}
    questions = {q["id"]: q for q in payload.get("questions", [])}
    
    # Öğrencileri filtrele - GR (sınava girmeyenler) hariç tut
    all_students = {s["id"]: s for s in payload.get("students", [])}
    # Sadece sınava giren öğrenciler
    students = {sid: s for sid, s in all_students.items() 
                if s.get("status", "").upper() not in ("GR", "DZ", "GİRMEDİ")}
    # GR öğrenciler
    gr_students = {sid: s for sid, s in all_students.items() 
                   if s.get("status", "").upper() in ("GR", "DZ", "GİRMEDİ")}
    
    scores = payload.get("scores", {})  # student_id -> {question_id: score}

    # --- Soru bazlı başarı (sadece sınava giren öğrenciler)
    q_stats = {}
    for qid, q in questions.items():
        maxp = float(q.get("max_points", 0))
        vals = []
        for sid in students.keys():  # Sadece sınava girenler
            srec = scores.get(sid, {})
            if qid in srec:
                vals.append(float(srec[qid]))
            else:
                vals.append(0.0)
        avg = statistics.mean(vals) if vals else 0.0
        success = _safe_div(avg, maxp)  # 0..1
        q_stats[qid] = {
            "avg_points": avg,
            "max_points": maxp,
            "success_pct": normalize_pct(success),
            "doc_id": q.get("doc_id"),
            "bloom": q.get("bloom", ""),
            "component_id": q.get("component_id"),
        }

    # --- Bileşen bazlı başarı (puan bazlı, normalize)
    comp_stats = {}
    for cid, comp in assessments.items():
        qids = [qid for qid, q in questions.items() if q.get("component_id") == cid]
        total_max = sum(float(questions[qid].get("max_points", 0)) for qid in qids)
        # öğrencilerin toplam puanı ortalaması
        totals = []
        for sid in students.keys():
            srec = scores.get(sid, {})
            tot = sum(float(srec.get(qid, 0.0)) for qid in qids)
            totals.append(tot)
        avg_total = statistics.mean(totals) if totals else 0.0
        success = _safe_div(avg_total, total_max)  # 0..1
        comp_stats[cid] = {
            "name": comp.get("name", cid),
            "weight": float(comp.get("weight", 0)),
            "avg_points": avg_total,
            "max_points": total_max,
            "success_pct": normalize_pct(success),
        }

    # --- Ders toplam başarı (bileşen ağırlıklı)
    # her bileşenin 0..100 başarı yüzdesini ağırlıkla birleştir
    total_weight = sum(float(c.get("weight", 0)) for c in assessments.values())
    # ağırlıklar 1'e tamamlanmamışsa normalize edelim
    overall = 0.0
    for cid, cs in comp_stats.items():
        w = float(cs["weight"])
        if total_weight:
            w = w / total_weight
        overall += (float(cs["success_pct"]) * w)
    overall_status = status_by_threshold(overall, thresholds)

    # --- DÖÇ bazlı başarı (puan bazlı)
    doc_stats = {}
    for did in docs.keys():
        # doc_ids (çoğul) veya doc_id (tekil) kontrolü
        qids = [qid for qid, q in questions.items() if did in (q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else []))]
        
        # Eğer bu DÖÇ'e hiç soru eşlenmemişse, ölçülmemiş olarak işaretle
        if not qids:
            doc_stats[did] = {
                "text": docs[did].get("text", ""),
                "avg_points": 0.0,
                "max_points": 0.0,
                "success_pct": 0.0,  # Ölçülmedi ama 0 olarak tut (karşılaştırma için)
                "status": "Ölçülmedi",
                "question_ids": [],
                "measured": False,
            }
            continue
        
        total_max = sum(float(questions[qid].get("max_points", 0)) for qid in qids)
        # öğrenci başına DÖÇ toplam puanı
        totals = []
        for sid in students.keys():
            srec = scores.get(sid, {})
            tot = sum(float(srec.get(qid, 0.0)) for qid in qids)
            totals.append(tot)
        avg_total = statistics.mean(totals) if totals else 0.0
        success = _safe_div(avg_total, total_max)
        pct = normalize_pct(success)
        doc_stats[did] = {
            "text": docs[did].get("text", ""),
            "avg_points": avg_total,
            "max_points": total_max,
            "success_pct": pct,
            "status": status_by_threshold(pct, thresholds),
            "question_ids": qids,
            "measured": True,
        }

    # --- Bloom dağılımı (birden fazla bloom desteği)
    bloom_stats = {}
    for qid, q in questions.items():
        # bloom_list varsa onu kullan, yoksa tekil bloom'u listeye çevir
        bloom_list = q.get("bloom_list") or []
        if not bloom_list:
            single_bloom = q.get("bloom", "")
            if single_bloom:
                # Virgülle ayrılmış olabilir
                bloom_list = [b.strip() for b in str(single_bloom).split(",") if b.strip()]
        
        # Hala boşsa "Bilinmiyor" ekle
        if not bloom_list:
            bloom_list = ["Bilinmiyor"]
        
        # Her bloom için puanı paylaştır
        bloom_count = len(bloom_list)
        points_per_bloom = float(q.get("max_points", 0.0)) / bloom_count
        avg_per_bloom = float(q_stats[qid]["avg_points"]) / bloom_count
        
        for b in bloom_list:
            b = (b or "").strip()
            if not b:
                b = "Bilinmiyor"
            bloom_stats.setdefault(b, {"max_points": 0.0, "avg_points": 0.0, "questions": 0})
            bloom_stats[b]["max_points"] += points_per_bloom
            bloom_stats[b]["avg_points"] += avg_per_bloom
            bloom_stats[b]["questions"] += 1
    
    for b, st in bloom_stats.items():
        st["success_pct"] = normalize_pct(_safe_div(st["avg_points"], st["max_points"]))
        st["status"] = status_by_threshold(float(st["success_pct"]), thresholds)

    # --- PÖÇ başarısı (doğrudan soru eşleştirmesi + DÖÇ katkısı)
    doc_poc_weights = payload.get("doc_poc_weights", {})  # did -> {pid: 0..3}
    poc_stats = {}
    for pid in pocs.keys():
        # 1. Doğrudan soru eşleştirmesinden hesapla
        direct_qids = [qid for qid, q in questions.items() if pid in (q.get("poc_list") or [])]
        direct_max = sum(float(questions[qid].get("max_points", 0)) for qid in direct_qids)
        direct_totals = []
        for sid in students.keys():
            srec = scores.get(sid, {})
            tot = sum(float(srec.get(qid, 0.0)) for qid in direct_qids)
            direct_totals.append(tot)
        direct_avg = statistics.mean(direct_totals) if direct_totals else 0.0
        direct_pct = normalize_pct(_safe_div(direct_avg, direct_max)) if direct_max > 0 else 0.0
        
        # 2. DÖÇ katkısından hesapla (sadece ölçülmüş DÖÇ'lerden)
        num = 0.0
        den = 0.0
        contrib_docs = []
        for did in docs.keys():
            w = float(doc_poc_weights.get(did, {}).get(pid, 0.0))
            doc_measured = doc_stats.get(did, {}).get("measured", False)
            doc_pct = doc_stats.get(did, {}).get("success_pct")
            if w > 0 and doc_measured and doc_pct is not None:
                den += w
                num += float(doc_pct) * w
                contrib_docs.append({"doc_id": did, "weight": w, "doc_pct": doc_pct})
        indirect_pct = _safe_div(num, den)
        
        # 3. Sonucu belirle: doğrudan eşleştirme varsa onu kullan, yoksa dolaylı
        if direct_qids:
            pct = direct_pct
            measured = True
        elif contrib_docs:
            pct = indirect_pct
            measured = True
        else:
            pct = 0.0  # Ölçülmedi ama 0 olarak tut (karşılaştırma için)
            measured = False
            
        poc_stats[pid] = {
            "text": pocs[pid].get("text", ""),
            "success_pct": pct,
            "status": status_by_threshold(pct, thresholds) if measured else "Ölçülmedi",
            "contributors": contrib_docs,
            "direct_questions": direct_qids,
            "measured": measured,
        }

    # --- PEA başarısı (doğrudan soru eşleştirmesi + PÖÇ katkısı + DÖÇ katkısı)
    poc_pea_map = payload.get("poc_pea_map", {})  # pid -> [aid,...]
    doc_pea_map = payload.get("doc_pea_map", {})  # did -> [aid,...] - DÖÇ'ten direkt PEA eşleştirmesi
    pea_stats = {}
    for aid in peas.keys():
        # 1. Doğrudan soru eşleştirmesinden hesapla
        direct_qids = [qid for qid, q in questions.items() if aid in (q.get("pea_list") or [])]
        direct_max = sum(float(questions[qid].get("max_points", 0)) for qid in direct_qids)
        direct_totals = []
        for sid in students.keys():
            srec = scores.get(sid, {})
            tot = sum(float(srec.get(qid, 0.0)) for qid in direct_qids)
            direct_totals.append(tot)
        direct_avg = statistics.mean(direct_totals) if direct_totals else 0.0
        direct_pct = normalize_pct(_safe_div(direct_avg, direct_max)) if direct_max > 0 else 0.0
        
        # 2. PÖÇ katkısından hesapla (sadece ölçülmüş PÖÇ'lerden)
        linked_pocs = [pid for pid, a_list in poc_pea_map.items() if aid in (a_list or [])]
        measured_poc_vals = []
        for pid in linked_pocs:
            poc_data = poc_stats.get(pid, {})
            if poc_data.get("measured", False) and poc_data.get("success_pct") is not None:
                measured_poc_vals.append(float(poc_data["success_pct"]))
        poc_indirect_pct = statistics.mean(measured_poc_vals) if measured_poc_vals else 0.0
        
        # 3. DÖÇ katkısından hesapla (doc_pea_map üzerinden)
        linked_docs = [did for did, pea_list in doc_pea_map.items() if aid in (pea_list or [])]
        measured_doc_vals = []
        for did in linked_docs:
            doc_data = doc_stats.get(did, {})
            if doc_data.get("measured", False) and doc_data.get("success_pct") is not None:
                measured_doc_vals.append(float(doc_data["success_pct"]))
        doc_indirect_pct = statistics.mean(measured_doc_vals) if measured_doc_vals else 0.0
        
        # 4. Sonucu belirle: doğrudan > DÖÇ > PÖÇ öncelik sırası
        if direct_qids:
            pct = direct_pct
            measured = True
        elif measured_doc_vals:
            pct = doc_indirect_pct
            measured = True
        elif measured_poc_vals:
            pct = poc_indirect_pct
            measured = True
        else:
            pct = 0.0
            measured = False
            
        pea_stats[aid] = {
            "text": peas[aid].get("text", ""),
            "pocs": linked_pocs,
            "docs": linked_docs,
            "success_pct": pct,
            "status": status_by_threshold(pct, thresholds) if measured else "Ölçülmedi",
            "direct_questions": direct_qids,
            "measured": measured,
        }

    # --- TYÇ başarısı (DÖÇ ve PÖÇ katkısından)
    doc_tyc_map = payload.get("doc_tyc_map", {})  # did -> [tyc_id,...]
    poc_tyc_map = payload.get("poc_tyc_map", {})  # pid -> [tyc_id,...]
    tyc_list = payload.get("tyc", [])
    tyc_stats = {}
    for tyc in tyc_list:
        tyc_id = tyc.get("id", "")
        if not tyc_id:
            continue
        
        # 1. DÖÇ'lerden gelen katkı
        linked_docs = [did for did, tyc_ids in doc_tyc_map.items() if tyc_id in (tyc_ids or [])]
        doc_pcts = []
        for did in linked_docs:
            doc_data = doc_stats.get(did, {})
            if doc_data.get("measured", False) and doc_data.get("success_pct") is not None:
                doc_pcts.append(float(doc_data["success_pct"]))
        
        # 2. PÖÇ'lerden gelen katkı
        linked_pocs = [pid for pid, tyc_ids in poc_tyc_map.items() if tyc_id in (tyc_ids or [])]
        poc_pcts = []
        for pid in linked_pocs:
            poc_data = poc_stats.get(pid, {})
            if poc_data.get("measured", False) and poc_data.get("success_pct") is not None:
                poc_pcts.append(float(poc_data["success_pct"]))
        
        # 3. Ortalama al (DÖÇ ve PÖÇ birlikte)
        all_pcts = doc_pcts + poc_pcts
        if all_pcts:
            pct = statistics.mean(all_pcts)
            measured = True
        else:
            pct = 0.0
            measured = False
        
        tyc_stats[tyc_id] = {
            "text": tyc.get("text", ""),
            "success_pct": pct,
            "status": status_by_threshold(pct, thresholds) if measured else "Ölçülmedi",
            "linked_docs": linked_docs,
            "linked_pocs": linked_pocs,
            "measured": measured,
        }

    # --- STAR-K başarısı (PEA katkısından + DÖÇ katkısından)
    pea_stark_map = payload.get("pea_stark_map", {})  # aid -> [stark_id,...]
    doc_stark_map = payload.get("doc_stark_map", {})  # did -> [stark_id,...] - DÖÇ'ten direkt STARK eşleştirmesi
    stark_list = payload.get("stark", [])
    stark_stats = {}
    for stark in stark_list:
        stark_id = stark.get("id", "")
        if not stark_id:
            continue
        
        # 1. PEA'lardan gelen katkı
        linked_peas = [aid for aid, stark_ids in pea_stark_map.items() if stark_id in (stark_ids or [])]
        pea_pcts = []
        for aid in linked_peas:
            pea_data = pea_stats.get(aid, {})
            if pea_data.get("measured", False) and pea_data.get("success_pct") is not None:
                pea_pcts.append(float(pea_data["success_pct"]))
        
        # 2. DÖÇ'lerden gelen katkı (doc_stark_map üzerinden)
        linked_docs = [did for did, stark_ids in doc_stark_map.items() if stark_id in (stark_ids or [])]
        doc_pcts = []
        for did in linked_docs:
            doc_data = doc_stats.get(did, {})
            if doc_data.get("measured", False) and doc_data.get("success_pct") is not None:
                doc_pcts.append(float(doc_data["success_pct"]))
        
        # 3. Tüm değerleri birleştir
        all_pcts = pea_pcts + doc_pcts
        if all_pcts:
            pct = statistics.mean(all_pcts)
            measured = True
        else:
            pct = 0.0
            measured = False
        
        stark_stats[stark_id] = {
            "text": stark.get("text", ""),
            "success_pct": pct,
            "status": status_by_threshold(pct, thresholds) if measured else "Ölçülmedi",
            "linked_peas": linked_peas,
            "linked_docs": linked_docs,
            "measured": measured,
        }

    # --- Öğrenci notları / harf dağılımı (opsiyonel)
    # her öğrenci için 0..100 genel başarı
    student_totals = {}
    for sid in students.keys():
        # bileşen bazlı normalize + ağırlıklı topla
        total = 0.0
        for cid, comp in assessments.items():
            qids = [qid for qid, q in questions.items() if q.get("component_id") == cid]
            max_total = sum(float(questions[qid].get("max_points", 0)) for qid in qids)
            got = sum(float(scores.get(sid, {}).get(qid, 0.0)) for qid in qids)
            pct = normalize_pct(_safe_div(got, max_total))
            w = float(comp.get("weight", 0))
            if total_weight:
                w = w / total_weight
            total += pct * w
        student_totals[sid] = total

    grade_dist = {}
    if grading:
        # grading dict: harf->alt_sınır (örn A:90)
        # büyükten küçüğe sırala
        bands = sorted([(k, float(v)) for k, v in grading.items()], key=lambda x: x[1], reverse=True)
        for sid, pct in student_totals.items():
            letter = None
            for k, cut in bands:
                if pct >= cut:
                    letter = k
                    break
            if letter is None:
                letter = bands[-1][0] if bands else "N/A"
            grade_dist[letter] = grade_dist.get(letter, 0) + 1

    # --- Otomatik değerlendirme metni
    # DÖÇ'lere göre kısa özet: en düşük 2 DÖÇ ve öneri
    doc_sorted = sorted(doc_stats.items(), key=lambda kv: kv[1]["success_pct"])
    weak = doc_sorted[:2]
    suggestions = []
    if weak:
        for did, st in weak:
            if st["success_pct"] < thresholds.get("partially", 50):
                suggestions.append(f"{did} düşük: üst düzey etkinlik/soru sayısını artırın, örnek çözüm oturumları planlayın.")
            else:
                suggestions.append(f"{did} kısmen: uygulama/pekiştirme etkinliği ekleyin, ölçme araçlarını çeşitlendirin.")

    narrative = {
        "overall_pct": overall,
        "overall_status": overall_status,
        "doc_summary": [{"doc_id": did, "pct": st["success_pct"], "status": st["status"]} for did, st in doc_stats.items() if st.get("measured", False)],
        "poc_summary": [{"poc_id": pid, "pct": st["success_pct"], "status": st["status"]} for pid, st in poc_stats.items() if st.get("measured", False)],
        "suggestions": suggestions,
    }

    return {
        "course": payload.get("course", {}),
        "thresholds": thresholds,
        "computed": {
            "questions": q_stats,
            "assessments": comp_stats,
            "overall": {"success_pct": overall, "status": overall_status},
            "docs": doc_stats,
            "pocs": poc_stats,
            "peas": pea_stats,
            "tyc": tyc_stats,
            "stark": stark_stats,
            "bloom": bloom_stats,
            "students": {
                "totals_pct": student_totals,
                "grade_dist": grade_dist,
                "count": len(students),  # Sadece sınava girenler
                "total_count": len(all_students),  # Tüm kayıtlı öğrenciler
                "gr_count": len(gr_students),  # Sınava girmeyenler
                "gr_students": list(gr_students.values()),  # GR öğrenci listesi
            },
            "narrative": narrative,
        },
    }

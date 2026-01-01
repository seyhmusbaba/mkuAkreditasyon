"""
Örnek veri: v2 demo
- Vize + Final
- 5 soru
- 30 öğrenci (rastgele ama kontrollü)
"""
from __future__ import annotations

import random

def build_sample_payload(seed: int = 42):
    random.seed(seed)

    payload = {
        "course": {
            "course_code": "BM203",
            "course_name": "Veri Yapıları",
            "program_name": "Bilgisayar Mühendisliği",
            "term": "2024-2025 Güz",
            "instructor": "Örnek Öğretim Elemanı",
        },
        "docs": [
            {"id": "DÖÇ1", "text": "Temel veri yapılarını açıklar."},
            {"id": "DÖÇ2", "text": "Veri yapıları üzerinde algoritma uygular."},
            {"id": "DÖÇ3", "text": "Algoritma verimliliğini analiz eder."},
        ],
        "pocs": [
            {"id": "PÖÇ1", "text": "Temel mühendislik bilgisi."},
            {"id": "PÖÇ2", "text": "Algoritmik problem çözme."},
            {"id": "PÖÇ3", "text": "Analitik düşünme."},
        ],
        "peas": [
            {"id": "PEA1", "text": "Yazılım sektöründe etkin rol alabilen mezunlar."},
            {"id": "PEA2", "text": "Analitik düşünebilen mühendis yetiştirmek."},
        ],
        "assessments": [
            {"id": "C1", "name": "Vize", "weight": 0.4},
            {"id": "C2", "name": "Final", "weight": 0.6},
        ],
        "questions": [
            {"id": "S1", "component_id": "C1", "text": "Stack nedir? Kısa açıklayınız.", "doc_id": "DÖÇ1", "bloom": "Bilgi", "max_points": 10},
            {"id": "S2", "component_id": "C1", "text": "Queue kullanım senaryosu veriniz.", "doc_id": "DÖÇ1", "bloom": "Kavrama", "max_points": 10},
            {"id": "S3", "component_id": "C2", "text": "LinkedList üzerinde ekleme işlemini uygulayınız.", "doc_id": "DÖÇ2", "bloom": "Uygulama", "max_points": 20},
            {"id": "S4", "component_id": "C2", "text": "Hash çakışmalarını analiz ediniz.", "doc_id": "DÖÇ2", "bloom": "Analiz", "max_points": 20},
            {"id": "S5", "component_id": "C2", "text": "Algoritma karmaşıklığını karşılaştırıp yorumlayınız.", "doc_id": "DÖÇ3", "bloom": "Değerlendirme", "max_points": 20},
        ],
        "students": [{"id": f"S{i:02d}", "name": f"Öğrenci {i:02d}"} for i in range(1, 31)],
        "scores": {},
        "doc_poc_weights": {
            "DÖÇ1": {"PÖÇ1": 2, "PÖÇ2": 1, "PÖÇ3": 0},
            "DÖÇ2": {"PÖÇ1": 0, "PÖÇ2": 3, "PÖÇ3": 2},
            "DÖÇ3": {"PÖÇ1": 0, "PÖÇ2": 1, "PÖÇ3": 3},
        },
        "poc_pea_map": {
            "PÖÇ1": ["PEA1"],
            "PÖÇ2": ["PEA1", "PEA2"],
            "PÖÇ3": ["PEA2"],
        },
        "thresholds": {"met": 70, "partially": 50},
        "grading": {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0},
    }

    # Başarı profili: DÖÇ1 yüksek, DÖÇ2 orta, DÖÇ3 düşük
    # Bu profili oluşturmak için soru bazında dağılım veriyoruz.
    # S1,S2: 7-10 aralığı; S3,S4: 8-16 aralığı; S5: 4-12 aralığı
    for st in payload["students"]:
        sid = st["id"]
        payload["scores"][sid] = {
            "S1": random.randint(7, 10),
            "S2": random.randint(6, 10),
            "S3": random.randint(10, 18),
            "S4": random.randint(6, 15),
            "S5": random.randint(3, 12),
        }

    return payload

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime
import pandas as pd

from engine import compute
from pdf_report import build_pdf as legacy_pdf
from login import get_user_curriculum, save_user_curriculum, get_course_data

# Claude API Key - SADECE environment variable'dan oku (güvenlik için)
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")


def generate_ai_suggestions(result: Dict[str, Any]) -> List[str]:
    """Claude API kullanarak detaylı sorun tespiti ve çözüm önerileri üret"""
    import ssl
    import traceback
    
    # API key kontrolü
    if not CLAUDE_API_KEY:
        print("[Claude AI] ⚠️ CLAUDE_API_KEY environment variable tanımlı değil!")
        print("[Claude AI] Railway Dashboard > Variables > CLAUDE_API_KEY ekleyin")
        return None
    
    print("[Claude AI] API çağrısı başlatılıyor...")
    
    try:
        computed = result.get("computed", {})
        overall = computed.get("overall", {})
        docs = computed.get("docs", {})
        pocs = computed.get("pocs", {})
        peas = computed.get("peas", {})
        bloom = computed.get("bloom", {})
        coverage = result.get("coverage", {})
        course = result.get("course", {})
        students_data = result.get("students_data", [])
        thresholds = result.get("thresholds", {"met": 70, "partially": 50})
        
        # Detaylı analiz verileri
        attending = [s for s in students_data if not s.get('is_absent')]
        scores = [s.get('success_pct', 0) for s in attending]
        avg_score = sum(scores) / len(scores) if scores else 0
        passed = len([s for s in scores if s >= 50])
        failed = len([s for s in scores if s < 50])
        
        # Kritik DÖÇ'ler (başarısız olanlar - sadece ölçülmüş olanlar)
        critical_docs = []
        for k, v in docs.items():
            if not v.get('measured', True):
                continue  # Ölçülmemiş olanları atla
            pct = v.get('success_pct')
            if pct is None:
                continue
            if pct < 70:
                status = "KRİTİK" if pct < 50 else "ZAYIF"
                critical_docs.append(f"{k}: %{pct:.1f} [{status}]")
        
        # Kritik PÖÇ'ler (sadece ölçülmüş olanlar)
        critical_pocs = []
        for k, v in pocs.items():
            if not v.get('measured', True):
                continue
            pct = v.get('success_pct')
            if pct is None:
                continue
            if pct < 70:
                status = "KRİTİK" if pct < 50 else "ZAYIF"
                critical_pocs.append(f"{k}: %{pct:.1f} [{status}]")
        
        # Kritik PEA'lar (sadece ölçülmüş olanlar)
        critical_peas = []
        for k, v in peas.items():
            if not v.get('measured', True):
                continue
            pct = v.get('success_pct')
            if pct is None:
                continue
            if pct < 70:
                status = "KRİTİK" if pct < 50 else "ZAYIF"
                critical_peas.append(f"{k}: %{pct:.1f} [{status}]")
        
        # Bloom analizi
        bloom_issues = []
        for k, v in bloom.items():
            pct = v.get('success_pct', 0)
            if pct < 70:
                bloom_issues.append(f"{k}: %{pct:.1f}")
        
        # Kapsam eksiklikleri
        doc_coverage = coverage.get("doc", [])
        uncovered = [c["id"] for c in doc_coverage if c.get("count", 0) == 0]
        low_coverage = [f"{c['id']} ({c['count']} soru)" for c in doc_coverage if 0 < c.get("count", 0) <= 2]
        
        course_name = course.get("course_name", "Bilinmiyor")
        overall_pct = overall.get('success_pct', 0)
        overall_status = overall.get('status', 'Bilinmiyor')
        
        prompt = f"""Sen bir üniversite akreditasyon ve eğitim kalitesi uzmanısın. Aşağıdaki ders değerlendirme raporunu analiz ederek ÖĞRETİM ÜYESİNE somut, uygulanabilir öneriler sun.

## DERS BİLGİLERİ
- Ders: {course_name}
- Genel Başarı: %{overall_pct:.1f} ({overall_status})
- Sınıf Ortalaması: %{avg_score:.1f}
- Geçen: {passed} öğrenci | Kalan: {failed} öğrenci
- Eşikler: Sağlandı≥%{thresholds.get('met', 70)}, Kısmen≥%{thresholds.get('partially', 50)}

## SORUNLU DERS ÖĞRENME ÇIKTILARI (DÖÇ)
{chr(10).join(critical_docs) if critical_docs else 'Tüm DÖÇler başarılı (≥%70)'}

## SORUNLU PROGRAM ÇIKTILARI (PÖÇ)
{chr(10).join(critical_pocs) if critical_pocs else 'Tüm PÖÇler başarılı (≥%70)'}

## SORUNLU PROGRAM EĞİTİM AMAÇLARI (PEA)
{chr(10).join(critical_peas) if critical_peas else 'Tüm PEAlar başarılı (≥%70)'}

## BLOOM TAKSONOMİSİ SORUNLARI
{chr(10).join(bloom_issues) if bloom_issues else 'Tüm Bloom düzeyleri başarılı'}

## KAPSAM EKSİKLİKLERİ
- Hiç ölçülmemiş DÖÇler: {', '.join(uncovered) if uncovered else 'Yok - tümü ölçülmüş'}
- Yetersiz kapsam (1-2 soru): {', '.join(low_coverage) if low_coverage else 'Yok'}

---

Lütfen aşağıdaki formatta 6-8 adet detaylı öneri yaz. Her öneri şu yapıda olmalı:
1. SORUN: [Tespit edilen spesifik sorun - hangi DÖÇ/PÖÇ/PEA/Bloom]
   ÇÖZÜM: [Somut, uygulanabilir çözüm önerisi]

Öneriler şunları kapsamalı:
- Kritik başarısız çıktılar için acil müdahale önerileri
- Öğretim yöntemi değişiklikleri
- Ek alıştırma/materyal önerileri
- Ölçme-değerlendirme iyileştirmeleri
- Kapsam eksikliklerinin giderilmesi
- Risk altındaki öğrenciler için destek

Her öneriyi tek satırda, başında numara ile yaz. SORUN ve ÇÖZÜM etiketlerini kullan."""

        # Claude API çağrısı
        url = "https://api.anthropic.com/v1/messages"
        
        data = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 2048,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        # SSL context - sertifika doğrulamasını esnek yap
        try:
            ssl_context = ssl.create_default_context()
        except Exception as ssl_err:
            print(f"[Claude AI] SSL context hatası, varsayılan kullanılıyor: {ssl_err}")
            ssl_context = ssl._create_unverified_context()
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'x-api-key': CLAUDE_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            method='POST'
        )
        
        print(f"[Claude AI] API isteği gönderiliyor: {url}")
        print(f"[Claude AI] API Key: {CLAUDE_API_KEY[:20]}...")
        
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            response_body = response.read().decode('utf-8')
            print(f"[Claude AI] Yanıt alındı: {len(response_body)} byte")
            result_json = json.loads(response_body)
        
        # Hata kontrolü
        if "error" in result_json:
            print(f"[Claude AI] API Hatası: {result_json['error']}")
            return None
        
        text = result_json.get("content", [{}])[0].get("text", "")
        print(f"[Claude AI] Öneriler: {len(text)} karakter")
        
        # Satırlara ayır ve temizle
        suggestions = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if line and len(line) > 20:
                # Numaralandırmayı kaldır
                if line[0].isdigit() and '.' in line[:4]:
                    line = line.split('.', 1)[1].strip()
                if line.startswith(('-', '*')):
                    line = line[1:].strip()
                if line and len(line) > 20:
                    suggestions.append(line)
        
        print(f"[Claude AI] ✅ {len(suggestions)} öneri oluşturuldu")
        return suggestions[:8] if suggestions else None
        
    except urllib.error.HTTPError as e:
        print(f"[Claude AI] HTTP Hatası: {e.code} - {e.reason}")
        try:
            error_body = e.read().decode('utf-8')
            print(f"[Claude AI] Hata detayı: {error_body}")
        except:
            pass
        return None
    except urllib.error.URLError as e:
        print(f"[Claude AI] URL/Network Hatası: {e.reason}")
        return None
    except ssl.SSLError as e:
        print(f"[Claude AI] SSL Hatası: {e}")
        # SSL hatası durumunda sertifika doğrulamasız dene
        try:
            print("[Claude AI] SSL doğrulamasız tekrar deneniyor...")
            ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
                result_json = json.loads(response.read().decode('utf-8'))
            text = result_json.get("content", [{}])[0].get("text", "")
            suggestions = [line.strip() for line in text.strip().split('\n') if line.strip() and len(line.strip()) > 20]
            return suggestions[:8] if suggestions else None
        except Exception as retry_err:
            print(f"[Claude AI] SSL bypass da başarısız: {retry_err}")
            return None
    except json.JSONDecodeError as e:
        print(f"[Claude AI] JSON Parse Hatası: {e}")
        return None
    except Exception as e:
        print(f"[Claude AI] Beklenmeyen Hata: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


STATE = {
    "last_result": None,
    "last_payload_text": None,
    "last_pdf_path": None,
    "last_v2_pdf_path": None,
}

FORM_KEYS = [
    "course_code", "course_name", "program_name", "term", "instructor",
    "curriculum_text", "curriculum_doc_map_text", "tyc_text", "stark_text",
    "doc_tyc_map_text", "poc_tyc_map_text", "pea_stark_map_text",
    "doc_stark_map_text", "doc_pea_map_text",
    "curriculum_tyc_map_text", "curriculum_stark_map_text", 
    "curriculum_poc_map_text", "curriculum_pea_map_text",
    "question_map_text", "docs_text", "pocs_text", "peas_text",
    "doc_poc_weights_text", "poc_pea_map_text", "bloom_text",
    "assessments_text", "questions_text", "students_text", "scores_text",
    "thresholds_met", "thresholds_partial", "grading_text",
    "payload_json_raw",
]

# =============================================================================
# MODERN TASARIM - CSS + JavaScript
# =============================================================================

HTML_HEAD = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    :root {
      --primary: #4f46e5;
      --primary-light: #6366f1;
      --secondary: #7c3aed;
      --success: #059669;
      --success-bg: #ecfdf5;
      --warning: #d97706;
      --warning-bg: #fffbeb;
      --danger: #dc2626;
      --danger-bg: #fef2f2;
      --bg: #f1f5f9;
      --bg-card: #ffffff;
      --border: #e2e8f0;
      --text: #1e293b;
      --text-secondary: #475569;
      --text-muted: #94a3b8;
    }
    
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg);
      min-height: 100vh;
      color: var(--text);
    }
    
    /* Header */
    .main-header {
      background: var(--primary);
      color: white;
    }
    
    .header-content {
      max-width: 1800px;
      margin: 0 auto;
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .header-brand { display: flex; align-items: center; gap: 1rem; }
    
    .brand-logo {
      width: 44px; height: 44px;
      background: white;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .brand-logo img { width: 75%; height: 75%; object-fit: contain; }
    .brand-text h1 { font-size: 1rem; font-weight: 600; }
    .brand-text span { font-size: 0.75rem; opacity: 0.9; }
    
    .header-user { display: flex; align-items: center; gap: 1rem; }
    .user-info { text-align: right; }
    .user-info .name { font-size: 0.9rem; font-weight: 500; }
    .user-info .details { font-size: 0.75rem; opacity: 0.85; }
    
    .user-avatar {
      width: 40px; height: 40px;
      background: white;
      color: var(--primary);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
    }
    
    .header-actions { display: flex; gap: 0.5rem; }
    
    .header-btn {
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 500;
      text-decoration: none;
      transition: all 0.2s;
    }
    
    .header-btn-ghost { background: rgba(255,255,255,0.15); color: white; }
    .header-btn-ghost:hover { background: rgba(255,255,255,0.25); }
    .header-btn-success { background: #10b981; color: white; }
    .header-btn-success:hover { background: #059669; }
    .header-btn-danger { background: white; color: var(--danger); }
    
    /* Container */
    .container { max-width: 1800px; margin: 0 auto; padding: 1.5rem 2rem; }
    
    .grid {
      display: grid;
      grid-template-columns: 580px 1fr;
      gap: 1.5rem;
      align-items: start;
    }
    
    @media (max-width: 1200px) { .grid { grid-template-columns: 1fr; } }
    
    /* Box */
    .box {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .box > h2:first-child {
      padding: 1.25rem 1.5rem;
      font-size: 0.95rem;
      font-weight: 600;
      background: linear-gradient(to right, #f8fafc, #f1f5f9);
      border-bottom: 1px solid var(--border);
      border-radius: 12px 12px 0 0;
    }
    
    .box-body { padding: 1.5rem; }
    
    /* Tabs */
    .tabs {
      display: flex;
      background: #f8fafc;
      border-radius: 8px;
      padding: 4px;
      margin-bottom: 1.25rem;
      gap: 4px;
    }
    
    .tab {
      flex: 1;
      padding: 0.65rem 1rem;
      border: none;
      background: transparent;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--text-muted);
      border-radius: 6px;
      transition: all 0.15s;
    }
    
    .tab:hover { color: var(--text-secondary); background: white; }
    .tab.active { background: var(--primary); color: white; }
    
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    
    /* Section Title */
    .section-title {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--primary);
      margin: 1.5rem 0 1rem 0;
      padding-bottom: 0.5rem;
      border-bottom: 2px solid var(--border);
    }
    
    .section-title:first-child { margin-top: 0; }
    
    /* Forms */
    label {
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-secondary);
      margin-bottom: 0.4rem;
      margin-top: 1rem;
    }
    
    label:first-child { margin-top: 0; }
    
    input[type="text"], input[type="number"], textarea, select {
      width: 100%;
      padding: 0.75rem 1rem;
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.9rem;
      font-family: inherit;
      color: var(--text);
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    
    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
      background: white;
    }
    
    input::placeholder, textarea::placeholder { color: var(--text-muted); }
    
    textarea {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      min-height: 90px;
      resize: vertical;
    }
    
    .helper { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.35rem; }
    
    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.75rem 1.25rem;
      font-size: 0.85rem;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s;
      text-decoration: none;
      border: none;
      font-family: inherit;
    }
    
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-light); }
    
    .btn-accent { background: var(--warning); color: white; }
    .btn-success { background: var(--success); color: white; }
    .btn-purple { background: var(--secondary); color: white; }
    .btn-secondary { background: #f1f5f9; color: var(--text-secondary); border: 1px solid var(--border); }
    .btn-danger { background: var(--danger); color: white; }
    .btn-sm { padding: 0.5rem 0.875rem; font-size: 0.8rem; }
    .btn-group { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid var(--border); }
    
    /* Badges */
    .badge { display: inline-flex; padding: 0.25rem 0.625rem; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
    .badge-success { background: var(--success-bg); color: var(--success); }
    .badge-warning { background: var(--warning-bg); color: var(--warning); }
    .badge-danger { background: var(--danger-bg); color: var(--danger); }
    
    /* Tables */
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    
    th {
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: #f8fafc;
      border-bottom: 2px solid var(--border);
    }
    
    td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
    tr:hover td { background: #f8fafc; }
    
    tr.row-success td { background: var(--success-bg); border-left: 3px solid var(--success); }
    tr.row-warning td { background: var(--warning-bg); border-left: 3px solid var(--warning); }
    tr.row-danger td { background: var(--danger-bg); border-left: 3px solid var(--danger); }
    tr.total td { background: #f1f5f9; font-weight: 600; color: var(--primary); }
    
    /* Checkbox Items */
    .checkbox-group { margin-bottom: 1rem; }
    .checkbox-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    
    .cb-item {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.4rem 0.75rem;
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.8rem;
      color: var(--text-secondary);
      transition: all 0.15s;
    }
    
    .cb-item:hover { border-color: var(--primary); }
    .cb-item.selected { background: var(--primary); border-color: var(--primary); color: white; }
    
    .cb-box { width: 16px; height: 16px; border: 2px solid currentColor; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; }
    .cb-item.selected .cb-box { background: white; color: var(--primary); }
    
    /* Questions */
    .question-card { border: 1px solid var(--border); border-radius: 10px; margin-bottom: 1rem; background: white; }
    
    .question-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1.25rem 1.5rem;
      background: #f8fafc;
      cursor: pointer;
      border-radius: 10px 10px 0 0;
      border-bottom: 1px solid var(--border);
    }
    
    .question-title { font-weight: 600; font-size: 0.9rem; display: flex; align-items: center; gap: 0.75rem; }
    
    .question-num {
      background: var(--primary);
      color: white;
      width: 28px; height: 28px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.8rem;
    }
    
    .question-body { padding: 1.5rem; }
    .question-body.collapsed { display: none; }
    .question-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem; }
    .question-checkboxes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border); }
    
    /* Mappings */
    .mapping-card { border: 1px solid var(--border); border-radius: 10px; margin-bottom: 1rem; }
    .mapping-card h4 { padding: 0.875rem 1rem; background: #f8fafc; font-size: 0.85rem; border-bottom: 1px solid var(--border); border-radius: 10px 10px 0 0; }
    .mapping-content { padding: 1rem; }
    .mapping-row { display: flex; gap: 1rem; padding: 0.625rem 0; border-bottom: 1px solid var(--border); }
    .mapping-row:last-child { border-bottom: none; }
    .mapping-source { min-width: 70px; font-weight: 600; color: var(--primary); }
    .mapping-targets { flex: 1; display: flex; flex-wrap: wrap; gap: 0.35rem; }
    
    /* Stats */
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.25rem; }
    
    .stat-card {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.5rem;
      text-align: center;
    }
    
    .stat-value { font-size: 1.75rem; font-weight: 700; color: var(--primary); }
    .stat-label { font-size: 0.7rem; color: var(--text-muted); margin-top: 0.25rem; text-transform: uppercase; }
    
    /* Collapsible */
    h2.collapsible {
      padding: 1.25rem 1.5rem;
      background: #f8fafc;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border);
    }
    
    h2.collapsible:hover { background: #f1f5f9; }
    h2.collapsible::before { content: "▼"; font-size: 0.65rem; color: var(--primary); }
    h2.collapsible.collapsed::before { transform: rotate(-90deg); }
    .collapsible-content { padding: 1.5rem; }
    
    /* Progress */
    .progress-bar { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }
    .progress-fill { height: 100%; border-radius: 4px; }
    
    /* Alerts */
    .alert { padding: 1.25rem 1.5rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.85rem; }
    .alert-success { background: var(--success-bg); color: var(--success); }
    .alert-warning { background: var(--warning-bg); color: var(--warning); }
    .alert-danger { background: var(--danger-bg); color: var(--danger); }
    .alert-info { background: #eff6ff; color: #1d4ed8; }
    .alert-error { background: var(--danger-bg); color: var(--danger); }
    
    /* Empty State */
    .empty-state { text-align: center; padding: 4rem 2rem; }
    .empty-state-icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.3; }
    .empty-state h3 { color: var(--text-muted); }
    
    /* Helpers */
    .text-muted { color: var(--text-muted); }
    .text-success { color: var(--success); }
    .text-warning { color: var(--warning); }
    .text-danger { color: var(--danger); }
    
    .add-question-btn {
      width: 100%;
      padding: 1rem;
      border: 2px dashed var(--border);
      border-radius: 10px;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 500;
    }
    
    .add-question-btn:hover { border-color: var(--primary); color: var(--primary); background: #f8fafc; }
    
    .questions-summary {
      display: flex;
      justify-content: space-between;
      padding: 1.25rem 1.5rem;
      background: #f8fafc;
      border-radius: 8px;
      margin-bottom: 1rem;
    }
    
    .questions-summary .count { color: var(--primary); font-weight: 700; }
    .result-panel .box { margin-bottom: 1rem; }
    
    /* Renkli Satır Stilleri */
    tr.row-success td { background: #ecfdf5; border-left: 4px solid #059669; }
    tr.row-warning td { background: #fffbeb; border-left: 4px solid #d97706; }
    tr.row-danger td { background: #fef2f2; border-left: 4px solid #dc2626; }
    
    /* Stat value renkleri */
    .stat-value.success { color: #059669; }
    .stat-value.warning { color: #d97706; }
    .stat-value.danger { color: #dc2626; }
    
    /* Check list */
    .check-list { list-style: none; padding: 0; margin: 0; }
    .check-list li { 
      display: flex; 
      gap: 1rem; 
      padding: 1rem; 
      border-bottom: 1px solid var(--border);
      background: #fefce8;
    }
    .check-list li:last-child { border-bottom: none; }
    .check-list .icon { font-size: 1.25rem; flex-shrink: 0; }
    
    /* Progress bars with colors */
    .progress-fill.success { background: #059669; }
    .progress-fill.warning { background: #d97706; }
    .progress-fill.danger { background: #dc2626; }
    
    /* Table hover daha belirgin */
    table { background: white; }
    tr:hover td { background: #f1f5f9 !important; }
    
    /* Badge daha belirgin */
    .badge { font-weight: 700; padding: 0.35rem 0.75rem; }
    
    /* ============ LOADING SPINNER ============ */
    .loading-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.7);
      z-index: 9999;
      justify-content: center;
      align-items: center;
      flex-direction: column;
      gap: 1.5rem;
    }
    
    .loading-overlay.active { display: flex; }
    
    .spinner {
      width: 56px; height: 56px;
      border: 4px solid rgba(255,255,255,0.2);
      border-top-color: var(--primary-light);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    .loading-text {
      color: white;
      font-size: 1rem;
      font-weight: 500;
    }
    
    .loading-progress {
      width: 200px;
      height: 6px;
      background: rgba(255,255,255,0.2);
      border-radius: 3px;
      overflow: hidden;
    }
    
    .loading-progress-bar {
      height: 100%;
      background: var(--primary-light);
      width: 0%;
      animation: progress 2s ease-in-out infinite;
    }
    
    @keyframes progress {
      0% { width: 0%; }
      50% { width: 70%; }
      100% { width: 100%; }
    }
    
    /* ============ TOOLTIP ============ */
    .tooltip-container { position: relative; display: inline-block; }
    
    .tooltip-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px; height: 16px;
      background: var(--border);
      color: var(--text-muted);
      border-radius: 50%;
      font-size: 0.65rem;
      font-weight: 700;
      cursor: help;
      margin-left: 0.35rem;
      vertical-align: middle;
    }
    
    .tooltip-icon:hover { background: var(--primary); color: white; }
    
    .tooltip-content {
      visibility: hidden;
      opacity: 0;
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%);
      background: #1e293b;
      color: white;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 400;
      width: 280px;
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      transition: opacity 0.2s, visibility 0.2s;
      line-height: 1.5;
    }
    
    .tooltip-content::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #1e293b;
    }
    
    .tooltip-container:hover .tooltip-content {
      visibility: visible;
      opacity: 1;
    }
    
    /* ============ FORM VALIDATION ============ */
    .field-error {
      color: var(--danger);
      font-size: 0.75rem;
      margin-top: 0.25rem;
      display: none;
    }
    
    .field-error.show { display: block; }
    
    input.input-error, textarea.input-error, select.input-error {
      border-color: var(--danger) !important;
      background: #fef2f2 !important;
    }
    
    input.input-success, textarea.input-success {
      border-color: var(--success) !important;
    }
    
    /* ============ AUTO-SAVE INDICATOR ============ */
    .autosave-status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.75rem;
      color: var(--text-muted);
      padding: 0.5rem 0;
    }
    
    .autosave-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--border);
    }
    
    .autosave-dot.saving { background: var(--warning); animation: pulse 1s infinite; }
    .autosave-dot.saved { background: var(--success); }
    .autosave-dot.error { background: var(--danger); }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    /* ============ SIDEBAR (Taslak & Rapor Geçmişi) ============ */
    .sidebar-panel {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 1rem;
      overflow: hidden;
    }
    
    .sidebar-header {
      padding: 1rem 1.25rem;
      background: linear-gradient(to right, #f8fafc, #f1f5f9);
      border-bottom: 1px solid var(--border);
      font-weight: 600;
      font-size: 0.9rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      cursor: pointer;
    }
    
    .sidebar-header:hover { background: #f1f5f9; }
    
    .sidebar-header .toggle-icon {
      margin-left: auto;
      transition: transform 0.2s;
    }
    
    .sidebar-header.collapsed .toggle-icon { transform: rotate(-90deg); }
    
    .sidebar-body { padding: 0.75rem; }
    .sidebar-body.collapsed { display: none; }
    
    .sidebar-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s;
      margin-bottom: 0.25rem;
    }
    
    .sidebar-item:hover { background: #f8fafc; }
    
    .sidebar-item-info { flex: 1; min-width: 0; }
    .sidebar-item-title { font-size: 0.85rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sidebar-item-meta { font-size: 0.7rem; color: var(--text-muted); margin-top: 0.15rem; }
    
    .sidebar-item-pct {
      font-size: 0.8rem;
      font-weight: 700;
      padding: 0.25rem 0.5rem;
      border-radius: 6px;
      margin-left: 0.5rem;
    }
    
    .sidebar-item-pct.success { background: var(--success-bg); color: var(--success); }
    .sidebar-item-pct.warning { background: var(--warning-bg); color: var(--warning); }
    .sidebar-item-pct.danger { background: var(--danger-bg); color: var(--danger); }
    
    .sidebar-item-actions {
      display: flex;
      gap: 0.25rem;
      opacity: 0;
      transition: opacity 0.15s;
    }
    
    .sidebar-item:hover .sidebar-item-actions { opacity: 1; }
    
    .sidebar-action-btn {
      width: 28px; height: 28px;
      border: none;
      background: transparent;
      cursor: pointer;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.8rem;
    }
    
    .sidebar-action-btn:hover { background: var(--border); }
    .sidebar-action-btn.delete:hover { background: var(--danger-bg); color: var(--danger); }
    
    .sidebar-empty {
      text-align: center;
      padding: 1.5rem;
      color: var(--text-muted);
      font-size: 0.85rem;
    }
    
    /* ============ SAVE DRAFT MODAL ============ */
    .modal-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.5);
      z-index: 9998;
      justify-content: center;
      align-items: center;
    }
    
    .modal-overlay.active { display: flex; }
    
    .modal {
      background: white;
      border-radius: 16px;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 25px 50px rgba(0,0,0,0.25);
      animation: modalIn 0.2s ease;
    }
    
    @keyframes modalIn {
      from { opacity: 0; transform: scale(0.95); }
      to { opacity: 1; transform: scale(1); }
    }
    
    .modal-header {
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border);
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    
    .modal-close {
      background: none;
      border: none;
      font-size: 1.25rem;
      cursor: pointer;
      color: var(--text-muted);
    }
    
    .modal-body { padding: 1.5rem; }
    
    .modal-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 0.75rem;
      justify-content: flex-end;
    }
    
    /* Mapping Table Stilleri */
    .mapping-table-container {
      overflow-x: auto;
      margin-bottom: 1rem;
    }
    .mapping-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
      min-width: 600px;
    }
    .mapping-table th, .mapping-table td {
      padding: 0.5rem;
      border: 1px solid var(--border);
      text-align: center;
    }
    .mapping-table th {
      background: #1e3a5f;
      color: white;
      font-weight: 600;
      white-space: nowrap;
    }
    .mapping-table th.row-header {
      background: #475569;
      text-align: left;
      min-width: 120px;
    }
    .mapping-table td.row-label {
      background: var(--bg);
      font-weight: 500;
      text-align: left;
    }
    .mapping-table input[type="checkbox"] {
      width: 18px;
      height: 18px;
      cursor: pointer;
      accent-color: #667eea;
    }
    .mapping-table tr:hover td {
      background: rgba(102, 126, 234, 0.05);
    }
    .mapping-group-header {
      background: #1e293b !important;
      color: #94a3b8 !important;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    
    /* Tablo Checkbox Stilleri (Sorular Sekmesi) */
    .table-cb-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }
    .table-cb {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.3rem 0.6rem;
      background: var(--bg);
      border: 2px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.75rem;
      font-weight: 600;
      transition: all 0.15s;
      user-select: none;
    }
    .table-cb input { display: none; }
    .table-cb span { color: var(--text); }
    .table-cb:hover { border-color: var(--cb-color, #667eea); }
    .table-cb.selected {
      background: var(--cb-color, #667eea);
      border-color: var(--cb-color, #667eea);
    }
    .table-cb.selected span { color: white; }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
</head>
<body>
<!-- Loading Overlay -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">Hesaplanıyor...</div>
  <div class="loading-progress"><div class="loading-progress-bar"></div></div>
</div>

<!-- Save Draft Modal -->
<div class="modal-overlay" id="saveDraftModal">
  <div class="modal">
    <div class="modal-header">
      <span>💾 Taslak Kaydet</span>
      <button class="modal-close" onclick="closeSaveDraftModal()">&times;</button>
    </div>
    <div class="modal-body">
      <label style="display:block;margin-bottom:0.5rem;font-weight:500;">Taslak Adı</label>
      <input type="text" id="draftName" placeholder="Örn: Vize Sonrası Değerlendirme" style="width:100%;">
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary btn-sm" onclick="closeSaveDraftModal()">İptal</button>
      <button class="btn btn-primary btn-sm" onclick="confirmSaveDraft()">Kaydet</button>
    </div>
  </div>
</div>

<!-- Student Report Modal -->
<div class="modal-overlay" id="studentReportModal">
  <div class="modal" style="max-width:900px;max-height:90vh;">
    <div class="modal-header">
      <span id="studentReportTitle">👤 Öğrenci Raporu</span>
      <button class="modal-close" onclick="closeStudentReportModal()">&times;</button>
    </div>
    <div class="modal-body" style="max-height:70vh;overflow-y:auto;">
      <div id="studentReportContent"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary btn-sm" onclick="closeStudentReportModal()">Kapat</button>
      <button class="btn btn-primary btn-sm" onclick="window.print()">🖨️ Yazdır</button>
    </div>
  </div>
</div>

<header class="main-header">
  <div class="header-content">
    <div class="header-brand">
      <div class="brand-logo">
        <img src="/assets/logo.png" alt="Logo" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 80 80%22><rect fill=%22%23667eea%22 width=%2280%22 height=%2280%22 rx=%2216%22/><text x=%2240%22 y=%2245%22 text-anchor=%22middle%22 fill=%22white%22 font-size=%2220%22 font-weight=%22bold%22>AX</text></svg>'">
      </div>
      <div class="brand-text">
        <h1>Hatay Mustafa Kemal Universitesi</h1>
        <span>Akreditasyon Raporlama Sistemi</span>
      </div>
    </div>
    <div id="user-section" class="header-user"></div>
  </div>
</header>
<div class="container">
"""

HTML_FOOT = """
</div>

<!-- Nasıl Hesaplanıyor Modal -->
<div id="helpModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:9999; overflow:auto;">
  <div style="background:var(--card); max-width:900px; margin:2rem auto; border-radius:16px; max-height:90vh; overflow:auto; box-shadow:0 25px 50px rgba(0,0,0,0.5);">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2); padding:1.5rem 2rem; border-radius:16px 16px 0 0; display:flex; justify-content:space-between; align-items:center;">
      <h2 style="margin:0; color:white; font-size:1.5rem;">📖 Nasıl Hesaplanıyor?</h2>
      <button onclick="closeHelpModal()" style="background:rgba(255,255,255,0.2); border:none; color:white; width:36px; height:36px; border-radius:50%; cursor:pointer; font-size:1.2rem;">✕</button>
    </div>
    <div style="padding:2rem; color:var(--text);">
      
      <div style="margin-bottom:2rem;">
        <h3 style="color:#667eea; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">📊 Genel Başarı Oranı</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #667eea;">
          <p><strong>Formül:</strong></p>
          <div style="background:#1e293b; padding:0.75rem; border-radius:6px; margin:0.5rem 0; font-family:monospace; color:#10b981;">
            Genel Başarı = (Tüm Öğrencilerin Başarı %'lerinin Toplamı) / Öğrenci Sayısı
          </div>
          <p style="margin-top:0.75rem;"><strong>Her Öğrencinin Başarısı:</strong></p>
          <div style="background:#1e293b; padding:0.75rem; border-radius:6px; margin:0.5rem 0; font-family:monospace; color:#10b981;">
            Öğrenci Başarı % = (Aldığı Toplam Puan / Maksimum Puan) × 100
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Örnek: 3 öğrenci var. Başarıları: %80, %65, %72. Genel Başarı = (80+65+72)/3 = %72.3</em></p>
        </div>
      </div>

      <div style="margin-bottom:2rem;">
        <h3 style="color:#10b981; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">📚 DÖÇ (Ders Öğrenme Çıktısı) Başarısı</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #10b981;">
          <p><strong>Adım 1:</strong> Her sorunun hangi DÖÇ'ü ölçtüğü belirlenir (Soru Eşleştirme)</p>
          <p><strong>Adım 2:</strong> O DÖÇ'e ait tüm sorulardan öğrencilerin aldığı puanlar toplanır</p>
          <p><strong>Adım 3:</strong> Maksimum alınabilecek puana bölünür</p>
          <div style="background:#1e293b; padding:0.75rem; border-radius:6px; margin:0.5rem 0; font-family:monospace; color:#10b981;">
            DÖÇ-1 Başarı = Σ(DÖÇ-1 sorularından alınan puanlar) / Σ(DÖÇ-1 sorularının max puanları) × 100
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Örnek: DÖÇ-1'i ölçen S1(20p), S3(30p), S5(10p) var. Sınıf ortalaması: S1=15, S3=22, S5=8 puan. DÖÇ-1 = (15+22+8)/(20+30+10) = 45/60 = %75</em></p>
        </div>
      </div>

      <div style="margin-bottom:2rem;">
        <h3 style="color:#8b5cf6; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">🎯 PÖÇ (Program Öğrenme Çıktısı) Başarısı</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #8b5cf6;">
          <p><strong>Adım 1:</strong> Her DÖÇ'ün hangi PÖÇ'e katkı sağladığı belirlenir (DÖÇ-PÖÇ Ağırlıkları)</p>
          <p><strong>Adım 2:</strong> Ağırlıklı ortalama hesaplanır</p>
          <div style="background:#1e293b; padding:0.75rem; border-radius:6px; margin:0.5rem 0; font-family:monospace; color:#10b981;">
            PÖÇ-1 Başarı = Σ(DÖÇ_başarısı × Ağırlık) / Σ(Ağırlıklar)
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Örnek: PÖÇ-1'e DÖÇ-1(%75, ağırlık:2) ve DÖÇ-2(%60, ağırlık:1) katkı yapıyor. PÖÇ-1 = (75×2 + 60×1)/(2+1) = 210/3 = %70</em></p>
        </div>
      </div>

      <div style="margin-bottom:2rem;">
        <h3 style="color:#f59e0b; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">🧠 Bloom Taksonomisi Başarısı</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #f59e0b;">
          <p><strong>Düzeyler:</strong> Bilgi (Hatırlama) → Kavrama (Anlama) → Uygulama → Analiz → Sentez → Değerlendirme</p>
          <p style="margin-top:0.5rem;"><strong>Hesaplama:</strong> Her düzeye ait soruların başarı ortalaması</p>
          <div style="background:#1e293b; padding:0.75rem; border-radius:6px; margin:0.5rem 0; font-family:monospace; color:#10b981;">
            Uygulama Başarı = Σ(Uygulama düzeyi sorularından alınan) / Σ(Uygulama düzeyi max puanlar) × 100
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Üst düzey (Analiz, Sentez, Değerlendirme) düşük ise → Öğrenciler ezberleme yapıyor, derin öğrenme eksik</em></p>
        </div>
      </div>

      <div style="margin-bottom:2rem;">
        <h3 style="color:#06b6d4; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">📝 Harf Notu Hesaplama</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #06b6d4;">
          <p><strong>Mutlak Değerlendirme Sistemi:</strong></p>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(80px, 1fr)); gap:0.5rem; margin-top:0.75rem;">
            <span style="background:#10b981; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">AA: 90-100</span>
            <span style="background:#22c55e; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">BA: 85-89</span>
            <span style="background:#84cc16; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">BB: 75-84</span>
            <span style="background:#eab308; color:black; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">CB: 65-74</span>
            <span style="background:#f59e0b; color:black; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">CC: 55-64</span>
            <span style="background:#f97316; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">DC: 50-54</span>
            <span style="background:#ef4444; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">DD: 45-49</span>
            <span style="background:#dc2626; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">FD: 40-44</span>
            <span style="background:#991b1b; color:white; padding:0.25rem 0.5rem; border-radius:4px; text-align:center; font-size:0.85rem;">FF: 0-39</span>
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Not aralıkları Profil sayfasından özelleştirilebilir.</em></p>
        </div>
      </div>

      <div style="margin-bottom:2rem;">
        <h3 style="color:#ef4444; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">✅ Akreditasyon Başarı Kriterleri</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #ef4444;">
          <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:1rem; margin-top:0.5rem;">
            <div style="text-align:center; padding:0.75rem; background:#10b98122; border-radius:8px;">
              <div style="font-size:1.5rem;">✓</div>
              <div style="color:#10b981; font-weight:bold;">Sağlandı</div>
              <div style="color:#94a3b8; font-size:0.85rem;">≥ %70</div>
            </div>
            <div style="text-align:center; padding:0.75rem; background:#f59e0b22; border-radius:8px;">
              <div style="font-size:1.5rem;">⚠</div>
              <div style="color:#f59e0b; font-weight:bold;">Kısmen</div>
              <div style="color:#94a3b8; font-size:0.85rem;">%50 - %69</div>
            </div>
            <div style="text-align:center; padding:0.75rem; background:#ef444422; border-radius:8px;">
              <div style="font-size:1.5rem;">✗</div>
              <div style="color:#ef4444; font-weight:bold;">Sağlanmadı</div>
              <div style="color:#94a3b8; font-size:0.85rem;">< %50</div>
            </div>
          </div>
          <p style="margin-top:0.75rem; color:#94a3b8;"><em>Bu eşik değerleri akreditasyon kurumu gereksinimlerine göre Profil'den ayarlanabilir.</em></p>
        </div>
      </div>

      <div style="margin-bottom:1rem;">
        <h3 style="color:#3b82f6; margin-bottom:0.75rem; display:flex; align-items:center; gap:0.5rem;">🤖 AI Destekli Sistem Önerileri</h3>
        <div style="background:var(--bg); padding:1rem; border-radius:8px; border-left:4px solid #3b82f6;">
          <p><strong>Yapay zeka şunları analiz eder:</strong></p>
          <ul style="margin:0.5rem 0 0 1.5rem; color:#94a3b8;">
            <li>Başarısız DÖÇ, PÖÇ ve PEA'ları tespit eder</li>
            <li>Bloom taksonomisi eksikliklerini belirler</li>
            <li>Ölçülmemiş veya az ölçülmüş çıktıları saptar</li>
            <li>Her sorun için spesifik çözüm önerisi sunar</li>
            <li>Acil müdahale gerektiren alanları vurgular</li>
          </ul>
        </div>
      </div>

    </div>
  </div>
</div>

<script>
// Newline karakteri için sabit (Python escape sorunlarını önler)
const NL = String.fromCharCode(10);

function openHelpModal() {
  document.getElementById('helpModal').style.display = 'block';
  document.body.style.overflow = 'hidden';
}
function closeHelpModal() {
  document.getElementById('helpModal').style.display = 'none';
  document.body.style.overflow = 'auto';
}
document.getElementById('helpModal').addEventListener('click', function(e) {
  if (e.target === this) closeHelpModal();
});

// Ölçme bileşenleri checkbox işleme
const COMP_CONFIG = [
  { id: 'vize', code: 'C1', name: 'Vize' },
  { id: 'final', code: 'C2', name: 'Final' },
  { id: 'odev', code: 'C3', name: 'Ödev' },
  { id: 'proje', code: 'C4', name: 'Proje' },
  { id: 'quiz', code: 'C5', name: 'Quiz' },
  { id: 'lab', code: 'C6', name: 'Lab' },
  { id: 'sunum', code: 'C7', name: 'Sunum' },
  { id: 'katilim', code: 'C8', name: 'Katılım' }
];

function updateAssessments() {
  const lines = [];
  let totalWeight = 0;
  
  COMP_CONFIG.forEach(comp => {
    const checkbox = document.getElementById('comp_' + comp.id);
    const weightInput = document.getElementById('comp_' + comp.id + '_w');
    
    if (checkbox && checkbox.checked) {
      let weight = parseFloat(weightInput?.value) || 0;
      totalWeight += weight;
      lines.push(comp.code + ' | ' + comp.name + ' | ' + weight);
      
      // Checkbox card styling
      checkbox.closest('.checkbox-card').style.borderColor = '#667eea';
      checkbox.closest('.checkbox-card').style.background = 'rgba(102, 126, 234, 0.1)';
    } else if (checkbox) {
      checkbox.closest('.checkbox-card').style.borderColor = 'transparent';
      checkbox.closest('.checkbox-card').style.background = 'var(--bg)';
    }
  });
  
  // Textarea'yı güncelle
  const textarea = document.querySelector('[name="assessments_text"]');
  if (textarea && lines.length > 0) {
    textarea.value = lines.join(NL);
  }
  
  // Ağırlık uyarısı
  const warning = document.getElementById('assessmentWeightWarning');
  const totalSpan = document.getElementById('weightTotal');
  if (warning && totalSpan) {
    totalSpan.textContent = totalWeight.toFixed(2);
    if (lines.length > 0 && Math.abs(totalWeight - 1.0) > 0.01) {
      warning.style.display = 'block';
    } else {
      warning.style.display = 'none';
    }
  }
}

// Sayfa yüklendiğinde mevcut değerleri checkbox'lara yükle
function loadAssessmentsToCheckboxes() {
  const textarea = document.querySelector('[name="assessments_text"]');
  if (!textarea || !textarea.value.trim()) return;
  
  const lines = textarea.value.trim().split(NL);
  lines.forEach(line => {
    const parts = line.split('|').map(p => p.trim());
    if (parts.length < 3) return;
    
    const name = parts[1].toLowerCase();
    const weight = parseFloat(parts[2]) || 0;
    
    COMP_CONFIG.forEach(comp => {
      if (name.includes(comp.name.toLowerCase()) || name.includes(comp.id)) {
        const checkbox = document.getElementById('comp_' + comp.id);
        const weightInput = document.getElementById('comp_' + comp.id + '_w');
        if (checkbox) checkbox.checked = true;
        if (weightInput) weightInput.value = weight;
      }
    });
  });
  
  updateAssessments();
}

// Sayfa yüklendiğinde çalıştır
document.addEventListener('DOMContentLoaded', loadAssessmentsToCheckboxes);
setTimeout(loadAssessmentsToCheckboxes, 100);
</script>

<script>
// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const group = tab.closest('.box').querySelector('.tabs');
    group.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const contents = tab.closest('.box').querySelectorAll('.tab-content');
    contents.forEach(c => c.classList.remove('active'));
    document.getElementById(tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'tab-questions') rebuildAllQuestions();
    if (tab.dataset.tab === 'tab-mappings') rebuildMappingTables();
  });
});
document.querySelectorAll('.collapsible').forEach(el => {
  el.addEventListener('click', () => el.classList.toggle('collapsed'));
});

// Parse helpers - hem | hem - destekler
function parseItems(text) {
  if (!text || !text.trim()) return [];
  return text.trim().split(NL).map((line, index) => {
    line = line.trim();
    if (!line || line.length < 2) return null;
    
    // Önce | ile dene
    let parts;
    if (line.includes('|')) {
      parts = line.split('|');
    } else if (line.includes(' - ')) {
      parts = line.split(' - ');
    } else {
      // Hafta formatını dene: "1.Hafta: ..." veya "Hafta 1: ..."
      const weekMatch = line.match(/^(\\d+)\\.?\\s*[Hh]afta\\s*[:\\-]?\\s*(.+)$/);
      if (weekMatch) {
        return { id: 'H' + weekMatch[1], desc: weekMatch[2].trim() };
      }
      const weekMatch2 = line.match(/^[Hh]afta\\s*(\\d+)\\s*[:\\-]?\\s*(.+)$/);
      if (weekMatch2) {
        return { id: 'H' + weekMatch2[1], desc: weekMatch2[2].trim() };
      }
      // ID formatını dene: "DÖÇ1 açıklama" veya "PÖÇ1 açıklama"
      const idMatch = line.match(/^([A-ZÖÜÇŞĞİa-zöüçşğı]+\\d+)\\s*[:\\-\\.]*\\s*(.*)$/);
      if (idMatch) {
        return { id: idMatch[1].toUpperCase(), desc: idMatch[2].trim() || idMatch[1] };
      }
      // Hiçbiri eşleşmedi - tüm satırı ID olarak kullan
      parts = [line, ''];
    }
    const id = parts[0]?.trim();
    const desc = parts[1]?.trim() || '';
    return id ? { id, desc } : null;
  }).filter(Boolean);
}
function parseComponents(text) {
  if (!text || !text.trim()) return [];
  return text.trim().split(NL).map(line => {
    // Önce | ile dene, yoksa - ile böl
    let parts;
    if (line.includes('|')) {
      parts = line.split('|');
    } else {
      parts = line.split(' - ');
      if (parts.length < 2) parts = line.split('-');
    }
    const id = parts[0]?.trim();
    const name = parts[1]?.trim() || '';
    return id ? { id, desc: name } : null;
  }).filter(Boolean);
}
const BLOOM_LEVELS = [
  { id: 'Bilgi', desc: 'Hatırlama' },
  { id: 'Kavrama', desc: 'Anlama' },
  { id: 'Uygulama', desc: 'Uygulama' },
  { id: 'Analiz', desc: 'Çözümleme' },
  { id: 'Sentez', desc: 'Birleştirme' },
  { id: 'Değerlendirme', desc: 'Yargılama' }
];

function getBloomLevels() {
  const bloomText = document.querySelector('[name="bloom_text"]')?.value || '';
  if (!bloomText.trim()) return BLOOM_LEVELS;
  return parseItems(bloomText);
}

let questionsData = [];

function createCheckboxes(items, type, selectedValues = []) {
  if (!items || items.length === 0) return '<div class="no-items-msg">Önce verileri girin</div>';
  return items.map(item => {
    const isSelected = selectedValues.includes(item.id);
    return `<div class="cb-item ${type}-type ${isSelected ? 'selected' : ''}" data-value="${item.id}" data-type="${type}" title="${item.desc || item.id}">
      <span class="cb-box">${isSelected ? '✓' : ''}</span><span>${item.id}</span>
    </div>`;
  }).join('');
}

function createCheckboxGroup(title, items, type, color, selectedValues = []) {
  return `<div class="checkbox-group">
    <div class="checkbox-group-title"><span class="cdot" style="background:${color}"></span>${title}</div>
    <div class="checkbox-list" data-type="${type}">${createCheckboxes(items, type, selectedValues)}</div>
  </div>`;
}

function createQuestionCard(index, data = {}) {
  const num = index + 1;
  const docs = parseItems(document.querySelector('[name="docs_text"]')?.value || '');
  const comps = parseComponents(document.querySelector('[name="assessments_text"]')?.value || '');
  const blooms = getBloomLevels();
  const curricula = parseItems(document.querySelector('[name="curriculum_text"]')?.value || '');
  
  // Tablo formatında checkbox'lar oluştur
  function createTableCheckboxes(items, type, color, selected = []) {
    if (!items.length) return '<span class="text-muted" style="font-size:0.75rem;">Veri yok</span>';
    return items.map(item => {
      const isSelected = selected.includes(item.id);
      return `<label class="table-cb ${isSelected ? 'selected' : ''}" style="--cb-color:${color};">
        <input type="checkbox" ${isSelected ? 'checked' : ''} data-type="${type}" data-value="${item.id}" onchange="handleCheckboxChange(this, ${index})">
        <span>${item.id}</span>
      </label>`;
    }).join('');
  }
  
  return `<div class="question-card" data-index="${index}">
    <div class="question-header" onclick="toggleQuestion(${index})">
      <div class="question-title"><span class="num">${num}</span><span>Soru ${num}</span><span class="q-preview text-muted" style="font-weight:normal;font-size:0.75rem;"></span></div>
      <div class="question-actions">
        <button type="button" class="btn btn-sm btn-secondary" onclick="event.stopPropagation();duplicateQuestion(${index})">📋</button>
        <button type="button" class="btn btn-sm btn-danger" onclick="event.stopPropagation();removeQuestion(${index})">✕</button>
      </div>
    </div>
    <div class="question-body">
      <div class="question-row">
        <div><label style="margin-top:0">Soru ID</label><input type="text" class="q-id" value="${data.id || 'S' + num}" onchange="updateQuestionData(${index})"></div>
        <div><label style="margin-top:0">Max Puan</label><input type="number" class="q-points" value="${data.points || '10'}" min="1" onchange="updateQuestionData(${index})"></div>
      </div>
      <div class="question-row" style="grid-template-columns:1fr;">
        <div><label style="margin-top:0;font-size:0.95rem;">Metin (Opsiyonel)</label><textarea class="q-text" rows="2" style="width:100%;padding:0.7rem;font-size:0.9rem;line-height:1.4;" onchange="updateQuestionData(${index})" placeholder="Soru metni...">${data.text || ''}</textarea></div>
      </div>
      
      <div class="question-mapping-table" style="margin-top:1rem;">
        <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
          <thead>
            <tr style="background:var(--bg);">
              <th style="padding:0.5rem; text-align:left; border:1px solid var(--border); width:120px;">Eşleştirme</th>
              <th style="padding:0.5rem; text-align:left; border:1px solid var(--border);">Seçenekler</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="padding:0.5rem; border:1px solid var(--border); font-weight:600; color:#06b6d4;">📝 Ölçme Türü</td>
              <td style="padding:0.5rem; border:1px solid var(--border);">
                <div class="table-cb-row">${createTableCheckboxes(comps, 'comp', '#06b6d4', data.comp || [])}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0.5rem; border:1px solid var(--border); font-weight:600; color:#3b82f6;">📘 DÖÇ</td>
              <td style="padding:0.5rem; border:1px solid var(--border);">
                <div class="table-cb-row">${createTableCheckboxes(docs, 'doc', '#3b82f6', data.doc || [])}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0.5rem; border:1px solid var(--border); font-weight:600; color:#14b8a6;">📚 Müfredat</td>
              <td style="padding:0.5rem; border:1px solid var(--border);">
                <div class="table-cb-row">${createTableCheckboxes(curricula, 'curriculum', '#14b8a6', data.curriculum || [])}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0.5rem; border:1px solid var(--border); font-weight:600; color:#f59e0b;">🧠 Bloom</td>
              <td style="padding:0.5rem; border:1px solid var(--border);">
                <div class="table-cb-row">${createTableCheckboxes(blooms, 'bloom', '#f59e0b', data.bloom || [])}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
}

function toggleTableCb(label, index) {
  // Artık kullanılmıyor - handleCheckboxChange kullanılıyor
}

function handleCheckboxChange(checkbox, index) {
  const label = checkbox.closest('.table-cb');
  if (label) {
    if (checkbox.checked) {
      label.classList.add('selected');
    } else {
      label.classList.remove('selected');
    }
  }
  updateQuestionData(index);
}

// Checkbox click handler - event delegation
document.addEventListener('click', function(e) {
  const cbItem = e.target.closest('.cb-item');
  if (cbItem) {
    e.preventDefault();
    e.stopPropagation();
    cbItem.classList.toggle('selected');
    cbItem.querySelector('.cb-box').textContent = cbItem.classList.contains('selected') ? '✓' : '';
    const questionCard = cbItem.closest('.question-card');
    if (questionCard) updateQuestionData(parseInt(questionCard.dataset.index));
    const mappingCard = cbItem.closest('.mapping-card');
    if (mappingCard) collectAllMappings();
  }
});

function getSelectedValues(container, type) {
  const values = [];
  // Hem eski hem yeni format için
  container.querySelectorAll(`.cb-item.${type}-type.selected`).forEach(item => values.push(item.dataset.value));
  // Tablo formatı için
  container.querySelectorAll(`input[data-type="${type}"]:checked`).forEach(input => values.push(input.dataset.value));
  return [...new Set(values)]; // Tekrarları kaldır
}

function updateQuestionData(index) {
  const card = document.querySelector(`.question-card[data-index="${index}"]`);
  if (!card) return;
  questionsData[index] = {
    id: card.querySelector('.q-id')?.value || 'S' + (index + 1),
    points: card.querySelector('.q-points')?.value || '10',
    text: card.querySelector('.q-text')?.value || '',
    comp: getSelectedValues(card, 'comp'),
    doc: getSelectedValues(card, 'doc'),
    poc: getSelectedValues(card, 'poc'),
    pea: getSelectedValues(card, 'pea'),
    bloom: getSelectedValues(card, 'bloom'),
    tyc: getSelectedValues(card, 'tyc'),
    stark: getSelectedValues(card, 'stark'),
    curriculum: getSelectedValues(card, 'curriculum')
  };
  updateQuestionPreview(index);
  collectAllQuestions();
}

function updateQuestionPreview(index) {
  const card = document.querySelector(`.question-card[data-index="${index}"]`);
  if (!card) return;
  const data = questionsData[index] || {};
  const parts = [];
  if (data.doc?.length) parts.push(data.doc.join(','));
  if (data.bloom?.length) parts.push(data.bloom.join(','));
  card.querySelector('.q-preview').textContent = parts.length ? `(${parts.join(' • ')})` : '';
}

function addQuestion(data = {}) {
  const index = questionsData.length;
  questionsData.push({
    id: data.id || 'S' + (index + 1), points: data.points || '10', text: data.text || '',
    comp: data.comp || [], doc: data.doc || [], poc: data.poc || [], pea: data.pea || [],
    bloom: data.bloom || [], tyc: data.tyc || [], stark: data.stark || [], curriculum: data.curriculum || []
  });
  rebuildAllQuestions();
  collectAllQuestions();
}

function removeQuestion(index) {
  if (!confirm('Bu soruyu silmek istediğinizden emin misiniz?')) return;
  questionsData.splice(index, 1);
  questionsData.forEach((q, i) => { if (q.id.match(/^S\\d+$/)) q.id = 'S' + (i + 1); });
  rebuildAllQuestions();
  collectAllQuestions();
}

function duplicateQuestion(index) {
  const original = questionsData[index];
  if (!original) return;
  const newData = JSON.parse(JSON.stringify(original));
  newData.id = 'S' + (questionsData.length + 1);
  questionsData.push(newData);
  rebuildAllQuestions();
  collectAllQuestions();
}

function toggleQuestion(index) {
  const card = document.querySelector(`.question-card[data-index="${index}"]`);
  if (card) card.classList.toggle('collapsed');
}

function rebuildAllQuestions() {
  const container = document.getElementById('questions-container');
  if (!container) return;
  container.innerHTML = questionsData.map((data, index) => createQuestionCard(index, data)).join('');
  const summary = document.getElementById('questions-summary');
  if (summary) summary.querySelector('.count').textContent = questionsData.length;
  questionsData.forEach((_, i) => updateQuestionPreview(i));
}

// ============ YENİ TABLO BAZLI EŞLEŞTİRMELER ============

function buildDocMappingTable() {
  const container = document.getElementById('doc-mapping-table');
  if (!container) return;
  
  const docs = parseItems(document.querySelector('[name="docs_text"]')?.value || '');
  const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
  const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
  const pocs = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
  const peas = parseItems(document.querySelector('[name="peas_text"]')?.value || '');
  
  if (!docs.length) {
    container.innerHTML = '<p class="helper">Önce Çıktılar sekmesinden DÖÇ verilerini girin.</p>';
    return;
  }
  
  // Mevcut eşleştirmeleri yükle
  const docTycMap = parseMapText(document.querySelector('[name="doc_tyc_map_text"]')?.value || '');
  const docStarkMap = parseMapText(document.querySelector('[name="doc_stark_map_text"]')?.value || '');
  const docPocMap = parseMapText(document.querySelector('[name="doc_poc_weights_text"]')?.value || '');
  const docPeaMap = parseMapText(document.querySelector('[name="doc_pea_map_text"]')?.value || '');
  
  let html = '<table class="mapping-table"><thead><tr>';
  html += '<th class="row-header">DÖÇ</th>';
  
  // TYÇ başlıkları
  if (tycs.length) {
    html += `<th colspan="${tycs.length}" style="background:#2563eb;">TYÇ</th>`;
  }
  // STAR-K başlıkları
  if (starks.length) {
    html += `<th colspan="${starks.length}" style="background:#7c2d12;">STAR-K</th>`;
  }
  // PÖÇ başlıkları
  if (pocs.length) {
    html += `<th colspan="${pocs.length}" style="background:#065f46;">PÖÇ</th>`;
  }
  // PEA başlıkları
  if (peas.length) {
    html += `<th colspan="${peas.length}" style="background:#7c3aed;">PEA</th>`;
  }
  html += '</tr><tr><th></th>';
  
  // Alt başlıklar
  tycs.forEach(t => { html += `<th style="background:#3b82f6; font-size:0.7rem;">${t.id}</th>`; });
  starks.forEach(s => { html += `<th style="background:#9c4221; font-size:0.7rem;">${s.id}</th>`; });
  pocs.forEach(p => { html += `<th style="background:#047857; font-size:0.7rem;">${p.id}</th>`; });
  peas.forEach(p => { html += `<th style="background:#8b5cf6; font-size:0.7rem;">${p.id}</th>`; });
  html += '</tr></thead><tbody>';
  
  // Her DÖÇ için satır
  docs.forEach(doc => {
    html += `<tr><td class="row-label" title="${doc.text || ''}">${doc.id}</td>`;
    
    // TYÇ checkboxları
    tycs.forEach(t => {
      const checked = (docTycMap[doc.id] || []).includes(t.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateDocMapping('${doc.id}', '${t.id}', 'tyc', this.checked)"></td>`;
    });
    
    // STAR-K checkboxları
    starks.forEach(s => {
      const checked = (docStarkMap[doc.id] || []).includes(s.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateDocMapping('${doc.id}', '${s.id}', 'stark', this.checked)"></td>`;
    });
    
    // PÖÇ checkboxları
    pocs.forEach(p => {
      const checked = (docPocMap[doc.id] || []).includes(p.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateDocMapping('${doc.id}', '${p.id}', 'poc', this.checked)"></td>`;
    });
    
    // PEA checkboxları
    peas.forEach(p => {
      const checked = (docPeaMap[doc.id] || []).includes(p.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateDocMapping('${doc.id}', '${p.id}', 'pea', this.checked)"></td>`;
    });
    
    html += '</tr>';
  });
  
  html += '</tbody></table>';
  container.innerHTML = html;
}

function buildCurriculumMappingTable() {
  const container = document.getElementById('curriculum-mapping-table');
  if (!container) return;
  
  const curriculum = parseItems(document.querySelector('[name="curriculum_text"]')?.value || '');
  const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
  const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
  const pocs = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
  const peas = parseItems(document.querySelector('[name="peas_text"]')?.value || '');
  
  if (!curriculum.length) {
    container.innerHTML = '<p class="helper">Önce Çıktılar sekmesinden Müfredat verilerini girin.</p>';
    return;
  }
  
  // Mevcut eşleştirmeleri yükle
  const currTycMap = parseMapText(document.querySelector('[name="curriculum_tyc_map_text"]')?.value || '');
  const currStarkMap = parseMapText(document.querySelector('[name="curriculum_stark_map_text"]')?.value || '');
  const currPocMap = parseMapText(document.querySelector('[name="curriculum_poc_map_text"]')?.value || '');
  const currPeaMap = parseMapText(document.querySelector('[name="curriculum_pea_map_text"]')?.value || '');
  
  let html = '<table class="mapping-table"><thead><tr>';
  html += '<th class="row-header">Müfredat</th>';
  
  if (tycs.length) html += `<th colspan="${tycs.length}" style="background:#2563eb;">TYÇ</th>`;
  if (starks.length) html += `<th colspan="${starks.length}" style="background:#7c2d12;">STAR-K</th>`;
  if (pocs.length) html += `<th colspan="${pocs.length}" style="background:#065f46;">PÖÇ</th>`;
  if (peas.length) html += `<th colspan="${peas.length}" style="background:#7c3aed;">PEA</th>`;
  
  html += '</tr><tr><th></th>';
  tycs.forEach(t => { html += `<th style="background:#3b82f6; font-size:0.7rem;">${t.id}</th>`; });
  starks.forEach(s => { html += `<th style="background:#9c4221; font-size:0.7rem;">${s.id}</th>`; });
  pocs.forEach(p => { html += `<th style="background:#047857; font-size:0.7rem;">${p.id}</th>`; });
  peas.forEach(p => { html += `<th style="background:#8b5cf6; font-size:0.7rem;">${p.id}</th>`; });
  html += '</tr></thead><tbody>';
  
  curriculum.forEach(curr => {
    html += `<tr><td class="row-label" title="${curr.text || ''}">${curr.id}</td>`;
    
    tycs.forEach(t => {
      const checked = (currTycMap[curr.id] || []).includes(t.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateCurriculumMapping('${curr.id}', '${t.id}', 'tyc', this.checked)"></td>`;
    });
    starks.forEach(s => {
      const checked = (currStarkMap[curr.id] || []).includes(s.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateCurriculumMapping('${curr.id}', '${s.id}', 'stark', this.checked)"></td>`;
    });
    pocs.forEach(p => {
      const checked = (currPocMap[curr.id] || []).includes(p.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateCurriculumMapping('${curr.id}', '${p.id}', 'poc', this.checked)"></td>`;
    });
    peas.forEach(p => {
      const checked = (currPeaMap[curr.id] || []).includes(p.id) ? 'checked' : '';
      html += `<td><input type="checkbox" ${checked} onchange="updateCurriculumMapping('${curr.id}', '${p.id}', 'pea', this.checked)"></td>`;
    });
    
    html += '</tr>';
  });
  
  html += '</tbody></table>';
  container.innerHTML = html;
}

function updateDocMapping(docId, targetId, targetType, isChecked) {
  const fieldName = targetType === 'tyc' ? 'doc_tyc_map_text' : 
                    targetType === 'stark' ? 'doc_stark_map_text' :
                    targetType === 'poc' ? 'doc_poc_weights_text' : 'doc_pea_map_text';
  updateMappingField(fieldName, docId, targetId, isChecked);
}

function updateCurriculumMapping(currId, targetId, targetType, isChecked) {
  const fieldName = targetType === 'tyc' ? 'curriculum_tyc_map_text' : 
                    targetType === 'stark' ? 'curriculum_stark_map_text' :
                    targetType === 'poc' ? 'curriculum_poc_map_text' : 'curriculum_pea_map_text';
  updateMappingField(fieldName, currId, targetId, isChecked);
}

function updateMappingField(fieldName, sourceId, targetId, isChecked) {
  const field = document.querySelector(`[name="${fieldName}"]`);
  if (!field) return;
  
  const map = parseMapText(field.value);
  if (!map[sourceId]) map[sourceId] = [];
  
  if (isChecked) {
    if (!map[sourceId].includes(targetId)) map[sourceId].push(targetId);
  } else {
    map[sourceId] = map[sourceId].filter(v => v !== targetId);
  }
  
  // Map'i text'e çevir - gerçek newline kullan
  const lines = Object.entries(map)
    .filter(([k, v]) => v.length > 0)
    .map(([k, v]) => `${k} | ${v.join(', ')}`);
  field.value = lines.join(NL);
  
  // Otomatik kayıt tetikle
  if (typeof triggerAutoSave === 'function') triggerAutoSave();
}

function rebuildMappingTables() {
  buildDocMappingTable();
  buildCurriculumMappingTable();
  rebuildAllMappings(); // Eski sistemle uyumluluk
}

// ============ ESKİ SİSTEM ============

function collectAllQuestions() {
  const lines = [];
  questionsData.forEach(q => {
    // Soru ID varsa kaydet (DÖÇ zorunlu değil)
    if (q.id) {
      lines.push([
        q.id, 
        '', 
        (q.comp||[]).join(','), 
        (q.doc||[]).join(','), 
        (q.poc||[]).join(','), 
        (q.pea||[]).join(','), 
        (q.bloom||[]).join(','), 
        q.points || '10', 
        q.text || '', 
        (q.tyc||[]).join(','), 
        (q.stark||[]).join(','), 
        (q.curriculum||[]).join(',')
      ].join(' | '));
    }
  });
  const hidden = document.querySelector('[name="question_map_text"]');
  if (hidden) {
    hidden.value = lines.join(NL);
    // Otomatik kayıt tetikle
    debounceAutoSave();
  }
}

// Mappings
function createMappingCard(title, sourceItems, targetItems, sourceType, targetType, existingMap = {}) {
  if (!sourceItems?.length) return `<div class="mapping-card"><h4>${title}</h4><div class="no-items-msg">Önce kaynak verileri girin</div></div>`;
  if (!targetItems?.length) return `<div class="mapping-card"><h4>${title}</h4><div class="no-items-msg">Önce hedef verileri girin</div></div>`;
  const rows = sourceItems.map(source => {
    const selected = existingMap[source.id] || [];
    const checkboxes = targetItems.map(target => {
      const isSelected = selected.includes(target.id);
      return `<div class="cb-item ${targetType}-type ${isSelected ? 'selected' : ''}" data-value="${target.id}" data-source="${source.id}" data-map-type="${sourceType}-${targetType}">
        <span class="cb-box">${isSelected ? '✓' : ''}</span><span>${target.id}</span>
      </div>`;
    }).join('');
    return `<div class="mapping-row"><div class="mapping-source">${source.id}</div><div class="mapping-targets">${checkboxes}</div></div>`;
  }).join('');
  return `<div class="mapping-card" data-source-type="${sourceType}" data-target-type="${targetType}"><h4>${title}</h4>${rows}</div>`;
}

function parseMapText(text) {
  const map = {};
  if (!text) return map;
  // Hem \\n hem de gerçek newline karakterini destekle
  text.trim().split(NL).forEach(line => {
    const parts = line.split('|');
    if (parts.length >= 2) {
      const key = parts[0].trim();
      const values = parts[1].split(',').map(v => v.trim().split(':')[0]).filter(Boolean);
      if (key && values.length) map[key] = values;
    }
  });
  return map;
}

function rebuildAllMappings() {
  const container = document.getElementById('mappings-container');
  if (!container) return;
  const docs = parseItems(document.querySelector('[name="docs_text"]')?.value || '');
  const pocs = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
  const peas = parseItems(document.querySelector('[name="peas_text"]')?.value || '');
  const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
  const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
  const docTycMap = parseMapText(document.querySelector('[name="doc_tyc_map_text"]')?.value || '');
  const pocTycMap = parseMapText(document.querySelector('[name="poc_tyc_map_text"]')?.value || '');
  const peaStarkMap = parseMapText(document.querySelector('[name="pea_stark_map_text"]')?.value || '');
  const docPocMap = parseMapText(document.querySelector('[name="doc_poc_weights_text"]')?.value || '');
  const pocPeaMap = parseMapText(document.querySelector('[name="poc_pea_map_text"]')?.value || '');
  container.innerHTML = `
    ${createMappingCard('🔗 DÖÇ → TYÇ', docs, tycs, 'doc', 'tyc', docTycMap)}
    ${createMappingCard('🔗 PÖÇ → TYÇ', pocs, tycs, 'poc', 'tyc', pocTycMap)}
    ${createMappingCard('🔗 PEA → STAR-K', peas, starks, 'pea', 'stark', peaStarkMap)}
    ${createMappingCard('🔗 DÖÇ → PÖÇ', docs, pocs, 'doc', 'poc', docPocMap)}
    ${createMappingCard('🔗 PÖÇ → PEA', pocs, peas, 'poc', 'pea', pocPeaMap)}
  `;
  
  // Müfredat-DÖÇ eşleştirmesi
  const currDocContainer = document.getElementById('curriculum-doc-container');
  if (currDocContainer) {
    const curriculum = parseItems(document.querySelector('[name="curriculum_text"]')?.value || '');
    const currDocMap = parseMapText(document.querySelector('[name="curriculum_doc_map_text"]')?.value || '');
    currDocContainer.innerHTML = createMappingCard('📚 Müfredat → DÖÇ', curriculum, docs, 'curriculum', 'doc', currDocMap);
  }
}

function collectAllMappings() {
  collectMapping('doc', 'tyc', 'doc_tyc_map_text');
  collectMapping('doc', 'stark', 'doc_stark_map_text');
  collectMapping('doc', 'pea', 'doc_pea_map_text');
  collectMapping('poc', 'tyc', 'poc_tyc_map_text');
  collectMapping('pea', 'stark', 'pea_stark_map_text');
  collectMappingWithWeight('doc', 'poc', 'doc_poc_weights_text');
  collectMapping('poc', 'pea', 'poc_pea_map_text');
  collectCurriculumDocMapping();
}

function collectCurriculumDocMapping() {
  const map = {};
  const field = document.querySelector('[name="curriculum_doc_map_text"]');
  
  // Önce mevcut textarea değerlerini koru
  if (field && field.value) {
    field.value.trim().split(NL).forEach(line => {
      const parts = line.split('|');
      if (parts.length >= 2) {
        const key = parts[0].trim();
        const values = parts[1].split(',').map(v => v.trim()).filter(Boolean);
        if (key && values.length) map[key] = values;
      }
    });
  }
  
  // DOM'daki seçili checkbox'ları topla
  const domMap = {};
  document.querySelectorAll('.cb-item[data-map-type="curriculum-doc"].selected').forEach(item => {
    const source = item.dataset.source;
    if (!domMap[source]) domMap[source] = [];
    domMap[source].push(item.dataset.value);
  });
  
  // Görünen source'ları bul
  const visibleSources = new Set();
  document.querySelectorAll('.cb-item[data-map-type="curriculum-doc"]').forEach(item => {
    visibleSources.add(item.dataset.source);
  });
  
  // Görünen source'lar için DOM'dan al, görünmeyenler için eski değeri koru
  visibleSources.forEach(source => {
    map[source] = domMap[source] || [];
  });
  
  // Boş olmayan satırları yaz
  const lines = Object.entries(map)
    .filter(([key, values]) => values.length > 0)
    .map(([key, values]) => `${key} | ${values.join(', ')}`);
  if (field) field.value = lines.join(NL);
}

function collectMapping(sourceType, targetType, fieldName) {
  const map = {};
  
  // Önce mevcut textarea değerlerini koru (DOM'da olmayan eşleştirmeler için)
  const field = document.querySelector(`[name="${fieldName}"]`);
  if (field && field.value) {
    field.value.trim().split(NL).forEach(line => {
      const parts = line.split('|');
      if (parts.length >= 2) {
        const key = parts[0].trim();
        const values = parts[1].split(',').map(v => v.trim().split(':')[0]).filter(Boolean);
        if (key && values.length) map[key] = values;
      }
    });
  }
  
  // YENİ TABLO SİSTEMİ: #doc-mapping-table içindeki checkbox'ları topla
  const docMappingTable = document.querySelector('#doc-mapping-table table');
  if (docMappingTable && sourceType === 'doc') {
    // Tablo varsa, tablodaki checkbox'lardan değerleri al
    const docs = parseItems(document.querySelector('[name="docs_text"]')?.value || '');
    let targetItems = [];
    let targetStartIdx = 0;
    
    if (targetType === 'tyc') {
      targetItems = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
      targetStartIdx = 0;
    } else if (targetType === 'stark') {
      const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
      targetItems = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
      targetStartIdx = tycs.length;
    } else if (targetType === 'poc') {
      const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
      const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
      targetItems = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
      targetStartIdx = tycs.length + starks.length;
    } else if (targetType === 'pea') {
      const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
      const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
      const pocs = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
      targetItems = parseItems(document.querySelector('[name="peas_text"]')?.value || '');
      targetStartIdx = tycs.length + starks.length + pocs.length;
    }
    
    // Her satırı (DÖÇ) kontrol et
    const rows = docMappingTable.querySelectorAll('tbody tr');
    rows.forEach((row, rowIdx) => {
      if (rowIdx >= docs.length) return;
      const docId = docs[rowIdx].id;
      const cells = row.querySelectorAll('td');
      const selectedTargets = [];
      
      // İlgili hedef sütunlarındaki checkbox'ları kontrol et
      for (let i = 0; i < targetItems.length; i++) {
        const cellIdx = 1 + targetStartIdx + i; // +1 for row label
        if (cellIdx < cells.length) {
          const checkbox = cells[cellIdx].querySelector('input[type="checkbox"]');
          if (checkbox && checkbox.checked) {
            selectedTargets.push(targetItems[i].id);
          }
        }
      }
      
      if (selectedTargets.length > 0) {
        map[docId] = selectedTargets;
      } else {
        delete map[docId]; // Hiç seçili değilse kaldır
      }
    });
    
    // Sonucu yaz
    const lines = Object.entries(map)
      .filter(([key, values]) => values.length > 0)
      .map(([key, values]) => `${key} | ${values.join(', ')}`);
    if (field) field.value = lines.join(NL);
    return; // Yeni tablo sistemini kullandık, eski sisteme geçme
  }
  
  // ESKİ SİSTEM: .cb-item öğelerini kullan
  const domMap = {};
  document.querySelectorAll(`.cb-item[data-map-type="${sourceType}-${targetType}"].selected`).forEach(item => {
    const source = item.dataset.source;
    if (!domMap[source]) domMap[source] = [];
    domMap[source].push(item.dataset.value);
  });
  
  // DOM'da görünen source'lar için DOM değerlerini kullan
  const visibleSources = new Set();
  document.querySelectorAll(`.cb-item[data-map-type="${sourceType}-${targetType}"]`).forEach(item => {
    visibleSources.add(item.dataset.source);
  });
  
  // Görünen source'lar için DOM'dan al, görünmeyenler için eski değeri koru
  visibleSources.forEach(source => {
    map[source] = domMap[source] || [];
  });
  
  // Boş olmayan satırları yaz
  const lines = Object.entries(map)
    .filter(([key, values]) => values.length > 0)
    .map(([key, values]) => `${key} | ${values.join(', ')}`);
  if (field) field.value = lines.join(NL);
}

function collectMappingWithWeight(sourceType, targetType, fieldName) {
  const map = {};
  
  // Önce mevcut textarea değerlerini koru
  const field = document.querySelector(`[name="${fieldName}"]`);
  if (field && field.value) {
    field.value.trim().split(NL).forEach(line => {
      const parts = line.split('|');
      if (parts.length >= 2) {
        const key = parts[0].trim();
        const values = parts[1].split(',').map(v => v.trim()).filter(Boolean);
        if (key && values.length) map[key] = values;
      }
    });
  }
  
  // YENİ TABLO SİSTEMİ: #doc-mapping-table içindeki checkbox'ları topla (doc-poc için)
  const docMappingTable = document.querySelector('#doc-mapping-table table');
  if (docMappingTable && sourceType === 'doc' && targetType === 'poc') {
    const docs = parseItems(document.querySelector('[name="docs_text"]')?.value || '');
    const tycs = parseItems(document.querySelector('[name="tyc_text"]')?.value || '');
    const starks = parseItems(document.querySelector('[name="stark_text"]')?.value || '');
    const pocs = parseItems(document.querySelector('[name="pocs_text"]')?.value || '');
    const targetStartIdx = tycs.length + starks.length;
    
    // Her satırı (DÖÇ) kontrol et
    const rows = docMappingTable.querySelectorAll('tbody tr');
    rows.forEach((row, rowIdx) => {
      if (rowIdx >= docs.length) return;
      const docId = docs[rowIdx].id;
      const cells = row.querySelectorAll('td');
      const selectedTargets = [];
      
      // PÖÇ sütunlarındaki checkbox'ları kontrol et
      for (let i = 0; i < pocs.length; i++) {
        const cellIdx = 1 + targetStartIdx + i; // +1 for row label
        if (cellIdx < cells.length) {
          const checkbox = cells[cellIdx].querySelector('input[type="checkbox"]');
          if (checkbox && checkbox.checked) {
            selectedTargets.push(pocs[i].id + ':1'); // Varsayılan ağırlık 1
          }
        }
      }
      
      if (selectedTargets.length > 0) {
        map[docId] = selectedTargets;
      } else {
        delete map[docId];
      }
    });
    
    // Sonucu yaz
    const lines = Object.entries(map)
      .filter(([key, values]) => values.length > 0)
      .map(([key, values]) => `${key} | ${values.join(', ')}`);
    if (field) field.value = lines.join(NL);
    return;
  }
  
  // ESKİ SİSTEM
  const domMap = {};
  document.querySelectorAll(`.cb-item[data-map-type="${sourceType}-${targetType}"].selected`).forEach(item => {
    const source = item.dataset.source;
    if (!domMap[source]) domMap[source] = [];
    domMap[source].push(item.dataset.value + ':1');
  });
  
  // Görünen source'ları bul
  const visibleSources = new Set();
  document.querySelectorAll(`.cb-item[data-map-type="${sourceType}-${targetType}"]`).forEach(item => {
    visibleSources.add(item.dataset.source);
  });
  
  // Görünen source'lar için DOM'dan al, görünmeyenler için eski değeri koru
  visibleSources.forEach(source => {
    map[source] = domMap[source] || [];
  });
  
  // Boş olmayan satırları yaz
  const lines = Object.entries(map)
    .filter(([key, values]) => values.length > 0)
    .map(([key, values]) => `${key} | ${values.join(', ')}`);
  if (field) field.value = lines.join(NL);
}

function loadSampleData() {
  if (!confirm('Örnek veri yüklenecek. Mevcut veriler silinecek. Devam?')) return;
  document.querySelector('[name="course_code"]').value = 'BM203';
  document.querySelector('[name="course_name"]').value = 'Veri Yapıları ve Algoritmalar';
  document.querySelector('[name="program_name"]').value = 'Bilgisayar Mühendisliği';
  document.querySelector('[name="term"]').value = '2024-2025 Güz';
  document.querySelector('[name="instructor"]').value = 'Dr. Öğr. Üyesi Ahmet Yılmaz';
  document.querySelector('[name="curriculum_text"]').value = 'MUC1 - Temel veri yapılarını açıklar\\nMUC2 - Algoritma karmaşıklığını analiz eder\\nMUC3 - Problem çözme yeteneği geliştirir';
  document.querySelector('[name="tyc_text"]').value = 'TYC1 - Bilgi, Kuramsal ve uygulamalı bilgi\\nTYC2 - Beceri, Bilişsel ve uygulamalı\\nTYC3 - Yetkinlik, Bağımsız çalışabilme';
  document.querySelector('[name="stark_text"]').value = 'ST1 - Yazılım geliştirme yetkinliği\\nST2 - Analitik düşünme becerisi';
  document.querySelector('[name="docs_text"]').value = 'DÖÇ1 - Stack ve Queue yapılarını uygular\\nDÖÇ2 - Ağaç yapılarını analiz eder\\nDÖÇ3 - Sıralama algoritmalarını karşılaştırır\\nDÖÇ4 - Graf algoritmalarını uygular';
  document.querySelector('[name="pocs_text"]').value = 'PÖÇ1 - Mühendislik problemlerini çözer\\nPÖÇ2 - Algoritma tasarlama becerisi\\nPÖÇ3 - Analitik düşünme yetkinliği';
  document.querySelector('[name="peas_text"]').value = 'PEA1 - Yazılım sektöründe etkin mezunlar\\nPEA2 - Araştırma yapabilen mezunlar';
  document.querySelector('[name="assessments_text"]').value = 'C1 | Vize | 0.4\\nC2 | Final | 0.6';
  document.querySelector('[name="bloom_text"]').value = 'Bilgi - Hatırlama düzeyi\\nKavrama - Anlama düzeyi\\nUygulama - Uygulama düzeyi\\nAnaliz - Çözümleme düzeyi\\nSentez - Birleştirme düzeyi\\nDeğerlendirme - Yargılama düzeyi';
  document.querySelector('[name="curriculum_doc_map_text"]').value = 'MUC1 | DÖÇ1, DÖÇ2\\nMUC2 | DÖÇ2, DÖÇ3\\nMUC3 | DÖÇ3, DÖÇ4';
  // TÜM EŞLEMELERİ DOLDUR
  document.querySelector('[name="doc_tyc_map_text"]').value = 'DÖÇ1 | TYC1, TYC2\\nDÖÇ2 | TYC2\\nDÖÇ3 | TYC2, TYC3\\nDÖÇ4 | TYC3';
  document.querySelector('[name="poc_tyc_map_text"]').value = 'PÖÇ1 | TYC1\\nPÖÇ2 | TYC2\\nPÖÇ3 | TYC2, TYC3';
  document.querySelector('[name="pea_stark_map_text"]').value = 'PEA1 | ST1\\nPEA2 | ST1, ST2';
  document.querySelector('[name="doc_poc_weights_text"]').value = 'DÖÇ1 | PÖÇ1:2, PÖÇ2:1\\nDÖÇ2 | PÖÇ1:1, PÖÇ2:3\\nDÖÇ3 | PÖÇ2:2, PÖÇ3:2\\nDÖÇ4 | PÖÇ1:1, PÖÇ2:1, PÖÇ3:2';
  document.querySelector('[name="poc_pea_map_text"]').value = 'PÖÇ1 | PEA1\\nPÖÇ2 | PEA1, PEA2\\nPÖÇ3 | PEA2';
  
  let students = '';
  for (let i = 1; i <= 25; i++) students += `OGR${String(i).padStart(2,'0')} - Öğrenci ${i}\\n`;
  document.querySelector('[name="students_text"]').value = students.trim();
  
  // Örnek sorular - questionsData'ya ekle
  questionsData = [
    { id: 'S1', points: '10', text: 'Stack nedir?', comp: ['C1'], doc: ['DÖÇ1'], poc: ['PÖÇ1'], pea: ['PEA1'], bloom: ['Bilgi'], tyc: ['TYC1'], stark: ['ST1'], curriculum: ['MUC1'] },
    { id: 'S2', points: '15', text: 'Queue ve Stack farkı', comp: ['C1'], doc: ['DÖÇ1','DÖÇ2'], poc: ['PÖÇ1','PÖÇ2'], pea: ['PEA1'], bloom: ['Kavrama'], tyc: ['TYC1','TYC2'], stark: ['ST1'], curriculum: ['MUC1','MUC2'] },
    { id: 'S3', points: '20', text: 'Binary tree oluştur', comp: ['C1'], doc: ['DÖÇ2'], poc: ['PÖÇ2'], pea: ['PEA1'], bloom: ['Uygulama'], tyc: ['TYC2'], stark: ['ST1','ST2'], curriculum: ['MUC2'] },
    { id: 'S4', points: '15', text: 'QuickSort karmaşıklığı', comp: ['C1'], doc: ['DÖÇ3'], poc: ['PÖÇ2','PÖÇ3'], pea: ['PEA1','PEA2'], bloom: ['Analiz'], tyc: ['TYC2','TYC3'], stark: ['ST2'], curriculum: ['MUC2'] },
    { id: 'S5', points: '10', text: 'Stack uygulamaları', comp: ['C2'], doc: ['DÖÇ1','DÖÇ2'], poc: ['PÖÇ1'], pea: ['PEA1'], bloom: ['Bilgi'], tyc: ['TYC1'], stark: ['ST1'], curriculum: ['MUC1','MUC3'] },
    { id: 'S6', points: '15', text: 'Heap yapısı', comp: ['C2'], doc: ['DÖÇ2','DÖÇ3'], poc: ['PÖÇ2'], pea: ['PEA1'], bloom: ['Kavrama'], tyc: ['TYC1','TYC2'], stark: ['ST1'], curriculum: ['MUC2','MUC3'] },
    { id: 'S7', points: '25', text: 'MergeSort implement et', comp: ['C2'], doc: ['DÖÇ3'], poc: ['PÖÇ2','PÖÇ3'], pea: ['PEA2'], bloom: ['Uygulama'], tyc: ['TYC2','TYC3'], stark: ['ST1','ST2'], curriculum: ['MUC2','MUC3'] },
    { id: 'S8', points: '20', text: 'Graf traversal', comp: ['C2'], doc: ['DÖÇ4'], poc: ['PÖÇ1','PÖÇ2','PÖÇ3'], pea: ['PEA1','PEA2'], bloom: ['Analiz'], tyc: ['TYC3'], stark: ['ST2'], curriculum: ['MUC3'] },
    { id: 'S9', points: '20', text: 'Algoritma tasarla', comp: ['C2'], doc: ['DÖÇ3','DÖÇ4'], poc: ['PÖÇ3'], pea: ['PEA2'], bloom: ['Sentez'], tyc: ['TYC3'], stark: ['ST2'], curriculum: ['MUC2','MUC3'] },
    { id: 'S10', points: '25', text: 'Karşılaştırmalı analiz', comp: ['C2'], doc: ['DÖÇ1','DÖÇ2','DÖÇ3','DÖÇ4'], poc: ['PÖÇ1','PÖÇ2','PÖÇ3'], pea: ['PEA1','PEA2'], bloom: ['Değerlendirme'], tyc: ['TYC1','TYC2','TYC3'], stark: ['ST1','ST2'], curriculum: ['MUC1','MUC2','MUC3'] }
  ];
  rebuildAllQuestions();
  collectAllQuestions();
  
  let scores = '';
  const maxScores = [10, 15, 20, 15, 10, 15, 25, 20, 20, 25];
  for (let i = 1; i <= 25; i++) {
    const sid = `OGR${String(i).padStart(2,'0')}`;
    for (let q = 1; q <= 10; q++) {
      const max = maxScores[q-1];
      const score = Math.round(max * (0.4 + Math.random() * 0.55));
      scores += `${sid}, S${q}, ${score}\\n`;
    }
  }
  document.querySelector('[name="scores_text"]').value = scores.trim();
}
function clearAllData() {
  if (!confirm('Tüm veriler silinecek (eşleştirmeler, sorular, öğrenciler dahil). Emin misiniz?')) return;
  
  // Tüm text input ve textarea'ları temizle
  document.querySelectorAll('input[type="text"], textarea').forEach(el => el.value = '');
  
  // Hidden alanları da temizle
  const hiddenFields = [
    'doc_tyc_map_text', 'poc_tyc_map_text', 'pea_stark_map_text',
    'doc_poc_weights_text', 'poc_pea_map_text', 'curriculum_doc_map_text',
    'doc_stark_map_text', 'doc_pea_map_text',
    'curriculum_tyc_map_text', 'curriculum_stark_map_text',
    'curriculum_poc_map_text', 'curriculum_pea_map_text',
    'question_map_text', 'scores_text', 'students_text'
  ];
  hiddenFields.forEach(name => {
    const field = document.querySelector(`[name="${name}"]`);
    if (field) field.value = '';
  });
  
  // Soru verilerini temizle
  questionsData = [];
  rebuildAllQuestions();
  
  // Eşleştirme tablolarını yeniden oluştur (boş olarak)
  setTimeout(() => {
    rebuildMappingTables();
    rebuildAllMappings();
  }, 100);
  
  // Varsayılan Bloom değerlerini koru
  const bloomField = document.querySelector('[name="bloom_text"]');
  if (bloomField && !bloomField.value) {
    bloomField.value = 'Bilgi\\nKavrama\\nUygulama\\nAnaliz\\nSentez\\nDeğerlendirme';
  }
  
  // Varsayılan eşik değerlerini koru
  const metField = document.querySelector('[name="thresholds_met"]');
  const partialField = document.querySelector('[name="thresholds_partial"]');
  if (metField && !metField.value) metField.value = '70';
  if (partialField && !partialField.value) partialField.value = '50';
  
  alert('Tüm veriler temizlendi.');
}

async function loadExcelGrades() {
  try {
    const res = await fetch('/load-grades');
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    if (data.students_text) document.querySelector('[name="students_text"]').value = data.students_text;
    if (data.scores_text) document.querySelector('[name="scores_text"]').value = data.scores_text;
  } catch (e) {
    alert('Excel okunamadı: ' + e);
  }
}

// ============ LOADING SPINNER ============
function showLoading(text = 'Hesaplanıyor...') {
  const overlay = document.getElementById('loadingOverlay');
  overlay.querySelector('.loading-text').textContent = text;
  overlay.classList.add('active');
}

function hideLoading() {
  document.getElementById('loadingOverlay').classList.remove('active');
}

// Form submit'te loading göster
document.getElementById('mainForm')?.addEventListener('submit', function(e) {
  // Hidden textarea'ları güncelle
  collectAllQuestions();
  collectAllMappings();
  
  // Validation
  if (!validateForm()) {
    e.preventDefault();
    return;
  }
  showLoading('Rapor hesaplanıyor...');
});

// ============ FORM VALIDATION ============
function validateForm() {
  let isValid = true;
  const errors = [];
  
  // Program adı kontrolü
  const programName = document.querySelector('[name="program_name"]');
  if (programName && !programName.value.trim()) {
    showFieldError(programName, 'Program adı zorunludur');
    isValid = false;
  } else if (programName) {
    clearFieldError(programName);
  }
  
  // Ölçme bileşenleri kontrolü
  const assessments = document.querySelector('[name="assessments_text"]');
  if (assessments && !assessments.value.trim()) {
    showFieldError(assessments, 'En az bir ölçme bileşeni gerekli');
    isValid = false;
  } else if (assessments) {
    clearFieldError(assessments);
  }
  
  // DÖÇ kontrolü
  const docs = document.querySelector('[name="docs_text"]');
  if (docs && !docs.value.trim()) {
    showFieldError(docs, 'En az bir DÖÇ tanımlanmalı');
    isValid = false;
  } else if (docs) {
    clearFieldError(docs);
  }
  
  if (!isValid) {
    const firstError = document.querySelector('.input-error');
    if (firstError) firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  
  return isValid;
}

function showFieldError(field, message) {
  field.classList.add('input-error');
  let errorEl = field.nextElementSibling;
  if (!errorEl || !errorEl.classList.contains('field-error')) {
    errorEl = document.createElement('div');
    errorEl.className = 'field-error';
    field.parentNode.insertBefore(errorEl, field.nextSibling);
  }
  errorEl.textContent = message;
  errorEl.classList.add('show');
}

function clearFieldError(field) {
  field.classList.remove('input-error');
  const errorEl = field.nextElementSibling;
  if (errorEl && errorEl.classList.contains('field-error')) {
    errorEl.classList.remove('show');
  }
}

// ============ AUTO-SAVE ============
let autoSaveTimer = null;
let lastSavedData = '';

function initAutoSave() {
  const form = document.getElementById('mainForm');
  if (!form) return;
  
  const inputs = form.querySelectorAll('input, textarea, select');
  inputs.forEach(input => {
    input.addEventListener('change', debounceAutoSave);
    input.addEventListener('input', debounceAutoSave);
  });
  
  updateAutoSaveStatus('idle');
}

function debounceAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  updateAutoSaveStatus('pending');
  autoSaveTimer = setTimeout(performAutoSave, 3000);
}

async function performAutoSave() {
  const form = document.getElementById('mainForm');
  if (!form) return;
  
  const formData = new FormData(form);
  const data = {};
  formData.forEach((value, key) => { data[key] = value; });
  
  const dataStr = JSON.stringify(data);
  if (dataStr === lastSavedData) return;
  
  updateAutoSaveStatus('saving');
  
  try {
    const res = await fetch('/api/autosave', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: dataStr
    });
    
    if (res.ok) {
      lastSavedData = dataStr;
      updateAutoSaveStatus('saved');
    } else {
      updateAutoSaveStatus('error');
    }
  } catch (e) {
    updateAutoSaveStatus('error');
  }
}

function updateAutoSaveStatus(status) {
  const indicator = document.getElementById('autosaveIndicator');
  if (!indicator) return;
  
  const dot = indicator.querySelector('.autosave-dot');
  const text = indicator.querySelector('.autosave-text');
  
  dot.className = 'autosave-dot';
  
  switch(status) {
    case 'saving':
      dot.classList.add('saving');
      text.textContent = 'Kaydediliyor...';
      break;
    case 'saved':
      dot.classList.add('saved');
      text.textContent = 'Kaydedildi';
      setTimeout(() => updateAutoSaveStatus('idle'), 3000);
      break;
    case 'error':
      dot.classList.add('error');
      text.textContent = 'Kayıt hatası';
      break;
    default:
      text.textContent = 'Otomatik kayıt aktif';
  }
}

// ============ TASLAK YÖNETİMİ ============
function openSaveDraftModal() {
  document.getElementById('saveDraftModal').classList.add('active');
  document.getElementById('draftName').focus();
}

function closeSaveDraftModal() {
  document.getElementById('saveDraftModal').classList.remove('active');
}

async function confirmSaveDraft() {
  const name = document.getElementById('draftName').value.trim() || 
               'Taslak ' + new Date().toLocaleDateString('tr-TR');
  
  // Önce tüm verileri topla
  collectAllMappings();
  collectAllQuestions();
  
  const form = document.getElementById('mainForm');
  const formData = new FormData(form);
  const data = {};
  formData.forEach((value, key) => { data[key] = value; });
  
  showLoading('Taslak kaydediliyor...');
  
  try {
    const res = await fetch('/api/drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, data })
    });
    
    if (res.ok) {
      closeSaveDraftModal();
      location.reload();
    } else {
      alert('Taslak kaydedilemedi');
    }
  } catch (e) {
    alert('Hata: ' + e);
  } finally {
    hideLoading();
  }
}

async function loadDraft(id) {
  showLoading('Taslak yükleniyor...');
  try {
    const res = await fetch('/api/drafts/' + id);
    const result = await res.json();
    
    if (result.data) {
      Object.entries(result.data).forEach(([key, value]) => {
        const field = document.querySelector('[name="' + key + '"]');
        if (field) field.value = value;
      });
      // Soruları yeniden yükle
      loadQuestionsFromText();
      // Eşlemeleri yeniden oluştur
      rebuildAllMappings();
    }
    hideLoading();
  } catch (e) {
    alert('Taslak yüklenemedi: ' + e);
    hideLoading();
  }
}

async function deleteDraft(id) {
  if (!confirm('Bu taslağı silmek istediğinize emin misiniz?')) return;
  
  try {
    const res = await fetch('/api/drafts/' + id, { method: 'DELETE' });
    if (res.ok) {
      // Sidebar'dan öğeyi kaldır
      const item = document.querySelector(`.sidebar-item[data-type="draft"][data-id="${id}"]`);
      if (item) item.remove();
    } else {
      alert('Silme işlemi başarısız');
    }
  } catch (e) {
    alert('Silinemedi: ' + e);
  }
}

// ============ RAPOR GEÇMİŞİ ============
async function deleteReportConfirm(id) {
  if (!confirm('Bu raporu silmek istediğinize emin misiniz?')) return;
  
  try {
    const res = await fetch('/api/reports/' + id, { method: 'DELETE' });
    if (res.ok) {
      // Sidebar'dan öğeyi kaldır
      const item = document.querySelector(`.sidebar-item[data-type="report"][data-id="${id}"]`);
      if (item) item.remove();
    } else {
      alert('Silme işlemi başarısız');
    }
  } catch (e) {
    alert('Silinemedi: ' + e);
  }
}

// ============ SIDEBAR TOGGLE ============
function toggleSidebar(header) {
  header.classList.toggle('collapsed');
  const body = header.nextElementSibling;
  if (body) body.classList.toggle('collapsed');
}

// ============ INIT ============
document.addEventListener('DOMContentLoaded', function() {
  initAutoSave();
  loadQuestionsFromText();
  // Eşleşmeleri de yükle (biraz gecikmeyle, DOM hazır olsun)
  setTimeout(() => {
    rebuildAllMappings();
    rebuildMappingTables(); // Yeni tablo bazlı eşleştirmeleri de yükle
  }, 100);
});

// Sayfa yüklendiğinde question_map_text'ten soruları yükle
function loadQuestionsFromText() {
  const hidden = document.querySelector('[name="question_map_text"]');
  if (!hidden || !hidden.value.trim()) return;
  
  const lines = hidden.value.trim().split(NL).filter(ln => ln.trim());
  questionsData = [];
  
  lines.forEach(line => {
    const parts = line.split('|').map(p => p.trim());
    if (parts.length >= 8) {
      questionsData.push({
        id: parts[0] || '',
        week: parts[1] || '',
        comp: parts[2] ? parts[2].split(',').map(s => s.trim()).filter(s => s) : [],
        doc: parts[3] ? parts[3].split(',').map(s => s.trim()).filter(s => s) : [],
        poc: parts[4] ? parts[4].split(',').map(s => s.trim()).filter(s => s) : [],
        pea: parts[5] ? parts[5].split(',').map(s => s.trim()).filter(s => s) : [],
        bloom: parts[6] ? parts[6].split(',').map(s => s.trim()).filter(s => s) : [],
        points: parts[7] || '10',
        text: parts[8] || '',
        tyc: parts[9] ? parts[9].split(',').map(s => s.trim()).filter(s => s) : [],
        stark: parts[10] ? parts[10].split(',').map(s => s.trim()).filter(s => s) : [],
        curriculum: parts[11] ? parts[11].split(',').map(s => s.trim()).filter(s => s) : []
      });
    }
  });
  
  if (questionsData.length > 0) {
    rebuildAllQuestions();
  }
}

// ============ EXCEL IMPORT FONKSİYONLARI ============
function importStudentsFromExcel(input) {
  const file = input.files[0];
  if (!file) return;
  
  showLoading('Excel dosyası okunuyor...');
  
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, { type: 'array' });
      
      // Öğrenci listesi sayfasını bul - ismine göre veya ilk sayfa
      let sheetName = workbook.SheetNames[0];
      for (const name of workbook.SheetNames) {
        const lower = name.toLowerCase();
        if (lower.includes('öğrenci') || lower.includes('ogrenci') || lower.includes('liste') || lower.includes('student')) {
          sheetName = name;
          break;
        }
      }
      console.log('Öğrenci listesi sayfası:', sheetName);
      
      const sheet = workbook.Sheets[sheetName];
      const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });
      
      // Boş satırları atla, başlık satırını bul
      let headerRowIdx = -1;
      let idCol = 0, adCol = -1, soyadCol = -1, durumCol = -1;
      
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        if (!row || row.length < 2) continue;
        
        // Başlık satırını bul
        const cells = row.map(c => String(c || '').toLowerCase().trim());
        
        for (let j = 0; j < cells.length; j++) {
          const c = cells[j];
          if (c.includes('numara') || c === 'no' || c === 'id' || c.includes('öğrenci no')) {
            idCol = j;
            headerRowIdx = i;
          }
          if (c === 'ad' || c === 'isim' || c === 'name') adCol = j;
          if (c === 'soyad' || c === 'soyadı' || c === 'surname') soyadCol = j;
          if (c.includes('durum') || c === 'status') durumCol = j;
        }
        
        if (headerRowIdx >= 0) break;
      }
      
      // Başlık bulunamadıysa ilk satırı başlık say
      if (headerRowIdx < 0) {
        headerRowIdx = 0;
        const firstRow = rows[0] || [];
        if (firstRow.length >= 2) {
          adCol = 1;
        }
      }
      
      const lines = [];
      const startRow = headerRowIdx + 1;
      
      for (let i = startRow; i < rows.length; i++) {
        const row = rows[i];
        if (!row || !row[idCol]) continue;
        
        const studentId = String(row[idCol]).trim();
        if (!studentId) continue;
        
        // Ad ve Soyad birleştir
        let name = '';
        if (adCol >= 0 && soyadCol >= 0) {
          const ad = String(row[adCol] || '').trim();
          const soyad = String(row[soyadCol] || '').trim();
          name = (ad + ' ' + soyad).trim();
        } else if (adCol >= 0) {
          name = String(row[adCol] || '').trim();
        } else {
          name = String(row[idCol + 1] || '').trim();
        }
        
        // Durum kontrolü
        let status = '';
        if (durumCol >= 0) {
          status = String(row[durumCol] || '').trim().toUpperCase();
        }
        
        if (studentId && name) {
          if (status === 'GR' || status === 'DZ' || status === 'GİRMEDİ') {
            lines.push(studentId + ' - ' + name + ' - GR');
          } else {
            lines.push(studentId + ' - ' + name);
          }
        }
      }
      
      if (lines.length > 0) {
        document.querySelector('[name="students_text"]').value = lines.join(NL);
        const grCount = lines.filter(l => l.includes(' - GR')).length;
        let msg = '✅ ' + lines.length + ' öğrenci başarıyla yüklendi!';
        if (grCount > 0) msg += '\\n(' + grCount + ' öğrenci derse girmemiş olarak işaretlendi)';
        alert(msg);
      } else {
        alert('⚠️ Excel dosyasında geçerli öğrenci verisi bulunamadı.');
      }
    } catch (err) {
      alert('❌ Excel okuma hatası: ' + err.message);
    } finally {
      hideLoading();
      input.value = '';
    }
  };
  reader.readAsArrayBuffer(file);
}

function importScoresFromExcel(input) {
  const file = input.files[0];
  if (!file) return;
  
  showLoading('Not dosyası okunuyor...');
  
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, { type: 'array' });
      
      // Notlar sayfasını bul - ismine göre veya ikinci sayfa (yoksa ilk)
      let sheetName = workbook.SheetNames.length > 1 ? workbook.SheetNames[1] : workbook.SheetNames[0];
      for (const name of workbook.SheetNames) {
        const lower = name.toLowerCase();
        if (lower.includes('not') || lower.includes('puan') || lower.includes('score') || lower.includes('grade')) {
          sheetName = name;
          break;
        }
      }
      console.log('Notlar sayfası:', sheetName);
      
      const sheet = workbook.Sheets[sheetName];
      const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });
      
      // Boş satırları atla, başlık satırını bul
      let headerRowIdx = 0;
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        if (row && row.length > 2) {
          headerRowIdx = i;
          break;
        }
      }
      
      if (headerRowIdx >= rows.length - 1) {
        alert('⚠️ Excel dosyasında yeterli veri yok.');
        hideLoading();
        return;
      }
      
      const headers = rows[headerRowIdx];
      const questionCols = []; // {colIdx, qid}
      
      // Atlanacak kelimeler
      const skipWords = ['numara', 'no', 'id', 'ad', 'soyad', 'isim', 'durum', 'status', 'name', 'öğrenci', 'toplam', 'total', 'ortalama', 'average', 'sum'];
      
      for (let i = 0; i < headers.length; i++) {
        const hVal = headers[i];
        if (hVal === null || hVal === undefined) continue;
        
        const hStr = String(hVal).trim().toLowerCase();
        
        // Atlanacak kelimeleri kontrol et
        if (skipWords.some(w => hStr.includes(w))) continue;
        
        // Sayısal değer mi kontrol et (number tipi veya sayıya çevrilebilir string)
        if (typeof hVal === 'number') {
          // Number tipinde - S prefix ekle
          questionCols.push({ colIdx: i, qid: 'S' + Math.floor(hVal) });
        } else {
          const hTrim = String(hVal).trim();
          // Sadece rakamlardan oluşuyor mu?
          if (/^[0-9]+$/.test(hTrim)) {
            questionCols.push({ colIdx: i, qid: 'S' + parseInt(hTrim) });
          } else if (/^[0-9]+\\.[0-9]+$/.test(hTrim)) {
            questionCols.push({ colIdx: i, qid: 'S' + Math.floor(parseFloat(hTrim)) });
          } else if (/^[SsQq][0-9]+$/.test(hTrim)) {
            questionCols.push({ colIdx: i, qid: hTrim.toUpperCase() });
          }
        }
      }
      
      if (questionCols.length === 0) {
        alert('⚠️ Başlık satırında soru sütunu bulunamadı.');
        hideLoading();
        return;
      }
      
      // Öğrenci ID sütununu bul
      let studentIdCol = 0;
      for (let i = 0; i < headers.length; i++) {
        const h = String(headers[i] || '').toLowerCase();
        if (h.includes('numara') || h.includes('no') || h === 'id' || h.includes('öğrenci')) {
          studentIdCol = i;
          break;
        }
      }
      
      const lines = [];
      for (let i = headerRowIdx + 1; i < rows.length; i++) {
        const row = rows[i];
        if (!row || !row[studentIdCol]) continue;
        
        const studentId = String(row[studentIdCol]).trim();
        if (!studentId) continue;
        
        for (const qc of questionCols) {
          const score = row[qc.colIdx];
          if (score === undefined || score === null || score === '') continue;
          
          const scoreStr = String(score).trim().toUpperCase();
          if (scoreStr === '-' || scoreStr === 'GR' || scoreStr === 'DZ' || scoreStr === 'NAN') continue;
          
          const numScore = parseFloat(score);
          if (!isNaN(numScore)) {
            lines.push(studentId + ', ' + qc.qid + ', ' + numScore);
          }
        }
      }
      
      if (lines.length > 0) {
        document.querySelector('[name="scores_text"]').value = lines.join(NL);
        const uniqueStudents = new Set(lines.map(l => l.split(',')[0].trim())).size;
        alert('✅ ' + uniqueStudents + ' öğrenci için ' + lines.length + ' not yüklendi!\\n\\nSorular: ' + questionCols.map(q => q.qid).join(', '));
      } else {
        alert('⚠️ Excel dosyasında geçerli not verisi bulunamadı.');
      }
    } catch (err) {
      alert('❌ Excel okuma hatası: ' + err.message);
    } finally {
      hideLoading();
      input.value = '';
    }
  };
  reader.readAsArrayBuffer(file);
}

// ============ ÖĞRENCİ RAPORU ============
function openStudentReportModal(studentId, studentName) {
  const modal = document.getElementById('studentReportModal');
  if (modal) {
    document.getElementById('studentReportTitle').textContent = studentName + ' - Bireysel Rapor';
    document.getElementById('studentReportContent').innerHTML = '<div style="text-align:center;padding:2rem;"><div class="spinner"></div><p>Rapor yükleniyor...</p></div>';
    modal.classList.add('active');
    
    fetch('/api/student-report/' + encodeURIComponent(studentId), {
      credentials: 'same-origin'
    })
      .then(res => {
        if (!res.ok) {
          throw new Error('HTTP ' + res.status);
        }
        return res.text();
      })
      .then(text => {
        try {
          const data = JSON.parse(text);
          if (data.error) {
            document.getElementById('studentReportContent').innerHTML = '<div class="alert alert-danger"><strong>Hata:</strong> ' + data.error + (data.detail ? '<pre style="font-size:0.7rem;margin-top:1rem;white-space:pre-wrap;">' + data.detail + '</pre>' : '') + '</div>';
          } else {
            document.getElementById('studentReportContent').innerHTML = data.html;
          }
        } catch(parseErr) {
          document.getElementById('studentReportContent').innerHTML = '<div class="alert alert-danger"><strong>JSON Parse Hatası:</strong><pre style="font-size:0.7rem;">' + text.substring(0, 500) + '</pre></div>';
        }
      })
      .catch(e => {
        document.getElementById('studentReportContent').innerHTML = '<div class="alert alert-danger">Rapor yüklenemedi: ' + e.message + '</div>';
      });
  }
}

function closeStudentReportModal() {
  const modal = document.getElementById('studentReportModal');
  if (modal) modal.classList.remove('active');
}

// ============ DERS DEĞİŞTİRME FONKSİYONU ============

function switchCourse(courseCode) {
  if (!courseCode) return;
  
  console.log('[switchCourse] Ders değiştiriliyor:', courseCode);
  
  // Önce sunucuya bildir (user tablosunu güncelle), sonra sayfayı yenile
  fetch('/api/switch-course', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_code: courseCode })
  })
  .then(res => {
    console.log('[switchCourse] API response status:', res.status);
    return res.json();
  })
  .then(data => {
    console.log('[switchCourse] API response:', data);
    if (data.success) {
      console.log('[switchCourse] Başarılı, sayfa yenileniyor...');
      window.location.reload();
    } else {
      console.error('[switchCourse] API hatası:', data.error);
      alert('Ders değiştirme hatası: ' + (data.error || 'Bilinmeyen hata'));
      window.location.reload();
    }
  })
  .catch(err => {
    console.error('[switchCourse] Fetch hatası:', err);
    window.location.reload();
  });
}

// ============ EXCEL IMPORT FONKSİYONLARI ============



</script>
</body>
</html>
"""


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def status_class(st: str) -> str:
    if "Sağlandı" in st and "Sağlanmadı" not in st:
        return "badge-success"
    if "Kısmen" in st:
        return "badge-warning"
    if "Sağlanmadı" in st:
        return "badge-danger"
    return ""


def _lines_to_list(text: str) -> List[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _smart_split(line: str, count: int) -> List[str]:
    """Hem | hem - ayırıcıyı destekle. Önce | dene, yoksa - ile böl."""
    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
    else:
        # İlk tire'yi ayırıcı olarak kullan (maxsplit ile)
        parts = [p.strip() for p in line.split(" - ", count - 1)]
        if len(parts) < count:
            # Boşluksuz tire de dene
            parts = [p.strip() for p in line.split("-", count - 1)]
    return parts


def _split_required(line: str, sep: str, count: int, label: str) -> List[str]:
    # Akıllı split kullan - hem | hem - destekle
    parts = _smart_split(line, count)
    if len(parts) < count:
        raise ValueError(f"{label} satırı eksik: '{line}'")
    return parts[:count]


def parse_docs(text: str) -> List[Dict[str, str]]:
    out = []
    counter = 1
    for ln in _lines_to_list(text):
        # Çok kısa satırları (3 karakterden az) atla
        if len(ln.strip()) < 3:
            continue
        
        # Önce | veya - ile böl
        parts = _smart_split(ln, 2)
        
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            # Normal format: ID | Text
            did = parts[0].strip()
            txt = parts[1].strip()
        else:
            # Sadece metin var, ID otomatik oluştur
            # Eğer satır "DÖÇ1" veya "DOC1" gibi başlıyorsa, onu ID olarak kullan
            import re
            match = re.match(r'^(DÖÇ\d+|DOC\d+|D\d+)', ln.strip(), re.IGNORECASE)
            if match:
                did = match.group(1).upper()
                txt = ln.strip()[len(match.group(1)):].strip(' .-:')
                if not txt:
                    txt = f"Öğrenme Çıktısı {did}"
            else:
                did = f"DÖÇ{counter}"
                txt = ln.strip()
                counter += 1
        
        if did and txt:
            out.append({"id": did, "text": txt})
    return out

def parse_pocs(text: str) -> List[Dict[str, str]]:
    out = []
    counter = 1
    for ln in _lines_to_list(text):
        if len(ln.strip()) < 3:
            continue
        
        parts = _smart_split(ln, 2)
        
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            pid = parts[0].strip()
            txt = parts[1].strip()
        else:
            import re
            match = re.match(r'^(PÖÇ\d+|POC\d+|P\d+)', ln.strip(), re.IGNORECASE)
            if match:
                pid = match.group(1).upper()
                txt = ln.strip()[len(match.group(1)):].strip(' .-:')
                if not txt:
                    txt = f"Program Çıktısı {pid}"
            else:
                pid = f"PÖÇ{counter}"
                txt = ln.strip()
                counter += 1
        
        if pid and txt:
            out.append({"id": pid, "text": txt})
    return out

def parse_peas(text: str) -> List[Dict[str, str]]:
    out = []
    counter = 1
    for ln in _lines_to_list(text):
        if len(ln.strip()) < 3:
            continue
        
        parts = _smart_split(ln, 2)
        
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            aid = parts[0].strip()
            txt = parts[1].strip()
        else:
            import re
            match = re.match(r'^(PEA\d+|A\d+)', ln.strip(), re.IGNORECASE)
            if match:
                aid = match.group(1).upper()
                txt = ln.strip()[len(match.group(1)):].strip(' .-:')
                if not txt:
                    txt = f"Eğitim Amacı {aid}"
            else:
                aid = f"PEA{counter}"
                txt = ln.strip()
                counter += 1
        
        if aid and txt:
            out.append({"id": aid, "text": txt})
    return out

def parse_curriculum(text: str) -> List[Dict[str, str]]:
    """Müfredat (haftalık konular) parse et - özel format desteği"""
    out = []
    import re
    
    for ln in _lines_to_list(text):
        if len(ln.strip()) < 3:
            continue
        
        # Önce standart format dene: ID | Text
        parts = _smart_split(ln, 2)
        
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            cid = parts[0].strip()
            txt = parts[1].strip()
        else:
            # Hafta formatını dene: "1.Hafta: Konu" veya "Hafta 1: Konu"
            match = re.match(r'^(\d+)\.?\s*[Hh]afta\s*[:\-]?\s*(.+)$', ln.strip())
            if match:
                cid = f"H{match.group(1)}"
                txt = match.group(2).strip()
            else:
                match2 = re.match(r'^[Hh]afta\s*(\d+)\s*[:\-]?\s*(.+)$', ln.strip())
                if match2:
                    cid = f"H{match2.group(1)}"
                    txt = match2.group(2).strip()
                else:
                    # MUC formatını dene
                    match3 = re.match(r'^(MUC\d+|M\d+|H\d+)', ln.strip(), re.IGNORECASE)
                    if match3:
                        cid = match3.group(1).upper()
                        txt = ln.strip()[len(match3.group(1)):].strip(' .-:')
                    else:
                        # Hiçbiri eşleşmedi, otomatik ID ver
                        cid = f"M{len(out)+1}"
                        txt = ln.strip()
        
        if cid and txt:
            out.append({"id": cid, "text": txt})
    
    return out

def parse_assessments(text: str) -> List[Dict[str, Any]]:
    out = []
    for ln in _lines_to_list(text):
        cid, name, weight = _split_required(ln, "|", 3, "Bileşen")
        out.append({"id": cid, "name": name, "weight": float(weight)})
    return out

def parse_questions(text: str) -> List[Dict[str, Any]]:
    out = []
    for ln in _lines_to_list(text):
        parts = _smart_split(ln, 6)
        if len(parts) < 6:
            raise ValueError(f"Soru satırı eksik: '{ln}'")
        qid, comp_id, doc_field, bloom_field, maxp, qtext = parts[:6]
        # doc_ids - virgülle ayrılmış olabilir
        doc_ids = [d.strip() for d in doc_field.split(",") if d.strip()]
        # bloom_list - virgülle ayrılmış olabilir
        bloom_list = [b.strip() for b in bloom_field.split(",") if b.strip()]
        out.append({
            "id": qid, 
            "component_id": comp_id, 
            "doc_id": doc_ids[0] if doc_ids else "",
            "doc_ids": doc_ids,
            "bloom": bloom_list[0] if bloom_list else "",
            "bloom_list": bloom_list,
            "max_points": float(maxp), 
            "text": qtext
        })
    return out

def parse_students(text: str) -> List[Dict[str, str]]:
    out = []
    for ln in _lines_to_list(text):
        parts = _smart_split(ln, 3)
        if len(parts) < 2:
            raise ValueError(f"Öğrenci satırı eksik: '{ln}'")
        sid = parts[0].strip()
        name = parts[1].strip()
        status = parts[2].strip().upper() if len(parts) > 2 else ""
        out.append({"id": sid, "name": name, "status": status})
    return out

def parse_scores(text: str) -> Dict[str, Dict[str, float]]:
    scores: Dict[str, Dict[str, float]] = {}
    for ln in _lines_to_list(text):
        parts = [p.strip() for p in ln.replace(",", "|").split("|")]
        if len(parts) < 3:
            raise ValueError(f"Not satırı eksik: '{ln}'")
        sid, qid, val = parts[:3]
        scores.setdefault(sid, {})[qid] = float(val)
    return scores

def parse_doc_poc_weights(text: str) -> Dict[str, Dict[str, float]]:
    mapping: Dict[str, Dict[str, float]] = {}
    for ln in _lines_to_list(text):
        did, rest = _split_required(ln, "|", 2, "DOC->POC")
        weight_map: Dict[str, float] = {}
        for pair in [p.strip() for p in rest.split(",") if p.strip()]:
            if ":" not in pair:
                raise ValueError(f"Ağırlık hatalı: '{ln}'")
            pid, w = pair.split(":", 1)
            weight_map[pid.strip()] = float(w.strip())
        mapping[did] = weight_map
    return mapping

def parse_poc_pea_map(text: str) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for ln in _lines_to_list(text):
        pid, rest = _split_required(ln, "|", 2, "POC->PEA")
        mapping[pid] = [p.strip() for p in rest.split(",") if p.strip()]
    return mapping

def flatten_scores(scores: Dict[str, Dict[str, float]]) -> str:
    rows = []
    for sid, qmap in scores.items():
        for qid, val in qmap.items():
            rows.append(f"{sid} | {qid} | {val}")
    return "\n".join(sorted(rows))

def compute_coverage(questions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    totals = len(questions) or 1
    buckets: Dict[str, Dict[str, int]] = {"doc": {}, "poc": {}, "pea": {}, "bloom": {}, "tyc": {}, "stark": {}, "curriculum": {}}
    for q in questions:
        doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
        for did in doc_ids:
            if did:
                buckets["doc"][did] = buckets["doc"].get(did, 0) + 1
        for pid in (q.get("poc_list") or []):
            if pid:
                buckets["poc"][pid] = buckets["poc"].get(pid, 0) + 1
        for aid in (q.get("pea_list") or []):
            if aid:
                buckets["pea"][aid] = buckets["pea"].get(aid, 0) + 1
        # Bloom - hem bloom_list hem tekil bloom destekle
        blooms = q.get("bloom_list") or []
        if not blooms:
            single_bloom = q.get("bloom", "")
            if single_bloom:
                blooms = [b.strip() for b in str(single_bloom).split(",") if b.strip()]
        for b in blooms:
            if b:
                buckets["bloom"][b] = buckets["bloom"].get(b, 0) + 1
        for t in (q.get("tyc_list") or []):
            if t:
                buckets["tyc"][t] = buckets["tyc"].get(t, 0) + 1
        for s in (q.get("stark_list") or []):
            if s:
                buckets["stark"][s] = buckets["stark"].get(s, 0) + 1
        for c in (q.get("curriculum_list") or []):
            if c:
                buckets["curriculum"][c] = buckets["curriculum"].get(c, 0) + 1
    coverage = {}
    for key, data in buckets.items():
        coverage[key] = [{"id": k, "count": v, "pct": (v / totals) * 100.0} for k, v in sorted(data.items())]
    return coverage

def compute_component_coverage(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = len(questions) or 1
    bucket: Dict[str, int] = {}
    for q in questions:
        cid = q.get("component_id", "")
        if cid:
            bucket[cid] = bucket.get(cid, 0) + 1
    return [{"id": k, "count": v, "pct": (v / total) * 100.0} for k, v in sorted(bucket.items())]

def compute_question_outcomes(questions: List[Dict[str, Any]], scores: Dict[str, Dict[str, float]], cutoff_ratio: float = 0.5) -> Dict[str, Any]:
    students = list(scores.keys())
    student_count = len(students) or 1
    outcomes = {}
    wrong_questions = []
    for q in questions:
        qid = q.get("id")
        if not qid: continue
        maxp = float(q.get("max_points", 0) or 0)
        cutoff = maxp * cutoff_ratio
        correct = incorrect = 0
        total_score = 0
        for sid in students:
            val = float(scores.get(sid, {}).get(qid, 0.0))
            total_score += val
            if val >= cutoff: correct += 1
            else: incorrect += 1
        outcomes[qid] = {
            "correct": correct, "incorrect": incorrect,
            "correct_pct": (correct / student_count) * 100.0,
            "incorrect_pct": (incorrect / student_count) * 100.0,
            "avg_score": total_score / student_count,
            "max_points": maxp,
            "question": q,
        }
        if incorrect > 0:
            wrong_questions.append(q)
    wrong_coverage = compute_coverage(wrong_questions) if wrong_questions else {}
    comp_coverage = {}
    by_comp: Dict[str, List] = {}
    for q in questions:
        cid = q.get("component_id", "")
        if cid:
            by_comp.setdefault(cid, []).append(q)
    for cid, qs in by_comp.items():
        comp_coverage[cid] = compute_coverage(qs)
    return {
        "per_question": outcomes, "wrong_coverage": wrong_coverage,
        "component_coverage": compute_component_coverage(questions),
        "component_relation_coverage": comp_coverage, "student_count": student_count,
    }

def compute_student_results(questions: List[Dict[str, Any]], scores: Dict[str, Dict[str, float]], students: List[Dict[str, str]], assessments: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    results = []
    total_max = sum(float(q.get("max_points", 0)) for q in questions)
    
    # Bileşen bilgisi ve eşleştirme kontrolü
    comp_map = {c.get("id"): c for c in (assessments or [])}
    total_weight = sum(float(c.get("weight", 0)) for c in (assessments or []))
    
    # Bileşen ID -> sorular
    comp_questions = {}
    questions_with_comp = 0
    for q in questions:
        cid = q.get("component_id", "")
        if cid and cid in comp_map:
            comp_questions.setdefault(cid, []).append(q)
            questions_with_comp += 1
    
    # Ağırlıklı hesaplama sadece: bileşenler var VE sorular bileşenlerle eşleştirilmiş VE toplam ağırlık > 0
    use_weighted = (len(comp_map) > 0 and questions_with_comp > 0 and total_weight > 0)
    
    for student in students:
        sid = student.get("id", "")
        status = student.get("status", "")
        student_scores = scores.get(sid, {})
        
        # GR (Girmedi) durumu
        is_absent = status.upper() in ("GR", "DZ", "GİRMEDİ")
        
        total_score = 0.0
        pct = 0.0
        
        if is_absent:
            # GR öğrenci - puan hesaplama
            total_score = sum(float(student_scores.get(q.get("id"), 0)) for q in questions)
            pct = 0.0
            grade = "GR"
        elif use_weighted:
            # Bileşen ağırlıklı hesaplama
            weighted_pct = 0.0
            for cid, comp in comp_map.items():
                comp_qs = comp_questions.get(cid, [])
                if not comp_qs:
                    continue
                comp_max = sum(float(q.get("max_points", 0)) for q in comp_qs)
                comp_got = sum(float(student_scores.get(q.get("id"), 0)) for q in comp_qs)
                total_score += comp_got
                
                if comp_max > 0:
                    comp_pct = (comp_got / comp_max) * 100
                    weight = float(comp.get("weight", 0)) / total_weight
                    weighted_pct += comp_pct * weight
            pct = weighted_pct
            
            # Harf notu
            if pct >= 90: grade = "AA"
            elif pct >= 85: grade = "BA"
            elif pct >= 80: grade = "BB"
            elif pct >= 75: grade = "CB"
            elif pct >= 70: grade = "CC"
            elif pct >= 65: grade = "DC"
            elif pct >= 60: grade = "DD"
            elif pct >= 50: grade = "FD"
            else: grade = "FF"
        else:
            # Basit toplam hesaplama (bileşen yoksa veya eşleşme yoksa)
            total_score = sum(float(student_scores.get(q.get("id"), 0)) for q in questions)
            pct = (total_score / total_max * 100) if total_max > 0 else 0
            
            # Harf notu
            if pct >= 90: grade = "AA"
            elif pct >= 85: grade = "BA"
            elif pct >= 80: grade = "BB"
            elif pct >= 75: grade = "CB"
            elif pct >= 70: grade = "CC"
            elif pct >= 65: grade = "DC"
            elif pct >= 60: grade = "DD"
            elif pct >= 50: grade = "FD"
            else: grade = "FF"
        
        results.append({
            "id": sid, 
            "name": student.get("name", ""), 
            "total_score": total_score, 
            "max_score": total_max, 
            "pct": pct, 
            "grade": grade,
            "is_absent": is_absent
        })
    
    # Önce katılanlar (puan sırasına göre), sonra girmeyenler
    attending = [r for r in results if not r.get("is_absent")]
    absent = [r for r in results if r.get("is_absent")]
    return sorted(attending, key=lambda x: -x["pct"]) + sorted(absent, key=lambda x: x["name"])

def compute_weekly_coverage(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    weeks: Dict[str, Dict[str, Any]] = {}
    for q in questions:
        week = q.get("week", "")
        if not week: continue
        if week not in weeks:
            weeks[week] = {"week": week, "count": 0, "total_points": 0, "docs": set(), "blooms": set()}
        weeks[week]["count"] += 1
        weeks[week]["total_points"] += float(q.get("max_points", 0))
        doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
        weeks[week]["docs"].update(doc_ids)
        blooms = q.get("bloom_list") or ([q.get("bloom")] if q.get("bloom") else [])
        weeks[week]["blooms"].update(blooms)
    result = []
    for w in sorted(weeks.values(), key=lambda x: int(x["week"]) if x["week"].isdigit() else 0):
        result.append({"week": w["week"], "count": w["count"], "total_points": w["total_points"], "docs": ", ".join(sorted(w["docs"])), "blooms": ", ".join(sorted(w["blooms"]))})
    return result

def parse_generic_map(text: str, label: str) -> Dict[str, List[str]]:
    mapping = {}
    for ln in _lines_to_list(text):
        key, rest = _split_required(ln, "|", 2, label)
        mapping[key] = [p.strip() for p in rest.split(",") if p.strip()]
    return mapping

def parse_question_map(text: str) -> Dict[str, Any]:
    """Soru haritasını parse et - daha toleranslı versiyon"""
    lines = _lines_to_list(text)
    if not lines:
        return {}
    
    questions = []
    doc_poc_weights: Dict[str, Dict[str, float]] = {}
    poc_pea_map: Dict[str, List[str]] = {}
    
    for ln in lines:
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) < 2:
            continue  # Eksik satırları atla, hata verme
        
        qid = parts[0]
        if not qid:
            continue
        
        # Format: id | week | comp | doc | poc | pea | bloom | points | text | tyc | stark | curriculum
        if len(parts) >= 8:
            week = parts[1] if len(parts) > 1 else ""
            comp_id = parts[2] if len(parts) > 2 else ""
            doc_field = parts[3] if len(parts) > 3 else ""
            poc_field = parts[4] if len(parts) > 4 else ""
            pea_field = parts[5] if len(parts) > 5 else ""
            bloom_field = parts[6] if len(parts) > 6 else ""
            try:
                max_points = float(parts[7]) if len(parts) > 7 and parts[7] else 10.0
            except:
                max_points = 10.0
            qtext = parts[8] if len(parts) > 8 else ""
            tyc_field = parts[9] if len(parts) > 9 else ""
            stark_field = parts[10] if len(parts) > 10 else ""
            curriculum_field = parts[11] if len(parts) > 11 else ""
        else:
            # Eski format desteği
            week = comp_id = ""
            doc_field = parts[1] if len(parts) > 1 else ""
            bloom_field = parts[2] if len(parts) > 2 else ""
            try:
                max_points = float(parts[3]) if len(parts) > 3 and parts[3] else 10.0
            except:
                max_points = 10.0
            qtext = parts[4] if len(parts) > 4 else ""
            tyc_field = parts[5] if len(parts) > 5 else ""
            stark_field = parts[6] if len(parts) > 6 else ""
            poc_field = pea_field = curriculum_field = ""
        
        doc_ids = [d.strip() for d in doc_field.split(",") if d.strip()]
        poc_list = [p.strip() for p in poc_field.split(",") if p.strip()]
        pea_list = [p.strip() for p in pea_field.split(",") if p.strip()]
        bloom_list = [b.strip() for b in bloom_field.split(",") if b.strip()]
        tyc_list = [t.strip() for t in tyc_field.split(",") if t.strip()]
        stark_list = [s.strip() for s in stark_field.split(",") if s.strip()]
        curriculum_list = [c.strip() for c in curriculum_field.split(",") if c.strip()]
        comp_list = [c.strip() for c in comp_id.split(",") if c.strip()]
        
        questions.append({
            "id": qid, 
            "week": week, 
            "component_id": comp_list[0] if comp_list else "",
            "component_ids": comp_list,
            "doc_id": doc_ids[0] if doc_ids else "",
            "doc_ids": doc_ids,
            "bloom": bloom_list[0] if bloom_list else "",
            "bloom_list": bloom_list, 
            "max_points": max_points, 
            "text": qtext,
            "poc_list": poc_list, 
            "pea_list": pea_list,
            "tyc_list": tyc_list, 
            "stark_list": stark_list,
            "curriculum_list": curriculum_list,
        })
        
        # DÖÇ-PÖÇ ağırlık haritası
        for did in doc_ids:
            for pid in poc_list:
                doc_poc_weights.setdefault(did, {})
                doc_poc_weights[did][pid] = doc_poc_weights[did].get(pid, 0) + 1
        
        # PÖÇ-PEA haritası
        for pid in poc_list:
            if pea_list:
                poc_pea_map[pid] = sorted(list(set(poc_pea_map.get(pid, []) + pea_list)))
    
    return {"questions": questions, "doc_poc_weights": doc_poc_weights, "poc_pea_map": poc_pea_map}

def form_defaults_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    course = payload.get("course", {})
    docs = payload.get("docs", [])
    pocs = payload.get("pocs", [])
    peas = payload.get("peas", [])
    assessments = payload.get("assessments", [])
    questions = payload.get("questions", [])
    students = payload.get("students", [])
    scores = payload.get("scores", {})
    doc_poc_weights = payload.get("doc_poc_weights", {})
    poc_pea_map = payload.get("poc_pea_map", {})
    curriculum = payload.get("curriculum", [])
    tyc = payload.get("tyc", [])
    stark = payload.get("stark", [])
    doc_tyc_map = payload.get("doc_tyc_map", {})
    poc_tyc_map = payload.get("poc_tyc_map", {})
    pea_stark_map = payload.get("pea_stark_map", {})
    doc_pea_map = payload.get("doc_pea_map", {})
    doc_stark_map = payload.get("doc_stark_map", {})
    curriculum_doc_map = payload.get("curriculum_doc_map", {})
    bloom = payload.get("bloom", [])  # Bloom listesi
    
    # question_map_text oluştur
    # Format: id | week | comp | doc | poc | pea | bloom | points | text | tyc | stark | curriculum
    question_map_lines = []
    for q in questions:
        qid = q.get("id", "")
        week = q.get("week", "")
        comp = q.get("component_id", "")
        # doc_ids veya doc_id kullan
        doc_ids = q.get("doc_ids", [])
        if not doc_ids:
            doc_id = q.get("doc_id", "")
            doc_ids = [doc_id] if doc_id else []
        doc = ",".join(doc_ids) if isinstance(doc_ids, list) else str(doc_ids)
        # poc_list veya poc_ids kullan
        poc_list = q.get("poc_list", q.get("poc_ids", []))
        poc = ",".join(poc_list) if isinstance(poc_list, list) else str(poc_list)
        # pea_list veya pea_ids kullan
        pea_list = q.get("pea_list", q.get("pea_ids", []))
        pea = ",".join(pea_list) if isinstance(pea_list, list) else str(pea_list)
        # bloom
        bloom_list = q.get("bloom_list", [])
        if not bloom_list:
            bloom_single = q.get("bloom", "")
            bloom_list = [bloom_single] if bloom_single else []
        bloom_str = ",".join(bloom_list) if isinstance(bloom_list, list) else str(bloom_list)
        points = str(q.get("max_points", "10"))
        text = q.get("text", "")
        # tyc_list veya tyc_ids kullan
        tyc_list = q.get("tyc_list", q.get("tyc_ids", []))
        tyc_str = ",".join(tyc_list) if isinstance(tyc_list, list) else str(tyc_list)
        # stark_list veya stark_ids kullan
        stark_list = q.get("stark_list", q.get("stark_ids", []))
        stark_str = ",".join(stark_list) if isinstance(stark_list, list) else str(stark_list)
        # curriculum_list veya curriculum_ids kullan
        curr_list = q.get("curriculum_list", q.get("curriculum_ids", []))
        curr_str = ",".join(curr_list) if isinstance(curr_list, list) else str(curr_list)
        question_map_lines.append(f"{qid} | {week} | {comp} | {doc} | {poc} | {pea} | {bloom_str} | {points} | {text} | {tyc_str} | {stark_str} | {curr_str}")
    
    # students_text oluştur - GR durumunu da ekle
    students_lines = []
    for s in students:
        sid = s.get("id", "")
        name = s.get("name", "")
        status = s.get("status", "")
        if status and status.upper() in ("GR", "DZ", "GİRMEDİ"):
            students_lines.append(f"{sid} - {name} - GR")
        else:
            students_lines.append(f"{sid} - {name}")
    
    # bloom_text oluştur - payload'dan veya varsayılan
    bloom_text = ""
    if bloom:
        bloom_text = "\n".join([f"{b.get('id','')} - {b.get('text','')}" for b in bloom])
    else:
        # Varsayılan Bloom seviyeleri
        bloom_text = "Bilgi - Hatırlama düzeyi\nKavrama - Anlama düzeyi\nUygulama - Uygulama düzeyi\nAnaliz - Çözümleme düzeyi\nSentez - Birleştirme düzeyi\nDeğerlendirme - Yargılama düzeyi"
    
    result = {
        "course_code": course.get("course_code", ""),
        "course_name": course.get("course_name", ""),
        "program_name": course.get("program_name", ""),
        "term": course.get("term", ""),
        "instructor": course.get("instructor", ""),
        "curriculum_text": "\n".join([f"{c.get('id','')} | {c.get('text','')}" for c in curriculum]),
        "curriculum_doc_map_text": "\n".join([f"{cid} | {', '.join(map(str, docs_list))}" for cid, docs_list in curriculum_doc_map.items()]),
        "tyc_text": "\n".join([f"{t.get('id','')} | {t.get('text','')}" for t in tyc]),
        "stark_text": "\n".join([f"{s.get('id','')} | {s.get('text','')}" for s in stark]),
        "docs_text": "\n".join([f"{d.get('id','')} | {d.get('text','')}" for d in docs]),
        "pocs_text": "\n".join([f"{p.get('id','')} | {p.get('text','')}" for p in pocs]),
        "peas_text": "\n".join([f"{a.get('id','')} | {a.get('text','')}" for a in peas]),
        "assessments_text": "\n".join([f"{c.get('id','')} | {c.get('name','')} | {c.get('weight',0)}" for c in assessments]),
        "questions_text": "\n".join([f"{q.get('id','')} | {q.get('component_id','')} | {q.get('doc_id','')} | {q.get('bloom','')} | {q.get('max_points',0)} | {q.get('text','')}" for q in questions]),
        "students_text": "\n".join(students_lines),
        "scores_text": flatten_scores(scores),
        "doc_poc_weights_text": "\n".join([f"{did} | " + ", ".join([f"{pid}:{val}" for pid, val in m.items()]) for did, m in doc_poc_weights.items()]),
        "poc_pea_map_text": "\n".join([f"{pid} | " + ", ".join(plist) for pid, plist in poc_pea_map.items()]),
        "doc_tyc_map_text": "\n".join([f"{did} | " + ", ".join(vals) for did, vals in doc_tyc_map.items()]),
        "poc_tyc_map_text": "\n".join([f"{pid} | " + ", ".join(vals) for pid, vals in poc_tyc_map.items()]),
        "pea_stark_map_text": "\n".join([f"{aid} | " + ", ".join(vals) for aid, vals in pea_stark_map.items()]),
        "doc_pea_map_text": "\n".join([f"{did} | " + ", ".join(vals) for did, vals in doc_pea_map.items()]),
        "doc_stark_map_text": "\n".join([f"{did} | " + ", ".join(vals) for did, vals in doc_stark_map.items()]),
        "bloom_text": bloom_text,
        "question_map_text": "\n".join(question_map_lines),
        "thresholds_met": str(payload.get("thresholds", {}).get("met", 70)),
        "thresholds_partial": str(payload.get("thresholds", {}).get("partially", 50)),
        "grading_text": "\n".join([f"{k} | {v}" for k, v in payload.get("grading", {}).items()]),
        "payload_json_raw": json.dumps(payload, ensure_ascii=False, indent=2),
    }
    
    # Eksik FORM_KEYS alanlarını boş string olarak ekle (values'dan güncellenecek)
    for key in FORM_KEYS:
        if key not in result:
            result[key] = ""
    
    return result

def ensure_form_defaults(values: Dict[str, str]) -> Dict[str, str]:
    return {key: values.get(key, "") for key in FORM_KEYS}


def get_empty_form_defaults() -> Dict[str, str]:
    """Tamamen boş form değerleri döndür - örnek veri yok"""
    defaults = {key: "" for key in FORM_KEYS}
    # Varsayılan eşik değerleri
    defaults["thresholds_met"] = "70"
    defaults["thresholds_partial"] = "50"
    # Varsayılan Bloom taksonomisi
    defaults["bloom_text"] = "Bilgi\nKavrama\nUygulama\nAnaliz\nSentez\nDeğerlendirme"
    return defaults


def export_pdf_from_html(html: str, out_path: Path):
    """Render verilen HTML'i PDF'e dönüştür. Başarılıysa True, aksi halde False."""
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        out_path.with_suffix(".html").write_text(html, encoding="utf-8")
        return False
    try:
        HTML(string=html, base_url=str(Path(__file__).parent)).write_pdf(out_path)
        return True
    except Exception:
        out_path.with_suffix(".html").write_text(html, encoding="utf-8")
        return False

def build_payload_from_form(values: Dict[str, str]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    raw_json = values.get("payload_json_raw", "").strip()
    if raw_json:
        payload = json.loads(raw_json)
        return payload, form_defaults_from_payload(payload)
    
    # Bloom text'i parse et
    bloom_list = []
    for ln in _lines_to_list(values.get("bloom_text", "")):
        parts = _smart_split(ln, 2)
        if parts:
            bloom_list.append({"id": parts[0], "text": parts[1] if len(parts) > 1 else ""})
    
    # Thresholds'u form'dan oku
    try:
        thresholds_met = int(values.get("thresholds_met", "70") or "70")
    except:
        thresholds_met = 70
    try:
        thresholds_partial = int(values.get("thresholds_partial", "50") or "50")
    except:
        thresholds_partial = 50
    
    # Grading'i parse et
    grading = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}
    grading_text = values.get("grading_text", "")
    if grading_text:
        for ln in _lines_to_list(grading_text):
            parts = ln.split("|")
            if len(parts) >= 2:
                try:
                    grading[parts[0].strip()] = int(parts[1].strip())
                except:
                    pass
    
    payload = {
        "course": {
            "course_code": values.get("course_code", ""),
            "course_name": values.get("course_name", ""),
            "program_name": values.get("program_name", ""),
            "term": values.get("term", ""),
            "instructor": values.get("instructor", ""),
        },
        "curriculum": parse_curriculum(values.get("curriculum_text", "")),
        "tyc": parse_docs(values.get("tyc_text", "")),
        "stark": parse_docs(values.get("stark_text", "")),
        "docs": parse_docs(values.get("docs_text", "")),
        "pocs": parse_pocs(values.get("pocs_text", "")),
        "peas": parse_peas(values.get("peas_text", "")),
        "bloom": bloom_list,
        "assessments": parse_assessments(values.get("assessments_text", "")),
        "students": parse_students(values.get("students_text", "")),
        "scores": parse_scores(values.get("scores_text", "")),
        "doc_tyc_map": parse_generic_map(values.get("doc_tyc_map_text", ""), "DOC->TYÇ"),
        "poc_tyc_map": parse_generic_map(values.get("poc_tyc_map_text", ""), "POC->TYÇ"),
        "pea_stark_map": parse_generic_map(values.get("pea_stark_map_text", ""), "PEA->STAR-K"),
        "doc_pea_map": parse_generic_map(values.get("doc_pea_map_text", ""), "DOC->PEA"),
        "doc_stark_map": parse_generic_map(values.get("doc_stark_map_text", ""), "DOC->STARK"),
        "thresholds": {"met": thresholds_met, "partially": thresholds_partial},
        "grading": grading,
    }
    
    # ÖNCE form'dan gelen ayrı eşleştirmeleri al
    form_doc_poc_weights = parse_doc_poc_weights(values.get("doc_poc_weights_text", ""))
    form_poc_pea_map = parse_poc_pea_map(values.get("poc_pea_map_text", ""))
    
    qmap = parse_question_map(values.get("question_map_text", ""))
    if qmap and qmap.get("questions"):
        payload["questions"] = qmap.get("questions", [])
        # Soru bazlı eşleştirmeler
        qmap_doc_poc_weights = qmap.get("doc_poc_weights", {})
        qmap_poc_pea_map = qmap.get("poc_pea_map", {})
        
        # MERGE: Form eşleştirmeleri + soru bazlı eşleştirmeler
        # Form eşleştirmeleri öncelikli (kullanıcının bilinçli seçimi)
        merged_doc_poc = {}
        # Önce form'dan gelenleri ekle
        for did, pocs_weights in form_doc_poc_weights.items():
            merged_doc_poc[did] = dict(pocs_weights)
        # Sonra soru bazlı olanlara ekle (varsa üzerine yaz değil, birleştir)
        for did, pocs_weights in qmap_doc_poc_weights.items():
            if did not in merged_doc_poc:
                merged_doc_poc[did] = {}
            for pid, w in pocs_weights.items():
                # Eğer form'dan gelen yoksa, soru bazlı olanı kullan
                if pid not in merged_doc_poc[did]:
                    merged_doc_poc[did][pid] = w
        
        merged_poc_pea = {}
        # Önce form'dan gelenleri ekle
        for pid, pea_list in form_poc_pea_map.items():
            merged_poc_pea[pid] = list(pea_list)
        # Sonra soru bazlı olanları birleştir
        for pid, pea_list in qmap_poc_pea_map.items():
            if pid not in merged_poc_pea:
                merged_poc_pea[pid] = []
            for pea in pea_list:
                if pea not in merged_poc_pea[pid]:
                    merged_poc_pea[pid].append(pea)
        
        payload["doc_poc_weights"] = merged_doc_poc
        payload["poc_pea_map"] = merged_poc_pea
    else:
        payload["questions"] = parse_questions(values.get("questions_text", ""))
        payload["doc_poc_weights"] = form_doc_poc_weights
        payload["poc_pea_map"] = form_poc_pea_map
    
    # Müfredat-DÖÇ eşleştirmesini ekle
    payload["curriculum_doc_map"] = parse_generic_map(values.get("curriculum_doc_map_text", ""), "Curriculum->DÖÇ")
    return payload, form_defaults_from_payload(payload)


# =============================================================================
# RENDER TABLES - DETAYLI STANDART RAPOR
# =============================================================================

def render_tables(result: Dict[str, Any], standalone: bool = False, report_id: int = None) -> str:
    curriculum = result.get("curriculum", [])
    tyc = result.get("tyc", [])
    stark = result.get("stark", [])
    doc_tyc_map = result.get("doc_tyc_map", {})
    poc_tyc_map = result.get("poc_tyc_map", {})
    pea_stark_map = result.get("pea_stark_map", {})
    doc_poc_weights = result.get("doc_poc_weights", {})
    poc_pea_map = result.get("poc_pea_map", {})
    doc_pea_map = result.get("doc_pea_map", {})
    doc_stark_map = result.get("doc_stark_map", {})
    input_questions = result.get("input_questions", [])
    coverage = result.get("coverage", {})
    question_outcomes = result.get("question_outcomes", {})
    thresholds = result.get("thresholds", {"met": 70, "partially": 50})
    comp = result["computed"]["assessments"]
    docs = result["computed"]["docs"]
    pocs = result["computed"]["pocs"]
    peas = result["computed"]["peas"]
    bloom = result["computed"]["bloom"]
    overall = result["computed"]["overall"]
    narrative = result["computed"]["narrative"]
    course = result.get("course", {})

    def pct_class(p) -> str:
        if p is None:
            p = 0
        if p >= thresholds.get("met", 70): return "row-success"
        if p >= thresholds.get("partially", 50): return "row-warning"
        return "row-danger"

    out = []
    overall_pct = overall.get("success_pct", 0)
    pct_cls = "success" if overall_pct >= 70 else ("warning" if overall_pct >= 50 else "danger")
    
    # İstatistik Kartları
    out.append(f"""
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value {pct_cls}">%{overall_pct:.1f}</div><div class="stat-label">Genel Başarı</div></div>
        <div class="stat-card"><div class="stat-value">{len(input_questions)}</div><div class="stat-label">Soru Sayısı</div></div>
        <div class="stat-card"><div class="stat-value">{question_outcomes.get('student_count', 0)}</div><div class="stat-label">Öğrenci</div></div>
        <div class="stat-card"><div class="stat-value"><span class="badge {status_class(overall.get('status',''))}">{esc(overall.get('status',''))}</span></div><div class="stat-label">Durum</div></div>
    </div>
    """)

    # Müfredat / TYÇ / STAR-K
    if curriculum or tyc or stark:
        out.append("<div class='box'><h2>📚 Müfredat / TYÇ / STAR-K Çıktıları</h2>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Dersin dayandığı ulusal ve kurumsal standartlar</p>")
        out.append("<table><tr><th>Tür</th><th>Kod</th><th>Açıklama</th></tr>")
        for item in curriculum:
            out.append(f"<tr><td><span class='badge badge-success'>Müfredat</span></td><td><strong>{esc(item.get('id',''))}</strong></td><td>{esc(item.get('text',''))}</td></tr>")
        for item in tyc:
            out.append(f"<tr><td><span class='badge badge-warning'>TYÇ</span></td><td><strong>{esc(item.get('id',''))}</strong></td><td>{esc(item.get('text',''))}</td></tr>")
        for item in stark:
            out.append(f"<tr><td><span class='badge badge-danger'>STAR-K</span></td><td><strong>{esc(item.get('id',''))}</strong></td><td>{esc(item.get('text',''))}</td></tr>")
        out.append("</table></div>")

    # İlişki Haritaları - Kapsamlı
    has_any_mapping = doc_tyc_map or poc_tyc_map or pea_stark_map or doc_poc_weights or poc_pea_map or doc_pea_map or doc_stark_map
    if has_any_mapping:
        out.append("<div class='box'><h2>Çıktı İlişki Matrisi</h2>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Ders çıktılarının birbirleri ve ulusal standartlarla eşleşmesi</p>")
        out.append("<table><tr><th>Kaynak Çıktı</th><th>Tür</th><th>Hedef Eşleşmeler</th></tr>")
        empty_html = "<span class='text-muted'>Eşleşme yok</span>"
        
        # DÖÇ → TYÇ
        for did, vals in doc_tyc_map.items():
            chips = " ".join([f"<span class='badge badge-warning'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(did)}</strong></td><td>DÖÇ → TYÇ</td><td>{chips or empty_html}</td></tr>")
        
        # DÖÇ → STARK
        for did, vals in doc_stark_map.items():
            chips = " ".join([f"<span class='badge badge-danger'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(did)}</strong></td><td>DÖÇ → STARK</td><td>{chips or empty_html}</td></tr>")
        
        # DÖÇ → PÖÇ (ağırlıklı)
        for did, pocs_weights in doc_poc_weights.items():
            chips = " ".join([f"<span class='badge badge-success'>{esc(pid)}:{w}</span>" for pid, w in pocs_weights.items()])
            out.append(f"<tr><td><strong>{esc(did)}</strong></td><td>DÖÇ → PÖÇ</td><td>{chips or empty_html}</td></tr>")
        
        # DÖÇ → PEA
        for did, vals in doc_pea_map.items():
            chips = " ".join([f"<span class='badge badge-primary'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(did)}</strong></td><td>DÖÇ → PEA</td><td>{chips or empty_html}</td></tr>")
        
        # PÖÇ → TYÇ
        for pid, vals in poc_tyc_map.items():
            chips = " ".join([f"<span class='badge badge-warning'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(pid)}</strong></td><td>PÖÇ → TYÇ</td><td>{chips or empty_html}</td></tr>")
        
        # PÖÇ → PEA
        for pid, vals in poc_pea_map.items():
            chips = " ".join([f"<span class='badge badge-primary'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(pid)}</strong></td><td>PÖÇ → PEA</td><td>{chips or empty_html}</td></tr>")
        
        # PEA → STARK
        for aid, vals in pea_stark_map.items():
            chips = " ".join([f"<span class='badge badge-danger'>{esc(v)}</span>" for v in vals])
            out.append(f"<tr><td><strong>{esc(aid)}</strong></td><td>PEA → STARK</td><td>{chips or empty_html}</td></tr>")
        out.append("</table></div>")

    # Soru Haritası
    if input_questions:
        out.append("<div class='box'><h2 class='collapsible'>❓ Soru-Çıktı Eşleme Tablosu</h2><div class='collapsible-content'>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Her sorunun hangi çıktıları ölçtüğü</p>")
        out.append("<table><tr><th>Soru</th><th>Hafta</th><th>Bileşen</th><th>DÖÇ</th><th>PÖÇ</th><th>PEA</th><th>Bloom</th><th>TYÇ</th><th>STAR-K</th><th>Müfredat</th><th>Puan</th></tr>")
        for q in input_questions:
            poc_txt = ", ".join(q.get("poc_list", []))
            pea_txt = ", ".join(q.get("pea_list", []))
            doc_ids = q.get("doc_ids") or [q.get("doc_id", "")]
            bloom_txt = ", ".join(q.get("bloom_list", []) or [q.get("bloom", "")])
            tyc_txt = ", ".join(q.get("tyc_list", []))
            stark_txt = ", ".join(q.get("stark_list", []))
            curriculum_txt = ", ".join(q.get("curriculum_list", []))
            out.append(f"<tr><td><strong>{esc(q.get('id',''))}</strong></td><td>{esc(q.get('week',''))}</td><td>{esc(q.get('component_id',''))}</td><td>{esc(', '.join(doc_ids))}</td><td>{esc(poc_txt)}</td><td>{esc(pea_txt)}</td><td>{esc(bloom_txt)}</td><td>{esc(tyc_txt)}</td><td>{esc(stark_txt)}</td><td>{esc(curriculum_txt)}</td><td>{q.get('max_points',0)}</td></tr>")
        out.append("</table></div></div>")

    # Soru Kapsamı
    if coverage:
        out.append("<div class='box'><h2 class='collapsible'>📊 Soru Kapsam Analizi</h2><div class='collapsible-content'>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Her çıktının kaç soru ile ölçüldüğü</p>")
        out.append("<table><tr><th>Tip</th><th>Kod</th><th>Soru Sayısı</th><th>Kapsam %</th><th>Normalize %</th></tr>")
        for key, label in [("doc","DÖÇ"),("poc","PÖÇ"),("pea","PEA"),("bloom","Bloom"),("tyc","TYÇ"),("stark","STAR-K"),("curriculum","Müfredat")]:
            items = coverage.get(key, [])
            total_pct = sum(it.get("pct", 0.0) for it in items) or 1.0
            for item in items:
                norm = (item.get("pct", 0.0) / total_pct) * 100.0
                cls = pct_class(item.get("pct", 0.0))
                out.append(f"<tr class='{cls}'><td>{label}</td><td><strong>{esc(item['id'])}</strong></td><td>{item['count']}</td><td>%{item['pct']:.1f}</td><td>%{norm:.1f}</td></tr>")
            if items:
                out.append(f"<tr class='total'><td colspan='2'><strong>TOPLAM {label}</strong></td><td>{sum(it.get('count',0) for it in items)}</td><td>%{total_pct:.1f}</td><td>%100</td></tr>")
        out.append("</table></div></div>")

    # Soru Doğru/Yanlış
    if question_outcomes:
        per_q = question_outcomes.get("per_question", {})
        if per_q:
            out.append("<div class='box'><h2 class='collapsible'>✅ Soru Bazlı Başarı Analizi</h2><div class='collapsible-content'>")
            out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Öğrencilerin her sorudaki performansı</p>")
            out.append("<table><tr><th>Soru</th><th>Doğru %</th><th>Yanlış %</th><th>Ortalama</th><th>Max</th><th>DÖÇ</th><th>Bloom</th></tr>")
            for qid, data in sorted(per_q.items()):
                q = data.get("question", {})
                doc_ids = q.get("doc_ids") or [q.get("doc_id", "")]
                bloom_txt = ", ".join(q.get("bloom_list", []) or [q.get("bloom", "")])
                cls = pct_class(data.get("correct_pct", 0.0))
                out.append(f"<tr class='{cls}'><td><strong>{esc(qid)}</strong></td><td>%{data.get('correct_pct',0):.1f}</td><td>%{data.get('incorrect_pct',0):.1f}</td><td>{data.get('avg_score',0):.1f}</td><td>{data.get('max_points',0):.0f}</td><td>{esc(', '.join(doc_ids))}</td><td>{esc(bloom_txt)}</td></tr>")
            out.append("</table></div></div>")

        # Yanlış yapılan soruların kapsamı
        wrong_cov = question_outcomes.get("wrong_coverage", {})
        if wrong_cov:
            out.append("<div class='box'><h2 class='collapsible collapsed'>⚠️ Yanlış Yapılan Sorularda Çıktı Dağılımı</h2><div class='collapsible-content'>")
            out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Hangi çıktılarda öğrenciler zorlanıyor?</p>")
            out.append("<table><tr><th>Tip</th><th>Kod</th><th>Yanlış Soru Sayısı</th><th>%</th></tr>")
            for key, label in [("doc","DÖÇ"),("poc","PÖÇ"),("bloom","Bloom")]:
                items = wrong_cov.get(key, [])
                for item in items:
                    cls = pct_class(100 - item.get("pct", 0.0))
                    out.append(f"<tr class='{cls}'><td>{label}</td><td><strong>{esc(item['id'])}</strong></td><td>{item['count']}</td><td>%{item['pct']:.1f}</td></tr>")
            out.append("</table></div></div>")

    # Eksik İlişkiler - BİLGİLENDİRME (zorunlu değil)
    def _missing(def_ids: List[str], cov_key: str) -> List[str]:
        cov_ids = {c["id"] for c in coverage.get(cov_key, [])}
        return [d for d in def_ids if d not in cov_ids]

    doc_defs = list(docs.keys())
    poc_defs = list(pocs.keys())
    pea_defs = list(peas.keys())
    tyc_defs = [t.get("id") for t in tyc if t.get("id")]
    stark_defs = [s.get("id") for s in stark if s.get("id")]

    md = _missing(doc_defs, "doc")
    mp = _missing(poc_defs, "poc")
    mea = _missing(pea_defs, "pea")
    mtyc = _missing(tyc_defs, "tyc") if tyc_defs else []
    mstark = _missing(stark_defs, "stark") if stark_defs else []
    doc_no_tyc = [d for d in doc_defs if not doc_tyc_map.get(d)] if tyc_defs else []
    poc_no_tyc = [p for p in poc_defs if not poc_tyc_map.get(p)] if tyc_defs else []
    pea_no_stark = [a for a in pea_defs if not pea_stark_map.get(a)] if stark_defs else []

    # Sadece eşleme eksiklikleri uyarı olarak gösterilsin
    has_mapping_issues = any([doc_no_tyc, poc_no_tyc, pea_no_stark])
    if has_mapping_issues:
        out.append("<div class='box' style='border-color:#60a5fa;'><h2>ℹ️ EŞLEŞTİRME BİLGİLERİ</h2>")
        out.append("<p style='margin-bottom:0.75rem;color:#60a5fa;'>Aşağıdaki çıktıların eşleştirmeleri tanımlanmamış:</p>")
        out.append("<ul class='check-list'>")
        if doc_no_tyc:
            out.append(f"<li><span class='icon'>🔗</span><div><strong>TYÇ ile eşlenmemiş DÖÇ:</strong> {esc(', '.join(doc_no_tyc))}</div></li>")
        if poc_no_tyc:
            out.append(f"<li><span class='icon'>🔗</span><div><strong>TYÇ ile eşlenmemiş PÖÇ:</strong> {esc(', '.join(poc_no_tyc))}</div></li>")
        if pea_no_stark:
            out.append(f"<li><span class='icon'>🔗</span><div><strong>STAR-K ile eşlenmemiş PEA:</strong> {esc(', '.join(pea_no_stark))}</div></li>")
        out.append("</ul></div>")

    # Ölçme Planı
    out.append("<div class='box'><h2>⚖️ Ölçme Planı (Bileşenler)</h2>")
    out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Vize, Final vb. bileşenlerin ağırlıkları ve başarı durumu</p>")
    out.append("<table><tr><th>Bileşen</th><th>Ağırlık</th><th>Ort. Puan</th><th>Max Puan</th><th>Başarı %</th></tr>")
    for cid, cs in comp.items():
        cls = pct_class(cs.get('success_pct', 0))
        out.append(f"<tr class='{cls}'><td><strong>{esc(cs.get('name', cid))}</strong></td><td>%{cs.get('weight',0)*100:.0f}</td><td>{cs.get('avg_points',0):.2f}</td><td>{cs.get('max_points',0):.0f}</td><td>%{cs.get('success_pct',0):.1f}</td></tr>")
    out.append("</table></div>")

    # DÖÇ Sonuçları
    out.append("<div class='box'><h2>📘 Ders Öğrenme Çıktıları (DÖÇ) Sonuçları</h2>")
    out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Her DÖÇ için öğrenci başarı durumu</p>")
    out.append("<table><tr><th>DÖÇ</th><th>Açıklama</th><th>Başarı %</th><th>Durum</th></tr>")
    for did, st in sorted(docs.items()):
        measured = st.get('measured', True)
        pct = st.get('success_pct', 0)
        status = st.get('status', '')
        if not measured:
            # Ölçülmemiş - gri renkte göster
            out.append(f"<tr style='opacity:0.5;background:#f8fafc;'><td><strong>{esc(did)}</strong></td><td>{esc(st.get('text',''))}</td><td style='color:#94a3b8;'>-</td><td><span class='badge' style='background:#e2e8f0;color:#64748b;'>Ölçülmedi</span></td></tr>")
        else:
            cls = pct_class(pct)
            out.append(f"<tr class='{cls}'><td><strong>{esc(did)}</strong></td><td>{esc(st.get('text',''))}</td><td>%{pct:.1f}</td><td><span class='badge {status_class(status)}'>{esc(status)}</span></td></tr>")
    out.append("</table></div>")

    # PÖÇ Sonuçları
    out.append("<div class='box'><h2>🎓 Program Öğrenme Çıktıları (PÖÇ) Sonuçları</h2>")
    out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Her PÖÇ için hesaplanan başarı ve katkı sağlayan DÖÇler</p>")
    out.append("<table><tr><th>PÖÇ</th><th>Açıklama</th><th>Başarı %</th><th>Durum</th><th>Katkı Sağlayan DÖÇ</th></tr>")
    for pid, st in sorted(pocs.items()):
        contrib = st.get("contributors", [])
        contrib_txt = ", ".join([f"{c['doc_id']}({int(c['weight'])})" for c in contrib]) if contrib else "-"
        measured = st.get('measured', True)
        pct = st.get('success_pct', 0)
        status = st.get('status', '')
        if not measured:
            out.append(f"<tr style='opacity:0.5;background:#f8fafc;'><td><strong>{esc(pid)}</strong></td><td>{esc(st.get('text',''))}</td><td style='color:#94a3b8;'>-</td><td><span class='badge' style='background:#e2e8f0;color:#64748b;'>Ölçülmedi</span></td><td class='text-muted'>-</td></tr>")
        else:
            cls = pct_class(pct)
            out.append(f"<tr class='{cls}'><td><strong>{esc(pid)}</strong></td><td>{esc(st.get('text',''))}</td><td>%{pct:.1f}</td><td><span class='badge {status_class(status)}'>{esc(status)}</span></td><td class='text-muted'>{esc(contrib_txt)}</td></tr>")
    out.append("</table></div>")

    # PEA Sonuçları
    out.append("<div class='box'><h2>🏆 Program Eğitim Amaçları (PEA) Sonuçları</h2>")
    out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Dolaylı olarak hesaplanan eğitim amaçları başarısı</p>")
    out.append("<table><tr><th>PEA</th><th>Açıklama</th><th>İlgili DÖÇ</th><th>İlgili PÖÇ</th><th>Başarı %</th><th>Durum</th></tr>")
    for aid, st in sorted(peas.items()):
        docs_txt = ", ".join(st.get("docs", [])) if st.get("docs") else "-"
        pocs_txt = ", ".join(st.get("pocs", [])) if st.get("pocs") else "-"
        measured = st.get('measured', True)
        pct = st.get('success_pct', 0)
        status = st.get('status', '')
        if not measured:
            out.append(f"<tr style='opacity:0.5;background:#f8fafc;'><td><strong>{esc(aid)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(pocs_txt)}</td><td style='color:#94a3b8;'>-</td><td><span class='badge' style='background:#e2e8f0;color:#64748b;'>Ölçülmedi</span></td></tr>")
        else:
            cls = pct_class(pct)
            out.append(f"<tr class='{cls}'><td><strong>{esc(aid)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(pocs_txt)}</td><td>%{pct:.1f}</td><td><span class='badge {status_class(status)}'>{esc(status)}</span></td></tr>")
    out.append("</table></div>")

    # TYÇ Sonuçları (varsa)
    computed_tyc = result.get("computed", {}).get("tyc", {})
    if computed_tyc:
        out.append("<div class='box'><h2>🎯 Türkiye Yeterlilikler Çerçevesi (TYÇ) Sonuçları</h2>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>DÖÇ ve PÖÇ eşleştirmelerinden hesaplanan TYÇ başarısı</p>")
        out.append("<table><tr><th>TYÇ</th><th>Açıklama</th><th>İlgili DÖÇ</th><th>İlgili PÖÇ</th><th>Başarı %</th><th>Durum</th></tr>")
        for tyc_id, st in sorted(computed_tyc.items()):
            linked_docs = st.get("linked_docs", [])
            linked_pocs = st.get("linked_pocs", [])
            docs_txt = ", ".join(linked_docs) if linked_docs else "-"
            pocs_txt = ", ".join(linked_pocs) if linked_pocs else "-"
            measured = st.get('measured', True)
            pct = st.get('success_pct', 0)
            status = st.get('status', '')
            if not measured:
                out.append(f"<tr style='opacity:0.5;background:#f8fafc;'><td><strong>{esc(tyc_id)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(pocs_txt)}</td><td style='color:#94a3b8;'>-</td><td><span class='badge' style='background:#e2e8f0;color:#64748b;'>Ölçülmedi</span></td></tr>")
            else:
                cls = pct_class(pct)
                out.append(f"<tr class='{cls}'><td><strong>{esc(tyc_id)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(pocs_txt)}</td><td>%{pct:.1f}</td><td><span class='badge {status_class(status)}'>{esc(status)}</span></td></tr>")
        out.append("</table></div>")

    # STAR-K Sonuçları (varsa)
    computed_stark = result.get("computed", {}).get("stark", {})
    if computed_stark:
        out.append("<div class='box'><h2>⭐ Sektör Yetkinlikleri (STAR-K) Sonuçları</h2>")
        out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>DÖÇ ve PEA eşleştirmelerinden hesaplanan STAR-K başarısı</p>")
        out.append("<table><tr><th>STAR-K</th><th>Açıklama</th><th>İlgili DÖÇ</th><th>İlgili PEA</th><th>Başarı %</th><th>Durum</th></tr>")
        for stark_id, st in sorted(computed_stark.items()):
            linked_docs = st.get("linked_docs", [])
            linked_peas = st.get("linked_peas", [])
            docs_txt = ", ".join(linked_docs) if linked_docs else "-"
            peas_txt = ", ".join(linked_peas) if linked_peas else "-"
            measured = st.get('measured', True)
            pct = st.get('success_pct', 0)
            status = st.get('status', '')
            if not measured:
                out.append(f"<tr style='opacity:0.5;background:#f8fafc;'><td><strong>{esc(stark_id)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(peas_txt)}</td><td style='color:#94a3b8;'>-</td><td><span class='badge' style='background:#e2e8f0;color:#64748b;'>Ölçülmedi</span></td></tr>")
            else:
                cls = pct_class(pct)
                out.append(f"<tr class='{cls}'><td><strong>{esc(stark_id)}</strong></td><td>{esc(st.get('text',''))}</td><td>{esc(docs_txt)}</td><td>{esc(peas_txt)}</td><td>%{pct:.1f}</td><td><span class='badge {status_class(status)}'>{esc(status)}</span></td></tr>")
        out.append("</table></div>")

    # Bloom Analizi
    out.append("<div class='box'><h2>🧠 Bloom Taksonomisi Analizi</h2>")
    out.append("<p class='text-muted' style='margin-bottom:0.75rem;'>Bilişsel düzeylere göre soru dağılımı ve başarı</p>")
    out.append("<table><tr><th>Bloom Düzeyi</th><th>Soru Sayısı</th><th>Başarı %</th><th>Durum</th></tr>")
    # Varsayılan sıralama (varsa bu sırada göster, yoksa alfabetik)
    bloom_order = ["Bilgi", "Kavrama", "Uygulama", "Analiz", "Sentez", "Değerlendirme"]
    shown_blooms = set()
    # Önce varsayılan sıradaki bloom'ları göster
    for b in bloom_order:
        if b in bloom:
            shown_blooms.add(b)
            st = bloom[b]
            cls = pct_class(st.get('success_pct', 0))
            out.append(f"<tr class='{cls}'><td><strong>{esc(b)}</strong></td><td>{st.get('questions',0)}</td><td>%{st.get('success_pct',0):.1f}</td><td>{esc(st.get('status',''))}</td></tr>")
    # Sonra kullanıcının eklediği diğer bloom'ları göster
    for b in sorted(bloom.keys()):
        if b not in shown_blooms and b != "Bilinmiyor":
            st = bloom[b]
            cls = pct_class(st.get('success_pct', 0))
            out.append(f"<tr class='{cls}'><td><strong>{esc(b)}</strong></td><td>{st.get('questions',0)}</td><td>%{st.get('success_pct',0):.1f}</td><td>{esc(st.get('status',''))}</td></tr>")
    out.append("</table></div>")

    # Öneriler - AI destekli
    ai_suggestions = generate_ai_suggestions(result)
    sugg = ai_suggestions if ai_suggestions else narrative.get("suggestions", [])
    is_ai = ai_suggestions is not None and len(ai_suggestions) > 0
    
    ai_badge = ' <span style="background:#10b981;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.7rem;">🤖 AI</span>' if is_ai else ''
    out.append(f"<div class='box'><h2>💡 Sistem Önerileri{ai_badge}</h2>")
    if sugg:
        out.append("<ul class='check-list'>")
        for s in sugg:
            out.append(f"<li><span class='icon'>📌</span><div>{esc(s)}</div></li>")
        out.append("</ul>")
    else:
        out.append("<p class='text-muted'>Öneri üretilmedi - başarı oranları yeterli seviyede.</p>")
    out.append("</div>")

    # ÖĞRENCİ BAŞARI LİSTESİ VE BİREYSEL RAPORLAR
    students_data = result.get("students_data", [])
    input_students = result.get("input_students", [])
    
    if students_data:
        # Katılanlar ve girmeyenler ayrımı
        attending = [s for s in students_data if not s.get('is_absent')]
        absent = [s for s in students_data if s.get('is_absent')]
        
        out.append("<div class='box'><h2>👥 ÖĞRENCİ BAŞARI LİSTESİ VE BİREYSEL RAPORLAR</h2>")
        out.append(f"<p class='text-muted' style='margin-bottom:1rem;'>Toplam: {len(students_data)} öğrenci | Katılan: {len(attending)} | Girmeyen (GR): {len(absent)}</p>")
        out.append("<table><tr><th>#</th><th>Öğrenci No</th><th>Ad Soyad</th><th>Başarı %</th><th>Harf</th><th>Durum</th><th style='text-align:center;'>Bireysel Rapor</th></tr>")
        
        for i, s in enumerate(attending, 1):
            sid = s.get("id", "")
            student_name = s.get("name", sid)
            pct = s.get("pct", 0)
            letter = s.get("grade", "FF")
            
            # Durum ve stil
            if letter in ["AA", "BA", "BB", "CB", "CC"]:
                cls = "row-success"
                status = "Başarılı"
                badge = "badge-success"
            elif letter in ["DC", "DD"]:
                cls = "row-warning"
                status = "Koşullu"
                badge = "badge-warning"
            else:
                cls = "row-danger"
                status = "Başarısız"
                badge = "badge-danger"
            
            # Escape for JavaScript
            safe_name = esc(student_name).replace("'", "\\'")
            safe_id = esc(sid).replace("'", "\\'")
            
            out.append(f"""<tr class='{cls}'>
                <td>{i}</td>
                <td><strong>{esc(sid)}</strong></td>
                <td>{esc(student_name)}</td>
                <td><strong>%{pct:.1f}</strong></td>
                <td><span class='badge badge-{"success" if letter in ["AA","BA","BB"] else "warning" if letter in ["CB","CC","DC","DD"] else "danger"}'>{letter}</span></td>
                <td><span class='badge {badge}'>{status}</span></td>
                <td style='text-align:center;'><button type='button' class='btn btn-sm' style='background:#667eea;color:white;padding:0.4rem 0.8rem;font-size:0.75rem;border:none;border-radius:6px;cursor:pointer;' onclick="openStudentReportModal('{safe_id}', '{safe_name}')">📊 Detay</button></td>
            </tr>""")
        
        # GR öğrenciler
        if absent:
            out.append(f"<tr><td colspan='7' style='background:#f3f4f6;text-align:center;font-weight:600;'>🚫 Sınava Girmeyenler ({len(absent)} kişi)</td></tr>")
            for i, s in enumerate(absent, len(attending) + 1):
                sid = s.get("id", "")
                student_name = s.get("name", sid)
                safe_name = esc(student_name).replace("'", "\\'")
                safe_id = esc(sid).replace("'", "\\'")
                out.append(f"""<tr class='row-muted' style='opacity:0.6;'>
                    <td>{i}</td>
                    <td><strong>{esc(sid)}</strong></td>
                    <td>{esc(student_name)}</td>
                    <td>-</td>
                    <td><span class='badge' style='background:#6b7280;color:white;'>GR</span></td>
                    <td><span class='badge' style='background:#6b7280;color:white;'>Girmedi</span></td>
                    <td style='text-align:center;'>-</td>
                </tr>""")
        out.append("</table></div>")

    # Butonlar
    out.append("<div class='btn-group no-print'>")
    if standalone and report_id:
        out.append("<button class='btn btn-success' onclick='window.print()'>📥 PDF Olarak Kaydet</button>")
        out.append(f"<a class='btn btn-purple' href='/report-history/{report_id}'>🚀 V2 Rapor</a>")
        out.append("<a class='btn btn-ghost' href='/'>← Ana Sayfa</a>")
    elif standalone:
        out.append("<button class='btn btn-success' onclick='window.print()'>📥 PDF Olarak Kaydet</button>")
        out.append("<a class='btn btn-purple' href='/report-v2'>🚀 V2 Rapor</a>")
        out.append("<a class='btn btn-ghost' href='/'>← Ana Sayfa</a>")
    else:
        # Ana sayfada - ayrı sayfalara yönlendir
        out.append("<a class='btn btn-success' href='/report-standalone' target='_blank'>📄 Tam Sayfa Rapor</a>")
        out.append("<a class='btn btn-purple' href='/report-v2' target='_blank'>🚀 V2 Rapor</a>")
    out.append("</div>")
    
    # Standalone modda tam HTML sayfası döndür
    if standalone:
        course_name = course.get('course_name', 'Rapor')
        standalone_html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Standart Rapor - {esc(course_name)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 1cm; }}
@media print {{
  .no-print {{ display: none !important; }}
  body {{ background: white !important; padding: 0 !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
  .container {{ max-width: 100% !important; }}
  .box {{ break-inside: avoid; page-break-inside: avoid; box-shadow: none !important; border: 1px solid #ccc !important; }}
  .stats-grid {{ display: block !important; }}
  .stat-card {{ display: inline-block !important; width: 23% !important; margin: 0.5% !important; box-shadow: none !important; }}
  table {{ font-size: 0.75rem !important; }}
  th, td {{ padding: 0.5rem !important; }}
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#f1f5f9;padding:2rem;color:#1e293b;}}
.container{{max-width:1200px;margin:0 auto;}}
.box{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;}}
h2{{font-size:1.1rem;margin-bottom:1rem;color:#1e293b;}}
table{{width:100%;border-collapse:collapse;margin:1rem 0;}}
th,td{{padding:0.75rem;text-align:left;border-bottom:1px solid #e2e8f0;font-size:0.85rem;}}
th{{background:#f8fafc;font-weight:600;}}
.badge{{display:inline-block;padding:0.25rem 0.5rem;border-radius:6px;font-size:0.75rem;font-weight:600;}}
.badge-success{{background:#ecfdf5;color:#059669;}}
.badge-warning{{background:#fffbeb;color:#d97706;}}
.badge-danger{{background:#fef2f2;color:#dc2626;}}
.row-success{{background:#ecfdf5;}}
.row-warning{{background:#fffbeb;}}
.row-danger{{background:#fef2f2;}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin-bottom:1.5rem;}}
.stat-card{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:1.25rem;text-align:center;}}
.stat-value{{font-size:1.5rem;font-weight:700;}}
.stat-value.success{{color:#059669;}}
.stat-value.warning{{color:#d97706;}}
.stat-value.danger{{color:#dc2626;}}
.stat-label{{font-size:0.75rem;color:#64748b;margin-top:0.25rem;}}
.btn-group{{display:flex;gap:0.75rem;flex-wrap:wrap;margin-top:1.5rem;}}
.btn{{padding:0.75rem 1.25rem;border-radius:8px;font-weight:600;text-decoration:none;display:inline-block;font-size:0.85rem;border:none;cursor:pointer;}}
.btn-success{{background:#059669;color:white;}}
.btn-purple{{background:#7c3aed;color:white;}}
.btn-secondary{{background:#64748b;color:white;border:none;cursor:pointer;}}
.btn-ghost{{background:transparent;color:#64748b;border:1px solid #e2e8f0;}}
.text-muted{{color:#64748b;font-size:0.85rem;}}
</style>
</head>
<body>
<div class="container">
{"".join(out)}
</div>
</body>
</html>"""
        return standalone_html

    return "\n".join(out)


# =============================================================================
# V2 RAPOR - DETAYLI GÖRSEL DASHBOARD
# =============================================================================

def render_v2_report(result: Dict[str, Any], show_toolbar: bool = False, report_id: int = None) -> str:
    overall = result["computed"]["overall"]
    docs = result["computed"]["docs"]
    pocs = result["computed"]["pocs"]
    peas = result["computed"]["peas"]
    bloom = result["computed"]["bloom"]
    comp = result["computed"]["assessments"]
    narrative = result["computed"]["narrative"]
    input_questions = result.get("input_questions", [])
    question_outcomes = result.get("question_outcomes", {})
    coverage = result.get("coverage", {})
    course = result.get("course", {})
    students_data = result.get("students_data", [])
    weekly_coverage = result.get("weekly_coverage", [])
    curriculum = result.get("curriculum", [])
    tyc = result.get("tyc", [])
    stark = result.get("stark", [])
    doc_tyc_map = result.get("doc_tyc_map", {})
    poc_tyc_map = result.get("poc_tyc_map", {})
    pea_stark_map = result.get("pea_stark_map", {})
    doc_poc_weights = result.get("doc_poc_weights", {})
    poc_pea_map = result.get("poc_pea_map", {})
    
    overall_pct = overall.get("success_pct", 0)
    student_count = question_outcomes.get("student_count", 0)
    report_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    def get_color(pct):
        if pct is None:
            pct = 0
        if pct >= 70: return "#10b981"
        if pct >= 50: return "#f59e0b"
        return "#ef4444"
    
    def get_status_text(pct):
        if pct is None:
            pct = 0
        if pct >= 70: return "Sağlandı"
        if pct >= 50: return "Kısmen Sağlandı"
        return "Sağlanmadı"
    
    def get_grade_color(grade):
        if grade == "GR": return "#6b7280"  # Gri - Girmedi
        if grade in ["AA", "BA"]: return "#10b981"
        if grade in ["BB", "CB", "CC"]: return "#06b6d4"
        if grade in ["DC", "DD"]: return "#f59e0b"
        return "#ef4444"

    # Eksiklik analizi
    doc_defs = list(docs.keys())
    poc_defs = list(pocs.keys())
    pea_defs = list(peas.keys())
    tyc_defs = [t.get("id") for t in tyc if t.get("id")]
    stark_defs = [s.get("id") for s in stark if s.get("id")]
    curriculum_defs = [c.get("id") for c in curriculum if c.get("id")]
    
    cov_doc_ids = {c["id"] for c in coverage.get("doc", [])}
    cov_poc_ids = {c["id"] for c in coverage.get("poc", [])}
    cov_pea_ids = {c["id"] for c in coverage.get("pea", [])}
    cov_tyc_ids = {c["id"] for c in coverage.get("tyc", [])}
    cov_stark_ids = {c["id"] for c in coverage.get("stark", [])}
    cov_curriculum_ids = {c["id"] for c in coverage.get("curriculum", [])}
    
    missing_docs = [d for d in doc_defs if d not in cov_doc_ids]
    missing_pocs = [p for p in poc_defs if p not in cov_poc_ids]
    missing_peas = [a for a in pea_defs if a not in cov_pea_ids]
    missing_tyc = [t for t in tyc_defs if t not in cov_tyc_ids]
    missing_stark = [s for s in stark_defs if s not in cov_stark_ids]
    missing_curriculum = [c for c in curriculum_defs if c not in cov_curriculum_ids]
    doc_no_tyc = [d for d in doc_defs if not doc_tyc_map.get(d)]
    poc_no_tyc = [p for p in poc_defs if not poc_tyc_map.get(p)]
    pea_no_stark = [a for a in pea_defs if not pea_stark_map.get(a)]

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>V2 Detaylı Rapor - {esc(course.get('course_name', 'Ders'))}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 1cm; }}
@media print {{
  body {{ background: white !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
  .no-print {{ display: none !important; }}
  .page-break {{ page-break-before: always; }}
  .card, .section, .alert, .info-box {{ break-inside: avoid; page-break-inside: avoid; }}
  .page {{ padding: 0.5cm !important; max-width: 100% !important; }}
  .hero {{ padding: 1rem !important; background: #f5f5f5 !important; }}
  .hero h1 {{ background: none !important; -webkit-text-fill-color: #7c8bf8 !important; color: #7c8bf8 !important; }}
  .score-ring {{ border: 10px solid {get_color(overall_pct)} !important; background: white !important; box-shadow: none !important; }}
  .score-ring::before {{ display: none !important; }}
  .grid-2, .grid-3 {{ display: block !important; }}
  .card {{ margin-bottom: 0.75rem !important; box-shadow: none !important; border: 1px solid #ccc !important; }}
  .stat-box {{ box-shadow: none !important; }}
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#f8f7f3;min-height:100vh;color:#1f1f1a;line-height:1.6;}}
.page{{max-width:1400px;margin:0 auto;padding:2rem;}}
.hero{{text-align:center;padding:2rem;background:linear-gradient(135deg,rgba(124,139,248,0.12) 0%,rgba(240,139,160,0.12) 100%);border-radius:20px;border:1px solid #d7d3c8;margin-bottom:2rem;}}
.hero h1{{font-size:1.75rem;font-weight:800;background:linear-gradient(135deg,#7c8bf8 0%,#f08ba0 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:0.5rem;}}
.hero .subtitle{{color:#3b3b32;font-size:1rem;}}
.hero .meta{{display:flex;justify-content:center;gap:2rem;margin-top:1rem;flex-wrap:wrap;font-size:0.85rem;color:#6b6b61;}}
.hero .meta strong{{color:#1f1f1a;}}
.info-box{{background:#f6f4ee;border:1px solid #d7d3c8;border-radius:12px;padding:1rem;margin:1rem 0;font-size:0.85rem;color:#3b3b32;}}
.info-box h4{{margin-bottom:0.5rem;color:#7c8bf8;}}
.score-section{{display:flex;justify-content:center;align-items:center;gap:2.5rem;margin:2rem 0;flex-wrap:wrap;}}
.score-ring{{width:160px;height:160px;border-radius:50%;background:conic-gradient({get_color(overall_pct)} {overall_pct*3.6}deg, #e4e0d6 {overall_pct*3.6}deg);display:flex;align-items:center;justify-content:center;position:relative;box-shadow:0 0 30px rgba(124,139,248,0.25);}}
.score-ring::before{{content:'';position:absolute;inset:10px;border-radius:50%;background:#f8f7f3;border:1px solid #d7d3c8;}}
.score-inner{{position:relative;text-align:center;}}
.score-inner .value{{font-size:2.5rem;font-weight:800;color:{get_color(overall_pct)};}}
.score-inner .label{{font-size:0.7rem;color:#6b6b61;text-transform:uppercase;letter-spacing:1px;}}
.stats-row{{display:flex;gap:1rem;flex-wrap:wrap;}}
.stat-box{{background:#ffffff;border:1px solid #d7d3c8;border-radius:12px;padding:1rem 1.25rem;text-align:center;min-width:100px;box-shadow:0 6px 14px rgba(0,0,0,0.06);}}
.stat-box .num{{font-size:1.5rem;font-weight:700;color:#1f1f1a;}}
.stat-box .txt{{font-size:0.7rem;color:#6b6b61;text-transform:uppercase;margin-top:0.25rem;}}
.section{{margin:2rem 0;}}
.section-title{{font-size:0.85rem;font-weight:700;color:#7c8bf8;text-transform:uppercase;letter-spacing:1px;margin-bottom:1rem;padding-bottom:0.5rem;border-bottom:2px solid #d7d3c8;display:flex;align-items:center;gap:0.5rem;}}
.grid-2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:1.25rem;}}
.grid-3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.25rem;}}
.card{{background:#ffffff;border:1px solid #d7d3c8;border-radius:16px;padding:1.25rem;box-shadow:0 8px 18px rgba(0,0,0,0.04);}}
.card-header{{display:flex;align-items:center;gap:0.75rem;margin-bottom:1rem;padding-bottom:0.75rem;border-bottom:1px solid #e4e0d6;}}
.card-icon{{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;}}
.card-title{{font-size:0.9rem;font-weight:600;color:#1f1f1a;}}
.card-subtitle{{font-size:0.75rem;color:#6b6b61;}}
.card-description{{font-size:0.8rem;color:#3b3b32;margin-bottom:1rem;padding:0.75rem;background:#f6f4ee;border-radius:8px;border-left:3px solid #7c8bf8;}}
.progress-item{{margin-bottom:0.75rem;}}
.progress-header{{display:flex;justify-content:space-between;margin-bottom:0.25rem;font-size:0.8rem;}}
.progress-label{{color:#6b6b61;}}
.progress-label small{{color:#6b6b61;font-size:0.7rem;display:block;}}
.progress-value{{font-weight:600;}}
.progress-bar{{height:8px;background:#ece9e2;border-radius:4px;overflow:hidden;}}
.progress-fill{{height:100%;border-radius:4px;transition:width 0.8s ease;}}
table{{width:100%;border-collapse:collapse;font-size:0.8rem;margin-top:0.5rem;}}
th{{padding:0.625rem;text-align:left;font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:#6b6b61;background:#f6f4ee;}}
th:first-child{{border-radius:8px 0 0 0;}}
th:last-child{{border-radius:0 8px 0 0;}}
td{{padding:0.625rem;border-bottom:1px solid #e4e0d6;color:#1f1f1a;}}
tr:hover td{{background:rgba(124,139,248,0.08);}}
.badge{{display:inline-flex;padding:0.2rem 0.5rem;font-size:0.7rem;font-weight:600;border-radius:4px;margin:0.1rem;}}
.badge-success{{background:rgba(47,133,90,0.15);color:#2f855a;}}
.badge-warning{{background:rgba(197,106,0,0.15);color:#c56a00;}}
.badge-danger{{background:rgba(214,63,63,0.15);color:#d63f3f;}}
.badge-info{{background:rgba(124,139,248,0.15);color:#7c8bf8;}}
.alert{{padding:1rem;border-radius:10px;margin:1rem 0;}}
.alert-warning{{background:rgba(197,106,0,0.12);border:1px solid rgba(197,106,0,0.25);color:#c56a00;}}
.alert-danger{{background:rgba(214,63,63,0.12);border:1px solid rgba(214,63,63,0.25);color:#d63f3f;}}
.alert-success{{background:rgba(47,133,90,0.12);border:1px solid rgba(47,133,90,0.25);color:#2f855a;}}
.alert h4{{margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;}}
.alert ul{{margin:0.5rem 0 0 1.25rem;}}
.alert li{{margin-bottom:0.375rem;font-size:0.85rem;}}
.relation-matrix{{overflow-x:auto;}}
.relation-table td{{vertical-align:middle;}}
.relation-arrow{{color:#7c8bf8;font-weight:bold;padding:0 0.5rem;}}
.bloom-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:0.5rem;}}
.bloom-item{{background:#ffffff;border-radius:10px;padding:0.75rem 0.5rem;text-align:center;border:1px solid #e4e0d6;}}
.bloom-item .level{{font-size:0.6rem;color:#6b6b61;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.25rem;}}
.bloom-item .pct{{font-size:1.25rem;font-weight:700;color:#1f1f1a;}}
.bloom-item .count{{font-size:0.65rem;color:#6b6b61;}}
.question-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(42px,1fr));gap:0.375rem;}}
.q-cell{{aspect-ratio:1;border-radius:6px;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:0.7rem;cursor:default;transition:transform 0.2s;background:#f6f4ee;border:1px solid #e4e0d6;color:#1f1f1a;}}
.q-cell:hover{{transform:scale(1.15);z-index:1;box-shadow:0 6px 14px rgba(0,0,0,0.08);}}
.week-bar{{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;}}
.week-label{{width:60px;font-size:0.75rem;color:#6b6b61;text-align:right;}}
.week-fill{{height:28px;border-radius:4px;display:flex;align-items:center;padding:0 0.75rem;font-size:0.75rem;font-weight:500;color:#1f1f1a;}}
.student-row{{display:flex;align-items:center;gap:0.5rem;padding:0.375rem 0.5rem;border-radius:6px;margin-bottom:0.25rem;}}
.student-row:nth-child(odd){{background:#f6f4ee;}}
.student-rank{{width:22px;height:22px;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:0.65rem;font-weight:600;}}
.student-name{{flex:1;font-size:0.8rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.student-score{{font-size:0.8rem;font-weight:600;width:45px;text-align:right;}}
.student-grade{{width:32px;text-align:center;font-size:0.7rem;font-weight:600;border-radius:4px;padding:0.15rem;}}
.mini-bar{{width:80px;height:5px;background:#ece9e2;border-radius:3px;overflow:hidden;}}
.mini-fill{{height:100%;border-radius:3px;}}
.check-list{{list-style:none;padding:0;}}
.check-list li{{padding:0.5rem 0;border-bottom:1px solid #e4e0d6;display:flex;align-items:flex-start;gap:0.5rem;font-size:0.85rem;color:#1f1f1a;}}
.check-list li:last-child{{border-bottom:none;}}
.check-list .icon{{font-size:1rem;flex-shrink:0;}}
.suggestions{{background:linear-gradient(135deg,rgba(124,139,248,0.08) 0%,rgba(240,139,160,0.08) 100%);border:1px solid #d7d3c8;border-radius:16px;padding:1.25rem;}}
.suggestions h3{{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.75rem;color:#7c8bf8;font-size:0.9rem;}}
.suggestions ul{{list-style:none;padding:0;}}
.suggestions li{{padding:0.625rem 1rem;background:#f6f4ee;border-radius:8px;margin-bottom:0.375rem;border-left:3px solid #7c8bf8;font-size:0.85rem;color:#1f1f1a;}}
.back-btn{{display:inline-flex;align-items:center;gap:0.5rem;padding:0.75rem 1.25rem;background:linear-gradient(135deg,#7c8bf8 0%,#f08ba0 100%);color:white;text-decoration:none;border-radius:10px;font-weight:600;font-size:0.85rem;margin-right:0.75rem;transition:all 0.2s;}}
.back-btn:hover{{transform:translateY(-2px);box-shadow:0 6px 20px rgba(124,139,248,0.3);}}
.footer{{text-align:center;margin-top:2rem;padding-top:1.5rem;border-top:1px solid #d7d3c8;color:#6b6b61;font-size:0.8rem;}}
</style>
</head>
<body>
<div class="page">

<!-- HERO -->
<div class="hero">
<h1>📊 DERS DEĞERLENDİRME RAPORU</h1>
</div>

<!-- BU RAPOR NE ANLATIYOR -->
<div class="info-box">
<h4>📖 Bu Rapor Ne Anlatıyor?</h4>
<p>Bu rapor, dersin öğrenme çıktılarının ne ölçüde başarıldığını, hangi konularda öğrencilerin zorlandığını ve akreditasyon standartlarıyla uyumu gösterir. Yeşil renkler başarıyı, sarı kısmen başarıyı, kırmızı ise iyileştirme gereken alanları gösterir.</p>
</div>

<!-- GENEL SKOR -->
<div class="score-section">
<div class="score-ring">
<div class="score-inner">
<div class="value">%{overall_pct:.0f}</div>
<div class="label">Genel Başarı</div>
</div>
</div>
<div class="stats-row">
<div class="stat-box"><div class="num">{student_count}</div><div class="txt">Öğrenci</div></div>
<div class="stat-box"><div class="num">{len(input_questions)}</div><div class="txt">Soru</div></div>
<div class="stat-box"><div class="num">{len(docs)}</div><div class="txt">DÖÇ</div></div>
<div class="stat-box"><div class="num">{len(pocs)}</div><div class="txt">PÖÇ</div></div>
<div class="stat-box"><div class="num">{len(peas)}</div><div class="txt">PEA</div></div>
<div class="stat-box"><div class="num" style="color:{get_color(overall_pct)};font-size:1rem;">{get_status_text(overall_pct)}</div><div class="txt">Durum</div></div>
</div>
</div>

"""

    # MÜFREDAT / TYÇ / STAR-K
    if curriculum or tyc or stark:
        html += """
<div class="section">
<div class="section-title">📚 ULUSAL VE KURUMSAL STANDARTLAR</div>
<div class="card">
<div class="card-description">
<strong>Bu bölüm ne anlatıyor?</strong> Dersin dayandığı ulusal yeterlilik çerçevesi (TYÇ), müfredat çıktıları ve sektör standartları (STAR-K) listelenir. 
Bu standartlar, dersin akreditasyon kriterlerini karşılayıp karşılamadığını belirler.
</div>
<table>
<tr><th style="width:100px;">Tür</th><th style="width:80px;">Kod</th><th>Açıklama</th></tr>
"""
        for item in curriculum:
            html += f'<tr><td><span class="badge badge-success">Müfredat</span></td><td><strong>{esc(item.get("id",""))}</strong></td><td>{esc(item.get("text",""))}</td></tr>'
        for item in tyc:
            html += f'<tr><td><span class="badge badge-warning">TYÇ</span></td><td><strong>{esc(item.get("id",""))}</strong></td><td>{esc(item.get("text",""))}</td></tr>'
        for item in stark:
            html += f'<tr><td><span class="badge badge-danger">STAR-K</span></td><td><strong>{esc(item.get("id",""))}</strong></td><td>{esc(item.get("text",""))}</td></tr>'
        html += """
</table>
</div>
</div>
"""

    # İLİŞKİ MATRİSLERİ - TÜM DETAYLAR
    html += """
<div class="section page-break">
<div class="section-title">🔗 ÇIKTI İLİŞKİ MATRİSLERİ</div>
<div class="card">
<div class="card-description">
<strong>Bu bölüm ne anlatıyor?</strong> Ders çıktılarının (DÖÇ) program çıktılarına (PÖÇ), program çıktılarının eğitim amaçlarına (PEA) ve tüm çıktıların ulusal standartlara (TYÇ, STAR-K) nasıl bağlandığını gösterir.
Her satırda bir çıktı ve onun bağlı olduğu hedefler listelenir. Eşleşme olmayan çıktılar akreditasyon için sorun oluşturabilir.
</div>
"""
    
    # DÖÇ -> TYÇ
    if doc_tyc_map or doc_defs:
        html += '<h4 style="color:#818cf8;margin:1rem 0 0.5rem 0;font-size:0.85rem;">DÖÇ → TYÇ Eşleştirmesi</h4>'
        html += '<table><tr><th>DÖÇ</th><th>Açıklama</th><th>Bağlı TYÇ</th><th>Durum</th></tr>'
        for did in doc_defs:
            doc_text = docs.get(did, {}).get("text", "")
            tyc_list = doc_tyc_map.get(did, [])
            chips = " ".join([f'<span class="badge badge-warning">{esc(t)}</span>' for t in tyc_list]) if tyc_list else '<span style="color:#ef4444;">Eşleşme yok!</span>'
            status = '✅' if tyc_list else '❌'
            html += f'<tr><td><strong>{esc(did)}</strong></td><td style="font-size:0.75rem;color:#94a3b8;">{esc(doc_text[:60])}...</td><td>{chips}</td><td>{status}</td></tr>'
        html += '</table>'
    
    # PÖÇ -> TYÇ
    if poc_tyc_map or poc_defs:
        html += '<h4 style="color:#818cf8;margin:1.5rem 0 0.5rem 0;font-size:0.85rem;">PÖÇ → TYÇ Eşleştirmesi</h4>'
        html += '<table><tr><th>PÖÇ</th><th>Açıklama</th><th>Bağlı TYÇ</th><th>Durum</th></tr>'
        for pid in poc_defs:
            poc_text = pocs.get(pid, {}).get("text", "")
            tyc_list = poc_tyc_map.get(pid, [])
            chips = " ".join([f'<span class="badge badge-warning">{esc(t)}</span>' for t in tyc_list]) if tyc_list else '<span style="color:#ef4444;">Eşleşme yok!</span>'
            status = '✅' if tyc_list else '❌'
            html += f'<tr><td><strong>{esc(pid)}</strong></td><td style="font-size:0.75rem;color:#94a3b8;">{esc(poc_text[:60])}...</td><td>{chips}</td><td>{status}</td></tr>'
        html += '</table>'
    
    # PEA -> STAR-K
    if pea_stark_map or pea_defs:
        html += '<h4 style="color:#818cf8;margin:1.5rem 0 0.5rem 0;font-size:0.85rem;">PEA → STAR-K Eşleştirmesi</h4>'
        html += '<table><tr><th>PEA</th><th>Açıklama</th><th>Bağlı STAR-K</th><th>Durum</th></tr>'
        for aid in pea_defs:
            pea_text = peas.get(aid, {}).get("text", "")
            stark_list = pea_stark_map.get(aid, [])
            chips = " ".join([f'<span class="badge badge-danger">{esc(s)}</span>' for s in stark_list]) if stark_list else '<span style="color:#ef4444;">Eşleşme yok!</span>'
            status = '✅' if stark_list else '❌'
            html += f'<tr><td><strong>{esc(aid)}</strong></td><td style="font-size:0.75rem;color:#94a3b8;">{esc(pea_text[:60])}...</td><td>{chips}</td><td>{status}</td></tr>'
        html += '</table>'
    
    # DÖÇ -> PÖÇ Katkı
    if doc_poc_weights:
        html += '<h4 style="color:#818cf8;margin:1.5rem 0 0.5rem 0;font-size:0.85rem;">DÖÇ → PÖÇ Katkı Ağırlıkları</h4>'
        html += '<table><tr><th>DÖÇ</th><th>Katkı Sağladığı PÖÇ ve Ağırlıklar</th></tr>'
        for did, poc_weights in doc_poc_weights.items():
            chips = " ".join([f'<span class="badge badge-info">{esc(p)}:{int(w)}</span>' for p, w in poc_weights.items()])
            html += f'<tr><td><strong>{esc(did)}</strong></td><td>{chips}</td></tr>'
        html += '</table>'
    
    # PÖÇ -> PEA
    if poc_pea_map:
        html += '<h4 style="color:#818cf8;margin:1.5rem 0 0.5rem 0;font-size:0.85rem;">PÖÇ → PEA Eşleştirmesi</h4>'
        html += '<table><tr><th>PÖÇ</th><th>Katkı Sağladığı PEA</th></tr>'
        for pid, pea_list in poc_pea_map.items():
            chips = " ".join([f'<span class="badge badge-info">{esc(a)}</span>' for a in pea_list])
            html += f'<tr><td><strong>{esc(pid)}</strong></td><td>{chips}</td></tr>'
        html += '</table>'
    
    html += '</div></div>'

    # EKSİKLİKLER VE YAPILMASI GEREKENLER
    has_issues = any([missing_docs, missing_pocs, missing_peas, missing_tyc, missing_stark, missing_curriculum, doc_no_tyc, poc_no_tyc, pea_no_stark])
    if has_issues:
        html += """
<div class="section">
<div class="section-title">⚠️ EKSİKLİKLER VE YAPILMASI GEREKENLER</div>
<div class="alert alert-danger">
<h4>❌ Dikkat! Aşağıdaki eksiklikler akreditasyon için sorun oluşturabilir:</h4>
<ul class="check-list" style="margin-left:0;">
"""
        if missing_docs:
            html += f'<li><span class="icon">📘</span><div><strong>Sorularla ölçülmeyen DÖÇ:</strong> {", ".join(missing_docs)}<br/><small style="color:#f87171;">Çözüm: Bu çıktıları ölçen sınav sorusu ekleyin.</small></div></li>'
        if missing_pocs:
            html += f'<li><span class="icon">🎓</span><div><strong>Sorularla ölçülmeyen PÖÇ:</strong> {", ".join(missing_pocs)}<br/><small style="color:#f87171;">Çözüm: Bu program çıktılarını ölçen DÖÇ ve soru ekleyin.</small></div></li>'
        if missing_peas:
            html += f'<li><span class="icon">🏆</span><div><strong>Sorularla ölçülmeyen PEA:</strong> {", ".join(missing_peas)}<br/><small style="color:#f87171;">Çözüm: Bu eğitim amaçlarına katkı sağlayan PÖÇ tanımlayın.</small></div></li>'
        if missing_tyc:
            html += f'<li><span class="icon">📜</span><div><strong>Sorularla eşleşmeyen TYÇ:</strong> {", ".join(missing_tyc)}<br/><small style="color:#fbbf24;">Çözüm: TYÇ standartlarını karşılayan sorular ekleyin.</small></div></li>'
        if missing_stark:
            html += f'<li><span class="icon">🏭</span><div><strong>Sorularla eşleşmeyen STAR-K:</strong> {", ".join(missing_stark)}<br/><small style="color:#fbbf24;">Çözüm: Sektör standartlarını karşılayan içerik ekleyin.</small></div></li>'
        if missing_curriculum:
            html += f'<li><span class="icon">📚</span><div><strong>Sorularla eşleşmeyen Müfredat:</strong> {", ".join(missing_curriculum)}<br/><small style="color:#fbbf24;">Çözüm: Müfredat çıktılarını ölçen sorular ekleyin.</small></div></li>'
        if doc_no_tyc:
            html += f'<li><span class="icon">🔗</span><div><strong>TYÇ ile eşlenmemiş DÖÇ:</strong> {", ".join(doc_no_tyc)}<br/><small style="color:#fbbf24;">Çözüm: Bu DÖÇlerin hangi TYÇ ile ilişkili olduğunu tanımlayın.</small></div></li>'
        if poc_no_tyc:
            html += f'<li><span class="icon">🔗</span><div><strong>TYÇ ile eşlenmemiş PÖÇ:</strong> {", ".join(poc_no_tyc)}<br/><small style="color:#fbbf24;">Çözüm: Bu PÖÇlerin TYÇ ile ilişkisini tanımlayın.</small></div></li>'
        if pea_no_stark:
            html += f'<li><span class="icon">🔗</span><div><strong>STAR-K ile eşlenmemiş PEA:</strong> {", ".join(pea_no_stark)}<br/><small style="color:#fbbf24;">Çözüm: Bu PEAların sektör standartları ile ilişkisini tanımlayın.</small></div></li>'
        html += '</ul></div></div>'
    else:
        html += """
<div class="section">
<div class="alert alert-success">
<h4>✅ Tebrikler! Tüm çıktılar ve ilişkiler eksiksiz tanımlanmış.</h4>
<p>Tüm DÖÇ, PÖÇ, PEA çıktıları sorularla ölçülüyor ve ulusal standartlarla eşleştirilmiş durumda.</p>
</div>
</div>
"""

    # DÖÇ ve PÖÇ BAŞARI ANALİZİ
    html += """
<div class="section page-break">
<div class="section-title">📈 ÇIKTI BAŞARI ANALİZİ</div>
<div class="grid-2">
<div class="card">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#3b82f6,#06b6d4);">📘</div>
<div><div class="card-title">Ders Öğrenme Çıktıları (DÖÇ)</div><div class="card-subtitle">Her çıktı için öğrenci başarı oranı</div></div>
</div>
<div class="card-description">DÖÇ, dersin sonunda öğrencinin kazanması gereken bilgi ve becerileri tanımlar. %70 üzeri "Sağlandı", %50-70 "Kısmen", altı "Sağlanmadı".</div>
"""
    for did, st in sorted(docs.items()):
        measured = st.get('measured', True)
        pct = st.get('success_pct', 0)
        text = st.get('text', '')[:80]
        if not measured:
            html += f'''
<div class="progress-item" style="opacity:0.5;">
<div class="progress-header">
<span class="progress-label"><strong>{esc(did)}</strong><small>{esc(text)}</small></span>
<span class="progress-value" style="color:#94a3b8;">Ölçülmedi</span>
</div>
<div class="progress-bar"><div class="progress-fill" style="width:0%;background:#e2e8f0;"></div></div>
</div>'''
        else:
            color = get_color(pct)
            html += f'''
<div class="progress-item">
<div class="progress-header">
<span class="progress-label"><strong>{esc(did)}</strong><small>{esc(text)}</small></span>
<span class="progress-value" style="color:{color}">%{pct:.0f}</span>
</div>
<div class="progress-bar"><div class="progress-fill" style="width:{pct}%;background:{color};"></div></div>
</div>'''
    
    html += """
</div>
<div class="card">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#a855f7,#ec4899);">🎓</div>
<div><div class="card-title">Program Öğrenme Çıktıları (PÖÇ)</div><div class="card-subtitle">DÖÇlerden hesaplanan program başarısı</div></div>
</div>
<div class="card-description">PÖÇ, programın bütününde öğrencinin kazanması gereken yetkinlikleri gösterir. DÖÇ başarılarının ağırlıklı ortalamasından hesaplanır.</div>
"""
    for pid, st in sorted(pocs.items()):
        measured = st.get('measured', True)
        pct = st.get('success_pct', 0)
        text = st.get('text', '')[:80]
        contrib = st.get("contributors", [])
        contrib_txt = ", ".join([c['doc_id'] for c in contrib[:4]]) if contrib else ""
        if not measured:
            html += f'''
<div class="progress-item" style="opacity:0.5;">
<div class="progress-header">
<span class="progress-label"><strong>{esc(pid)}</strong><small>{esc(text)}</small></span>
<span class="progress-value" style="color:#94a3b8;">Ölçülmedi</span>
</div>
<div class="progress-bar"><div class="progress-fill" style="width:0%;background:#e2e8f0;"></div></div>
</div>'''
        else:
            color = get_color(pct)
            html += f'''
<div class="progress-item">
<div class="progress-header">
<span class="progress-label"><strong>{esc(pid)}</strong><small>{esc(text)}</small></span>
<span class="progress-value" style="color:{color}">%{pct:.0f}</span>
</div>
<div class="progress-bar"><div class="progress-fill" style="width:{pct}%;background:{color};"></div></div>
</div>'''
    
    html += """
</div>
</div>
</div>
"""

    # BLOOM TAKSONOMİSİ
    html += """
<div class="section">
<div class="section-title">🧠 BLOOM TAKSONOMİSİ ANALİZİ</div>
<div class="card">
<div class="card-description">
Bloom Taksonomisi, soruların bilişsel düzeyini gösterir. Üst düzey sorularda düşük başarı normaldir, ancak çok düşükse (%30 altı) müfredat veya öğretim yöntemi gözden geçirilmelidir.
</div>
<div class="bloom-grid">
"""
    # Varsayılan sıralama, sonra kullanıcının eklediği bloom'lar
    bloom_order = ["Bilgi", "Kavrama", "Uygulama", "Analiz", "Sentez", "Değerlendirme"]
    shown_blooms = set()
    
    # Önce varsayılan sıradaki bloom'ları göster
    for b in bloom_order:
        if b in bloom:
            shown_blooms.add(b)
            st = bloom[b]
            pct = st.get('success_pct', 0)
            count = st.get('questions', 0)
            color = get_color(pct)
            html += f'<div class="bloom-item"><div class="level">{esc(b)}</div><div class="pct" style="color:{color}">%{pct:.0f}</div><div class="count">{count} soru</div></div>'
    
    # Sonra kullanıcının eklediği diğer bloom'ları göster
    for b in sorted(bloom.keys()):
        if b not in shown_blooms and b != "Bilinmiyor":
            st = bloom[b]
            pct = st.get('success_pct', 0)
            count = st.get('questions', 0)
            color = get_color(pct)
            html += f'<div class="bloom-item"><div class="level">{esc(b)}</div><div class="pct" style="color:{color}">%{pct:.0f}</div><div class="count">{count} soru</div></div>'
    
    # Eğer hiç bloom yoksa bilgi mesajı
    if not bloom or (len(bloom) == 1 and "Bilinmiyor" in bloom):
        html += '<div class="bloom-item" style="opacity:0.5;grid-column:1/-1;"><div class="level">Bloom bilgisi girilmemiş</div></div>'
    
    html += """
</div>
</div>
</div>
"""

    # SORU BAŞARI HARİTASI
    per_q = question_outcomes.get("per_question", {})
    if per_q:
        html += """
<div class="section">
<div class="section-title">✅ SORU BAŞARI HARİTASI</div>
<div class="card">
<div class="card-description">
Her kutucuk bir soruyu temsil eder. <strong style="color:#10b981;">Yeşil</strong> = %70+ başarı, <strong style="color:#f59e0b;">Sarı</strong> = %50-70, <strong style="color:#ef4444;">Kırmızı</strong> = %50 altı.
Kırmızı sorulardaki çıktılar gözden geçirilmelidir.
</div>
<div class="question-grid">
"""
        for qid, data in sorted(per_q.items()):
            pct = data.get('correct_pct', 0)
            color = get_color(pct)
            q = data.get('question', {})
            doc_ids = q.get("doc_ids") or [q.get("doc_id", "")]
            html += f'<div class="q-cell" style="background:{color}22;border:2px solid {color};" title="{esc(qid)}: %{pct:.0f} doğru | {", ".join(doc_ids)}">{esc(qid.replace("S",""))}</div>'
        html += """
</div>
</div>
</div>
"""

    # HAFTALIK DAĞILIM
    if weekly_coverage:
        max_points = max(w.get("total_points", 1) for w in weekly_coverage)
        html += """
<div class="section">
<div class="section-title">📅 HAFTALIK SORU DAĞILIMI</div>
<div class="card">
<div class="card-description">Her hafta için soru sayısı ve toplam puan. Dağılımın dengeli olması beklenir.</div>
"""
        for w in weekly_coverage:
            width = (w.get("total_points", 0) / max_points) * 100
            html += f'''
<div class="week-bar">
<span class="week-label">Hafta {esc(w.get('week', ''))}</span>
<div class="week-fill" style="width:{width}%;background:linear-gradient(90deg,#6366f1,#a855f7);">
{w.get('count', 0)} soru • {w.get('total_points', 0):.0f} puan
</div>
</div>'''
        html += '</div></div>'

    # ÖĞRENCİ BAŞARI SIRALAMASI
    if students_data:
        # Katılan ve girmeyen öğrencileri ayır
        attending = [s for s in students_data if not s.get('is_absent')]
        absent = [s for s in students_data if s.get('is_absent')]
        
        # Not dağılımı
        grade_dist = {}
        for s in students_data:
            grade_dist[s['grade']] = grade_dist.get(s['grade'], 0) + 1
        
        html += """
<div class="section page-break">
<div class="section-title">👥 ÖĞRENCİ BAŞARI ANALİZİ</div>
"""
        # Özet bilgi
        html += f'''
<div class="alert alert-info" style="margin-bottom:1rem;">
📊 <strong>Toplam:</strong> {len(students_data)} öğrenci | 
<strong>Derse Giren:</strong> {len(attending)} | 
<strong>Derse Girmeyen:</strong> {len(absent)}
</div>
'''
        
        html += """<div class="grid-3">
<div class="card">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#10b981,#06b6d4);">🏆</div>
<div><div class="card-title">En Başarılı 10</div></div>
</div>
"""
        for i, s in enumerate(attending[:10]):
            color = get_color(s['pct'])
            grade_color = get_grade_color(s['grade'])
            html += f'''
<div class="student-row">
<div class="student-rank" style="background:{color}22;color:{color};">{i+1}</div>
<div class="student-name">{esc(s['name'])}</div>
<div class="mini-bar"><div class="mini-fill" style="width:{s['pct']}%;background:{color};"></div></div>
<div class="student-score" style="color:{color}">%{s['pct']:.0f}</div>
<div class="student-grade" style="background:{grade_color}22;color:{grade_color};">{s['grade']}</div>
</div>'''
        
        html += """
</div>
<div class="card">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#f59e0b,#ef4444);">📉</div>
<div><div class="card-title">Destek Gerekenler</div></div>
</div>
"""
        # Sadece katılanlardan destek gerekenler
        need_support = [s for s in attending if s['pct'] < 60][-10:][::-1]
        if need_support:
            for s in need_support:
                color = get_color(s['pct'])
                grade_color = get_grade_color(s['grade'])
                html += f'''
<div class="student-row">
<div class="student-name">{esc(s['name'])}</div>
<div class="mini-bar"><div class="mini-fill" style="width:{s['pct']}%;background:{color};"></div></div>
<div class="student-score" style="color:{color}">%{s['pct']:.0f}</div>
<div class="student-grade" style="background:{grade_color}22;color:{grade_color};">{s['grade']}</div>
</div>'''
        else:
            html += '<div class="no-items-msg">Destek gereken öğrenci yok</div>'
        
        html += """
</div>
<div class="card">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#ec4899,#f472b6);">📊</div>
<div><div class="card-title">Not Dağılımı</div></div>
</div>
<div class="card-description">Harf notlarına göre öğrenci dağılımı.</div>
<table>
<tr><th>Not</th><th>Sayı</th><th>Oran</th></tr>
"""
        for grade in ["AA", "BA", "BB", "CB", "CC", "DC", "DD", "FD", "FF", "GR"]:
            count = grade_dist.get(grade, 0)
            pct = (count / len(students_data) * 100) if students_data else 0
            if count > 0:
                color = get_grade_color(grade)
                label = "Girmedi" if grade == "GR" else grade
                html += f'<tr><td><span class="badge" style="background:{color}22;color:{color};">{label}</span></td><td>{count}</td><td>%{pct:.0f}</td></tr>'
        html += """
</table>
</div>
</div>
"""
        
        # Derse Girmeyen Öğrenciler
        if absent:
            html += f'''
<div class="card" style="margin-top:1rem;">
<div class="card-header">
<div class="card-icon" style="background:linear-gradient(135deg,#6b7280,#9ca3af);">🚫</div>
<div><div class="card-title">Derse Girmeyen Öğrenciler ({len(absent)} kişi)</div></div>
</div>
<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));gap:0.5rem;padding:0.5rem;">
'''
            for s in absent:
                html += f'''<div style="background:#f3f4f6;padding:0.5rem 0.75rem;border-radius:6px;font-size:0.85rem;">
<span style="color:#6b7280;">●</span> {esc(s['name'])}
</div>'''
            html += '</div></div>'
        
        html += "</div>"

    # ÖNERİLER - AI destekli
    ai_suggestions = generate_ai_suggestions(result)
    sugg = ai_suggestions if ai_suggestions else narrative.get("suggestions", [])
    is_ai = ai_suggestions is not None and len(ai_suggestions) > 0
    
    if sugg:
        ai_badge = '<span style="background:#10b981;color:white;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;margin-left:0.5rem;">🤖 AI</span>' if is_ai else ''
        html += f"""
<div class="section">
<div class="suggestions">
<h3>💡 SİSTEM ÖNERİLERİ{ai_badge}</h3>
<ul>
"""
        for s in sugg:
            html += f'<li>{esc(s)}</li>'
        html += """
</ul>
</div>
</div>
"""

    # FOOTER
    html += f"""
<div class="footer">
<p>Bu rapor otomatik olarak oluşturulmuştur. • Oluşturma Tarihi: {report_date}</p>
</div>

<div class="no-print" style="text-align:center;margin-top:2rem;">
<a href="/" class="back-btn">← Ana Sayfaya Dön</a>
<button onclick="window.print()" class="back-btn" style="background:linear-gradient(135deg,#10b981,#06b6d4);border:none;cursor:pointer;">📥 PDF Olarak Kaydet</button>
{"<a href='/report-history/" + str(report_id) + "/standard' class='back-btn' style='background:linear-gradient(135deg,#3b82f6,#60a5fa);'>📊 Standart Rapor</a>" if report_id else "<a href='/report-standalone' class='back-btn' style='background:linear-gradient(135deg,#3b82f6,#60a5fa);'>📊 Standart Rapor</a>"}
</div>

</div>
</body>
</html>
"""
    return html


# =============================================================================
# FORM RENDER
# =============================================================================

def render_form(values: Dict[str, str], message: str = "", sidebar_html: str = "", user_courses: list = None) -> str:
    v = ensure_form_defaults(values)
    alert = f"<div class='alert alert-error'>⚠️ {esc(message)}</div>" if message else ""
    
    # Ders seçici dropdown
    course_selector = ""
    if user_courses and len(user_courses) > 0:
        options = ""
        current_course = v.get('course_code', '')
        for uc in user_courses:
            code = uc.get('course_code', '')
            name = uc.get('course_name', '') or code
            selected = 'selected' if code == current_course else ''
            options += f'<option value="{code}" {selected}>{code} - {name}</option>'
        
        course_selector = f"""
        <div class="course-selector-box" style="background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);padding:1rem 1.25rem;border-radius:12px;margin-bottom:1rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
          <div style="color:white;">
            <span style="font-size:1.25rem;">📚</span>
            <strong style="margin-left:0.5rem;">Aktif Ders:</strong>
          </div>
          <select id="activeCourseSelect" onchange="switchCourse(this.value)" style="flex:1;min-width:250px;padding:0.6rem 1rem;border-radius:8px;border:2px solid rgba(255,255,255,0.3);background:rgba(255,255,255,0.95);color:#1e293b;font-weight:600;font-size:0.9rem;cursor:pointer;">
            {options}
          </select>
          <span style="color:rgba(255,255,255,0.8);font-size:0.8rem;">({len(user_courses)} ders yetkili)</span>
        </div>
        """
    
    return f"""
<div class='box'>
<h2>📝 Veri Girişi</h2>
{alert}
{course_selector}

<!-- Auto-save indicator -->
<div class="autosave-status" id="autosaveIndicator">
  <span class="autosave-dot"></span>
  <span class="autosave-text">Otomatik kayıt aktif</span>
</div>

<form method="POST" action="/compute" id="mainForm">

<div class="tabs">
<button type="button" class="tab active" data-tab="tab-course">📚 Ders</button>
<button type="button" class="tab" data-tab="tab-outcomes">🎯 Çıktılar</button>
<button type="button" class="tab" data-tab="tab-mappings">🔗 Eşleştirmeler</button>
<button type="button" class="tab" data-tab="tab-students">👥 Öğrenciler</button>
<button type="button" class="tab" data-tab="tab-questions">❓ Sorular</button>
</div>

<div id="tab-course" class="tab-content active">
<div class="alert alert-info">💡 Sağ üstteki <strong>Örnek Veri</strong> butonu ile tüm alanları otomatik doldurabilirsiniz.</div>
<input type="hidden" name="course_code" value="{esc(v['course_code'])}"/>
<input type="hidden" name="term" value="{esc(v['term'])}"/>
<input type="hidden" name="course_name" value="{esc(v['course_name'])}"/>

<label>
  Program
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Dersin ait olduğu lisans/yüksek lisans programının adı. Örn: Bilgisayar Mühendisliği, Elektrik-Elektronik Mühendisliği</span>
  </span>
</label>
<input type="text" name="program_name" value="{esc(v['program_name'])}" placeholder="Bilgisayar Mühendisliği"/>

<label>
  Öğretim Elemanı
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Dersi veren öğretim üyesinin unvanı ve adı</span>
  </span>
</label>
<input type="text" name="instructor" value="{esc(v['instructor'])}" placeholder="Dr. Öğr. Üyesi Ahmet Yılmaz"/>

<div class="section-title">
  ⚖️ Ölçme Bileşenleri
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Kullanacağınız değerlendirme bileşenlerini seçin ve ağırlıklarını girin. Ağırlıkların toplamı 1.0 (veya 100) olmalıdır.</span>
  </span>
</div>
<div class="assessment-checkboxes" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:0.75rem; margin-bottom:1rem;">
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_vize" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">📝 Vize</span>
    <input type="number" id="comp_vize_w" step="0.1" min="0" max="1" placeholder="0.4" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_final" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">📋 Final</span>
    <input type="number" id="comp_final_w" step="0.1" min="0" max="1" placeholder="0.6" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_odev" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">📚 Ödev</span>
    <input type="number" id="comp_odev_w" step="0.1" min="0" max="1" placeholder="0.2" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_proje" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">🎯 Proje</span>
    <input type="number" id="comp_proje_w" step="0.1" min="0" max="1" placeholder="0.3" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_quiz" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">⚡ Quiz</span>
    <input type="number" id="comp_quiz_w" step="0.1" min="0" max="1" placeholder="0.1" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_lab" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">🔬 Lab</span>
    <input type="number" id="comp_lab_w" step="0.1" min="0" max="1" placeholder="0.2" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_sunum" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">🎤 Sunum</span>
    <input type="number" id="comp_sunum_w" step="0.1" min="0" max="1" placeholder="0.15" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
  <label class="checkbox-card" style="display:flex; align-items:center; gap:0.5rem; padding:0.75rem; background:var(--bg); border-radius:8px; cursor:pointer; border:2px solid transparent; transition:all 0.2s;">
    <input type="checkbox" id="comp_katilim" onchange="updateAssessments()" style="width:18px; height:18px; accent-color:#667eea;">
    <span style="flex:1;">✋ Katılım</span>
    <input type="number" id="comp_katilim_w" step="0.1" min="0" max="1" placeholder="0.1" style="width:60px; padding:0.25rem; border-radius:4px; border:1px solid var(--border); background:var(--card); color:var(--text);" onchange="updateAssessments()">
  </label>
</div>
<div id="assessmentWeightWarning" style="display:none; background:#fef3c7; color:#92400e; padding:0.5rem 1rem; border-radius:6px; margin-bottom:0.5rem; font-size:0.85rem;">
  ⚠️ Ağırlıkların toplamı 1.0 olmalıdır. Şu anki toplam: <span id="weightTotal">0</span>
</div>
<details style="margin-bottom:0.5rem;">
  <summary style="cursor:pointer; color:#94a3b8; font-size:0.85rem;">📝 Manuel giriş (ileri düzey)</summary>
  <p class="helper" style="margin-top:0.5rem;">Her satır: Kod | Ad | Ağırlık</p>
  <textarea name="assessments_text" rows="3" placeholder="C1 | Vize | 0.4&#10;C2 | Final | 0.6" style="font-size:0.85rem;">{esc(v['assessments_text'])}</textarea>
</details>
</div>

<div id="tab-outcomes" class="tab-content">
<div class="section-title">
  📚 Ulusal Standartlar
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">TYÇ (Türkiye Yeterlilikler Çerçevesi) ve STAR-K (Sektör Standartları) gibi ulusal düzeyde belirlenen çıktıları buraya girin.</span>
  </span>
</div>
<div class="alert alert-info" style="margin-bottom:1rem;padding:0.75rem;font-size:0.85rem;">
  🔒 <strong>Bu veriler Profil sayfasından düzenlenir.</strong> Değişiklik yapmak için <a href="/profile" style="color:#2563eb;font-weight:600;">Profil</a> sayfasına gidin.
</div>
<label>Müfredat Çıktıları</label>
<textarea name="curriculum_text" rows="3" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['curriculum_text'])}</textarea>

<label>
  TYÇ Çıktıları
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Türkiye Yeterlilikler Çerçevesi çıktıları. Lisans düzeyi için TYÇ 6. seviye yeterlilikleri kullanılır.</span>
  </span>
</label>
<textarea name="tyc_text" rows="3" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['tyc_text'])}</textarea>

<label>
  STAR-K Çıktıları
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Sektör Tabanlı Akreditasyon Standartları. Meslek alanına özgü yeterlilikleri içerir.</span>
  </span>
</label>
<textarea name="stark_text" rows="3" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['stark_text'])}</textarea>

<div class="section-title">
  🎯 Öğrenme Çıktıları
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">DÖÇ: Ders düzeyinde kazanımlar. PÖÇ: Program düzeyinde kazanımlar. PEA: Mezunların 3-5 yıl sonra ulaşması beklenen hedefler.</span>
  </span>
</div>

<label>
  DÖÇ (Ders Öğrenme Çıktıları)
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Öğrencinin bu dersi tamamladığında kazanacağı bilgi, beceri ve yetkinlikler</span>
  </span>
</label>
<textarea name="docs_text" rows="4" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['docs_text'])}</textarea>

<label>
  PÖÇ (Program Öğrenme Çıktıları)
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Programdan mezun olduğunda öğrencinin sahip olacağı yeterlilikler</span>
  </span>
</label>
<textarea name="pocs_text" rows="4" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['pocs_text'])}</textarea>

<label>
  PEA (Program Eğitim Amaçları)
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Mezunların 3-5 yıl içinde mesleki ve kariyer hedeflerine ulaşma beklentileri</span>
  </span>
</label>
<textarea name="peas_text" rows="3" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['peas_text'])}</textarea>

<div class="section-title">
  🧠 Bloom Taksonomisi
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Bilişsel düzeyler: Bilgi (hatırlama) → Kavrama (anlama) → Uygulama → Analiz → Sentez → Değerlendirme. Sorular bu düzeylere göre sınıflandırılır.</span>
  </span>
</div>
<p class="helper">Bloom düzeyleri (Format: Düzey - Açıklama)</p>
<textarea name="bloom_text" rows="6" readonly style="background:#f1f5f9;cursor:not-allowed;color:#64748b;" placeholder="Profil sayfasından giriş yapın...">{esc(v['bloom_text'])}</textarea>
</div>

<div id="tab-questions" class="tab-content">
<div class="section-title">❓ Soru Oluşturucu</div>
<div class="alert alert-info">
🎯 Her soru için <strong>Ölçme Türü</strong>, <strong>DÖÇ</strong>, <strong>Müfredat</strong> ve <strong>Bloom Taksonomisi</strong> eşleştirmelerini yapın.
</div>
<div class="questions-summary" id="questions-summary">
<span>Toplam: <strong class="count">0</strong> soru</span>
<button type="button" class="btn btn-sm btn-secondary" onclick="rebuildAllQuestions()">🔄 Yenile</button>
</div>
<div id="questions-container"></div>
<button type="button" class="add-question-btn" onclick="addQuestion()">➕ Yeni Soru Ekle</button>
<textarea name="question_map_text" style="display:none;">{esc(v['question_map_text'])}</textarea>
</div>

<div id="tab-mappings" class="tab-content">
<div class="section-title">
  🔗 DÖÇ Eşleştirmeleri
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Her DÖÇ'ün TYÇ, STAR-K, PÖÇ ve PEA ile ilişkisini belirleyin. Checkbox işaretleyerek eşleştirme yapın.</span>
  </span>
</div>
<div class="alert alert-info">
🎯 Önce <strong>Çıktılar</strong> sekmesinden verileri girin, sonra burada tablo şeklinde eşleştirmeleri yapın.
</div>
<div id="doc-mapping-table" class="mapping-table-container"></div>

<div class="section-title" style="margin-top:1.5rem;">
  📚 Müfredat Eşleştirmeleri
  <span class="tooltip-container">
    <span class="tooltip-icon">?</span>
    <span class="tooltip-content">Her Müfredat çıktısının TYÇ, STAR-K, PÖÇ ve PEA ile ilişkisini belirleyin.</span>
  </span>
</div>
<div id="curriculum-mapping-table" class="mapping-table-container"></div>

<div class="section-title" style="margin-top:1.5rem;">📅 Eski Eşleştirmeler (Uyumluluk)</div>
<details style="margin-bottom:0.5rem;">
  <summary style="cursor:pointer; color:#94a3b8; font-size:0.85rem;">📝 Manuel giriş (ileri düzey)</summary>
  <div id="mappings-container" style="margin-top:0.5rem;"></div>
  <div id="curriculum-doc-container" style="margin-top:0.5rem;"></div>
</details>
<textarea name="doc_tyc_map_text" style="display:none;">{esc(v['doc_tyc_map_text'])}</textarea>
<textarea name="poc_tyc_map_text" style="display:none;">{esc(v['poc_tyc_map_text'])}</textarea>
<textarea name="pea_stark_map_text" style="display:none;">{esc(v['pea_stark_map_text'])}</textarea>
<textarea name="doc_poc_weights_text" style="display:none;">{esc(v['doc_poc_weights_text'])}</textarea>
<textarea name="poc_pea_map_text" style="display:none;">{esc(v['poc_pea_map_text'])}</textarea>
<textarea name="curriculum_doc_map_text" style="display:none;">{esc(v['curriculum_doc_map_text'])}</textarea>
<textarea name="doc_stark_map_text" style="display:none;">{esc(v.get('doc_stark_map_text',''))}</textarea>
<textarea name="doc_pea_map_text" style="display:none;">{esc(v.get('doc_pea_map_text',''))}</textarea>
<textarea name="curriculum_tyc_map_text" style="display:none;">{esc(v.get('curriculum_tyc_map_text',''))}</textarea>
<textarea name="curriculum_stark_map_text" style="display:none;">{esc(v.get('curriculum_stark_map_text',''))}</textarea>
<textarea name="curriculum_poc_map_text" style="display:none;">{esc(v.get('curriculum_poc_map_text',''))}</textarea>
<textarea name="curriculum_pea_map_text" style="display:none;">{esc(v.get('curriculum_pea_map_text',''))}</textarea>
</div>

<div id="tab-students" class="tab-content">

<div class="section-title">👥 Öğrenci Listesi</div>
<div class="import-row" style="display:flex;gap:0.5rem;margin-bottom:0.5rem;">
  <label class="btn btn-sm btn-secondary" style="cursor:pointer;display:inline-flex;align-items:center;gap:0.3rem;">
    📥 Excel'den Yükle
    <input type="file" accept=".xlsx,.xls,.csv" onchange="importStudentsFromExcel(this)" style="display:none;">
  </label>
  <span class="helper" style="align-self:center;">Numara, Ad, Soyad, Durum sütunları otomatik algılanır</span>
</div>
<textarea name="students_text" rows="8" placeholder="OGR01 - Ahmet Yılmaz">{esc(v['students_text'])}</textarea>

<div class="section-title" style="margin-top:1.5rem;">📊 Notlar</div>
<div class="import-row" style="display:flex;gap:0.5rem;margin-bottom:0.5rem;">
  <label class="btn btn-sm btn-secondary" style="cursor:pointer;display:inline-flex;align-items:center;gap:0.3rem;">
    📥 Excel'den Yükle
    <input type="file" accept=".xlsx,.xls,.csv" onchange="importScoresFromExcel(this)" style="display:none;">
  </label>
  <span class="helper" style="align-self:center;">Başlıkta soru numaraları (1, 2, 3...) otomatik algılanır</span>
</div>
<textarea name="scores_text" rows="10" placeholder="OGR01, S1, 8">{esc(v['scores_text'])}</textarea>
</div>

<div class="btn-group" style="margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border);">
<button class="btn btn-primary" type="submit">🚀 Hesapla</button>
<button class="btn btn-accent" type="button" onclick="openSaveDraftModal()">💾 Taslak Kaydet</button>
<button class="btn btn-secondary" type="button" onclick="loadSampleData()">📋 Örnek Veri</button>
<button class="btn btn-ghost" type="button" onclick="clearAllData()">🗑️ Temizle</button>
</div>
</form>

<!-- Sidebar: Taslaklar ve Rapor Geçmişi -->
{sidebar_html}
</div>
"""


def build_page(form_values: Dict[str, str], result_html: str | None, message: str = "", user_info: Dict[str, str] = None, drafts: List[Dict] = None, reports: List[Dict] = None, user_courses: List[Dict] = None) -> str:
    user_html = ""
    if user_info:
        name = user_info.get('full_name', '')
        role = user_info.get('role', 'ogretim_elemani')
        initials = ''.join([n[0].upper() for n in name.split()[:2]]) if name else 'U'
        
        # Admin linki (sadece admin için)
        admin_link = '<a href="/admin" class="header-btn" style="background:#1e3a5f;color:white;">⚙️ Yönetim</a>' if role in ['admin', 'dekan', 'bolum_baskani'] else ''
        
        # Rol badge renkleri
        role_colors = {
            'admin': ('#1e3a5f', 'Yönetici'),
            'dekan': ('#7c2d12', 'Dekan'),
            'bolum_baskani': ('#065f46', 'Bölüm Bşk.'),
            'ogretim_elemani': ('#475569', 'Öğr. Elm.')
        }
        role_color, role_label = role_colors.get(role, ('#475569', 'Öğr. Elm.'))
        
        user_html = f"""
        <div class="user-info">
          <div class="name">{esc(name)} <span style="background:{role_color};color:white;padding:0.15rem 0.5rem;border-radius:10px;font-size:0.65rem;margin-left:0.25rem;">{role_label}</span></div>
          <div class="details">{esc(user_info.get('course_name', ''))} - {esc(user_info.get('program_name', ''))}</div>
        </div>
        <div class="user-avatar" style="background:{role_color};">{initials}</div>
        <div class="header-actions">
          {admin_link}
          <button onclick="openHelpModal()" class="header-btn header-btn-ghost" title="Hesaplama Yöntemleri">📖 Nasıl Hesaplanıyor?</button>
          <a href="/download-form" class="header-btn header-btn-success" title="Öğrenci veri giriş formu">📥 Excel Form</a>
          <a href="/profile" class="header-btn header-btn-ghost">Profil</a>
          <a href="/logout" class="header-btn header-btn-danger">Cikis</a>
        </div>
        """
    
    header = HTML_HEAD.replace('<div id="user-section" class="header-user"></div>', f'<div class="header-user">{user_html}</div>')
    
    # Sidebar HTML
    sidebar_html = build_sidebar(drafts or [], reports or [])
    
    body = [header, "<div class='grid'>"]
    body.append(render_form(form_values, message, sidebar_html, user_courses or []))
    if result_html:
        body.append(f"<div class='result-panel'>{result_html}</div>")
    else:
        body.append("<div class='box result-panel'><div class='empty-state'><div class='empty-state-icon'>&#128202;</div><h3>Sonuclar burada gorunecek</h3><p class='text-muted'>Verileri girip Hesapla butonuna basin.</p></div></div>")
    body.append("</div>")
    body.append(HTML_FOOT)
    return "\n".join(body)


def build_sidebar(drafts: List[Dict], reports: List[Dict]) -> str:
    """Taslak ve Rapor Geçmişi sidebar HTML'i"""
    html = []
    
    # Taslaklar
    html.append("""
    <div class="sidebar-panel">
      <div class="sidebar-header" onclick="toggleSidebar(this)">
        <span>📝 Taslaklar</span>
        <span class="toggle-icon">▼</span>
      </div>
      <div class="sidebar-body">
    """)
    
    if drafts:
        for d in drafts[:5]:
            date_str = d.get('updated_at', '')[:10] if d.get('updated_at') else ''
            html.append(f"""
            <div class="sidebar-item" data-type="draft" data-id="{d['id']}" onclick="loadDraft({d['id']})">
              <div class="sidebar-item-info">
                <div class="sidebar-item-title">{esc(d.get('name', 'Taslak'))}</div>
                <div class="sidebar-item-meta">{date_str}</div>
              </div>
              <div class="sidebar-item-actions">
                <button class="sidebar-action-btn delete" onclick="event.stopPropagation(); deleteDraft({d['id']})" title="Sil">🗑️</button>
              </div>
            </div>
            """)
    else:
        html.append('<div class="sidebar-empty">Henüz taslak yok</div>')
    
    html.append("""
      </div>
    </div>
    """)
    
    # Rapor Geçmişi
    html.append("""
    <div class="sidebar-panel">
      <div class="sidebar-header" onclick="toggleSidebar(this)">
        <span>📊 Rapor Geçmişi</span>
        <span class="toggle-icon">▼</span>
      </div>
      <div class="sidebar-body">
    """)
    
    if reports:
        for r in reports[:10]:
            date_str = r.get('created_at', '')[:10] if r.get('created_at') else ''
            pct = r.get('overall_pct', 0) or 0
            pct_class = 'success' if pct >= 70 else ('warning' if pct >= 50 else 'danger')
            html.append(f"""
            <div class="sidebar-item" data-type="report" data-id="{r['id']}" onclick="window.location.href='/report-history/{r['id']}/standard'">
              <div class="sidebar-item-info">
                <div class="sidebar-item-title">{esc(r.get('title', 'Rapor'))}</div>
                <div class="sidebar-item-meta">{date_str}</div>
              </div>
              <span class="sidebar-item-pct {pct_class}">%{pct:.0f}</span>
              <div class="sidebar-item-actions">
                <button class="sidebar-action-btn" onclick="event.stopPropagation(); window.location.href='/report-history/{r['id']}'" title="V2 Rapor">🚀</button>
                <button class="sidebar-action-btn delete" onclick="event.stopPropagation(); deleteReportConfirm({r['id']})" title="Sil">🗑️</button>
              </div>
            </div>
            """)
    else:
        html.append('<div class="sidebar-empty">Henüz rapor yok</div>')
    
    html.append("""
      </div>
    </div>
    """)
    
    return "\n".join(html)


# =============================================================================
# V2 PDF OLUŞTURUCU
# =============================================================================

def build_v2_pdf(result: Dict[str, Any], output_path: str):
    """V2 raporu PDF olarak kaydet - webdeki V2 raporun aynısı."""
    try:
        html = render_v2_report(result)
        # Basit HTML -> PDF dönüştürme: mevcut build_pdf kullanımı yerine HTML'i statik dosyaya yaz
        tmp_html = Path(output_path).with_suffix(".html")
        tmp_html.write_text(html, encoding="utf-8")
        # Eğer mevcut build_pdf aynı path'i kullanıyorsa, aynı PDF'i döndür
        build_pdf(result, output_path)
    except Exception as e:
        print(f"PDF oluşturma hatası: {e}")


# =============================================================================
# HTTP HANDLER
# =============================================================================

class Handler(BaseHTTPRequestHandler):
    def _profile_from_cookie(self) -> Dict[str, str]:
        """Kullanıcı profilini cookie'den oku (login.py tarafından yazılıyor)."""
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        raw = cookie.get("profile")
        if not raw:
            return {}
        try:
            data = json.loads(urllib.parse.unquote(raw.value))
            allowed = {"course_code", "course_name", "program_name", "term", "instructor"}
            return {k: str(v) for k, v in data.items() if k in allowed}
        except Exception:
            return {}
    
    def _get_user_email(self) -> str:
        """Cookie'den kullanıcı email'ini al."""
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        raw = cookie.get("profile")
        if not raw:
            return ""
        try:
            data = json.loads(urllib.parse.unquote(raw.value))
            return data.get("email", "")
        except Exception:
            return ""
    
    def _is_auth(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return bool(cookie.get("auth"))

    def _redirect_login(self):
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:5001/")
        self.end_headers()
        return

    def _send(self, body: str, code: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
    
    def _json_response(self, data, code: int = 200):
        import json
        body = json.dumps(data, ensure_ascii=False)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
    
    def _generate_student_report(self, student_id: str, result):
        """Öğrenciye özel kapsamlı başarı raporu oluştur."""
        try:
            computed = result.get("computed", {})
            students_data = result.get("students_data", [])
            questions = result.get("input_questions", [])
            scores = result.get("scores", {})
            docs = computed.get("docs", {})
            pocs = computed.get("pocs", {})
            peas = computed.get("peas", {})
            bloom_stats = computed.get("bloom", {})
            course = result.get("course", {})
            assessments = result.get("input_assessments", [])
            curriculum = result.get("curriculum", [])
            tyc = result.get("tyc", [])
            stark = result.get("stark", [])
            doc_tyc_map = result.get("doc_tyc_map", {})
            poc_tyc_map = result.get("poc_tyc_map", {})
            pea_stark_map = result.get("pea_stark_map", {})
            
            # Öğrenci verilerini bul
            student_info = None
            for s in students_data:
                if s.get("id") == student_id:
                    student_info = s
                    break
            
            if not student_info:
                return "<div style='padding:2rem;text-align:center;color:#ef4444;'>Öğrenci bulunamadı</div>"
            
            student_name = student_info.get("name", student_id)
            student_pct = student_info.get("pct", 0)
            student_grade = student_info.get("grade", "FF")
            is_absent = student_info.get("is_absent", False)
            student_scores = scores.get(student_id, {})
            
            # GR öğrenci kontrolü
            if is_absent:
                return f'''
                <div style="background:linear-gradient(135deg,#6b7280,#9ca3af);color:white;padding:2rem;border-radius:12px;text-align:center;">
                    <h2 style="margin:0 0 1rem 0;">🚫 SINAVA GİRMEDİ</h2>
                    <p style="margin:0;font-size:1.1rem;"><strong>{esc(student_name)}</strong> ({esc(student_id)})</p>
                    <p style="margin:1rem 0 0 0;opacity:0.8;">Bu öğrenci sınava girmemiştir. Performans analizi yapılamaz.</p>
                </div>
                '''
            
            # Sınıf istatistikleri
            attending_students = [s for s in students_data if not s.get('is_absent')]
            all_pcts = sorted([s.get("pct", 0) for s in attending_students], reverse=True)
            rank = (all_pcts.index(student_pct) + 1) if student_pct in all_pcts else len(all_pcts)
            total_students = len(all_pcts) or 1
            class_avg = computed.get("overall", {}).get("success_pct", 0)
            diff_from_avg = student_pct - class_avg
            
            # Toplam puan
            total_got = sum(float(student_scores.get(q.get("id", ""), 0)) for q in questions)
            total_max = sum(float(q.get("max_points", 0)) for q in questions) or 1
            
            # Başarılı soru sayısı
            success_count = sum(1 for q in questions if float(student_scores.get(q.get("id", ""), 0)) >= float(q.get("max_points", 1)) * 0.6)
            
            # DÖÇ bazlı performans
            doc_perf = {}
            for q in questions:
                qid = q.get("id", "")
                doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                for did in doc_ids:
                    if did:
                        if did not in doc_perf:
                            doc_perf[did] = {"got": 0, "max": 0, "questions": []}
                        doc_perf[did]["got"] += got / len(doc_ids)
                        doc_perf[did]["max"] += maxp / len(doc_ids)
                        doc_perf[did]["questions"].append(qid)
            
            # PÖÇ bazlı performans
            poc_perf = {}
            for q in questions:
                qid = q.get("id", "")
                poc_list = q.get("poc_list", [])
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                for pid in poc_list:
                    if pid:
                        if pid not in poc_perf:
                            poc_perf[pid] = {"got": 0, "max": 0, "questions": []}
                        poc_perf[pid]["got"] += got / len(poc_list) if poc_list else 0
                        poc_perf[pid]["max"] += maxp / len(poc_list) if poc_list else 0
                        poc_perf[pid]["questions"].append(qid)
            
            # PEA bazlı performans
            pea_perf = {}
            for q in questions:
                qid = q.get("id", "")
                pea_list = q.get("pea_list", [])
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                for aid in pea_list:
                    if aid:
                        if aid not in pea_perf:
                            pea_perf[aid] = {"got": 0, "max": 0, "questions": []}
                        pea_perf[aid]["got"] += got / len(pea_list) if pea_list else 0
                        pea_perf[aid]["max"] += maxp / len(pea_list) if pea_list else 0
                        pea_perf[aid]["questions"].append(qid)
            
            # Bloom bazlı performans
            bloom_perf = {}
            for q in questions:
                qid = q.get("id", "")
                bloom_list = q.get("bloom_list") or ([q.get("bloom")] if q.get("bloom") else [])
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                for b in bloom_list:
                    if b:
                        if b not in bloom_perf:
                            bloom_perf[b] = {"got": 0, "max": 0, "questions": []}
                        bloom_perf[b]["got"] += got / len(bloom_list) if bloom_list else 0
                        bloom_perf[b]["max"] += maxp / len(bloom_list) if bloom_list else 0
                        bloom_perf[b]["questions"].append(qid)
            
            # TYÇ bazlı performans (DÖÇ üzerinden)
            tyc_perf = {}
            for did, perf in doc_perf.items():
                tyc_ids = doc_tyc_map.get(did, [])
                for tid in tyc_ids:
                    if tid not in tyc_perf:
                        tyc_perf[tid] = {"got": 0, "max": 0}
                    tyc_perf[tid]["got"] += perf["got"]
                    tyc_perf[tid]["max"] += perf["max"]
            
            # STAR-K bazlı performans (PEA üzerinden)
            stark_perf = {}
            for aid, perf in pea_perf.items():
                stark_ids = pea_stark_map.get(aid, [])
                for sid in stark_ids:
                    if sid not in stark_perf:
                        stark_perf[sid] = {"got": 0, "max": 0}
                    stark_perf[sid]["got"] += perf["got"]
                    stark_perf[sid]["max"] += perf["max"]
            
            # Müfredat bazlı performans
            curr_perf = {}
            for q in questions:
                qid = q.get("id", "")
                curr_list = q.get("curriculum_list", [])
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                for cid in curr_list:
                    if cid:
                        if cid not in curr_perf:
                            curr_perf[cid] = {"got": 0, "max": 0}
                        curr_perf[cid]["got"] += got / len(curr_list) if curr_list else 0
                        curr_perf[cid]["max"] += maxp / len(curr_list) if curr_list else 0
            
            # Bileşen bazlı performans
            comp_perf = {}
            for q in questions:
                qid = q.get("id", "")
                cid = q.get("component_id", "")
                maxp = float(q.get("max_points", 0))
                got = float(student_scores.get(qid, 0))
                if cid:
                    if cid not in comp_perf:
                        comp_perf[cid] = {"got": 0, "max": 0, "name": ""}
                    comp_perf[cid]["got"] += got
                    comp_perf[cid]["max"] += maxp
            # Bileşen adlarını ekle
            for a in assessments:
                aid = a.get("id", "")
                if aid in comp_perf:
                    comp_perf[aid]["name"] = a.get("name", aid)
            
            # Güçlü ve zayıf yönler
            strong_docs = [(did, (p["got"]/p["max"]*100) if p["max"] else 0) for did, p in doc_perf.items() if p["max"] and (p["got"]/p["max"]*100) >= 70]
            weak_docs = [(did, (p["got"]/p["max"]*100) if p["max"] else 0) for did, p in doc_perf.items() if p["max"] and (p["got"]/p["max"]*100) < 50]
            strong_docs.sort(key=lambda x: -x[1])
            weak_docs.sort(key=lambda x: x[1])
            
            # Durum renkleri
            status_color = "#059669" if student_pct >= 70 else "#f59e0b" if student_pct >= 50 else "#ef4444"
            grade_color = "#059669" if student_grade in ["AA","BA","BB"] else "#f59e0b" if student_grade in ["CB","CC","DC","DD"] else "#ef4444"
            
            def get_perf_color(pct):
                if pct >= 70: return "#059669"
                if pct >= 50: return "#f59e0b"
                return "#ef4444"
            
            def get_status_badge(pct):
                if pct >= 70: return '<span style="background:#ecfdf5;color:#059669;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;">✓ Sağlandı</span>'
                if pct >= 50: return '<span style="background:#fffbeb;color:#d97706;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;">△ Kısmen</span>'
                return '<span style="background:#fef2f2;color:#dc2626;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;">✗ Yetersiz</span>'
            
            # HTML oluştur
            html = f'''
            <div style="background:linear-gradient(135deg,#1e3a5f,#2d5a87);color:white;padding:1.5rem;border-radius:12px;margin-bottom:1.5rem;">
                <h2 style="margin:0 0 0.5rem 0;font-size:1.3rem;">📋 BİREYSEL BAŞARI RAPORU</h2>
                <div style="opacity:0.9;font-size:0.9rem;">{esc(course.get("course_code", ""))} - {esc(course.get("course_name", "Ders"))}</div>
                <div style="display:flex;gap:2rem;margin-top:1rem;font-size:0.85rem;flex-wrap:wrap;">
                    <span>👤 <strong>{esc(student_name)}</strong></span>
                    <span>🔢 {esc(student_id)}</span>
                    <span>📅 {esc(course.get("term", ""))}</span>
                    <span>👨‍🏫 {esc(course.get("instructor", ""))}</span>
                </div>
            </div>
            
            <!-- ÖZET KARTLARI -->
            <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:0.75rem;margin-bottom:1.5rem;">
                <div style="text-align:center;padding:1rem;background:linear-gradient(135deg,{status_color}15,{status_color}05);border-radius:10px;border:2px solid {status_color};">
                    <div style="font-size:1.5rem;font-weight:700;color:{status_color};">%{student_pct:.1f}</div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">GENEL BAŞARI</div>
                </div>
                <div style="text-align:center;padding:1rem;background:linear-gradient(135deg,{grade_color}15,{grade_color}05);border-radius:10px;border:2px solid {grade_color};">
                    <div style="font-size:1.5rem;font-weight:700;color:{grade_color};">{student_grade}</div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">HARF NOTU</div>
                </div>
                <div style="text-align:center;padding:1rem;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
                    <div style="font-size:1.5rem;font-weight:700;color:#3b82f6;">{rank}<span style="font-size:0.9rem;color:#94a3b8;">/{total_students}</span></div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">SINIF SIRASI</div>
                </div>
                <div style="text-align:center;padding:1rem;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
                    <div style="font-size:1.5rem;font-weight:700;">{total_got:.0f}<span style="font-size:0.9rem;color:#94a3b8;">/{total_max:.0f}</span></div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">TOPLAM PUAN</div>
                </div>
                <div style="text-align:center;padding:1rem;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
                    <div style="font-size:1.5rem;font-weight:700;color:#8b5cf6;">{success_count}<span style="font-size:0.9rem;color:#94a3b8;">/{len(questions)}</span></div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">BAŞARILI SORU</div>
                </div>
                <div style="text-align:center;padding:1rem;background:{'#ecfdf5' if diff_from_avg >= 0 else '#fef2f2'};border-radius:10px;border:1px solid {'#059669' if diff_from_avg >= 0 else '#ef4444'};">
                    <div style="font-size:1.5rem;font-weight:700;color:{'#059669' if diff_from_avg >= 0 else '#ef4444'};">{diff_from_avg:+.1f}</div>
                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.25rem;">ORT. FARKI</div>
                </div>
            </div>
            
            <!-- SINIF KARŞILAŞTIRMASI -->
            <div style="padding:1rem;border-radius:8px;margin-bottom:1.5rem;background:{'#ecfdf5' if diff_from_avg >= 0 else '#fef2f2'};border-left:4px solid {'#059669' if diff_from_avg >= 0 else '#dc2626'};">
                <strong>📊 Sınıf Karşılaştırması:</strong> 
                Sınıf ortalaması <strong>%{class_avg:.1f}</strong>. Bu öğrenci sınıf ortalamasının 
                <strong style="color:{'#059669' if diff_from_avg >= 0 else '#dc2626'};">{"üzerinde ↑" if diff_from_avg >= 0 else "altında ↓"}</strong> 
                ({diff_from_avg:+.1f} puan). Sınıfın <strong>%{(rank/total_students*100):.0f}</strong>'lik diliminde.
            </div>
            '''
            
            # BİLEŞEN BAZLI PERFORMANS (Vize, Final vs.)
            if comp_perf:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #667eea;">📝 BİLEŞEN BAZLI PERFORMANS</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0.75rem;">
                '''
                for cid, perf in sorted(comp_perf.items()):
                    pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                    color = get_perf_color(pct)
                    name = perf.get("name", cid)
                    html += f'''
                    <div style="text-align:center;padding:1rem;background:#f8fafc;border-radius:8px;border-left:3px solid {color};">
                        <div style="font-size:0.75rem;color:#64748b;margin-bottom:0.25rem;">{esc(name)}</div>
                        <div style="font-size:1.3rem;font-weight:700;color:{color};">%{pct:.0f}</div>
                        <div style="font-size:0.7rem;color:#94a3b8;">{perf["got"]:.1f}/{perf["max"]:.0f}</div>
                    </div>
                    '''
                html += '</div></div>'
            
            # DÖÇ PERFORMANSI
            if doc_perf:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #10b981;">🎯 DERS ÖĞRENME ÇIKTILARI (DÖÇ) PERFORMANSI</h3>
                    <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
                        <tr style="background:#f1f5f9;"><th style="padding:0.6rem;text-align:left;border:1px solid #e2e8f0;">DÖÇ</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Puan</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Öğrenci</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Sınıf Ort.</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Fark</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Durum</th></tr>
                '''
                for did, perf in sorted(doc_perf.items()):
                    pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                    c_avg = docs.get(did, {}).get("success_pct", 0)
                    diff = pct - c_avg
                    diff_color = "#059669" if diff >= 0 else "#dc2626"
                    html += f'''<tr>
                        <td style="padding:0.6rem;border:1px solid #e2e8f0;"><strong>{esc(did)}</strong></td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">{perf["got"]:.1f}/{perf["max"]:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;font-weight:600;color:{get_perf_color(pct)};">%{pct:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">%{c_avg:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;color:{diff_color};font-weight:600;">{diff:+.1f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">{get_status_badge(pct)}</td>
                    </tr>'''
                html += '</table></div>'
            
            # PÖÇ PERFORMANSI
            if poc_perf:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #3b82f6;">🏆 PROGRAM ÖĞRENME ÇIKTILARI (PÖÇ) PERFORMANSI</h3>
                    <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
                        <tr style="background:#f1f5f9;"><th style="padding:0.6rem;text-align:left;border:1px solid #e2e8f0;">PÖÇ</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Öğrenci</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Sınıf Ort.</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Fark</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Durum</th></tr>
                '''
                for pid, perf in sorted(poc_perf.items()):
                    pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                    c_avg = pocs.get(pid, {}).get("success_pct", 0)
                    diff = pct - c_avg
                    diff_color = "#059669" if diff >= 0 else "#dc2626"
                    html += f'''<tr>
                        <td style="padding:0.6rem;border:1px solid #e2e8f0;"><strong>{esc(pid)}</strong></td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;font-weight:600;color:{get_perf_color(pct)};">%{pct:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">%{c_avg:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;color:{diff_color};font-weight:600;">{diff:+.1f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">{get_status_badge(pct)}</td>
                    </tr>'''
                html += '</table></div>'
            
            # PEA PERFORMANSI
            if pea_perf:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #8b5cf6;">🎓 PROGRAM EĞİTİM AMAÇLARI (PEA) PERFORMANSI</h3>
                    <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
                        <tr style="background:#f1f5f9;"><th style="padding:0.6rem;text-align:left;border:1px solid #e2e8f0;">PEA</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Öğrenci</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Sınıf Ort.</th><th style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">Durum</th></tr>
                '''
                for aid, perf in sorted(pea_perf.items()):
                    pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                    c_avg = peas.get(aid, {}).get("success_pct", 0)
                    html += f'''<tr>
                        <td style="padding:0.6rem;border:1px solid #e2e8f0;"><strong>{esc(aid)}</strong></td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;font-weight:600;color:{get_perf_color(pct)};">%{pct:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">%{c_avg:.0f}</td>
                        <td style="padding:0.6rem;text-align:center;border:1px solid #e2e8f0;">{get_status_badge(pct)}</td>
                    </tr>'''
                html += '</table></div>'
            
            # TYÇ YETERLİLİKLERİ
            if tyc_perf and tyc:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #f59e0b;">🇹🇷 TÜRKİYE YETERLİLİKLER ÇERÇEVESİ (TYÇ)</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:0.5rem;">
                '''
                for t in tyc:
                    tid = t.get("id", "")
                    if tid in tyc_perf:
                        perf = tyc_perf[tid]
                        pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                        color = get_perf_color(pct)
                        html += f'''
                        <div style="text-align:center;padding:0.75rem;background:#fffbeb;border-radius:6px;border:1px solid #fcd34d;">
                            <div style="font-size:0.7rem;color:#92400e;font-weight:600;">{esc(tid)}</div>
                            <div style="font-size:1.1rem;font-weight:700;color:{color};">%{pct:.0f}</div>
                        </div>
                        '''
                html += '</div></div>'
            
            # STAR-K SEKTÖR STANDARTLARI
            if stark_perf and stark:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #06b6d4;">⭐ STAR-K SEKTÖR STANDARTLARI</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:0.5rem;">
                '''
                for s in stark:
                    sid = s.get("id", "")
                    if sid in stark_perf:
                        perf = stark_perf[sid]
                        pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                        color = get_perf_color(pct)
                        html += f'''
                        <div style="text-align:center;padding:0.75rem;background:#ecfeff;border-radius:6px;border:1px solid #67e8f9;">
                            <div style="font-size:0.7rem;color:#0e7490;font-weight:600;">{esc(sid)}</div>
                            <div style="font-size:1.1rem;font-weight:700;color:{color};">%{pct:.0f}</div>
                        </div>
                        '''
                html += '</div></div>'
            
            # BLOOM TAKSONOMİSİ
            if bloom_perf:
                html += '''
                <div style="margin-bottom:1.5rem;">
                    <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #ec4899;">🧠 BLOOM TAKSONOMİSİ PERFORMANSI</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:0.5rem;">
                '''
                bloom_order = ["Bilgi", "Kavrama", "Uygulama", "Analiz", "Sentez", "Değerlendirme"]
                shown = set()
                for b in bloom_order:
                    if b in bloom_perf:
                        shown.add(b)
                        perf = bloom_perf[b]
                        pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                        c_avg = bloom_stats.get(b, {}).get("success_pct", 0)
                        color = get_perf_color(pct)
                        html += f'''
                        <div style="text-align:center;padding:0.75rem;background:#fdf4ff;border-radius:6px;border:1px solid #f0abfc;">
                            <div style="font-size:0.7rem;color:#86198f;font-weight:600;">{esc(b)}</div>
                            <div style="font-size:1.1rem;font-weight:700;color:{color};">%{pct:.0f}</div>
                            <div style="font-size:0.6rem;color:#a855f7;">Sınıf: %{c_avg:.0f}</div>
                        </div>
                        '''
                for b, perf in sorted(bloom_perf.items()):
                    if b not in shown:
                        pct = (perf["got"] / perf["max"] * 100) if perf["max"] else 0
                        c_avg = bloom_stats.get(b, {}).get("success_pct", 0)
                        color = get_perf_color(pct)
                        html += f'''
                        <div style="text-align:center;padding:0.75rem;background:#fdf4ff;border-radius:6px;border:1px solid #f0abfc;">
                            <div style="font-size:0.7rem;color:#86198f;font-weight:600;">{esc(b)}</div>
                            <div style="font-size:1.1rem;font-weight:700;color:{color};">%{pct:.0f}</div>
                            <div style="font-size:0.6rem;color:#a855f7;">Sınıf: %{c_avg:.0f}</div>
                        </div>
                        '''
                html += '</div></div>'
            
            # GÜÇLÜ VE ZAYIF YÖNLER
            html += '''
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem;">
            '''
            # Güçlü yönler
            html += '<div style="padding:1rem;background:#ecfdf5;border-radius:8px;border:1px solid #a7f3d0;">'
            html += '<h4 style="margin:0 0 0.75rem 0;font-size:0.85rem;color:#059669;">💪 GÜÇLÜ YÖNLER</h4>'
            if strong_docs:
                html += '<ul style="margin:0;padding-left:1.2rem;font-size:0.8rem;color:#047857;">'
                for did, pct in strong_docs[:5]:
                    html += f'<li style="margin-bottom:0.3rem;"><strong>{esc(did)}</strong>: %{pct:.0f}</li>'
                html += '</ul>'
            else:
                html += '<p style="margin:0;font-size:0.8rem;color:#6b7280;font-style:italic;">Henüz güçlü alan belirlenmedi</p>'
            html += '</div>'
            
            # Zayıf yönler
            html += '<div style="padding:1rem;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;">'
            html += '<h4 style="margin:0 0 0.75rem 0;font-size:0.85rem;color:#dc2626;">⚠️ GELİŞTİRİLMESİ GEREKEN ALANLAR</h4>'
            if weak_docs:
                html += '<ul style="margin:0;padding-left:1.2rem;font-size:0.8rem;color:#b91c1c;">'
                for did, pct in weak_docs[:5]:
                    html += f'<li style="margin-bottom:0.3rem;"><strong>{esc(did)}</strong>: %{pct:.0f}</li>'
                html += '</ul>'
            else:
                html += '<p style="margin:0;font-size:0.8rem;color:#6b7280;font-style:italic;">Tüm alanlarda yeterli performans</p>'
            html += '</div></div>'
            
            # SORU BAZLI DETAYLI PERFORMANS
            html += '''
            <div style="margin-bottom:1.5rem;">
                <h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #64748b;">📝 SORU BAZLI DETAYLI PERFORMANS</h3>
                <table style="width:100%;border-collapse:collapse;font-size:0.75rem;">
                    <tr style="background:#f1f5f9;"><th style="padding:0.5rem;text-align:left;border:1px solid #e2e8f0;">Soru</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">DÖÇ</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">Bloom</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">Alınan</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">Max</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">%</th><th style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">Sınıf Ort.</th></tr>
            '''
            question_outcomes = result.get("question_outcomes", {}).get("per_question", {})
            for q in questions:
                qid = q.get("id", "")
                got = float(student_scores.get(qid, 0))
                maxp = float(q.get("max_points", 1)) or 1
                pct = (got / maxp * 100)
                doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
                bloom_list = q.get("bloom_list") or ([q.get("bloom")] if q.get("bloom") else [])
                q_outcome = question_outcomes.get(qid, {})
                class_avg = (q_outcome.get("avg_score", 0) / maxp * 100) if maxp else 0
                row_bg = "#ecfdf5" if pct >= 70 else "#fef2f2" if pct < 50 else "#fffbeb"
                html += f'''<tr style="background:{row_bg};">
                    <td style="padding:0.5rem;border:1px solid #e2e8f0;font-weight:600;">{esc(qid)}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;font-size:0.7rem;">{esc(", ".join(doc_ids))}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;font-size:0.7rem;">{esc(", ".join(bloom_list))}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;font-weight:600;">{got:.1f}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">{maxp:.0f}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;font-weight:700;color:{get_perf_color(pct)};">%{pct:.0f}</td>
                    <td style="padding:0.5rem;text-align:center;border:1px solid #e2e8f0;">%{class_avg:.0f}</td>
                </tr>'''
            html += '</table></div>'
            
            # DEĞERLENDİRME VE ÖNERİLER
            html += '<div style="margin-bottom:1rem;">'
            html += '<h3 style="font-size:0.95rem;font-weight:600;color:#1e293b;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:2px solid #6366f1;">💡 DEĞERLENDİRME VE ÖNERİLER</h3>'
            
            if student_pct >= 70:
                html += f'''<div style="padding:1rem;border-radius:8px;background:#ecfdf5;border-left:4px solid #059669;margin-bottom:0.75rem;">
                    <strong>✅ Tebrikler!</strong> Bu öğrenci dersi başarıyla tamamlamıştır. Tüm öğrenme çıktılarında yeterli performans göstermiştir.
                </div>'''
            elif student_pct >= 50:
                html += f'''<div style="padding:1rem;border-radius:8px;background:#fffbeb;border-left:4px solid #d97706;margin-bottom:0.75rem;">
                    <strong>⚠️ Koşullu Başarı:</strong> Bu öğrenci dersi kısmen başarılı tamamlamıştır. Bazı alanlarda ek çalışma önerilir.
                </div>'''
            else:
                html += f'''<div style="padding:1rem;border-radius:8px;background:#fef2f2;border-left:4px solid #dc2626;margin-bottom:0.75rem;">
                    <strong>❌ Dikkat:</strong> Bu öğrenci başarı kriterlerini karşılamamaktadır. Acil destek ve telafi çalışması gereklidir.
                </div>'''
            
            # Öneriler
            if weak_docs:
                html += '<div style="padding:1rem;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">'
                html += '<strong style="color:#475569;">📌 Öneriler:</strong><ul style="margin:0.5rem 0 0 0;padding-left:1.2rem;font-size:0.85rem;color:#64748b;">'
                for did, pct in weak_docs[:3]:
                    html += f'<li style="margin-bottom:0.3rem;"><strong>{esc(did)}</strong> konusunda ek çalışma yapılmalı</li>'
                html += '</ul></div>'
            
            html += '</div>'
            
            # FOOTER
            html += f'''
            <div style="margin-top:1.5rem;padding-top:1rem;border-top:2px solid #e2e8f0;font-size:0.7rem;color:#94a3b8;text-align:center;">
                Bu rapor {esc(course.get("course_name", ""))} dersi için otomatik olarak oluşturulmuştur.<br>
                Rapor Tarihi: {datetime.now().strftime("%d.%m.%Y %H:%M")}
            </div>
            '''
            
            return html
        except Exception as e:
            import traceback
            return f"<div style='padding:2rem;color:#ef4444;'>Rapor oluşturma hatası: {str(e)}<br><pre style='font-size:0.7rem;'>{traceback.format_exc()}</pre></div>"
    
    def _generate_pdf_from_html(self, html: str) -> bytes:
        """HTML'den PDF oluştur ve bytes olarak döndür."""
        try:
            from weasyprint import HTML
            import io
            pdf_buffer = io.BytesIO()
            HTML(string=html, base_url=str(Path(__file__).parent)).write_pdf(pdf_buffer)
            return pdf_buffer.getvalue()
        except Exception as e:
            # WeasyPrint yoksa veya hata varsa, HTML'i döndür
            return html.encode('utf-8')

    def do_GET(self):
        # API endpoint'leri için özel auth kontrolü (JSON döndür)
        if self.path.startswith("/api/"):
            if not self._is_auth():
                self._json_response({"error": "Oturum açmanız gerekiyor"}, 401)
                return
            
            # Ders Verisi API - /api/course-data/<course_code>
            if self.path.startswith("/api/course-data/"):
                try:
                    course_code = urllib.parse.unquote(self.path.split("/api/course-data/")[1].split("?")[0])
                    if not course_code:
                        self._json_response({"error": "Ders kodu gerekli", "success": False})
                        return
                    
                    course_data = get_course_data(course_code)
                    if course_data:
                        self._json_response({
                            "success": True,
                            "tyc_text": course_data.get('tyc_text', ''),
                            "bloom_text": course_data.get('bloom_text', ''),
                            "stark_text": course_data.get('stark_text', ''),
                            "pea_text": course_data.get('pea_text', ''),
                            "poc_text": course_data.get('poc_text', ''),
                            "doc_text": course_data.get('doc_text', ''),
                            "curriculum_text": course_data.get('curriculum_text', ''),
                            "bologna_link": course_data.get('bologna_link', ''),
                            "course_name": course_data.get('course_name', ''),
                        })
                    else:
                        self._json_response({"success": False, "error": "Ders bulunamadı"})
                except Exception as e:
                    self._json_response({"error": f"Ders verisi hatası: {str(e)}", "success": False})
                return
            
            # Öğrenci Raporu API
            if self.path.startswith("/api/student-report/"):
                try:
                    student_id = urllib.parse.unquote(self.path.split("/api/student-report/")[1].split("?")[0])
                    result = STATE.get("last_result")
                    if not result:
                        self._json_response({"error": "Önce hesaplama yapın"})
                        return
                    html = self._generate_student_report(student_id, result)
                    self._json_response({"html": html})
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    self._json_response({"error": f"Rapor oluşturma hatası: {str(e)}", "detail": error_detail})
                return
            
            # Bilinmeyen API endpoint
            self._json_response({"error": "Bilinmeyen API"}, 404)
            return
        
        if not self._is_auth():
            return self._redirect_login()
        
        if self.path.startswith("/download.pdf"):
            pdf_path = STATE.get("last_pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                self.send_error(404, "PDF yok")
                return
            data = Path(pdf_path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", "attachment; filename=standart_rapor.pdf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        
        if self.path.startswith("/download-v2.pdf"):
            # V2 için de aynı PDF'i kullan (mevcut engine çıktısı)
            pdf_path = STATE.get("last_pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                self.send_error(404, "Önce hesaplama yapın")
                return
            data = Path(pdf_path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", "attachment; filename=v2_detayli_rapor.pdf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        
        if self.path.startswith("/report-v2"):
            result = STATE.get("last_result")
            if not result:
                self.send_error(404, "Önce hesaplama yapın")
                return
            self._send(render_v2_report(result))
            return
        
        # Geçmiş Rapor Görüntüleme
        if self.path.startswith("/report-history/"):
            try:
                parts = self.path.split("/")
                report_id = int(parts[2])
                
                # PDF indirme
                if len(parts) > 3 and parts[3] == "pdf":
                    report = get_report(report_id)
                    if not report:
                        self.send_error(404, "Rapor bulunamadı")
                        return
                    result = json.loads(report.get("result", "{}"))
                    html = render_tables(result, standalone=True, report_id=report_id)
                    pdf_data = self._generate_pdf_from_html(html)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f"attachment; filename=rapor_{report_id}.pdf")
                    self.send_header("Content-Length", str(len(pdf_data)))
                    self.end_headers()
                    self.wfile.write(pdf_data)
                    return
                
                # PDF-V2 indirme
                if len(parts) > 3 and parts[3] == "pdf-v2":
                    report = get_report(report_id)
                    if not report:
                        self.send_error(404, "Rapor bulunamadı")
                        return
                    result = json.loads(report.get("result", "{}"))
                    html = render_v2_report(result, show_toolbar=False, report_id=report_id)
                    pdf_data = self._generate_pdf_from_html(html)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f"attachment; filename=rapor_v2_{report_id}.pdf")
                    self.send_header("Content-Length", str(len(pdf_data)))
                    self.end_headers()
                    self.wfile.write(pdf_data)
                    return
                
                # Standart Rapor görüntüleme
                if len(parts) > 3 and parts[3] == "standard":
                    report = get_report(report_id)
                    if not report:
                        self.send_error(404, "Rapor bulunamadı")
                        return
                    result = json.loads(report.get("result", "{}"))
                    html = render_tables(result, standalone=True, report_id=report_id)
                    self._send(html)
                    return
                
                # Varsayılan: V2 Rapor görüntüleme
                report = get_report(report_id)
                if not report:
                    self.send_error(404, "Rapor bulunamadı")
                    return
                result = json.loads(report.get("result", "{}"))
                # V2 raporda toolbar ile standart rapora geçiş linki ekle
                html = render_v2_report(result, show_toolbar=True, report_id=report_id)
                self._send(html)
                return
            except Exception as e:
                self.send_error(500, f"Rapor yükleme hatası: {str(e)}")
                return
        
        # Kullanıcı verilerini veritabanından yükle
        user_email = self._get_user_email()
        defaults = get_empty_form_defaults()  # Boş başlangıç değerleri
        
        # DEBUG: Sayfa yüklenirken bilgi logla
        import sys
        print(f"[do_GET] user_email: {user_email}", file=sys.stderr)
        
        # Kullanıcı bilgilerini al
        user_info = None
        user_courses = []
        drafts = []
        reports = []
        course_code = ""
        
        if user_email:
            from login import fetch_user, get_user_courses, get_drafts, get_report_history
            user = fetch_user(user_email)
            
            if user:
                # ÖNEMLİ: course_code'u USER TABLOSUNDAN al (en güncel ve güvenilir kaynak)
                course_code = user.get('course_code', '')
                course_name = user.get('course_name', '')
                
                print(f"[do_GET] user.course_code: {course_code}, course_name: {course_name}", file=sys.stderr)
                
                # Ders bazlı verileri yükle (course_data tablosundan)
                if course_code:
                    course_data = get_course_data(course_code)
                    print(f"[do_GET] course_data keys: {list(course_data.keys()) if course_data else 'None'}", file=sys.stderr)
                    print(f"[do_GET] tyc_text length: {len(course_data.get('tyc_text', '')) if course_data else 0}", file=sys.stderr)
                    print(f"[do_GET] doc_text length: {len(course_data.get('doc_text', '')) if course_data else 0}", file=sys.stderr)
                    
                    if course_data:
                        # Alan adı eşleştirmeleri: course_data -> form alanları
                        field_mappings = {
                            'tyc_text': 'tyc_text',
                            'stark_text': 'stark_text',
                            'doc_text': 'docs_text',
                            'poc_text': 'pocs_text',
                            'pea_text': 'peas_text',
                            'curriculum_text': 'curriculum_text',
                            'bloom_text': 'bloom_text',
                        }
                        for src_key, dst_key in field_mappings.items():
                            val = course_data.get(src_key, '')
                            if val:
                                defaults[dst_key] = val
                        # course_name'i de course_data'dan al (daha güncel olabilir)
                        if course_data.get('course_name'):
                            course_name = course_data['course_name']
                
                # Kullanıcının kaydedilmiş eşleştirme verilerini yükle (user_curriculum tablosundan)
                curriculum_data = get_user_curriculum(user_email)
                if curriculum_data:
                    for key in ["doc_tyc_map_text", "poc_tyc_map_text",
                               "pea_stark_map_text", "poc_pea_map_text", "doc_poc_weights_text",
                               "components_text", "grading_text", "curriculum_doc_map_text",
                               "question_map_text"]:
                        if curriculum_data.get(key):
                            defaults[key] = curriculum_data[key]
                    if curriculum_data.get("thresholds_met"):
                        defaults["thresholds_met"] = curriculum_data["thresholds_met"]
                    if curriculum_data.get("thresholds_partial"):
                        defaults["thresholds_partial"] = curriculum_data["thresholds_partial"]
                
                # Ders ve kullanıcı bilgilerini defaults'a ekle
                defaults['course_code'] = course_code
                defaults['course_name'] = course_name
                defaults['program_name'] = user.get('program_name', '')
                defaults['term'] = user.get('term', '')
                defaults['instructor'] = user.get('instructor', '') or user.get('full_name', '')
                
                user_info = {
                    'email': user_email,
                    'full_name': user.get('full_name', ''),
                    'role': user.get('role', 'ogretim_elemani'),
                    'course_code': course_code,
                    'course_name': course_name,
                    'program_name': user.get('program_name', ''),
                    'term': user.get('term', ''),
                }
                
                # Yetkili dersleri al
                user_courses = get_user_courses(user_email)
                # Ana dersi de ekle (eğer listede yoksa)
                if course_code:
                    course_codes = [uc.get('course_code') for uc in user_courses]
                    if course_code not in course_codes:
                        user_courses.insert(0, {
                            'course_code': course_code,
                            'course_name': course_name
                        })
                
                # Taslak ve raporları al
                drafts = get_drafts(user_email)
                reports = get_report_history(user_email)
        
        self._send(build_page(defaults, result_html=None, user_info=user_info, drafts=drafts, reports=reports, user_courses=user_courses))

    def do_POST(self):
        if not self._is_auth():
            return self._redirect_login()
        
        # API: Ders değiştirme
        if self.path == "/api/switch-course":
            import sys
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                new_course_code = data.get('course_code', '').strip()
                
                print(f"[api/switch-course] Gelen course_code: {new_course_code}", file=sys.stderr)
                
                if not new_course_code:
                    self._json_response({"error": "Ders kodu gerekli", "success": False})
                    return
                
                user_email = self._get_user_email()
                print(f"[api/switch-course] user_email: {user_email}", file=sys.stderr)
                
                if not user_email:
                    self._json_response({"error": "Kullanıcı bulunamadı", "success": False})
                    return
                
                from login import fetch_user, update_user_course, get_course_data as get_cd
                
                # Ders verilerini al
                course_data = get_cd(new_course_code)
                course_name = course_data.get('course_name', '') if course_data else ''
                
                print(f"[api/switch-course] course_data bulundu: {bool(course_data)}, course_name: {course_name}", file=sys.stderr)
                
                # User tablosunu güncelle
                update_user_course(user_email, new_course_code, course_name)
                print(f"[api/switch-course] User tablosu güncellendi", file=sys.stderr)
                
                # Cookie'yi güncelle
                user = fetch_user(user_email)
                print(f"[api/switch-course] Güncel user.course_code: {user.get('course_code') if user else 'None'}", file=sys.stderr)
                
                if user:
                    profile_data = {
                        "email": user_email,
                        "full_name": user.get('full_name', ''),
                        "role": user.get('role', ''),
                        "course_code": new_course_code,
                        "course_name": course_name,
                        "program_name": user.get('program_name', ''),
                        "term": user.get('term', ''),
                        "instructor": user.get('instructor', ''),
                    }
                    
                    cookie_value = urllib.parse.quote(json.dumps(profile_data))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Set-Cookie", f"profile={cookie_value}; Path=/; Max-Age=2592000")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "course_code": new_course_code, "course_name": course_name}).encode('utf-8'))
                    return
                
                self._json_response({"success": True, "course_code": new_course_code})
            except Exception as e:
                print(f"[api/switch-course] HATA: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._json_response({"error": str(e), "success": False})
            return
        
        if not self.path.startswith("/compute"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw)
        values = {k: form.get(k, [""])[0] for k in FORM_KEYS}
        try:
            payload, defaults = build_payload_from_form(values)
        except Exception as e:
            self._send(build_page(ensure_form_defaults(values), None, f"Hata: {e}"), 400)
            return
        try:
            result = compute(payload)
            out_pdf = Path(__file__).parent / "web_report.pdf"
            out_pdf_v2 = Path(__file__).parent / "web_report_v2.pdf"
            html_main = render_tables(result, standalone=True)
            html_v2 = render_v2_report(result)
            ok_main = export_pdf_from_html(html_main, out_pdf)
            ok_v2 = export_pdf_from_html(html_v2, out_pdf_v2)
            # WeasyPrint yoksa legacy PDF'e dön
            if not ok_main:
                legacy_pdf(result, str(out_pdf))
            if not ok_v2:
                legacy_pdf(result, str(out_pdf_v2))
            result["curriculum"] = payload.get("curriculum", [])
            result["tyc"] = payload.get("tyc", [])
            result["stark"] = payload.get("stark", [])
            result["doc_tyc_map"] = payload.get("doc_tyc_map", {})
            result["poc_tyc_map"] = payload.get("poc_tyc_map", {})
            result["pea_stark_map"] = payload.get("pea_stark_map", {})
            result["doc_poc_weights"] = payload.get("doc_poc_weights", {})
            result["poc_pea_map"] = payload.get("poc_pea_map", {})
            result["doc_pea_map"] = payload.get("doc_pea_map", {})
            result["doc_stark_map"] = payload.get("doc_stark_map", {})
            result["input_questions"] = payload.get("questions", [])
            result["input_students"] = payload.get("students", [])
            result["input_assessments"] = payload.get("assessments", [])
            result["scores"] = payload.get("scores", {})
            result["grading"] = payload.get("grading", {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0})
            result["coverage"] = compute_coverage(payload.get("questions", []))
            result["question_outcomes"] = compute_question_outcomes(payload.get("questions", []), payload.get("scores", {}))
            result["course"] = payload.get("course", {})
            result["students_data"] = compute_student_results(payload.get("questions", []), payload.get("scores", {}), payload.get("students", []), payload.get("assessments", []))
            result["weekly_coverage"] = compute_weekly_coverage(payload.get("questions", []))
            STATE["last_result"] = result
            STATE["last_payload_text"] = json.dumps(payload, ensure_ascii=False, indent=2)
            STATE["last_pdf_path"] = str(out_pdf)
            STATE["last_v2_pdf_path"] = str(out_pdf_v2)
            
            # Kullanıcının müfredat verilerini kaydet (sonraki girişlerde otomatik yüklenecek)
            user_email = self._get_user_email()
            if user_email:
                curriculum_data = {
                    "tyc_text": values.get("tyc_text", ""),
                    "stark_text": values.get("stark_text", ""),
                    "docs_text": values.get("docs_text", ""),
                    "pocs_text": values.get("pocs_text", ""),
                    "peas_text": values.get("peas_text", ""),
                    "curriculum_text": values.get("curriculum_text", ""),
                    "bloom_text": values.get("bloom_text", ""),
                    "doc_tyc_map_text": values.get("doc_tyc_map_text", ""),
                    "poc_tyc_map_text": values.get("poc_tyc_map_text", ""),
                    "pea_stark_map_text": values.get("pea_stark_map_text", ""),
                    "poc_pea_map_text": values.get("poc_pea_map_text", ""),
                    "doc_poc_weights_text": values.get("doc_poc_weights_text", ""),
                    "components_text": values.get("assessments_text", ""),
                    "thresholds_met": values.get("thresholds_met", "70"),
                    "thresholds_partial": values.get("thresholds_partial", "50"),
                    "grading_text": values.get("grading_text", ""),
                }
                save_user_curriculum(user_email, curriculum_data)
        except Exception as e:
            self._send(build_page(defaults, None, f"Hesap hatası: {e}"), 500)
            return
        self._send(build_page(defaults, render_tables(result)))


def main():
    host, port = "127.0.0.1", 5000
    print(f"🚀 Server: http://{host}:{port}")
    print("   Modern arayüz hazır.")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()

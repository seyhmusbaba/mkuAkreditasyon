"""
AkrediX - Login Module
Güvenli Authentication + Rol Sistemi + Bologna Entegrasyonu
"""
import sqlite3
import hashlib
import secrets
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

# Web scraping için
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False

DB_PATH = Path(__file__).with_name("auth.db")


# ============ BOLOGNA WEB SCRAPING ============

def fetch_bologna_data(bologna_url: str) -> dict:
    """Bologna sayfasından DÖÇ ve Müfredat verilerini çek - MKÜ Bologna yapısına özel"""
    if not HAS_SCRAPING or not bologna_url:
        return {"doc_text": "", "curriculum_text": "", "error": "Scraping modülü yüklü değil veya URL boş"}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        response = requests.get(bologna_url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        doc_text = ""
        curriculum_text = ""
        
        # ============ DÖÇ - lblDersinOgrenmeCiktilari ID'li başlığın altındaki tablo ============
        doc_header = soup.find(id='lblDersinOgrenmeCiktilari')
        if doc_header:
            # Başlıktan sonraki tabloyu bul
            doc_table = doc_header.find_next('table')
            if doc_table:
                doc_items = []
                rows = doc_table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        num_cell = cells[0].get_text(strip=True)
                        desc_cell = cells[1].get_text(strip=True)
                        
                        # Header satırını atla
                        if num_cell.lower() in ['no', 'sıra', '#', '']:
                            continue
                        if 'öğrenme' in desc_cell.lower() or 'çıktı' in desc_cell.lower():
                            continue
                        
                        if num_cell.isdigit() and desc_cell and len(desc_cell) > 5:
                            doc_items.append(f"DÖÇ{num_cell} | {desc_cell}")
                        elif desc_cell and len(desc_cell) > 15 and not num_cell.isdigit():
                            doc_items.append(f"DÖÇ{len(doc_items)+1} | {desc_cell}")
                
                if doc_items:
                    doc_text = "\n".join(doc_items[:15])
        
        # ============ MÜFREDAT - lblDersKonulari_h ID'li başlığın altındaki tablo ============
        curr_header = soup.find(id='lblDersKonulari_h')
        if curr_header:
            # Başlıktan sonraki tabloyu bul
            curr_table = curr_header.find_next('table')
            if curr_table:
                curr_items = []
                rows = curr_table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        week_cell = cells[0].get_text(strip=True)
                        topic_cell = cells[1].get_text(strip=True)
                        
                        # Header satırını atla
                        if week_cell.lower() in ['hafta', 'week', 'no', '#', '']:
                            continue
                        if 'konu' in topic_cell.lower() or 'ders içeriği' in topic_cell.lower():
                            continue
                        
                        if topic_cell and len(topic_cell) > 2:
                            if week_cell.isdigit():
                                curr_items.append(f"H{week_cell} | {topic_cell}")
                            else:
                                curr_items.append(f"H{len(curr_items)+1} | {topic_cell}")
                
                if curr_items:
                    curriculum_text = "\n".join(curr_items[:16])
        
        # ============ FALLBACK - ID bulunamazsa genel arama ============
        if not doc_text:
            # Tüm tabloları tara, "Öğrenme Çıktıları" içeren başlığı ara
            for table in soup.find_all('table'):
                prev_text = ""
                prev_el = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'span', 'div', 'label'])
                if prev_el:
                    prev_text = prev_el.get_text().lower()
                
                if 'öğrenme' in prev_text and 'çıktı' in prev_text:
                    doc_items = []
                    rows = table.find_all('tr')
                    for row in rows[1:]:  # İlk satır header
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            num_cell = cells[0].get_text(strip=True)
                            desc_cell = cells[1].get_text(strip=True)
                            if num_cell.isdigit() and desc_cell and len(desc_cell) > 5:
                                doc_items.append(f"DÖÇ{num_cell} | {desc_cell}")
                    if doc_items:
                        doc_text = "\n".join(doc_items[:15])
                        break
        
        if not curriculum_text:
            # Tüm tabloları tara, "Ders Konuları" içeren başlığı ara
            for table in soup.find_all('table'):
                prev_text = ""
                prev_el = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'span', 'div', 'label'])
                if prev_el:
                    prev_text = prev_el.get_text().lower()
                
                if 'ders konu' in prev_text or 'hafta' in prev_text:
                    curr_items = []
                    rows = table.find_all('tr')
                    for row in rows[1:]:  # İlk satır header
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            week_cell = cells[0].get_text(strip=True)
                            topic_cell = cells[1].get_text(strip=True)
                            if week_cell.isdigit() and topic_cell and len(topic_cell) > 2:
                                curr_items.append(f"H{week_cell} | {topic_cell}")
                    if curr_items:
                        curriculum_text = "\n".join(curr_items[:16])
                        break
        
        return {
            "doc_text": doc_text,
            "curriculum_text": curriculum_text,
            "success": bool(doc_text or curriculum_text)
        }
        
    except Exception as e:
        return {"doc_text": "", "curriculum_text": "", "error": str(e)}


# ============ ROL TANIMLARI ============
ROLES = {
    "admin": {
        "name": "Sistem Yöneticisi",
        "level": 100,
        "color": "#1e3a5f",           # Koyu lacivert
        "bg_color": "#e8eef4",
        "border_color": "#2c5282",
        "permissions": ["all", "add_department", "manage_users", "edit_department_data", "edit_all_data"]
    },
    "dekan": {
        "name": "Dekan",
        "level": 80,
        "color": "#7c2d12",            # Koyu bordo
        "bg_color": "#fef2f2",
        "border_color": "#9c4221",
        "permissions": ["edit_department_data", "view_all_reports", "manage_department_users", "edit_pea_poc"]
    },
    "bolum_baskani": {
        "name": "Bölüm Başkanı",
        "level": 60,
        "color": "#065f46",            # Koyu yeşil
        "bg_color": "#ecfdf5",
        "border_color": "#047857",
        "permissions": ["edit_department_data", "view_department_reports", "manage_department_users", "edit_pea_poc"]
    },
    "ogretim_elemani": {
        "name": "Öğretim Elemanı",
        "level": 20,
        "color": "#475569",            # Koyu gri
        "bg_color": "#f8fafc",
        "border_color": "#64748b",
        "permissions": ["edit_own_courses", "view_own_reports"]
    }
}

# ============ VARSAYILAN VERİLER (Boş - Kullanıcı girecek) ============
DEFAULT_TYC = ""
DEFAULT_BLOOM = ""
DEFAULT_STARK = ""

# ============ BÖLÜM VERİLERİ ============
DEPARTMENTS = {
    "siyaset_bilimi": {
        "id": "5719",
        "name": "Siyaset Bilimi ve Kamu Yönetimi",
        "faculty": "İktisadi ve İdari Bilimler Fakültesi"
    }
}

# ============ DÖNEM BAZLI DERS LİSTESİ (Bologna'dan) ============
DEPARTMENT_COURSES = {
    "siyaset_bilimi": {
        "1": [
            {"code": "1403101", "name": "Yönetim Bilimi I", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403103", "name": "Toplum Bilimi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403105", "name": "Siyaset Bilimi I", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403107", "name": "Hukukun Temel Kavramları", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403109", "name": "İktisada Giriş I", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403111", "name": "Kamu Yönetimi", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403131", "name": "Türk Dili I", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403141", "name": "Yabancı Dil I", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403199", "name": "Kariyer Planlama", "credits": "1+0+0", "akts": 2, "type": "Zorunlu"},
        ],
        "2": [
            {"code": "1403202", "name": "Yönetim Bilimi II", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403206", "name": "Siyaset Bilimi II", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403208", "name": "Medeni Hukuk", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403210", "name": "İktisada Giriş II", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403212", "name": "Anayasaya Giriş", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403232", "name": "Türk Dili II", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403242", "name": "Yabancı Dil II", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403252", "name": "Uygarlık Tarihi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
        ],
        "3": [
            {"code": "1403301", "name": "Türk Anayasa Hukuku", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403303", "name": "Yönetim Hukuku", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403307", "name": "Kent ve Çevre Sorunları", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403309", "name": "Toplum Bilim. Araştırma Yöntemleri", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403327", "name": "Siyasal Düşünceler Tarihine Giriş", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403351", "name": "Atatürk İlkeleri Ve İnkılap Tarihi I", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403313", "name": "Mesleki İngilizce I", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403315", "name": "Yönetim Bilişim Sistemleri", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403317", "name": "İşletme Bilimine Giriş", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403321", "name": "Makro İktisat", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403325", "name": "Siyaset Sosyolojisi", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
        ],
        "4": [
            {"code": "1403402", "name": "Kamu Maliyesi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403404", "name": "Personel Yönetimi", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403406", "name": "Yönetsel Yargı", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403408", "name": "Çevre Yönetimi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403410", "name": "Siyasal Düşünceler Tarihi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403452", "name": "Atatürk İlkeleri ve İnkılap Tarihi II", "credits": "2+0+0", "akts": 2, "type": "Zorunlu"},
            {"code": "1403416", "name": "Örgüt Kuramları", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403418", "name": "Avrupa Birliği Politikaları", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403426", "name": "Sosyal Politika", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
        ],
        "5": [
            {"code": "1403501", "name": "Yerel Yönetimler", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403505", "name": "Türk Siyasal Yaşamı I", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403507", "name": "Borçlar Hukuku", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403513", "name": "Kentleşme ve Konut Politikaları", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403529", "name": "Bürokrasi", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403503", "name": "İnsan Hakları", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403517", "name": "Devlet Kuramları", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403519", "name": "Uluslararası İlişkiler", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403531", "name": "Doğu Siyasal Düşüncesi", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
        ],
        "6": [
            {"code": "1403604", "name": "Türkiye'nin Yönetim Tarihi", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403606", "name": "Türk Siyasal Yaşamı II", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403608", "name": "Ticaret Hukuku", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403612", "name": "Ceza Hukuku", "credits": "3+0+0", "akts": 4, "type": "Zorunlu"},
            {"code": "1403628", "name": "Yerel Yönetimler Maliyesi", "credits": "3+0+0", "akts": 3, "type": "Zorunlu"},
            {"code": "1403616", "name": "Kent Sosyolojisi", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403620", "name": "Bölge Yönetimi", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403622", "name": "Halkla İlişkiler", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
            {"code": "1403626", "name": "Kamu Politikaları", "credits": "3+0+0", "akts": 3, "type": "Seçmeli"},
        ],
        "7": [
            {"code": "1403701", "name": "Karşılaştırmalı Kamu Yönetimi", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403703", "name": "Vergi Hukuku", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403715", "name": "Çağdaş Siyasal Düşünceler", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403705", "name": "İş Hukuku", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403707", "name": "Türkiyenin Toplumsal Yapısı", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403709", "name": "Siyasal Tarih", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403713", "name": "Yönetme Sanatı", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403721", "name": "Çevre Politikası", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
        ],
        "8": [
            {"code": "1403802", "name": "Yönetim Sosyolojisi", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403806", "name": "Türkiye Ekonomisi", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403808", "name": "Kamu Yönetiminde Güncel Sorunlar", "credits": "3+0+0", "akts": 5, "type": "Zorunlu"},
            {"code": "1403804", "name": "Uluslararası Kuruluşlar", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403810", "name": "Yönetim Etiği", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403814", "name": "Çevresel Etki Değerlendirme", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403822", "name": "Karşılaştırmalı Siyaset", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
            {"code": "1403826", "name": "Kent Kuramları", "credits": "3+0+0", "akts": 5, "type": "Seçmeli"},
        ]
    }
}

# ============ PÖÇ VERİLERİ (Bologna'dan) ============
DEPARTMENT_POC = {
    "siyaset_bilimi": [
        {"id": "PÖÇ1", "text": "Öğrenciler Kuramsal Arka Plana Sahiptir. Siyaset bilimi ve kamu yönetimi alanının temel kavram, kuram ve kurumlarını bilir."},
        {"id": "PÖÇ2", "text": "Öğrencilerin Problem Çözme Becerisi Gelişmiştir. Toplum, devlet ve birey arasındaki ilişkileri tarihsel ve güncel bağlamda analiz eder."},
        {"id": "PÖÇ3", "text": "Öğrenciler Doğru Bilgiye Nasıl Ulaşacağını Bilir. Bilimsel araştırma yöntemlerini uygular, veri toplar ve analiz eder."},
        {"id": "PÖÇ4", "text": "Öğrenciler Etik Değerler ve Toplumsal Sorumluluk Bilincine Sahiptir. Demokrasi, insan hakları ve çevre bilinci değerlerine bağlıdır."},
        {"id": "PÖÇ5", "text": "Öğrenciler Kamu Kurumlarında İstihdam Edilecek Mesleki Donanıma Sahiptir. Kamu politikalarını geliştirme süreçlerine hakimdir."},
        {"id": "PÖÇ6", "text": "Öğrenciler Kendini Etkili Şekilde İfade Eder. Türkçe'yi etkin biçimde kullanarak sözlü ve yazılı iletişim kurar."},
        {"id": "PÖÇ7", "text": "Öğrenciler Güncel Gelişmelerin Hızına Yetişir. Teknolojik ve bilimsel gelişmeleri takip eder, güncelliğini korur."},
        {"id": "PÖÇ8", "text": "Öğrenciler İşbirliğine Açıktır. Takım çalışmasına yatkındır; disiplinler arası iş birliklerinde sorumluluk alır."},
    ]
}

# ============ PEA VERİLERİ (Bologna'dan) ============
DEPARTMENT_PEA = {
    "siyaset_bilimi": [
        {"id": "PEA1", "text": "Kamu yararını önceleyen, etik değerlere bağlı, eleştirel ve analitik düşünme yetkinliğine sahip bireyler yetiştirmek."},
        {"id": "PEA2", "text": "Öğrencilere siyaset bilimi, kamu yönetimi, hukuk, kentleşme ve çevre gibi temel alanlarda kuramsal bilgi ile uygulama becerilerini kazandırmak."},
        {"id": "PEA3", "text": "Kamu politikalarını eleştirel, karşılaştırmalı ve uygulamaya dönük bir bakış açısıyla değerlendirebilmelerini sağlamak."},
        {"id": "PEA4", "text": "Demokratik yönetişim ilkelerini içselleştiren, eleştirel düşünceye ve toplumsal duyarlılığa sahip bireylerin yetişmesini sağlamak."},
        {"id": "PEA5", "text": "Akademik özgürlük, sosyal adalet, bilimsel yenilikçilik ilkeleri doğrultusunda ulusal ve uluslararası düzeyde bilgi üretimine katkı sunmak."},
    ]
}

# Şifre hash'leme
def hash_password(password: str) -> str:
    salt = "hmku_akreditasyon_2024"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def init_db():
    conn = sqlite3.connect(DB_PATH)
    
    # Users tablosu
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        full_name TEXT,
        role TEXT DEFAULT 'ogretim_elemani',
        department_id TEXT,
        course_code TEXT,
        course_name TEXT,
        term TEXT,
        program_name TEXT,
        instructor TEXT,
        department TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Bölümler tablosu (yeni)
    conn.execute("""CREATE TABLE IF NOT EXISTS departments (
        department_id TEXT PRIMARY KEY,
        name TEXT,
        faculty TEXT,
        bologna_courses_url TEXT,
        bologna_pea_url TEXT,
        bologna_poc_url TEXT,
        pea_text TEXT,
        poc_text TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT
    )""")
    
    # Ders bazlı paylaşılan veriler (TYÇ, Bloom, STAR-K, PEA, PÖÇ, DÖÇ, Müfredat)
    conn.execute("""CREATE TABLE IF NOT EXISTS course_data (
        course_code TEXT PRIMARY KEY,
        course_name TEXT,
        department_id TEXT,
        semester INTEGER,
        akts INTEGER DEFAULT 5,
        course_type TEXT DEFAULT 'Z',
        bologna_link TEXT,
        tyc_text TEXT,
        bloom_text TEXT,
        stark_text TEXT,
        pea_text TEXT,
        poc_text TEXT,
        doc_text TEXT,
        curriculum_text TEXT,
        updated_at TEXT,
        updated_by TEXT
    )""")
    
    # akts ve course_type sütunları yoksa ekle
    try:
        conn.execute("ALTER TABLE course_data ADD COLUMN akts INTEGER DEFAULT 5")
    except:
        pass
    try:
        conn.execute("ALTER TABLE course_data ADD COLUMN course_type TEXT DEFAULT 'Z'")
    except:
        pass
    
    # Bölüm verileri (paylaşılan PEA/PÖÇ - eski sistem uyumluluğu)
    conn.execute("""CREATE TABLE IF NOT EXISTS department_data (
        department_id TEXT PRIMARY KEY,
        peas_text TEXT,
        pocs_text TEXT,
        updated_at TEXT,
        updated_by TEXT
    )""")
    
    # Role sütunu yoksa ekle
    try:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'ogretim_elemani'")
    except:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN department_id TEXT")
    except:
        pass
    
    # Şifre sıfırlama token'ları
    conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        email TEXT PRIMARY KEY,
        token TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""")
    
    # Taslaklar tablosu
    conn.execute("""CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        name TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Rapor geçmişi tablosu
    conn.execute("""CREATE TABLE IF NOT EXISTS report_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        title TEXT,
        payload TEXT NOT NULL,
        result TEXT NOT NULL,
        overall_pct REAL,
        department_id TEXT,
        course_code TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # report_history'ye department_id ve course_code ekle (mevcut tablolar için)
    try:
        conn.execute("ALTER TABLE report_history ADD COLUMN department_id TEXT")
    except:
        pass
    try:
        conn.execute("ALTER TABLE report_history ADD COLUMN course_code TEXT")
    except:
        pass
    
    # Kullanıcı Müfredat Verileri tablosu
    conn.execute("""CREATE TABLE IF NOT EXISTS user_curriculum (
        user_email TEXT PRIMARY KEY,
        tyc_text TEXT,
        stark_text TEXT,
        docs_text TEXT,
        pocs_text TEXT,
        peas_text TEXT,
        curriculum_text TEXT,
        bloom_text TEXT,
        doc_tyc_map_text TEXT,
        poc_tyc_map_text TEXT,
        pea_stark_map_text TEXT,
        poc_pea_map_text TEXT,
        doc_poc_weights_text TEXT,
        curriculum_doc_map_text TEXT,
        doc_stark_map_text TEXT,
        doc_pea_map_text TEXT,
        curriculum_tyc_map_text TEXT,
        curriculum_stark_map_text TEXT,
        curriculum_poc_map_text TEXT,
        curriculum_pea_map_text TEXT,
        components_text TEXT,
        thresholds_met TEXT,
        thresholds_partial TEXT,
        grading_text TEXT,
        question_map_text TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Yeni sütunları ekle (migration)
    new_columns = [
        "question_map_text", "doc_stark_map_text", "doc_pea_map_text",
        "curriculum_tyc_map_text", "curriculum_stark_map_text",
        "curriculum_poc_map_text", "curriculum_pea_map_text"
    ]
    for col in new_columns:
        try:
            conn.execute(f"ALTER TABLE user_curriculum ADD COLUMN {col} TEXT")
        except:
            pass  # Sütun zaten var
    
    # Kullanıcı-Ders İlişkisi tablosu (çoklu ders atama)
    conn.execute("""CREATE TABLE IF NOT EXISTS user_courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        course_code TEXT NOT NULL,
        can_create_report INTEGER DEFAULT 1,
        assigned_by TEXT,
        assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_email, course_code)
    )""")
    
    # Bölüm Ortak Verileri tablosu (PEA, PÖÇ - sadece Dekan/Bölüm Başkanı düzenleyebilir)
    conn.execute("""CREATE TABLE IF NOT EXISTS department_data (
        department_id TEXT PRIMARY KEY,
        peas_text TEXT,
        pocs_text TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT
    )""")
    
    conn.commit()
    
    # Admin kullanıcı oluştur
    hashed_admin = hash_password("Admin123!")
    cur = conn.execute("SELECT email FROM users WHERE email=?", ("admin@mku.edu.tr",))
    if not cur.fetchone():
        conn.execute("""INSERT INTO users (email, password, full_name, role, department_id, program_name, department) 
                        VALUES (?,?,?,?,?,?,?)""",
            ("admin@mku.edu.tr", hashed_admin, "Sistem Yöneticisi", "admin", None, "Tüm Bölümler", "Sistem"))
        conn.commit()
    
    # Demo kullanıcı
    cur = conn.execute("SELECT password FROM users WHERE email=?", ("demo@example.com",))
    row = cur.fetchone()
    hashed_demo = hash_password("P@ssw0rd!")
    if not row:
        conn.execute("""INSERT INTO users (email, password, full_name, role, department_id, course_code, course_name, term, program_name, instructor, department) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("demo@example.com", hashed_demo, "Dr. Ahmet Yilmaz", "ogretim_elemani", "siyaset_bilimi", "1403101",
             "Yönetim Bilimi I", "2024-2025 Güz", "Siyaset Bilimi ve Kamu Yönetimi", "Dr. Ahmet Yilmaz", "Siyaset Bilimi ve Kamu Yönetimi"))
        conn.commit()
    elif row[0] == "P@ssw0rd!":
        conn.execute("UPDATE users SET password=?, role=?, department_id=? WHERE email=?", 
                     (hashed_demo, "ogretim_elemani", "siyaset_bilimi", "demo@example.com"))
        conn.commit()
    
    # Varsayılan bölüm verilerini ekle
    cur = conn.execute("SELECT department_id FROM department_data WHERE department_id=?", ("siyaset_bilimi",))
    if not cur.fetchone():
        pocs_text = "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_POC.get("siyaset_bilimi", [])])
        peas_text = "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_PEA.get("siyaset_bilimi", [])])
        
        conn.execute("""INSERT INTO department_data (department_id, peas_text, pocs_text, updated_by)
                        VALUES (?,?,?,?)""",
            ("siyaset_bilimi", peas_text, pocs_text, "system"))
        conn.commit()
    
    # Varsayılan ders verilerini ekle (tüm dersler için)
    _init_course_data(conn)
    
    # Varsayılan bölümü departments tablosuna ekle (yoksa)
    cur = conn.execute("SELECT department_id FROM departments WHERE department_id=?", ("siyaset_bilimi",))
    if not cur.fetchone():
        conn.execute("""INSERT INTO departments 
            (department_id, name, faculty, bologna_courses_url, bologna_pea_url, bologna_poc_url, updated_by)
            VALUES (?,?,?,?,?,?,?)""",
            ("siyaset_bilimi", "Siyaset Bilimi ve Kamu Yönetimi", "İktisadi ve İdari Bilimler Fakültesi",
             "https://obs.mku.edu.tr/oibs/bologna/progCourses.aspx?curCourse=1403&lang=tr",
             "https://obs.mku.edu.tr/oibs/bologna/progGoalsObjectives.aspx?curCourse=1403&lang=tr",
             "https://obs.mku.edu.tr/oibs/bologna/progLearnOutcomes.aspx?curCourse=1403&lang=tr",
             "system"))
        conn.commit()
    
    # departments ve department_data senkronizasyonu:
    # departments'taki her bölüm için department_data'da kayıt yoksa oluştur
    cur = conn.execute("SELECT department_id FROM departments")
    all_depts = [row[0] for row in cur.fetchall()]
    for dept_id in all_depts:
        cur2 = conn.execute("SELECT department_id FROM department_data WHERE department_id=?", (dept_id,))
        if not cur2.fetchone():
            conn.execute("""INSERT INTO department_data (department_id, peas_text, pocs_text, updated_by)
                VALUES (?,?,?,?)""", (dept_id, '', '', 'system'))
    conn.commit()
    
    conn.close()


def _init_course_data(conn):
    """Tüm dersler için varsayılan verileri ekle"""
    pocs_text = "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_POC.get("siyaset_bilimi", [])])
    peas_text = "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_PEA.get("siyaset_bilimi", [])])
    
    # Bologna linkleri (kullanıcının verdiği)
    BOLOGNA_LINKS = {
        "1403101": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436921&lang=tr",  # Yönetim Bilimi I
        "1403103": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436923&lang=tr",  # Toplum Bilimi
        "1403105": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436924&lang=tr",  # Siyaset Bilimi I
        "1403107": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436912&lang=tr",  # Hukukun Temel Kavramları
        "1403109": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436929&lang=tr",  # İktisada Giriş I
        "1403111": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436911&lang=tr",  # Kamu Yönetimi
        "1403131": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436913&lang=tr",  # Türk Dili I
        "1403141": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436914&lang=tr",  # Yabancı Dil I
        "1403199": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436964&lang=tr",  # Kariyer Planlama
        
        "1403202": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436886&lang=tr",  # Yönetim Bilimi II
        "1403206": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436888&lang=tr",  # Siyaset Bilimi II
        "1403208": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436890&lang=tr",  # Medeni Hukuk
        "1403210": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436893&lang=tr",  # İktisada Giriş II
        "1403212": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436894&lang=tr",  # Anayasaya Giriş
        "1403232": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436901&lang=tr",  # Türk Dili II
        "1403242": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436901&lang=tr",  # Yabancı Dil II
        "1403252": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436876&lang=tr",  # Uygarlık Tarihi
        
        "1403301": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436915&lang=tr",  # Türk Anayasa Hukuku
        "1403303": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436925&lang=tr",  # Yönetim Hukuku
        "1403307": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436927&lang=tr",  # Kent ve Çevre Sorunları
        "1403309": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436933&lang=tr",  # Toplum Bilim. Araştırma Yöntemleri
        "1403327": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436879&lang=tr",  # Siyasal Düşünceler Tarihine Giriş
        "1403351": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436934&lang=tr",  # Atatürk İlkeleri Ve İnkılap Tarihi I
        
        "1403402": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436942&lang=tr",  # Kamu Maliyesi
        "1403404": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436941&lang=tr",  # Personel Yönetimi
        "1403406": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436944&lang=tr",  # Yönetsel Yargı
        "1403408": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436945&lang=tr",  # Çevre Yönetimi
        "1403410": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436946&lang=tr",  # Siyasal Düşünceler Tarihi
        "1403452": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436947&lang=tr",  # Atatürk İlkeleri ve İnkılap Tarihi II
        
        "1403501": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436916&lang=tr",  # Yerel Yönetimler
        "1403505": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436931&lang=tr",  # Türk Siyasal Yaşamı I
        "1403507": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436932&lang=tr",  # Borçlar Hukuku
        "1403513": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436917&lang=tr",  # Kentleşme ve Konut Politikaları
        "1403529": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436952&lang=tr",  # Bürokrasi
        
        "1403604": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436943&lang=tr",  # Türkiye'nin Yönetim Tarihi
        "1403606": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436908&lang=tr",  # Türk Siyasal Yaşamı II
        "1403608": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436909&lang=tr",  # Ticaret Hukuku
        "1403612": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436910&lang=tr",  # Ceza Hukuku
        "1403628": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436878&lang=tr",  # Yerel Yönetimler Maliyesi
        
        "1403701": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436928&lang=tr",  # Karşılaştırmalı Kamu Yönetimi
        "1403703": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436892&lang=tr",  # Vergi Hukuku
        "1403715": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436937&lang=tr",  # Çağdaş Siyasal Düşünceler
        
        "1403802": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436938&lang=tr",  # Yönetim Sosyolojisi
        "1403806": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436940&lang=tr",  # Türkiye Ekonomisi
        "1403808": "https://obs.mku.edu.tr/oibs/bologna/progCourseDetails.aspx?curCourse=1436885&lang=tr",  # Kamu Yönetiminde Güncel Sorunlar
    }
    
    for semester_str, courses in DEPARTMENT_COURSES.get("siyaset_bilimi", {}).items():
        semester_num = int(semester_str)
        for course in courses:
            code = course['code']
            akts = course.get('akts', 5)
            course_type = course.get('type', 'Zorunlu')
            # Type kısaltma
            if course_type in ['Zorunlu', 'Z']:
                course_type = 'Z'
            elif course_type in ['Seçmeli', 'S']:
                course_type = 'S'
            
            cur = conn.execute("SELECT course_code FROM course_data WHERE course_code=?", (code,))
            if not cur.fetchone():
                bologna_link = BOLOGNA_LINKS.get(code, '')
                conn.execute("""INSERT INTO course_data 
                    (course_code, course_name, department_id, semester, akts, course_type, bologna_link, 
                     tyc_text, bloom_text, stark_text, pea_text, poc_text, doc_text, curriculum_text, updated_by)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (code, course['name'], 'siyaset_bilimi', semester_num, akts, course_type, bologna_link,
                     DEFAULT_TYC, DEFAULT_BLOOM, DEFAULT_STARK, peas_text, pocs_text, '', '', 'system'))
            else:
                # Mevcut dersin department_id, semester, akts, course_type bilgisini güncelle
                conn.execute("""UPDATE course_data SET 
                    department_id = COALESCE(NULLIF(department_id, ''), ?),
                    semester = COALESCE(semester, ?),
                    akts = COALESCE(akts, ?),
                    course_type = COALESCE(NULLIF(course_type, ''), ?)
                    WHERE course_code=?""",
                    ('siyaset_bilimi', semester_num, akts, course_type, code))
        conn.commit()


# ============ DERS VERİLERİ (COURSE_DATA) ============

def get_course_data(course_code: str) -> dict:
    """Ders bazlı verileri getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM course_data WHERE course_code=?", (course_code,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def save_course_data(course_code: str, data: dict, updated_by: str):
    """Ders bazlı verileri kaydet"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT course_code FROM course_data WHERE course_code=?", (course_code,))
    
    if cur.fetchone():
        conn.execute("""UPDATE course_data SET 
            course_name=?, bologna_link=?, tyc_text=?, bloom_text=?, stark_text=?, 
            pea_text=?, poc_text=?, doc_text=?, curriculum_text=?, updated_at=CURRENT_TIMESTAMP, updated_by=?
            WHERE course_code=?""",
            (data.get('course_name', ''), data.get('bologna_link', ''),
             data.get('tyc_text', ''), data.get('bloom_text', ''), data.get('stark_text', ''),
             data.get('pea_text', ''), data.get('poc_text', ''), data.get('doc_text', ''),
             data.get('curriculum_text', ''), updated_by, course_code))
    else:
        conn.execute("""INSERT INTO course_data 
            (course_code, course_name, bologna_link, tyc_text, bloom_text, stark_text, pea_text, poc_text, doc_text, curriculum_text, updated_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (course_code, data.get('course_name', ''), data.get('bologna_link', ''),
             data.get('tyc_text', ''), data.get('bloom_text', ''), data.get('stark_text', ''),
             data.get('pea_text', ''), data.get('poc_text', ''), data.get('doc_text', ''),
             data.get('curriculum_text', ''), updated_by))
    
    conn.commit()
    conn.close()


def get_all_courses_data() -> list:
    """Tüm derslerin verilerini getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM course_data ORDER BY course_code")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_department_courses(dept_id: str, semester: int = None) -> list:
    """Bölüme ait dersleri getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if semester:
        cur = conn.execute("""SELECT * FROM course_data 
            WHERE department_id=? AND semester=? 
            ORDER BY course_code""", (dept_id, semester))
    else:
        cur = conn.execute("""SELECT * FROM course_data 
            WHERE department_id=? 
            ORDER BY semester, course_code""", (dept_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_course(dept_id: str, course_code: str, course_name: str, semester: int, 
               akts: int = 5, course_type: str = "Z", bologna_link: str = "", updated_by: str = "") -> bool:
    """Bölüme yeni ders ekle"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Bölümün PEA/PÖÇ verilerini al
        dept_data = get_department_data(dept_id)
        peas_text = dept_data.get('peas_text', '')
        pocs_text = dept_data.get('pocs_text', '')
        
        conn.execute("""INSERT INTO course_data 
            (course_code, course_name, department_id, semester, akts, course_type, bologna_link, 
             tyc_text, bloom_text, stark_text, pea_text, poc_text, doc_text, curriculum_text, updated_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (course_code, course_name, dept_id, semester, akts, course_type, bologna_link,
             DEFAULT_TYC, DEFAULT_BLOOM, DEFAULT_STARK, peas_text, pocs_text, '', '', updated_by))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except Exception as e:
        print(f"add_course error: {e}", file=sys.stderr)
        conn.close()
        return False


def update_course(course_code: str, course_name: str = None, semester: int = None, 
                  akts: int = None, course_type: str = None, bologna_link: str = None, updated_by: str = "") -> bool:
    """Ders bilgilerini güncelle"""
    conn = sqlite3.connect(DB_PATH)
    try:
        updates = []
        params = []
        
        if course_name is not None:
            updates.append("course_name=?")
            params.append(course_name)
        if semester is not None:
            updates.append("semester=?")
            params.append(semester)
        if akts is not None:
            updates.append("akts=?")
            params.append(akts)
        if course_type is not None:
            updates.append("course_type=?")
            params.append(course_type)
        if bologna_link is not None:
            updates.append("bologna_link=?")
            params.append(bologna_link)
        
        if updates:
            updates.append("updated_at=CURRENT_TIMESTAMP")
            updates.append("updated_by=?")
            params.append(updated_by)
            params.append(course_code)
            
            sql = f"UPDATE course_data SET {', '.join(updates)} WHERE course_code=?"
            conn.execute(sql, params)
            conn.commit()
        
        conn.close()
        return True
    except Exception as e:
        print(f"update_course error: {e}", file=sys.stderr)
        conn.close()
        return False


def delete_course(course_code: str) -> bool:
    """Dersi sil"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM course_data WHERE course_code=?", (course_code,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"delete_course error: {e}", file=sys.stderr)
        conn.close()
        return False


def fetch_courses_from_bologna(url: str, dept_id: str, updated_by: str = "") -> dict:
    """Bologna'dan ders listesi çek ve veritabanına ekle"""
    if not HAS_SCRAPING or not url:
        return {"success": False, "error": "URL boş veya scraping modülü yüklü değil", "courses": []}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        courses = []
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 4:
                    # Tipik Bologna tablosu: Kod | Ad | AKTS | Tür
                    code_text = cells[0].get_text(strip=True)
                    name_text = cells[1].get_text(strip=True)
                    
                    # Ders kodu formatı kontrolü (örn: 1403101)
                    if code_text and name_text and code_text[0].isdigit():
                        akts = 5
                        course_type = "Z"
                        semester = 1
                        
                        # AKTS bulmaya çalış
                        for cell in cells[2:]:
                            text = cell.get_text(strip=True)
                            if text.isdigit() and 1 <= int(text) <= 30:
                                akts = int(text)
                                break
                        
                        # Tür bulmaya çalış (Z=Zorunlu, S=Seçmeli)
                        for cell in cells:
                            text = cell.get_text(strip=True).upper()
                            if text in ['Z', 'S', 'ZORUNLU', 'SEÇMELİ']:
                                course_type = 'Z' if text in ['Z', 'ZORUNLU'] else 'S'
                                break
                        
                        # Yarıyıl bulmaya çalış (ders kodundan)
                        if len(code_text) >= 6:
                            try:
                                sem_digit = int(code_text[4]) if code_text[4].isdigit() else 1
                                semester = sem_digit if 1 <= sem_digit <= 8 else 1
                            except:
                                pass
                        
                        courses.append({
                            'code': code_text,
                            'name': name_text,
                            'akts': akts,
                            'type': course_type,
                            'semester': semester
                        })
        
        # Dersleri veritabanına ekle
        added = 0
        for course in courses:
            if add_course(dept_id, course['code'], course['name'], course['semester'],
                         course['akts'], course['type'], '', updated_by):
                added += 1
        
        return {
            "success": True,
            "courses": courses,
            "total": len(courses),
            "added": added
        }
        
    except Exception as e:
        return {"success": False, "error": str(e), "courses": []}


def update_course_bologna_link(course_code: str, bologna_link: str, updated_by: str):
    """Ders Bologna linkini güncelle"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE course_data SET bologna_link=?, updated_at=CURRENT_TIMESTAMP, updated_by=? WHERE course_code=?",
                 (bologna_link, updated_by, course_code))
    conn.commit()
    conn.close()


# ============ KULLANICI-DERS İLİŞKİSİ ============

def get_user_courses(email: str) -> list:
    """Kullanıcının yetkili olduğu dersleri getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Önce tablo var mı kontrol et
        conn.execute("""CREATE TABLE IF NOT EXISTS user_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            course_code TEXT NOT NULL,
            can_create_report INTEGER DEFAULT 1,
            assigned_by TEXT,
            assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, course_code)
        )""")
        
        cur = conn.execute("""
            SELECT uc.*, cd.course_name, cd.bologna_link
            FROM user_courses uc
            LEFT JOIN course_data cd ON uc.course_code = cd.course_code
            WHERE uc.user_email = ?
            ORDER BY uc.assigned_at DESC
        """, (email,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_user_courses error: {e}")
        conn.close()
        return []


def add_user_course(email: str, course_code: str, assigned_by: str) -> bool:
    """Kullanıcıya ders yetkisi ekle"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Önce tablo var mı kontrol et, yoksa oluştur
        conn.execute("""CREATE TABLE IF NOT EXISTS user_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            course_code TEXT NOT NULL,
            can_create_report INTEGER DEFAULT 1,
            assigned_by TEXT,
            assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, course_code)
        )""")
        
        conn.execute("""INSERT OR IGNORE INTO user_courses 
            (user_email, course_code, assigned_by) VALUES (?,?,?)""",
            (email, course_code, assigned_by))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"add_user_course error: {e}")
        conn.close()
        return False


def remove_user_course(email: str, course_code: str) -> bool:
    """Kullanıcıdan ders yetkisini kaldır"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM user_courses WHERE user_email=? AND course_code=?", (email, course_code))
    conn.commit()
    conn.close()
    return True


def user_has_course_access(email: str, course_code: str) -> bool:
    """Kullanıcının derse erişimi var mı kontrol et"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT 1 FROM user_courses WHERE user_email=? AND course_code=?", (email, course_code))
    result = cur.fetchone() is not None
    conn.close()
    return result


def get_course_users(course_code: str) -> list:
    """Bir derse yetkili kullanıcıları getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT uc.*, u.full_name, u.role
        FROM user_courses uc
        LEFT JOIN users u ON uc.user_email = u.email
        WHERE uc.course_code = ?
        ORDER BY u.full_name
    """, (course_code,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ BÖLÜM YÖNETİMİ ============

def add_department(dept_id: str, name: str, faculty: str, bologna_courses_url: str, bologna_pea_url: str, bologna_poc_url: str, updated_by: str) -> bool:
    """Yeni bölüm ekle"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # departments tablosuna ekle
        conn.execute("""INSERT INTO departments 
            (department_id, name, faculty, bologna_courses_url, bologna_pea_url, bologna_poc_url, updated_by)
            VALUES (?,?,?,?,?,?,?)""",
            (dept_id, name, faculty, bologna_courses_url, bologna_pea_url, bologna_poc_url, updated_by))
        
        # department_data tablosuna da boş kayıt ekle (PEA/PÖÇ için)
        conn.execute("""INSERT OR IGNORE INTO department_data 
            (department_id, peas_text, pocs_text, updated_by)
            VALUES (?,?,?,?)""",
            (dept_id, '', '', updated_by))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def get_department(dept_id: str) -> dict:
    """Bölüm bilgilerini getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM departments WHERE department_id=?", (dept_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_departments() -> list:
    """Tüm bölümleri getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM departments ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_department(dept_id: str, name: str, faculty: str, bologna_courses_url: str, bologna_pea_url: str, bologna_poc_url: str, updated_by: str) -> bool:
    """Bölüm bilgilerini güncelle"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""UPDATE departments SET 
            name=?, faculty=?, bologna_courses_url=?, bologna_pea_url=?, bologna_poc_url=?, updated_by=?
            WHERE department_id=?""",
            (name, faculty, bologna_courses_url, bologna_pea_url, bologna_poc_url, updated_by, dept_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"update_department error: {e}")
        conn.close()
        return False


def delete_department(dept_id: str) -> bool:
    """Bölümü sil"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Varsayılan bölümü silme
        if dept_id == "siyaset_bilimi":
            conn.close()
            return False
        
        # departments tablosundan sil
        conn.execute("DELETE FROM departments WHERE department_id=?", (dept_id,))
        
        # department_data tablosundan da sil (varsa)
        conn.execute("DELETE FROM department_data WHERE department_id=?", (dept_id,))
        
        # Bu bölümün derslerinin department_id'sini temizle (dersleri silme, sadece bağlantıyı kes)
        conn.execute("UPDATE course_data SET department_id=NULL WHERE department_id=?", (dept_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"delete_department error: {e}")
        conn.close()
        return False


def fetch_pea_from_bologna(url: str) -> dict:
    """Bologna'dan PEA verilerini çek"""
    if not HAS_SCRAPING or not url:
        return {"pea_text": "", "error": "URL boş veya scraping modülü yüklü değil"}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        pea_items = []
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if text and len(text) > 20:
                        # Skip headers
                        if any(skip in text.lower() for skip in ['amaç', 'objective', 'no', 'sıra']):
                            continue
                        pea_items.append(f"PEA{len(pea_items)+1}. {text}")
        
        return {"pea_text": "\n".join(pea_items[:10]), "success": bool(pea_items)}
    except Exception as e:
        return {"pea_text": "", "error": str(e)}


def fetch_poc_from_bologna(url: str) -> dict:
    """Bologna'dan PÖÇ verilerini çek"""
    if not HAS_SCRAPING or not url:
        return {"poc_text": "", "error": "URL boş veya scraping modülü yüklü değil"}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        poc_items = []
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if text and len(text) > 20:
                        # Skip headers
                        if any(skip in text.lower() for skip in ['çıktı', 'outcome', 'no', 'sıra']):
                            continue
                        poc_items.append(f"PÖÇ{len(poc_items)+1}. {text}")
        
        return {"poc_text": "\n".join(poc_items[:15]), "success": bool(poc_items)}
    except Exception as e:
        return {"poc_text": "", "error": str(e)}


def fetch_user(email: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(email: str, password: str, profile: dict):
    conn = sqlite3.connect(DB_PATH)
    hashed = hash_password(password)
    conn.execute("""INSERT INTO users (email, password, full_name, role, department_id, course_code, course_name, term, program_name, instructor, department) 
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (email, hashed, 
         profile.get("full_name",""), 
         profile.get("role", "ogretim_elemani"),
         profile.get("department_id", "siyaset_bilimi"),
         profile.get("course_code",""),
         profile.get("course_name",""), 
         profile.get("term",""), 
         profile.get("program_name",""),
         profile.get("instructor",""), 
         profile.get("department","")))
    conn.commit()
    
    # Seçilen dersi user_courses'a da ekle
    course_code = profile.get("course_code", "")
    if course_code:
        conn.execute("""INSERT OR IGNORE INTO user_courses 
            (user_email, course_code, assigned_by) VALUES (?,?,?)""",
            (email, course_code, "signup"))
        conn.commit()
    
    conn.close()

def update_user(email: str, profile: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE users SET full_name=?, role=?, department_id=?, course_code=?, course_name=?, 
                    term=?, program_name=?, instructor=?, department=? WHERE email=?""",
        (profile.get("full_name",""), 
         profile.get("role", "ogretim_elemani"),
         profile.get("department_id", ""),
         profile.get("course_code",""), 
         profile.get("course_name",""),
         profile.get("term",""), 
         profile.get("program_name",""), 
         profile.get("instructor",""),
         profile.get("department",""), 
         email))
    conn.commit()
    conn.close()

def update_password(email: str, new_password: str):
    conn = sqlite3.connect(DB_PATH)
    hashed = hash_password(new_password)
    conn.execute("UPDATE users SET password=? WHERE email=?", (hashed, email))
    conn.commit()
    conn.close()

# Rol yardımcı fonksiyonları
def get_role_info(role: str) -> dict:
    return ROLES.get(role, ROLES["ogretim_elemani"])

def can_edit_pea_poc(role: str) -> bool:
    return role in ["admin", "dekan", "bolum_baskani"]

def get_department_data(department_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM department_data WHERE department_id=?", (department_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"department_id": department_id, "peas_text": "", "pocs_text": ""}

def save_department_data(department_id: str, data: dict, updated_by: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO department_data 
                    (department_id, peas_text, pocs_text, updated_at, updated_by)
                    VALUES (?,?,?,?,?)""",
        (department_id,
         data.get("peas_text", ""),
         data.get("pocs_text", ""),
         datetime.now().isoformat(),
         updated_by))
    conn.commit()
    conn.close()

# Şifre sıfırlama
def create_reset_token(email: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO password_resets (email, token, expires_at) VALUES (?,?,?)",
                 (email, token, expires))
    conn.commit()
    conn.close()
    return token

def verify_reset_token(token: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT email, expires_at FROM password_resets WHERE token=?", (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    email, expires_at = row
    if datetime.fromisoformat(expires_at) < datetime.now():
        return None
    return email

def delete_reset_token(email: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM password_resets WHERE email=?", (email,))
    conn.commit()
    conn.close()

# Taslak işlemleri
def save_draft(user_email: str, name: str, data: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    cur = conn.execute("INSERT INTO drafts (user_email, name, data, updated_at) VALUES (?,?,?,?)",
                       (user_email, name, data, now))
    draft_id = cur.lastrowid
    conn.commit()
    conn.close()
    return draft_id

def update_draft(draft_id: int, data: str):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    conn.execute("UPDATE drafts SET data=?, updated_at=? WHERE id=?", (data, now, draft_id))
    conn.commit()
    conn.close()

def get_drafts(user_email: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, name, updated_at FROM drafts WHERE user_email=? ORDER BY updated_at DESC LIMIT 20", (user_email,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_draft(draft_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_draft(draft_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
    conn.commit()
    conn.close()

# Rapor geçmişi
def save_report(user_email: str, title: str, payload: str, result: str, overall_pct: float, department_id: str = None, course_code: str = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO report_history (user_email, title, payload, result, overall_pct, department_id, course_code) VALUES (?,?,?,?,?,?,?)",
                       (user_email, title, payload, result, overall_pct, department_id, course_code))
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id

def get_report_history(user_email: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, title, overall_pct, department_id, course_code, created_at FROM report_history WHERE user_email=? ORDER BY created_at DESC LIMIT 50", (user_email,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_report(report_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM report_history WHERE id=?", (report_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_report(report_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM report_history WHERE id=?", (report_id,))
    conn.commit()
    conn.close()

# Yardımcı fonksiyonlar - Dinamik (veritabanından)
def get_courses_json(dept_id: str = None) -> str:
    """Bölümün derslerini JSON olarak getir"""
    if not dept_id:
        dept_id = "siyaset_bilimi"  # Varsayılan
    
    courses = get_department_courses(dept_id)
    
    # Yarıyıla göre grupla
    by_semester = {}
    for c in courses:
        sem = str(c.get('semester', 1))
        if sem not in by_semester:
            by_semester[sem] = []
        by_semester[sem].append({
            'code': c.get('course_code', ''),
            'name': c.get('course_name', ''),
            'akts': c.get('akts', 5),
            'type': c.get('course_type', 'Z')
        })
    
    # Eğer veritabanında ders yoksa sabit listeden al (geriye uyumluluk)
    if not by_semester and dept_id == "siyaset_bilimi":
        return json.dumps(DEPARTMENT_COURSES.get("siyaset_bilimi", {}), ensure_ascii=False)
    
    return json.dumps(by_semester, ensure_ascii=False)

def get_pea_text(dept_id: str = None) -> str:
    """Bölümün PEA verilerini getir"""
    if not dept_id:
        dept_id = "siyaset_bilimi"
    
    # Önce department_data'dan dene
    dept_data = get_department_data(dept_id)
    if dept_data.get('peas_text'):
        return dept_data.get('peas_text', '')
    
    # Yoksa sabit listeden (geriye uyumluluk)
    return "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_PEA.get(dept_id, [])])

def get_poc_text(dept_id: str = None) -> str:
    """Bölümün PÖÇ verilerini getir"""
    if not dept_id:
        dept_id = "siyaset_bilimi"
    
    # Önce department_data'dan dene
    dept_data = get_department_data(dept_id)
    if dept_data.get('pocs_text'):
        return dept_data.get('pocs_text', '')
    
    # Yoksa sabit listeden (geriye uyumluluk)
    return "\n".join([f"{p['id']} | {p['text']}" for p in DEPARTMENT_POC.get(dept_id, [])])


# Template rendering
def _css():
    return """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --primary: #1e3a5f;
  --primary-light: #2c5282;
  --bg: #f1f5f9;
  --bg-card: #ffffff;
  --border: #e2e8f0;
  --text: #1e293b;
  --text-muted: #64748b;
  --success: #059669;
  --danger: #dc2626;
}

body {
  font-family: 'Inter', -apple-system, sans-serif;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  overflow-y: auto;
}

.card {
  width: 100%;
  max-width: 420px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.card-header {
  padding: 2rem;
  text-align: center;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(to bottom, #f8fafc, white);
  border-radius: 16px 16px 0 0;
}

.logo-box {
  width: 56px; height: 56px;
  margin: 0 auto 1rem;
  background: var(--primary);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-box img { width: 65%; height: 65%; object-fit: contain; }

.card-header h1 { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.25rem; }
.card-header p { font-size: 0.8rem; color: var(--text-muted); }

.card-body { padding: 1.5rem 2rem 2rem; }

.welcome h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 0.25rem; }
.welcome p { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1.5rem; }

.form-group { margin-bottom: 1rem; }

label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

input, select {
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

input::placeholder { color: var(--text-muted); }
input:focus, select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(30, 58, 95, 0.1);
  background: white;
}

input.input-error { border-color: var(--danger); }

.btn {
  width: 100%;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  font-family: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  margin-top: 0.5rem;
}

.btn-primary { background: var(--primary); color: white; }
.btn-primary:hover { background: var(--primary-light); }

.btn-secondary {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
  margin-top: 0.75rem;
}

.btn-secondary:hover { background: #f8fafc; color: var(--text); }

.btn-success { background: #059669; color: white; }
.btn-success:hover { background: #047857; }

.error {
  padding: 0.75rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

.success {
  padding: 0.75rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  color: #059669;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

.info {
  padding: 0.75rem;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  color: #1d4ed8;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

.link {
  text-align: center;
  margin-top: 1.25rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.link a { color: var(--primary); text-decoration: none; font-weight: 500; }
.link a:hover { text-decoration: underline; }

.card-footer {
  padding: 1rem;
  text-align: center;
  font-size: 0.7rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  background: #f8fafc;
  border-radius: 0 0 16px 16px;
}

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }

.field-error { color: var(--danger); font-size: 0.75rem; margin-top: 0.25rem; }

.password-strength {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin-top: 0.5rem;
  overflow: hidden;
}

.password-strength-bar {
  height: 100%;
  width: 0;
  transition: width 0.3s, background 0.3s;
}

.strength-weak { width: 33%; background: var(--danger); }
.strength-medium { width: 66%; background: #f59e0b; }
.strength-strong { width: 100%; background: var(--success); }
"""


# ===== HTML RENDER FONKSİYONLARI =====

def render_login(error_block: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Giris</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>AkrediX</span>'">
      </div>
      <h1>Hatay Mustafa Kemal Universitesi</h1>
      <p>Akreditasyon Raporlama Sistemi</p>
    </div>
    <div class="card-body">
      <div class="welcome">
        <h2>Hos Geldiniz</h2>
        <p>Devam etmek icin giris yapin</p>
      </div>
      {error_block}
      <form method="POST" action="/login" id="loginForm">
        <div class="form-group">
          <label>E-posta</label>
          <input type="email" name="email" id="email" placeholder="ornek@mku.edu.tr" required>
          <div class="field-error" id="emailError"></div>
        </div>
        <div class="form-group">
          <label>Sifre</label>
          <input type="password" name="password" id="password" placeholder="Sifreniz" required>
        </div>
        <button type="submit" class="btn btn-primary">Giris Yap</button>
      </form>
      <div class="link">
        <a href="/forgot-password">Sifremi Unuttum</a>
      </div>
      <div class="link">
        Hesabiniz yok mu? <a href="/signup">Kayit olun</a>
      </div>
    </div>
    <div class="card-footer">
      2026 AkrediX Sistemi
    </div>
  </div>
  <script>
    document.getElementById('loginForm').addEventListener('submit', function(e) {{
      let valid = true;
      const email = document.getElementById('email');
      const emailError = document.getElementById('emailError');
      
      if (!email.value.includes('@')) {{
        emailError.textContent = 'Gecerli bir e-posta adresi girin';
        email.classList.add('input-error');
        valid = false;
      }} else {{
        emailError.textContent = '';
        email.classList.remove('input-error');
      }}
      
      if (!valid) e.preventDefault();
    }});
  </script>
</body>
</html>
"""


def render_signup(error_block: str = "") -> str:
    # Dinamik bölüm listesi
    departments = get_all_departments()
    dept_options = ""
    for dept in departments:
        dept_id = dept.get('department_id', '')
        dept_name = dept.get('name', '')
        dept_faculty = dept.get('faculty', '')
        selected = "selected" if dept_id == "siyaset_bilimi" else ""
        dept_options += f'<option value="{dept_id}" data-faculty="{dept_faculty}" {selected}>{dept_name}</option>'
    
    # Bölüm yoksa varsayılan ekle
    if not dept_options:
        dept_options = '<option value="siyaset_bilimi" data-faculty="İktisadi ve İdari Bilimler Fakültesi" selected>Siyaset Bilimi ve Kamu Yönetimi</option>'
    
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Kayit</title>
  <style>
    {_css()}
    .card {{ max-width: 700px; }}
    .steps {{ display: flex; justify-content: center; gap: 0.5rem; margin-bottom: 1.5rem; }}
    .step {{ width: 12px; height: 12px; border-radius: 50%; background: #e2e8f0; transition: all 0.3s; }}
    .step.active {{ background: #1e3a5f; transform: scale(1.2); }}
    .step.done {{ background: #059669; }}
    .step-content {{ display: none; }}
    .step-content.active {{ display: block; }}
    .step-title {{ font-size: 1rem; font-weight: 600; color: #1e293b; margin-bottom: 0.5rem; }}
    .step-desc {{ font-size: 0.8rem; color: #64748b; margin-bottom: 1rem; }}
    .btn-group {{ display: flex; gap: 0.75rem; margin-top: 1rem; }}
    .btn-back {{ background: #64748b; color: white; }}
    .btn-back:hover {{ background: #475569; }}
    textarea {{ width: 100%; min-height: 80px; padding: 0.75rem; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 0.85rem; font-family: inherit; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #1e3a5f; box-shadow: 0 0 0 3px rgba(30,58,95,0.1); }}
    textarea.readonly {{ background: #f1f5f9; color: #64748b; }}
    .helper {{ font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }}
    .section-label {{ font-weight: 600; color: #1e293b; margin-bottom: 0.5rem; display: block; }}
    .info-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; font-size: 0.8rem; color: #1e40af; }}
    .password-strength {{ height: 6px; background: #e2e8f0; border-radius: 3px; margin-top: 0.5rem; overflow: hidden; }}
    .password-strength-bar {{ height: 100%; width: 0; transition: width 0.3s, background 0.3s; border-radius: 3px; }}
    .strength-weak {{ width: 33%; background: #ef4444; }}
    .strength-medium {{ width: 66%; background: #f59e0b; }}
    .strength-strong {{ width: 100%; background: #10b981; }}
    .strength-text {{ font-size: 0.7rem; margin-top: 0.25rem; }}
    .strength-text.weak {{ color: #ef4444; }}
    .strength-text.medium {{ color: #f59e0b; }}
    .strength-text.strong {{ color: #10b981; }}
    .bologna-btn {{ background: #059669; color: white; padding: 0.5rem 1rem; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem; margin-bottom: 1rem; }}
    .bologna-btn:hover {{ background: #047857; }}
    .bologna-status {{ display: none; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>AkrediX</span>'">
      </div>
      <h1>Hatay Mustafa Kemal Universitesi</h1>
      <p>Akreditasyon Raporlama Sistemi</p>
    </div>
    <div class="card-body">
      <div class="welcome">
        <h2>Kayit Olun</h2>
        <p>Hesap, bölüm ve müfredat bilgilerinizi girin</p>
      </div>
      
      <div class="steps">
        <div class="step active" data-step="1"></div>
        <div class="step" data-step="2"></div>
        <div class="step" data-step="3"></div>
      </div>
      
      {error_block}
      <form method="POST" action="/signup" id="signupForm">
        <input type="hidden" name="role" value="ogretim_elemani">
        
        <!-- ADIM 1: Kişisel Bilgiler -->
        <div class="step-content active" data-step="1">
          <div class="step-title">👤 Kişisel Bilgiler</div>
          <div class="step-desc">Hesap bilgilerinizi girin</div>
          
          <div class="form-group">
            <label>Ad Soyad</label>
            <input type="text" name="full_name" id="fullName" placeholder="Dr. Ahmet Yilmaz" required>
          </div>
          <div class="form-group">
            <label>E-posta</label>
            <input type="email" name="email" id="email" placeholder="ornek@mku.edu.tr" required>
          </div>
          <div class="form-group">
            <label>Şifre</label>
            <input type="password" name="password" id="password" placeholder="En az 6 karakter" required>
            <div class="password-strength"><div class="password-strength-bar" id="strengthBar"></div></div>
            <div class="strength-text" id="strengthText"></div>
          </div>
          <div class="form-group">
            <label>Şifre Tekrar</label>
            <input type="password" name="password_confirm" id="passwordConfirm" placeholder="Şifreyi tekrar girin" required>
            <div class="field-error" id="confirmError"></div>
          </div>
          
          <div class="btn-group">
            <button type="button" class="btn btn-primary" onclick="nextStep(2)">Devam →</button>
          </div>
        </div>
        
        <!-- ADIM 2: Bölüm ve Ders Seçimi -->
        <div class="step-content" data-step="2">
          <div class="step-title">🏛️ Bölüm ve Ders Seçimi</div>
          <div class="step-desc">Bölüm ve ders bilgilerinizi seçin</div>
          
          <div class="form-group">
            <label>Fakülte</label>
            <input type="text" id="facultyInput" value="İktisadi ve İdari Bilimler Fakültesi" readonly style="background:#f1f5f9;">
          </div>
          
          <div class="form-group">
            <label>Bölüm</label>
            <select name="department_id" id="departmentSelect" onchange="updateFaculty()" required>
              {dept_options}
            </select>
            <input type="hidden" name="program_name" id="programName" value="Siyaset Bilimi ve Kamu Yönetimi">
          </div>
          
          <div class="grid-2">
            <div class="form-group">
              <label>Akademik Yıl</label>
              <select name="academic_year" id="academicYear" onchange="updateTermInput()">
                <option value="2025-2026" selected>2025-2026</option>
                <option value="2024-2025">2024-2025</option>
              </select>
            </div>
            <div class="form-group">
              <label>Yarıyıl</label>
              <select name="semester" id="semesterSelect" onchange="updateCourses()" required>
                <option value="1" selected>1. Yarıyıl (Güz)</option>
                <option value="2">2. Yarıyıl (Bahar)</option>
                <option value="3">3. Yarıyıl (Güz)</option>
                <option value="4">4. Yarıyıl (Bahar)</option>
                <option value="5">5. Yarıyıl (Güz)</option>
                <option value="6">6. Yarıyıl (Bahar)</option>
                <option value="7">7. Yarıyıl (Güz)</option>
                <option value="8">8. Yarıyıl (Bahar)</option>
              </select>
            </div>
          </div>
          
          <div class="form-group">
            <label>Ders</label>
            <select name="course_code" id="courseSelect" onchange="updateCourseName()" required>
              <option value="">-- Önce yarıyıl seçin --</option>
            </select>
            <input type="hidden" name="course_name" id="courseNameHidden">
          </div>
          
          <div class="form-group">
            <label>Dönem</label>
            <input type="text" name="term" id="termInput" readonly style="background:#f1f5f9;">
          </div>
          
          <div class="btn-group">
            <button type="button" class="btn btn-back" onclick="prevStep(1)">← Geri</button>
            <button type="button" class="btn btn-primary" onclick="nextStep(3)">Devam →</button>
          </div>
        </div>
        
        <!-- ADIM 3: Müfredat Çıktıları -->
        <div class="step-content" data-step="3">
          <div class="step-title">🎯 Müfredat Çıktıları</div>
          <div class="step-desc">Program ve ders çıktılarını tanımlayın</div>
          
          <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:1rem;">
            <button type="button" class="bologna-btn" onclick="loadFromBologna()">📥 PEA + PÖÇ Getir</button>
            <button type="button" class="bologna-btn" onclick="fetchDocFromBologna()" style="background:#059669;">📥 DÖÇ + Müfredat Getir</button>
          </div>
          <div id="bolognaStatus" class="success bologna-status">✅ Veriler Bologna'dan yüklendi!</div>
          
          <div class="info-box">
            💡 <strong>Kolay format:</strong> TYÇ1. veya B1. veya ST1. yazmanız yeterli!<br>
            📌 Ders seçtikten sonra "DÖÇ + Müfredat Getir" butonuna basın.
          </div>
          
          <div class="form-group">
            <label class="section-label">🎓 TYÇ Çıktıları (Türkiye Yeterlilikler Çerçevesi)</label>
            <textarea name="tyc_text" id="tycText" placeholder="TYÇ1.&#10;TYÇ2.&#10;TYÇ3.&#10;..."></textarea>
            <div class="helper">Örnek: TYÇ1. veya TYÇ1 | Açıklama</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🧠 Bloom Taksonomisi</label>
            <textarea name="bloom_text" id="bloomText" placeholder="B1.&#10;B2.&#10;B3.&#10;B4.&#10;B5.&#10;B6."></textarea>
            <div class="helper">Örnek: B1. veya B1 | Bilgi</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🏢 STAR-K Çıktıları (Sektör Standartları)</label>
            <textarea name="stark_text" id="starkText" placeholder="ST1.&#10;ST2.&#10;ST3.&#10;..."></textarea>
            <div class="helper">Örnek: ST1. veya ST1 | Açıklama</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🎯 PEA (Program Eğitim Amaçları) - Bologna'dan</label>
            <textarea name="peas_text" id="peasText" placeholder="PEA + PÖÇ Getir butonuna basın..." readonly class="readonly"></textarea>
            <div class="helper">Sadece Dekan/Bölüm Başkanı değiştirebilir</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📗 PÖÇ (Program Öğrenim Çıktıları) - Bologna'dan</label>
            <textarea name="pocs_text" id="pocsText" placeholder="PEA + PÖÇ Getir butonuna basın..." readonly class="readonly"></textarea>
            <div class="helper">Sadece Dekan/Bölüm Başkanı değiştirebilir</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📘 DÖÇ (Ders Öğrenim Çıktıları) - Bologna'dan</label>
            <textarea name="docs_text" id="docsText" placeholder="DÖÇ + Müfredat Getir butonuna basın..."></textarea>
            <div class="helper">Ders seçtikten sonra Bologna'dan otomatik çekilir</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📚 Müfredat (Ders Konuları) - Bologna'dan</label>
            <textarea name="curriculum_text" id="curriculumText" placeholder="DÖÇ + Müfredat Getir butonuna basın..."></textarea>
            <div class="helper">Ders seçtikten sonra Bologna'dan otomatik çekilir</div>
          </div>
          
          <div class="btn-group">
            <button type="button" class="btn btn-back" onclick="prevStep(2)">← Geri</button>
            <button type="submit" class="btn btn-primary" id="submitBtn">✓ Kayit Ol</button>
          </div>
        </div>
        
      </form>
      <div class="link">
        Hesabiniz var mi? <a href="/login">Giris yapin</a>
      </div>
    </div>
    <div class="card-footer">
      2026 AkrediX Sistemi
    </div>
  </div>
  <script>
    // Dersler ve PEA/PÖÇ artık API'den dinamik çekiliyor
    const COURSES = {{}};  // Geriye uyumluluk için boş
    const PEA_DATA = '';
    const POC_DATA = '';
    
    let currentStep = 1;
    const password = document.getElementById('password');
    const strengthBar = document.getElementById('strengthBar');
    const strengthText = document.getElementById('strengthText');
    const passwordConfirm = document.getElementById('passwordConfirm');
    const confirmError = document.getElementById('confirmError');
    
    // Şifre güvenlik göstergesi
    password.addEventListener('input', function() {{
      const val = this.value;
      let strength = 0;
      let text = '';
      
      if (val.length >= 6) strength++;
      if (val.length >= 10) strength++;
      if (val.match(/[A-Z]/)) strength++;
      if (val.match(/[0-9]/)) strength++;
      if (val.match(/[^A-Za-z0-9]/)) strength++;
      
      strengthBar.className = 'password-strength-bar';
      strengthText.className = 'strength-text';
      
      if (val.length === 0) {{
        text = '';
      }} else if (strength <= 2) {{
        strengthBar.classList.add('strength-weak');
        strengthText.classList.add('weak');
        text = '⚠️ Zayıf şifre';
      }} else if (strength <= 3) {{
        strengthBar.classList.add('strength-medium');
        strengthText.classList.add('medium');
        text = '⚡ Orta güçlükte';
      }} else {{
        strengthBar.classList.add('strength-strong');
        strengthText.classList.add('strong');
        text = '✓ Güçlü şifre';
      }}
      strengthText.textContent = text;
    }});
    
    // Şifre eşleşme kontrolü
    passwordConfirm.addEventListener('input', function() {{
      if (this.value && this.value !== password.value) {{
        confirmError.textContent = 'Şifreler eşleşmiyor';
        confirmError.style.color = '#ef4444';
      }} else if (this.value && this.value === password.value) {{
        confirmError.textContent = '✓ Şifreler eşleşiyor';
        confirmError.style.color = '#10b981';
      }} else {{
        confirmError.textContent = '';
      }}
    }});
    
    function showStep(step) {{
      document.querySelectorAll('.step-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.step').forEach(el => {{
        el.classList.remove('active', 'done');
        if (parseInt(el.dataset.step) < step) el.classList.add('done');
        if (parseInt(el.dataset.step) === step) el.classList.add('active');
      }});
      document.querySelector(`.step-content[data-step="${{step}}"]`).classList.add('active');
      currentStep = step;
    }}
    
    function nextStep(step) {{
      // Adım 1 validasyonu
      if (currentStep === 1) {{
        const fullName = document.getElementById('fullName');
        const email = document.getElementById('email');
        
        if (fullName.value.trim().length < 3) {{
          alert('Ad soyad en az 3 karakter olmalı');
          fullName.focus();
          return;
        }}
        if (!email.value.includes('@')) {{
          alert('Geçerli bir e-posta girin');
          email.focus();
          return;
        }}
        if (password.value.length < 6) {{
          alert('Şifre en az 6 karakter olmalı');
          password.focus();
          return;
        }}
        if (password.value !== passwordConfirm.value) {{
          alert('Şifreler eşleşmiyor');
          passwordConfirm.focus();
          return;
        }}
      }}
      // Adım 2 validasyonu
      if (currentStep === 2) {{
        const courseSelect = document.getElementById('courseSelect');
        if (!courseSelect.value) {{
          alert('Lütfen bir ders seçin');
          return;
        }}
      }}
      showStep(step);
    }}
    
    function prevStep(step) {{
      showStep(step);
    }}
    
    function updateCourses() {{
      const semester = document.getElementById('semesterSelect').value;
      const deptId = document.getElementById('departmentSelect').value;
      const courseSelect = document.getElementById('courseSelect');
      
      courseSelect.innerHTML = '<option value="">Yükleniyor...</option>';
      
      // Bölüme göre dersleri API'den çek
      fetch('/api/department-courses/' + deptId + '/' + semester)
        .then(r => r.json())
        .then(data => {{
          const courses = data.courses || [];
          if (courses.length === 0) {{
            courseSelect.innerHTML = '<option value="">-- Bu yarıyılda ders yok --</option>';
          }} else {{
            courseSelect.innerHTML = '<option value="">-- Ders Seçin --</option>';
            courses.forEach(c => {{
              const opt = document.createElement('option');
              opt.value = c.code;
              opt.textContent = c.code + ' - ' + c.name + ' (' + c.akts + ' AKTS, ' + c.type + ')';
              opt.dataset.name = c.name;
              courseSelect.appendChild(opt);
            }});
          }}
        }})
        .catch((err) => {{
          console.error('Ders listesi yüklenemedi:', err);
          courseSelect.innerHTML = '<option value="">-- Dersler yüklenemedi --</option>';
        }});
      
      updateTermInput();
    }}
    
    function updateFaculty() {{
      const deptSelect = document.getElementById('departmentSelect');
      const selected = deptSelect.options[deptSelect.selectedIndex];
      const faculty = selected ? selected.dataset.faculty || '' : '';
      document.getElementById('facultyInput').value = faculty;
      document.getElementById('programName').value = selected ? selected.textContent : '';
      
      // PEA/PÖÇ verilerini de bölüme göre yükle
      loadPeaPocForDepartment(selected ? selected.value : '');
      
      updateCourses();
    }}
    
    function loadPeaPocForDepartment(deptId) {{
      if (!deptId) return;
      
      fetch('/api/department-pea-poc/' + deptId)
        .then(r => r.json())
        .then(data => {{
          if (data.pea_text) {{
            document.getElementById('peasText').value = data.pea_text;
          }}
          if (data.poc_text) {{
            document.getElementById('pocsText').value = data.poc_text;
          }}
        }})
        .catch(() => {{}});
    }}
    
    function updateCourseName() {{
      const courseSelect = document.getElementById('courseSelect');
      const selected = courseSelect.options[courseSelect.selectedIndex];
      document.getElementById('courseNameHidden').value = selected ? selected.dataset.name || '' : '';
    }}
    
    function updateTermInput() {{
      const year = document.getElementById('academicYear').value;
      const sem = document.getElementById('semesterSelect').value;
      const semType = parseInt(sem) % 2 === 1 ? 'Güz' : 'Bahar';
      document.getElementById('termInput').value = year + ' ' + semType + ' (' + sem + '. Yarıyıl)';
    }}
    
    function loadFromBologna() {{
      const deptId = document.getElementById('departmentSelect').value;
      const statusEl = document.getElementById('bolognaStatus');
      
      if (!deptId) {{
        alert('Lütfen önce bölüm seçin!');
        return;
      }}
      
      statusEl.textContent = '⏳ PEA/PÖÇ yükleniyor...';
      statusEl.style.display = 'block';
      statusEl.style.background = '#fef3c7';
      statusEl.style.color = '#92400e';
      
      fetch('/api/department-pea-poc/' + deptId)
        .then(r => r.json())
        .then(data => {{
          if (data.pea_text || data.poc_text) {{
            if (data.pea_text) document.getElementById('peasText').value = data.pea_text;
            if (data.poc_text) document.getElementById('pocsText').value = data.poc_text;
            statusEl.textContent = '✅ PEA ve PÖÇ yüklendi!';
            statusEl.style.background = '#dcfce7';
            statusEl.style.color = '#166534';
          }} else {{
            statusEl.textContent = '⚠️ PEA/PÖÇ verisi bulunamadı. Admin panelinden ekleyin.';
            statusEl.style.background = '#fef2f2';
            statusEl.style.color = '#dc2626';
          }}
        }})
        .catch(() => {{
          statusEl.textContent = '❌ Bağlantı hatası';
          statusEl.style.background = '#fef2f2';
          statusEl.style.color = '#dc2626';
        }});
    }}
    
    function fetchDocFromBologna() {{
      const courseCode = document.getElementById('courseSelect').value;
      if (!courseCode) {{
        alert('Lütfen önce bir ders seçin!');
        return;
      }}
      
      const statusEl = document.getElementById('bolognaStatus');
      statusEl.textContent = '⏳ Bologna\\'dan veriler çekiliyor...';
      statusEl.style.display = 'block';
      statusEl.style.background = '#fef3c7';
      statusEl.style.color = '#92400e';
      
      fetch('/api/fetch-bologna-signup/' + courseCode)
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            if (data.doc_text) {{
              document.getElementById('docsText').value = data.doc_text;
            }}
            if (data.curriculum_text) {{
              document.getElementById('curriculumText').value = data.curriculum_text;
            }}
            statusEl.textContent = '✅ DÖÇ ve Müfredat Bologna\\'dan yüklendi!';
            statusEl.style.background = '#dcfce7';
            statusEl.style.color = '#166534';
          }} else {{
            statusEl.textContent = '⚠️ ' + (data.error || 'Veri çekilemedi. Manuel giriş yapın.');
            statusEl.style.background = '#fef2f2';
            statusEl.style.color = '#dc2626';
          }}
        }})
        .catch(err => {{
          statusEl.textContent = '❌ Bağlantı hatası. Manuel giriş yapın.';
          statusEl.style.background = '#fef2f2';
          statusEl.style.color = '#dc2626';
        }});
    }}
    
    // Sayfa yüklendiğinde
    document.addEventListener('DOMContentLoaded', function() {{
      updateCourses();
      updateTermInput();
    }});
  </script>
</body>
</html>
"""


def render_forgot_password(message_block: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Sifremi Unuttum</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>AkrediX</span>'">
      </div>
      <h1>Sifre Sifirlama</h1>
      <p>E-posta adresinizi girin</p>
    </div>
    <div class="card-body">
      {message_block}
      <form method="POST" action="/forgot-password">
        <div class="form-group">
          <label>E-posta</label>
          <input type="email" name="email" placeholder="ornek@mku.edu.tr" required>
        </div>
        <button type="submit" class="btn btn-primary">Sifirlama Linki Gonder</button>
      </form>
      <div class="link">
        <a href="/login">Girise don</a>
      </div>
    </div>
    <div class="card-footer">
      2026 AkrediX Sistemi
    </div>
  </div>
</body>
</html>
"""


def render_reset_password(token: str, message_block: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Yeni Sifre</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>AkrediX</span>'">
      </div>
      <h1>Yeni Sifre Belirle</h1>
      <p>Yeni sifrenizi girin</p>
    </div>
    <div class="card-body">
      {message_block}
      <form method="POST" action="/reset-password/{token}" id="resetForm">
        <div class="form-group">
          <label>Yeni Sifre</label>
          <input type="password" name="password" id="password" placeholder="En az 6 karakter" required>
          <div class="password-strength"><div class="password-strength-bar" id="strengthBar"></div></div>
        </div>
        <div class="form-group">
          <label>Sifre Tekrar</label>
          <input type="password" name="password_confirm" id="passwordConfirm" placeholder="Sifreyi tekrar girin" required>
          <div class="field-error" id="confirmError"></div>
        </div>
        <button type="submit" class="btn btn-primary">Sifreyi Degistir</button>
      </form>
    </div>
    <div class="card-footer">
      2026 AkrediX Sistemi
    </div>
  </div>
  <script>
    const password = document.getElementById('password');
    const strengthBar = document.getElementById('strengthBar');
    const passwordConfirm = document.getElementById('passwordConfirm');
    
    password.addEventListener('input', function() {{
      const val = this.value;
      let strength = 0;
      if (val.length >= 6) strength++;
      if (val.match(/[A-Z]/)) strength++;
      if (val.match(/[0-9]/)) strength++;
      if (val.match(/[^A-Za-z0-9]/)) strength++;
      
      strengthBar.className = 'password-strength-bar';
      if (strength <= 1) strengthBar.classList.add('strength-weak');
      else if (strength <= 2) strengthBar.classList.add('strength-medium');
      else strengthBar.classList.add('strength-strong');
    }});
    
    document.getElementById('resetForm').addEventListener('submit', function(e) {{
      if (password.value !== passwordConfirm.value) {{
        document.getElementById('confirmError').textContent = 'Sifreler eslesmiyor';
        e.preventDefault();
      }}
      if (password.value.length < 6) {{
        e.preventDefault();
        alert('Sifre en az 6 karakter olmali');
      }}
    }});
  </script>
</body>
</html>
"""


# ===== ADMIN PANELİ =====

def get_all_users() -> list:
    """Tüm kullanıcıları getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT email, full_name, role, department_id, course_code, course_name, created_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_user_role(email: str, new_role: str):
    """Kullanıcı rolünü güncelle"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET role=? WHERE email=?", (new_role, email))
    conn.commit()
    conn.close()

def update_user_course(email: str, course_code: str, course_name: str = ""):
    """Kullanıcının aktif dersini güncelle"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET course_code=?, course_name=? WHERE email=?", 
                (course_code, course_name, email))
    conn.commit()
    conn.close()

def delete_user(email: str):
    """Kullanıcıyı sil"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("DELETE FROM users WHERE email=?", (email,))
        
        # user_curriculum - user_email sütunu
        try:
            conn.execute("DELETE FROM user_curriculum WHERE user_email=?", (email,))
        except:
            pass
        
        # user_courses - user_email sütunu
        try:
            conn.execute("DELETE FROM user_courses WHERE user_email=?", (email,))
        except:
            pass
        
        # drafts - user_email sütunu
        try:
            conn.execute("DELETE FROM drafts WHERE user_email=?", (email,))
        except:
            pass
        
        # report_history - user_email sütunu
        try:
            conn.execute("DELETE FROM report_history WHERE user_email=?", (email,))
        except:
            pass
        
        conn.commit()
    except Exception as e:
        print(f"delete_user error: {e}")
    finally:
        conn.close()

def add_user(email: str, password: str, full_name: str, role: str, department_id: str = None, course_code: str = None, course_name: str = None, program_name: str = None):
    """Yeni kullanıcı ekle"""
    conn = sqlite3.connect(DB_PATH)
    hashed = hash_password(password)
    
    # Varsayılan değerler
    if not department_id:
        department_id = "siyaset_bilimi"
    if not program_name:
        # Bölüm adını veritabanından al
        dept = get_department(department_id)
        program_name = dept.get('name', 'Siyaset Bilimi ve Kamu Yönetimi') if dept else 'Siyaset Bilimi ve Kamu Yönetimi'
    
    try:
        conn.execute("""INSERT INTO users (email, password, full_name, role, department_id, course_code, course_name, program_name) 
                        VALUES (?,?,?,?,?,?,?,?)""",
            (email, hashed, full_name, role, department_id, course_code, course_name, program_name))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


# ============ PROFİL SAYFASI ============

def render_profile(user: dict, message_block: str = "") -> str:
    """Profil sayfası - Kişisel bilgiler ve ders verileri"""
    role = user.get('role', 'ogretim_elemani')
    role_info = get_role_info(role)
    course_code = user.get('course_code', '')
    course_name = user.get('course_name', '')
    
    # Ders verilerini al
    course_data = get_course_data(course_code) if course_code else {}
    
    # YETKİ YAPISI:
    # - TYÇ, STAR-K, Bloom, DÖÇ, Müfredat: HERKES düzenleyebilir
    # - PÖÇ, PEA: Sadece Dekan/BB/Admin düzenleyebilir (program düzeyinde)
    can_edit_program = role in ['admin', 'dekan', 'bolum_baskani']
    readonly_program = '' if can_edit_program else 'readonly'
    readonly_class_program = '' if can_edit_program else 'readonly'
    
    # Tüm dersler ve bölümler
    all_courses = get_all_courses_data()
    departments = get_all_departments()
    user_email = user.get('email', '')
    user_dept_id = user.get('department_id', '')
    
    # Öğretim elemanı için yetkili dersleri al
    user_course_codes = []
    if not can_edit_program:
        user_courses = get_user_courses(user_email)
        user_course_codes = [uc.get('course_code') for uc in user_courses]
        # Mevcut (ana) ders kodunu da ekle
        if course_code and course_code not in user_course_codes:
            user_course_codes.append(course_code)
    
    # Dersleri bölüme göre grupla
    courses_by_dept = {}
    for cd in all_courses:
        cd_dept = cd.get('department_id', 'diger') or 'diger'
        if cd_dept not in courses_by_dept:
            courses_by_dept[cd_dept] = []
        courses_by_dept[cd_dept].append(cd)
    
    # Bölüm adlarını al
    dept_names = {d.get('department_id'): d.get('name') for d in departments}
    dept_names['diger'] = 'Diğer'
    
    # Ders seçim dropdown'ı - bölüm bazlı gruplu
    courses_select = ""
    
    if can_edit_program:
        # Admin/Dekan/BB tüm dersleri görebilir - bölümlere göre gruplu
        for dept_id in sorted(courses_by_dept.keys(), key=lambda x: dept_names.get(x, x)):
            dept_name = dept_names.get(dept_id, dept_id)
            dept_courses = courses_by_dept[dept_id]
            
            if dept_courses:
                courses_select += f'<optgroup label="📚 {dept_name}">'
                # Yarıyıla göre sırala
                dept_courses_sorted = sorted(dept_courses, key=lambda x: (x.get('semester', 0), x.get('course_code', '')))
                for cd in dept_courses_sorted:
                    selected = "selected" if cd.get('course_code') == course_code else ""
                    sem = cd.get('semester', '')
                    sem_str = f" [{sem}. YY]" if sem else ""
                    courses_select += f'<option value="{cd.get("course_code","")}" {selected}>{cd.get("course_code","")}{sem_str} - {cd.get("course_name","")}</option>'
                courses_select += '</optgroup>'
    else:
        # Öğretim elemanı sadece yetkili olduğu dersleri görebilir
        user_courses_by_dept = {}
        for cd in all_courses:
            cd_code = cd.get('course_code', '')
            if cd_code in user_course_codes:
                cd_dept = cd.get('department_id', 'diger') or 'diger'
                if cd_dept not in user_courses_by_dept:
                    user_courses_by_dept[cd_dept] = []
                user_courses_by_dept[cd_dept].append(cd)
        
        for dept_id in sorted(user_courses_by_dept.keys(), key=lambda x: dept_names.get(x, x)):
            dept_name = dept_names.get(dept_id, dept_id)
            dept_courses = user_courses_by_dept[dept_id]
            
            if dept_courses:
                courses_select += f'<optgroup label="📚 {dept_name}">'
                dept_courses_sorted = sorted(dept_courses, key=lambda x: (x.get('semester', 0), x.get('course_code', '')))
                for cd in dept_courses_sorted:
                    selected = "selected" if cd.get('course_code') == course_code else ""
                    sem = cd.get('semester', '')
                    sem_str = f" [{sem}. YY]" if sem else ""
                    courses_select += f'<option value="{cd.get("course_code","")}" {selected}>{cd.get("course_code","")}{sem_str} - {cd.get("course_name","")}</option>'
                courses_select += '</optgroup>'
        
        # Eğer hiç ders yoksa bilgi ver
        if not courses_select:
            courses_select = '<option value="">-- Yetkili olduğunuz ders bulunamadı --</option>'
    
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Profil</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Inter',sans-serif; background:#f1f5f9; min-height:100vh; color:#1e293b; padding:2rem; }}
    
    .profile-container {{ max-width:900px; margin:0 auto; }}
    
    .profile-header {{ display:flex; align-items:center; gap:1.5rem; margin-bottom:2rem; background:white; padding:1.5rem; border-radius:16px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .avatar {{ width:80px; height:80px; border-radius:50%; background:{role_info['color']}; display:flex; align-items:center; justify-content:center; font-size:2rem; color:white; font-weight:700; }}
    .profile-info h1 {{ font-size:1.5rem; color:#1e293b; margin-bottom:0.25rem; }}
    .profile-info p {{ color:#64748b; font-size:0.9rem; }}
    .role-badge {{ display:inline-block; padding:0.25rem 0.75rem; border-radius:20px; font-size:0.75rem; font-weight:600; background:{role_info['bg_color']}; color:{role_info['color']}; margin-top:0.5rem; }}
    
    .tabs {{ display:flex; gap:0.5rem; margin-bottom:1.5rem; }}
    .tab-btn {{ padding:0.75rem 1.5rem; background:white; border:1px solid #e2e8f0; color:#64748b; cursor:pointer; border-radius:8px 8px 0 0; font-weight:500; font-size:0.9rem; transition:all 0.2s; }}
    .tab-btn:hover {{ color:#1e293b; background:#f8fafc; }}
    .tab-btn.active {{ background:#4f46e5; color:white; border-color:#4f46e5; }}
    
    .tab-content {{ display:none; background:white; border-radius:0 12px 12px 12px; padding:2rem; border:1px solid #e2e8f0; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .tab-content.active {{ display:block; }}
    
    .form-group {{ margin-bottom:1.25rem; }}
    .form-group label {{ display:block; font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:0.5rem; }}
    .form-group input, .form-group textarea, .form-group select {{ 
      width:100%; padding:0.75rem 1rem; background:white; border:1px solid #e2e8f0; border-radius:8px; 
      color:#1e293b; font-size:0.9rem; font-family:inherit;
    }}
    .form-group input:focus, .form-group textarea:focus {{ outline:none; border-color:#4f46e5; box-shadow:0 0 0 3px rgba(79,70,229,0.1); }}
    .form-group input.readonly, .form-group textarea.readonly {{ background:#f8fafc; color:#94a3b8; cursor:not-allowed; }}
    .form-group textarea {{ min-height:100px; resize:vertical; }}
    .helper {{ font-size:0.75rem; color:#94a3b8; margin-top:0.35rem; }}
    
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; }}
    
    .btn {{ padding:0.75rem 1.5rem; border-radius:8px; font-weight:600; font-size:0.9rem; cursor:pointer; border:none; transition:all 0.2s; }}
    .btn-primary {{ background:#4f46e5; color:white; }}
    .btn-primary:hover {{ background:#4338ca; transform:translateY(-1px); box-shadow:0 4px 12px rgba(79,70,229,0.3); }}
    .btn-secondary {{ background:#f1f5f9; color:#475569; text-decoration:none; display:inline-block; border:1px solid #e2e8f0; }}
    .btn-secondary:hover {{ background:#e2e8f0; }}
    .btn:disabled {{ opacity:0.5; cursor:not-allowed; }}
    
    .section-title {{ font-size:1rem; font-weight:600; color:#1e293b; margin:1.5rem 0 1rem 0; padding-top:1rem; border-top:1px solid #e2e8f0; }}
    .section-title:first-child {{ margin-top:0; padding-top:0; border-top:none; }}
    
    .alert {{ padding:1rem; border-radius:8px; margin-bottom:1rem; }}
    .alert-success {{ background:#ecfdf5; border:1px solid #10b981; color:#065f46; }}
    .alert-error {{ background:#fef2f2; border:1px solid #dc2626; color:#991b1b; }}
    .alert-info {{ background:#eff6ff; border:1px solid #3b82f6; color:#1e40af; }}
    
    .back-link {{ display:inline-flex; align-items:center; gap:0.5rem; color:#64748b; text-decoration:none; margin-bottom:1.5rem; }}
    .back-link:hover {{ color:#4f46e5; }}
    
    .data-info {{ background:#f8fafc; border-radius:8px; padding:1rem; margin-top:1rem; border:1px solid #e2e8f0; }}
    .data-info p {{ font-size:0.8rem; color:#64748b; margin-bottom:0.5rem; }}
    .data-info strong {{ color:#475569; }}
  </style>
</head>
<body>
  <div class="profile-container">
    <a href="/" class="back-link">← Ana Sayfaya Dön</a>
    
    {message_block}
    
    <div class="profile-header">
      <div class="avatar">{user.get('full_name', 'U')[0].upper()}</div>
      <div class="profile-info">
        <h1>{user.get('full_name', 'Kullanıcı')}</h1>
        <p>{user.get('email', '')}</p>
        <span class="role-badge">{role_info['name']}</span>
      </div>
    </div>
    
    <div class="tabs">
      <button class="tab-btn active" onclick="showTab('personal')">👤 Kişisel Bilgiler</button>
      <button class="tab-btn" onclick="showTab('course')">📚 Ders Verileri</button>
    </div>
    
    <!-- Kişisel Bilgiler -->
    <div id="tab-personal" class="tab-content active">
      <div class="section-title">📋 Hesap Bilgileri</div>
      
      <div class="grid-2">
        <div class="form-group">
          <label>Ad Soyad</label>
          <input type="text" value="{user.get('full_name', '')}" readonly class="readonly">
        </div>
        <div class="form-group">
          <label>E-posta</label>
          <input type="email" value="{user.get('email', '')}" readonly class="readonly">
          <div class="helper">E-posta adresi değiştirilemez</div>
        </div>
      </div>
      
      <div class="grid-2">
        <div class="form-group">
          <label>Şifre</label>
          <input type="password" value="********" readonly class="readonly">
          <div class="helper">Şifre değiştirilemez</div>
        </div>
        <div class="form-group">
          <label>Rol</label>
          <input type="text" value="{role_info['name']}" readonly class="readonly">
        </div>
      </div>
      
      <div class="section-title">🏛️ Kurum Bilgileri</div>
      
      <div class="grid-2">
        <div class="form-group">
          <label>Program</label>
          <input type="text" value="{user.get('program_name', 'Siyaset Bilimi ve Kamu Yönetimi')}" readonly class="readonly">
        </div>
        <div class="form-group">
          <label>Dönem</label>
          <input type="text" value="{user.get('term', '-')}" readonly class="readonly">
        </div>
      </div>
      
      <div class="grid-2">
        <div class="form-group">
          <label>Ders Kodu</label>
          <input type="text" value="{course_code or '-'}" readonly class="readonly">
        </div>
        <div class="form-group">
          <label>Ders Adı</label>
          <input type="text" value="{course_name or '-'}" readonly class="readonly">
        </div>
      </div>
    </div>
    
    <!-- Ders Verileri -->
    <div id="tab-course" class="tab-content">
      <div class="alert alert-info">
        ⚠️ TYÇ, STAR-K, Bloom, DÖÇ ve Müfredat herkes tarafından düzenlenebilir. PÖÇ ve PEA sadece Dekan/BB tarafından düzenlenebilir.
      </div>
      
      <div class="form-group" style="margin-bottom:1.5rem;">
        <label>📚 Ders Seçin</label>
        <select id="courseSelector" onchange="loadCourseData(this.value)" style="max-width:400px;">
          {courses_select}
        </select>
        {'<div class="helper">Yetkili olduğunuz dersler listelenmektedir</div>' if not can_edit_program else ''}
      </div>
      
      <form method="POST" action="/profile/course-data" id="courseDataForm">
        <input type="hidden" name="course_code" id="formCourseCode" value="{course_code}">
        
        <div class="section-title">🎓 Çerçeve Verileri</div>
        
        <div class="grid-2">
          <div class="form-group">
            <label>TYÇ (Türkiye Yeterlilikler Çerçevesi)</label>
            <textarea name="tyc_text" placeholder="TYÇ1.&#10;TYÇ2.&#10;TYÇ3.&#10;...">{course_data.get('tyc_text', '')}</textarea>
            <div class="helper">Kolay format: TYÇ1. veya TYÇ1 | Açıklama</div>
          </div>
          <div class="form-group">
            <label>Bloom Taksonomisi</label>
            <textarea name="bloom_text" placeholder="B1.&#10;B2.&#10;B3.&#10;B4.&#10;B5.&#10;B6.">{course_data.get('bloom_text', '')}</textarea>
            <div class="helper">Kolay format: B1. veya B1 | Açıklama</div>
          </div>
        </div>
        
        <div class="grid-2">
          <div class="form-group">
            <label>STAR-K (Sektör Standartları)</label>
            <textarea name="stark_text" placeholder="ST1.&#10;ST2.&#10;ST3.&#10;...">{course_data.get('stark_text', '')}</textarea>
            <div class="helper">Kolay format: ST1. veya ST1 | Açıklama</div>
          </div>
          <div class="form-group">
            <label>PEA (Program Eğitim Amaçları) {'🔒' if not can_edit_program else ''}</label>
            <textarea name="pea_text" {readonly_program} class="{readonly_class_program}" placeholder="PEA1.&#10;PEA2.&#10;...">{course_data.get('pea_text', '')}</textarea>
            <div class="helper">{'Sadece Dekan/BB düzenleyebilir' if not can_edit_program else 'Kolay format: PEA1. veya PEA1 | Açıklama'}</div>
          </div>
        </div>
        
        <div class="section-title">📘 Ders Çıktıları</div>
        
        <div class="grid-2">
          <div class="form-group">
            <label>PÖÇ (Program Öğrenim Çıktıları) {'🔒' if not can_edit_program else ''}</label>
            <textarea name="poc_text" {readonly_program} class="{readonly_class_program}" placeholder="PÖÇ1.&#10;PÖÇ2.&#10;...">{course_data.get('poc_text', '')}</textarea>
            <div class="helper">{'Sadece Dekan/BB düzenleyebilir' if not can_edit_program else 'Kolay format: PÖÇ1. veya PÖÇ1 | Açıklama'}</div>
          </div>
          <div class="form-group">
            <label>DÖÇ (Ders Öğrenim Çıktıları)</label>
            <textarea name="doc_text" placeholder="DÖÇ1.&#10;DÖÇ2.&#10;...">{course_data.get('doc_text', '')}</textarea>
            <div class="helper">Kolay format: DÖÇ1. veya DÖÇ1 | Açıklama</div>
          </div>
        </div>
        
        <div class="form-group">
          <label>Müfredat (Ders Konuları)</label>
          <textarea name="curriculum_text" style="min-height:150px;" placeholder="H1 | Konu 1&#10;H2 | Konu 2&#10;...">{course_data.get('curriculum_text', '')}</textarea>
          <div class="helper">Format: H1 | Konu veya MUF1 | Konu</div>
        </div>
        
        <div style="margin-top:1.5rem; display:flex; gap:1rem; flex-wrap:wrap;">
          <button type="submit" class="btn btn-primary">💾 Değişiklikleri Kaydet</button>
          <button type="button" class="btn btn-secondary" onclick="fetchFromBologna()">📥 Bolognadan DÖÇ/Müfredat Çek</button>
        </div>
        
        <div class="data-info">
          <p><strong>Bologna Linki:</strong> {course_data.get('bologna_link', '-') or '-'}</p>
          <p><strong>Son Güncelleme:</strong> {course_data.get('updated_at', '-') or '-'}</p>
          <p><strong>Güncelleyen:</strong> {course_data.get('updated_by', '-') or '-'}</p>
        </div>
      </form>
    </div>
  </div>
  
  <script>
    function showTab(tabId) {{
      document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + tabId).classList.add('active');
      event.target.classList.add('active');
    }}
    
    function loadCourseData(courseCode) {{
      if (!courseCode) return;
      document.getElementById('formCourseCode').value = courseCode;
      
      // Yükleniyor göster
      const btn = document.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      
      fetch('/api/course-data/' + courseCode)
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            document.querySelector('[name="tyc_text"]').value = data.tyc_text || '';
            document.querySelector('[name="bloom_text"]').value = data.bloom_text || '';
            document.querySelector('[name="stark_text"]').value = data.stark_text || '';
            document.querySelector('[name="pea_text"]').value = data.pea_text || '';
            document.querySelector('[name="poc_text"]').value = data.poc_text || '';
            document.querySelector('[name="doc_text"]').value = data.doc_text || '';
            document.querySelector('[name="curriculum_text"]').value = data.curriculum_text || '';
            
            // Cookie'yi güncelle - ana sayfanın doğru ders kodunu okuması için
            try {{
              const profileCookie = document.cookie.split('; ').find(row => row.startsWith('profile='));
              if (profileCookie) {{
                let profileData = JSON.parse(decodeURIComponent(profileCookie.split('=')[1]));
                profileData.course_code = courseCode;
                profileData.course_name = data.course_name || '';
                document.cookie = 'profile=' + encodeURIComponent(JSON.stringify(profileData)) + '; path=/; max-age=2592000';
              }}
            }} catch(e) {{
              console.warn('Cookie güncelleme hatası:', e);
            }}
            
            // Eğer DÖÇ veya Müfredat boşsa ve Bologna linki varsa otomatik çek
            if ((!data.doc_text || !data.curriculum_text) && data.bologna_link) {{
              fetchFromBolognaAuto();
            }}
          }} else {{
            alert('Ders verileri yüklenemedi: ' + (data.error || 'Bilinmeyen hata'));
          }}
        }})
        .catch(err => {{
          console.error('Ders verisi yükleme hatası:', err);
          alert('Ders verileri yüklenirken bir hata oluştu');
        }})
        .finally(() => {{
          if (btn) btn.disabled = false;
        }});
    }}
    
    function fetchFromBolognaAuto() {{
      const courseCode = document.getElementById('formCourseCode').value;
      if (!courseCode) return;
      
      fetch('/api/fetch-bologna/' + courseCode)
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            if (data.doc_text) document.querySelector('[name="doc_text"]').value = data.doc_text;
            if (data.curriculum_text) document.querySelector('[name="curriculum_text"]').value = data.curriculum_text;
            console.log('Bologna verileri otomatik yüklendi');
          }}
        }})
        .catch(err => console.error('Bologna auto-fetch hatası:', err));
    }}
    
    function fetchFromBologna() {{
      const courseCode = document.getElementById('formCourseCode').value;
      if (!courseCode) {{ alert('Önce bir ders seçin'); return; }}
      
      const btn = event.target;
      btn.disabled = true;
      btn.textContent = '⏳ Yükleniyor...';
      
      fetch('/api/fetch-bologna/' + courseCode)
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            if (data.doc_text) document.querySelector('[name="doc_text"]').value = data.doc_text;
            if (data.curriculum_text) document.querySelector('[name="curriculum_text"]').value = data.curriculum_text;
            alert('Bologna\\'dan veriler çekildi! Kaydetmeyi unutmayın.');
          }} else {{
            alert('Hata: ' + (data.error || 'Veri çekilemedi'));
          }}
        }})
        .finally(() => {{
          btn.disabled = false;
          btn.textContent = '📥 Bolognadan DÖÇ/Müfredat Çek';
        }});
    }}
  </script>
</body>
</html>
"""


def render_admin_panel(message_block: str = "", current_user: dict = None) -> str:
    """Admin paneli HTML'i - Profesyonel Dashboard"""
    users = get_all_users()
    courses_data = get_all_courses_data()
    departments = get_all_departments()
    
    # Bölüm adlarını hazırla
    dept_names = {d.get('department_id'): d.get('name') for d in departments}
    dept_names['diger'] = 'Diğer'
    dept_names[None] = 'Diğer'
    dept_names[''] = 'Diğer'
    
    # Dersleri bölüme göre grupla
    courses_by_dept = {}
    for cd in courses_data:
        cd_dept = cd.get('department_id') or 'diger'
        if cd_dept not in courses_by_dept:
            courses_by_dept[cd_dept] = []
        courses_by_dept[cd_dept].append(cd)
    
    # Ders seçenekleri (modal için) - bölüm bazlı gruplu
    course_options = ""
    for dept_id in sorted(courses_by_dept.keys(), key=lambda x: dept_names.get(x, str(x))):
        dept_name = dept_names.get(dept_id, dept_id)
        dept_courses = sorted(courses_by_dept[dept_id], key=lambda x: (x.get('semester', 0), x.get('course_code', '')))
        
        if dept_courses:
            course_options += f'<optgroup label="📚 {dept_name}">'
            for cd in dept_courses:
                sem = cd.get('semester', '')
                sem_str = f" [{sem}. YY]" if sem else ""
                course_options += f'<option value="{cd.get("course_code","")}">{cd.get("course_code","")}{sem_str} - {cd.get("course_name","")}</option>'
            course_options += '</optgroup>'
    
    # Bölüm seçenekleri (kullanıcı ekleme formu için)
    dept_select_options = ""
    for dept in departments:
        dept_id = dept.get('department_id', '')
        dept_name = dept.get('name', '')
        dept_select_options += f'<option value="{dept_id}">{dept_name}</option>'
    if not dept_select_options:
        dept_select_options = '<option value="siyaset_bilimi">Siyaset Bilimi ve Kamu Yönetimi</option>'
    
    # İstatistikler
    total_users = len(users)
    admin_count = len([u for u in users if u.get('role') == 'admin'])
    dekan_count = len([u for u in users if u.get('role') == 'dekan'])
    bolum_baskani_count = len([u for u in users if u.get('role') == 'bolum_baskani'])
    ogretim_count = len([u for u in users if u.get('role') == 'ogretim_elemani'])
    total_departments = len(departments)
    
    # Son 7 gün kayıt
    from datetime import datetime, timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent_users = len([u for u in users if u.get('created_at', '')[:10] >= seven_days_ago])
    
    users_rows = ""
    for u in users:
        role = u.get('role', 'ogretim_elemani')
        role_info = get_role_info(role)
        
        role_options = ""
        for r_key, r_val in ROLES.items():
            selected = "selected" if r_key == role else ""
            role_options += f'<option value="{r_key}" {selected}>{r_val["name"]}</option>'
        
        # Kullanıcının yetkili olduğu ders sayısı
        user_courses = get_user_courses(u.get('email', ''))
        course_count = len(user_courses)
        course_badge = f'<span style="background:#4f46e5;color:white;padding:0.15rem 0.5rem;border-radius:10px;font-size:0.7rem;margin-left:0.25rem;">{course_count}</span>' if course_count > 0 else ''
        
        users_rows += f"""
        <tr>
            <td><strong>{u.get('email','')}</strong></td>
            <td>{u.get('full_name','') or '-'}</td>
            <td>
                <select onchange="updateRole('{u.get('email','')}', this.value)" 
                        style="padding:0.4rem 0.6rem; border-radius:6px; border:1px solid #e2e8f0; background:{role_info['bg_color']}; color:{role_info['color']}; font-weight:600; font-size:0.75rem; cursor:pointer;">
                    {role_options}
                </select>
            </td>
            <td style="font-size:0.8rem;">
                {u.get('course_name','') or u.get('course_code','') or '-'}
                {course_badge}
            </td>
            <td style="font-size:0.75rem; color:#64748b;">{u.get('created_at','')[:10] if u.get('created_at') else '-'}</td>
            <td>
                <button onclick="openUserCoursesModal('{u.get('email','')}', '{u.get('full_name','')}')" class="btn-icon" title="Ders Ata" style="color:#4f46e5;">📚</button>
                <button onclick="deleteUser('{u.get('email','')}')" class="btn-icon" title="Sil" style="color:#dc2626;">🗑️</button>
            </td>
        </tr>"""
    
    # Ders listesi tablosu - veritabanından
    courses_rows = ""
    for cd in courses_data:
        bologna_link = cd.get('bologna_link', '')
        link_status = '✅' if bologna_link else '❌'
        courses_rows += f"""
        <tr data-code="{cd.get('course_code','')}">
            <td><strong>{cd.get('course_code','')}</strong></td>
            <td>{cd.get('course_name','')}</td>
            <td style="text-align:center;">{link_status}</td>
            <td>
                <input type="text" class="link-input" value="{bologna_link}" 
                       style="width:100%;padding:0.3rem;font-size:0.7rem;background:white;border:1px solid #e2e8f0;border-radius:4px;color:#1e293b;"
                       onchange="updateCourseLink('{cd.get('course_code','')}', this.value)">
            </td>
            <td>
                <button onclick="editCourseData('{cd.get('course_code','')}')" class="btn-icon" title="Verileri Düzenle" style="color:#4f46e5;">📝</button>
            </td>
        </tr>"""
    
    # Dinamik bölüm kartları
    dept_cards = ""
    for dept in departments:
        dept_id = dept.get('department_id', '')
        dept_name = dept.get('name', '')
        dept_faculty = dept.get('faculty', '')
        bologna_courses = dept.get('bologna_courses_url', '')
        bologna_pea = dept.get('bologna_pea_url', '')
        bologna_poc = dept.get('bologna_poc_url', '')
        dept_pea = get_department_data(dept_id).get('peas_text', '') if dept_id else ''
        dept_poc = get_department_data(dept_id).get('pocs_text', '') if dept_id else ''
        
        dept_cards += f"""
        <div class="panel-card" style="margin-bottom:1.5rem;" id="dept-card-{dept_id}">
          <div class="panel-card-header" style="display:flex; justify-content:space-between; align-items:center;">
            <h3>📌 {dept_name}</h3>
            <div style="display:flex; gap:0.5rem; align-items:center;">
              <span class="badge badge-info">{dept_faculty or 'Fakülte belirtilmemiş'}</span>
              <button onclick="editDepartment('{dept_id}')" class="btn-icon" title="Düzenle" style="color:#4f46e5;">✏️</button>
              <button onclick="deleteDepartment('{dept_id}', '{dept_name}')" class="btn-icon" title="Sil" style="color:#dc2626;">🗑️</button>
            </div>
          </div>
          <div class="panel-card-body">
            <!-- Düzenleme formu (gizli) -->
            <div id="edit-form-{dept_id}" style="display:none; background:#f8fafc; padding:1rem; border-radius:8px; margin-bottom:1rem;">
              <h4 style="margin-bottom:0.75rem; color:#4f46e5;">✏️ Bölüm Bilgilerini Düzenle</h4>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:0.75rem;">
                <div class="form-group" style="margin:0;">
                  <label style="font-size:0.8rem;">Bölüm Adı</label>
                  <input type="text" id="edit-name-{dept_id}" value="{dept_name}" style="width:100%;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label style="font-size:0.8rem;">Fakülte</label>
                  <input type="text" id="edit-faculty-{dept_id}" value="{dept_faculty}" style="width:100%;">
                </div>
              </div>
              <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.75rem; margin-bottom:0.75rem;">
                <div class="form-group" style="margin:0;">
                  <label style="font-size:0.75rem;">📚 Ders Listesi URL</label>
                  <input type="url" id="edit-courses-url-{dept_id}" value="{bologna_courses}" style="width:100%;font-size:0.8rem;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label style="font-size:0.75rem;">🎯 PEA URL</label>
                  <input type="url" id="edit-pea-url-{dept_id}" value="{bologna_pea}" style="width:100%;font-size:0.8rem;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label style="font-size:0.75rem;">📗 PÖÇ URL</label>
                  <input type="url" id="edit-poc-url-{dept_id}" value="{bologna_poc}" style="width:100%;font-size:0.8rem;">
                </div>
              </div>
              <div style="display:flex; gap:0.5rem;">
                <button onclick="saveDepartmentEdit('{dept_id}')" class="btn btn-primary" style="font-size:0.85rem;">💾 Kaydet</button>
                <button onclick="cancelDepartmentEdit('{dept_id}')" class="btn btn-secondary" style="font-size:0.85rem;">İptal</button>
              </div>
            </div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1rem;">
              <div>
                <label style="font-size:0.75rem; color:#94a3b8;">📚 Ders Listesi</label>
                {'<a href="' + bologna_courses + '" target="_blank" class="btn btn-secondary" style="display:block; text-align:center; margin-top:0.25rem;">Bologna ↗</a>' if bologna_courses else '<span style="color:#94a3b8;font-size:0.8rem;">Link yok</span>'}
              </div>
              <div>
                <label style="font-size:0.75rem; color:#94a3b8;">🎯 PEA</label>
                {'<a href="' + bologna_pea + '" target="_blank" class="btn btn-secondary" style="display:block; text-align:center; margin-top:0.25rem;">Bologna ↗</a>' if bologna_pea else '<span style="color:#94a3b8;font-size:0.8rem;">Link yok</span>'}
              </div>
              <div>
                <label style="font-size:0.75rem; color:#94a3b8;">📗 PÖÇ</label>
                {'<a href="' + bologna_poc + '" target="_blank" class="btn btn-secondary" style="display:block; text-align:center; margin-top:0.25rem;">Bologna ↗</a>' if bologna_poc else '<span style="color:#94a3b8;font-size:0.8rem;">Link yok</span>'}
              </div>
            </div>
            
            <form method="POST" action="/admin/department">
              <input type="hidden" name="department_id" value="{dept_id}">
              
              <div class="form-group">
                <label>🎯 PEA (Program Eğitim Amaçları)</label>
                <textarea name="peas_text" placeholder="PEA1.&#10;PEA2.&#10;...">{dept_pea}</textarea>
              </div>
              
              <div class="form-group">
                <label>📗 PÖÇ (Program Öğrenim Çıktıları)</label>
                <textarea name="pocs_text" placeholder="PÖÇ1.&#10;PÖÇ2.&#10;...">{dept_poc}</textarea>
              </div>
              
              <div style="display:flex; gap:0.5rem;">
                <button type="submit" class="btn btn-primary">💾 Kaydet</button>
                <button type="button" class="btn btn-secondary" onclick="fetchPeaPocFromBologna('{dept_id}')">📥 Bologna'dan PEA/PÖÇ Çek</button>
              </div>
            </form>
            
            <!-- Ders Yönetimi Bölümü -->
            <div style="border-top:1px solid #e2e8f0; margin-top:1.5rem; padding-top:1.5rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <h4 style="color:#4f46e5; margin:0;">📚 Bölüm Dersleri</h4>
                <div style="display:flex; gap:0.5rem;">
                  <button type="button" class="btn btn-secondary" style="font-size:0.8rem;" onclick="toggleCourseForm('{dept_id}')">➕ Ders Ekle</button>
                  <button type="button" class="btn btn-secondary" style="font-size:0.8rem;" onclick="fetchCoursesFromBologna('{dept_id}', '{bologna_courses}')">📥 Bologna'dan Çek</button>
                  <button type="button" class="btn btn-secondary" style="font-size:0.8rem;" onclick="loadDepartmentCourses('{dept_id}')">🔄 Yenile</button>
                </div>
              </div>
              
              <!-- Ders Ekleme Formu (Gizli) -->
              <div id="course-form-{dept_id}" style="display:none; background:#f0fdf4; padding:1rem; border-radius:8px; margin-bottom:1rem; border:1px solid #bbf7d0;">
                <h5 style="margin-bottom:0.75rem; color:#166534;">➕ Yeni Ders Ekle</h5>
                <div style="display:grid; grid-template-columns:1fr 2fr 1fr 1fr; gap:0.5rem; margin-bottom:0.75rem;">
                  <input type="text" id="new-course-code-{dept_id}" placeholder="Ders Kodu" style="padding:0.5rem; border:1px solid #e2e8f0; border-radius:6px;">
                  <input type="text" id="new-course-name-{dept_id}" placeholder="Ders Adı" style="padding:0.5rem; border:1px solid #e2e8f0; border-radius:6px;">
                  <select id="new-course-semester-{dept_id}" style="padding:0.5rem; border:1px solid #e2e8f0; border-radius:6px;">
                    <option value="1">1. Yarıyıl</option>
                    <option value="2">2. Yarıyıl</option>
                    <option value="3">3. Yarıyıl</option>
                    <option value="4">4. Yarıyıl</option>
                    <option value="5">5. Yarıyıl</option>
                    <option value="6">6. Yarıyıl</option>
                    <option value="7">7. Yarıyıl</option>
                    <option value="8">8. Yarıyıl</option>
                  </select>
                  <input type="number" id="new-course-akts-{dept_id}" placeholder="AKTS" value="5" min="1" max="30" style="padding:0.5rem; border:1px solid #e2e8f0; border-radius:6px;">
                </div>
                <div style="display:flex; gap:0.5rem;">
                  <input type="url" id="new-course-link-{dept_id}" placeholder="Bologna Link (opsiyonel)" style="flex:1; padding:0.5rem; border:1px solid #e2e8f0; border-radius:6px;">
                  <button onclick="addCourse('{dept_id}')" class="btn btn-primary" style="font-size:0.85rem;">Ekle</button>
                  <button onclick="toggleCourseForm('{dept_id}')" class="btn btn-secondary" style="font-size:0.85rem;">İptal</button>
                </div>
              </div>
              
              <!-- Ders Listesi -->
              <div id="courses-list-{dept_id}" style="max-height:300px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:8px; background:#f8fafc;">
                <p style="padding:1rem; color:#64748b; text-align:center;">Dersler yükleniyor...</p>
              </div>
            </div>
          </div>
        </div>
        """
        
        # Bu bölümün derslerini yüklemek için script ekle
        dept_cards += f"""
        <script>
          document.addEventListener('DOMContentLoaded', function() {{
            loadDepartmentCourses('{dept_id}');
          }});
        </script>
        """
    
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/png" href="/assets/logo.png">
  <title>AkrediX - Admin Paneli</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Inter',sans-serif; background:#f1f5f9; min-height:100vh; color:#1e293b; }}
    
    .admin-container {{ display:grid; grid-template-columns:250px 1fr; min-height:100vh; }}
    
    /* Sidebar */
    .sidebar {{ background:#4f46e5; border-right:1px solid #4338ca; padding:1.5rem 0; }}
    .sidebar-header {{ padding:0 1.5rem 1.5rem; border-bottom:1px solid rgba(255,255,255,0.2); margin-bottom:1rem; }}
    .sidebar-logo {{ display:flex; align-items:center; gap:0.75rem; }}
    .sidebar-logo img {{ width:40px; height:40px; border-radius:8px; background:white; }}
    .sidebar-logo span {{ font-weight:700; font-size:1.1rem; color:white; }}
    
    .sidebar-nav {{ padding:0 0.75rem; }}
    .nav-item {{ display:flex; align-items:center; gap:0.75rem; padding:0.75rem 1rem; border-radius:8px; color:rgba(255,255,255,0.8); cursor:pointer; transition:all 0.2s; margin-bottom:0.25rem; border:none; background:none; width:100%; text-align:left; font-size:0.9rem; }}
    .nav-item:hover {{ background:rgba(255,255,255,0.15); color:white; }}
    .nav-item.active {{ background:white; color:#4f46e5; font-weight:600; }}
    .nav-item span {{ font-size:1.1rem; }}
    
    .sidebar-footer {{ padding:1rem 1.5rem; border-top:1px solid rgba(255,255,255,0.2); margin-top:auto; position:absolute; bottom:0; width:250px; }}
    .sidebar-footer a {{ color:rgba(255,255,255,0.8); text-decoration:none; font-size:0.85rem; display:flex; align-items:center; gap:0.5rem; }}
    .sidebar-footer a:hover {{ color:white; }}
    
    /* Main Content */
    .main-content {{ padding:2rem; overflow-y:auto; }}
    .page-header {{ margin-bottom:2rem; }}
    .page-header h1 {{ font-size:1.75rem; font-weight:700; color:#1e293b; margin-bottom:0.5rem; }}
    .page-header p {{ color:#64748b; }}
    
    /* Stats Cards */
    .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin-bottom:2rem; }}
    .stat-card {{ background:white; border-radius:12px; padding:1.25rem; border:1px solid #e2e8f0; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .stat-card-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; }}
    .stat-card-icon {{ width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:1.25rem; }}
    .stat-card-icon.blue {{ background:#eff6ff; }}
    .stat-card-icon.green {{ background:#ecfdf5; }}
    .stat-card-icon.purple {{ background:#f5f3ff; }}
    .stat-card-icon.orange {{ background:#fff7ed; }}
    .stat-value {{ font-size:2rem; font-weight:700; color:#1e293b; }}
    .stat-label {{ font-size:0.8rem; color:#64748b; margin-top:0.25rem; }}
    .stat-change {{ font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:20px; }}
    .stat-change.up {{ background:#ecfdf5; color:#059669; }}
    
    /* Content Panels */
    .content-panel {{ display:none; }}
    .content-panel.active {{ display:block; }}
    
    .panel-card {{ background:white; border-radius:12px; border:1px solid #e2e8f0; overflow:hidden; margin-bottom:1.5rem; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .panel-card-header {{ padding:1rem 1.5rem; border-bottom:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; background:#f8fafc; }}
    .panel-card-header h3 {{ font-size:1rem; font-weight:600; color:#1e293b; }}
    .panel-card-body {{ padding:1.5rem; }}
    
    /* Table */
    table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
    th, td {{ padding:0.75rem 1rem; text-align:left; border-bottom:1px solid #e2e8f0; }}
    th {{ background:#f8fafc; font-weight:600; color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.5px; }}
    tr:hover {{ background:#f8fafc; }}
    
    /* Badges */
    .badge {{ padding:0.25rem 0.5rem; border-radius:20px; font-size:0.7rem; font-weight:600; }}
    .badge-success {{ background:#ecfdf5; color:#059669; }}
    .badge-warning {{ background:#fff7ed; color:#ea580c; }}
    .badge-info {{ background:#eff6ff; color:#2563eb; }}
    
    /* Buttons */
    .btn {{ padding:0.6rem 1.25rem; border-radius:8px; font-weight:600; font-size:0.85rem; cursor:pointer; border:none; transition:all 0.2s; }}
    .btn-primary {{ background:#4f46e5; color:white; }}
    .btn-primary:hover {{ background:#4338ca; transform:translateY(-1px); box-shadow:0 4px 12px rgba(79,70,229,0.3); }}
    .btn-secondary {{ background:#f1f5f9; color:#475569; border:1px solid #e2e8f0; }}
    .btn-secondary:hover {{ background:#e2e8f0; }}
    .btn-danger {{ background:#dc2626; color:white; }}
    .btn-icon {{ background:none; border:none; cursor:pointer; padding:0.25rem; font-size:1rem; }}
    
    /* Forms */
    .form-group {{ margin-bottom:1.25rem; }}
    .form-group label {{ display:block; font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:0.5rem; }}
    textarea, input[type="text"], input[type="url"], input[type="email"], input[type="password"], select {{ 
      width:100%; padding:0.75rem 1rem; background:white; border:1px solid #e2e8f0; border-radius:8px; 
      color:#1e293b; font-size:0.9rem; font-family:inherit; resize:vertical;
    }}
    textarea:focus, input:focus, select:focus {{ outline:none; border-color:#4f46e5; box-shadow:0 0 0 3px rgba(79,70,229,0.1); }}
    textarea {{ min-height:120px; }}
    .helper {{ font-size:0.75rem; color:#94a3b8; margin-top:0.35rem; }}
    
    /* Search */
    .search-box {{ position:relative; margin-bottom:1rem; }}
    .search-box input {{ width:100%; padding:0.75rem 1rem 0.75rem 2.5rem; background:white; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b; }}
    .search-box::before {{ content:'🔍'; position:absolute; left:0.75rem; top:50%; transform:translateY(-50%); }}
    
    /* Messages */
    .alert {{ padding:1rem; border-radius:8px; margin-bottom:1rem; }}
    .alert-success {{ background:#ecfdf5; border:1px solid #10b981; color:#065f46; }}
    .alert-error {{ background:#fef2f2; border:1px solid #dc2626; color:#991b1b; }}
    
    /* Quick Actions */
    .quick-actions {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:1rem; margin-top:1.5rem; }}
    .quick-action {{ background:#334155; border-radius:10px; padding:1rem; text-align:center; cursor:pointer; transition:all 0.2s; border:1px solid transparent; }}
    .quick-action:hover {{ border-color:#3b82f6; transform:translateY(-2px); }}
    .quick-action span {{ font-size:1.5rem; display:block; margin-bottom:0.5rem; }}
    .quick-action p {{ font-size:0.8rem; color:#94a3b8; }}
    
    /* Tabs (for sub-sections) */
    .tabs {{ display:flex; gap:0.5rem; margin-bottom:1rem; border-bottom:1px solid #334155; padding-bottom:0.5rem; }}
    .tab-btn {{ padding:0.5rem 1rem; background:none; border:none; color:#94a3b8; cursor:pointer; border-radius:6px 6px 0 0; font-size:0.85rem; }}
    .tab-btn:hover {{ color:white; }}
    .tab-btn.active {{ background:#334155; color:white; }}
  </style>
</head>
<body>
  <div class="admin-container">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-logo">
          <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<div style=\\'background:#3b82f6;width:40px;height:40px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;\\'>P</div>'">
          <span>AkrediX</span>
        </div>
      </div>
      <nav class="sidebar-nav">
        <button class="nav-item active" onclick="showPanel('dashboard')"><span>📊</span> Dashboard</button>
        <button class="nav-item" onclick="showPanel('users')"><span>👥</span> Kullanıcılar</button>
        <button class="nav-item" onclick="showPanel('departments')"><span>🏛️</span> Bölümler</button>
        <button class="nav-item" onclick="showPanel('courses')"><span>📚</span> Dersler</button>
        <button class="nav-item" onclick="showPanel('settings')"><span>⚙️</span> Ayarlar</button>
      </nav>
      <div class="sidebar-footer">
        <a href="/"><span>←</span> Ana Sayfaya Dön</a>
      </div>
    </aside>
    
    <!-- Main Content -->
    <main class="main-content">
      {message_block}
      
      <!-- Dashboard Panel -->
      <div id="panel-dashboard" class="content-panel active">
        <div class="page-header">
          <h1>👋 Hoş Geldiniz, Admin</h1>
          <p>Sistem genel durumu ve hızlı işlemler</p>
        </div>
        
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-card-header">
              <div class="stat-card-icon blue">👥</div>
              <span class="stat-change up">+{recent_users} hafta</span>
            </div>
            <div class="stat-value">{total_users}</div>
            <div class="stat-label">Toplam Kullanıcı</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-header">
              <div class="stat-card-icon purple">🎓</div>
            </div>
            <div class="stat-value">{ogretim_count}</div>
            <div class="stat-label">Öğretim Elemanı</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-header">
              <div class="stat-card-icon green">🏛️</div>
            </div>
            <div class="stat-value">{dekan_count + bolum_baskani_count}</div>
            <div class="stat-label">Yönetici (Dekan + BB)</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-header">
              <div class="stat-card-icon orange">📚</div>
            </div>
            <div class="stat-value">71</div>
            <div class="stat-label">Toplam Ders</div>
          </div>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>🚀 Hızlı İşlemler</h3>
          </div>
          <div class="panel-card-body">
            <div class="quick-actions">
              <div class="quick-action" onclick="showPanel('users')">
                <span>➕</span>
                <p>Kullanıcı Yönet</p>
              </div>
              <div class="quick-action" onclick="showPanel('department')">
                <span>📝</span>
                <p>PEA/PÖÇ Düzenle</p>
              </div>
              <div class="quick-action" onclick="showPanel('courses')">
                <span>🔗</span>
                <p>Ders Linkleri</p>
              </div>
              <div class="quick-action" onclick="showPanel('settings')">
                <span>⚙️</span>
                <p>Ayarlar</p>
              </div>
            </div>
          </div>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>📈 Son Kayıtlar</h3>
          </div>
          <div class="panel-card-body">
            <table>
              <thead><tr><th>E-posta</th><th>Ad Soyad</th><th>Rol</th><th>Tarih</th></tr></thead>
              <tbody>
                {''.join([f"<tr><td>{u.get('email','')}</td><td>{u.get('full_name','') or '-'}</td><td><span class='badge badge-info'>{ROLES.get(u.get('role','ogretim_elemani'),{}).get('name','')}</span></td><td>{u.get('created_at','')[:10] if u.get('created_at') else '-'}</td></tr>" for u in users[:5]])}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      <!-- Users Panel -->
      <div id="panel-users" class="content-panel">
        <div class="page-header">
          <h1>👥 Kullanıcı Yönetimi</h1>
          <p>Tüm kullanıcıları görüntüle, ekle ve rollerini düzenle</p>
        </div>
        
        <!-- Kullanıcı Ekleme Formu -->
        <div class="panel-card" style="margin-bottom:1.5rem;">
          <div class="panel-card-header">
            <h3>➕ Yeni Kullanıcı Ekle</h3>
          </div>
          <div class="panel-card-body">
            <form id="addUserForm" onsubmit="addNewUser(event)" style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr auto; gap:0.75rem; align-items:end;">
              <div>
                <label style="display:block;font-size:0.75rem;color:#94a3b8;margin-bottom:0.3rem;">E-posta</label>
                <input type="email" name="email" placeholder="ornek@mku.edu.tr" required style="width:100%;padding:0.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;font-size:0.85rem;">
              </div>
              <div>
                <label style="display:block;font-size:0.75rem;color:#94a3b8;margin-bottom:0.3rem;">Ad Soyad</label>
                <input type="text" name="full_name" placeholder="Ad Soyad" required style="width:100%;padding:0.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;font-size:0.85rem;">
              </div>
              <div>
                <label style="display:block;font-size:0.75rem;color:#94a3b8;margin-bottom:0.3rem;">Şifre</label>
                <input type="password" name="password" placeholder="Şifre" required minlength="6" style="width:100%;padding:0.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;font-size:0.85rem;">
              </div>
              <div>
                <label style="display:block;font-size:0.75rem;color:#94a3b8;margin-bottom:0.3rem;">Bölüm</label>
                <select name="department_id" style="width:100%;padding:0.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;font-size:0.85rem;">
                  {dept_select_options}
                </select>
              </div>
              <div>
                <label style="display:block;font-size:0.75rem;color:#94a3b8;margin-bottom:0.3rem;">Rol</label>
                <select name="role" style="width:100%;padding:0.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:white;font-size:0.85rem;">
                  <option value="ogretim_elemani">Öğretim Elemanı</option>
                  <option value="bolum_baskani">Bölüm Başkanı</option>
                  <option value="dekan">Dekan</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button type="submit" class="btn btn-primary" style="height:38px;">Ekle</button>
            </form>
          </div>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>Kullanıcı Listesi ({total_users} kişi)</h3>
          </div>
          <div class="panel-card-body">
            <div class="search-box">
              <input type="text" placeholder="Kullanıcı ara..." onkeyup="filterUsers(this.value)">
            </div>
            <table id="usersTable">
              <thead>
                <tr>
                  <th>E-posta</th>
                  <th>Ad Soyad</th>
                  <th>Rol</th>
                  <th>Ders</th>
                  <th>Kayıt</th>
                  <th>İşlem</th>
                </tr>
              </thead>
              <tbody>{users_rows}</tbody>
            </table>
          </div>
        </div>
      </div>
      
      <!-- Courses Panel -->
      <div id="panel-courses" class="content-panel">
        <div class="page-header">
          <h1>📚 Ders Yönetimi</h1>
          <p>Bologna linkleri ve ders bilgileri</p>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>Ders Listesi ve Bologna Linkleri</h3>
          </div>
          <div class="panel-card-body">
            <div class="helper" style="margin-bottom:1rem;">
              ✅ = Bologna linki mevcut, ❌ = Link yok. Linkler üzerinden DÖÇ ve Müfredat çekilebilir.
            </div>
            <div style="max-height:500px; overflow-y:auto;">
              <table>
                <thead>
                  <tr>
                    <th>Yarıyıl</th>
                    <th>Kod</th>
                    <th>Ders Adı</th>
                    <th>Tür</th>
                    <th>Link</th>
                    <th>Bologna</th>
                  </tr>
                </thead>
                <tbody>{courses_rows}</tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Department Panel -->
      <!-- Departments Panel -->
      <div id="panel-departments" class="content-panel">
        <div class="page-header">
          <h1>🏛️ Bölüm Yönetimi</h1>
          <p>Bölüm ekle, düzenle ve Bologna linklerini yönet</p>
        </div>
        
        <!-- Yeni Bölüm Ekleme -->
        <div class="panel-card" style="margin-bottom:1.5rem;">
          <div class="panel-card-header">
            <h3>➕ Yeni Bölüm Ekle</h3>
          </div>
          <div class="panel-card-body">
            <form id="addDepartmentForm" onsubmit="addDepartment(event)">
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
                <div class="form-group" style="margin:0;">
                  <label>Bölüm ID (Kısa Kod)</label>
                  <input type="text" name="dept_id" placeholder="siyaset_bilimi" required style="width:100%;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label>Bölüm Adı</label>
                  <input type="text" name="dept_name" placeholder="Siyaset Bilimi ve Kamu Yönetimi" required style="width:100%;">
                </div>
              </div>
              <div class="form-group">
                <label>Fakülte</label>
                <input type="text" name="dept_faculty" placeholder="İktisadi ve İdari Bilimler Fakültesi" style="width:100%;">
              </div>
              <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1rem;">
                <div class="form-group" style="margin:0;">
                  <label>📚 Ders Listesi Bologna URL</label>
                  <input type="url" name="bologna_courses_url" placeholder="https://obs.mku.edu.tr/oibs/bologna/progCourses.aspx?..." style="width:100%;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label>🎯 PEA Bologna URL</label>
                  <input type="url" name="bologna_pea_url" placeholder="https://obs.mku.edu.tr/oibs/bologna/progGoalsObjectives.aspx?..." style="width:100%;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label>📗 PÖÇ Bologna URL</label>
                  <input type="url" name="bologna_poc_url" placeholder="https://obs.mku.edu.tr/oibs/bologna/progLearnOutcomes.aspx?..." style="width:100%;">
                </div>
              </div>
              <button type="submit" class="btn btn-primary">➕ Bölüm Ekle</button>
            </form>
          </div>
        </div>
        
        <!-- Mevcut Bölümler (Dinamik) -->
        <div class="page-header" style="margin-top:1.5rem;">
          <h2>📋 Mevcut Bölümler ({total_departments})</h2>
        </div>
        {dept_cards if dept_cards else '<div class="alert alert-info">Henüz bölüm eklenmemiş.</div>'}
      </div>
      
      <!-- Settings Panel -->
      <div id="panel-settings" class="content-panel">
        <div class="page-header">
          <h1>⚙️ Sistem Ayarları</h1>
          <p>Rol renkleri ve sistem bilgileri</p>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>🎨 Rol Renkleri</h3>
          </div>
          <div class="panel-card-body">
            <table>
              <thead><tr><th>Rol</th><th>Renk</th><th>Yetki Düzeyi</th></tr></thead>
              <tbody>
                <tr><td>Sistem Yöneticisi</td><td><span style="color:#1e3a5f;font-size:1.5rem;">■</span> Lacivert</td><td>100</td></tr>
                <tr><td>Dekan</td><td><span style="color:#7c2d12;font-size:1.5rem;">■</span> Bordo</td><td>80</td></tr>
                <tr><td>Bölüm Başkanı</td><td><span style="color:#065f46;font-size:1.5rem;">■</span> Yeşil</td><td>60</td></tr>
                <tr><td>Öğretim Elemanı</td><td><span style="color:#475569;font-size:1.5rem;">■</span> Gri</td><td>20</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        
        <div class="panel-card">
          <div class="panel-card-header">
            <h3>📋 Sistem Bilgileri</h3>
          </div>
          <div class="panel-card-body">
            <p style="line-height:2;">
              <strong>Versiyon:</strong> AkrediX v2.1<br>
              <strong>Toplam Kullanıcı:</strong> {total_users}<br>
              <strong>Toplam Ders:</strong> 71 (8 yarıyıl)<br>
              <strong>Aktif Bölüm:</strong> Siyaset Bilimi ve Kamu Yönetimi<br>
              <strong>Akademik Yıl:</strong> 2025-2026
            </p>
          </div>
        </div>
      </div>
      
    </main>
  </div>
  
  <script>
    function showPanel(panelId) {{
      document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.getElementById('panel-' + panelId).classList.add('active');
      event.target.classList.add('active');
    }}
    
    function updateRole(email, newRole) {{
      fetch('/admin/role', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
        body: 'email=' + encodeURIComponent(email) + '&role=' + encodeURIComponent(newRole)
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Rol güncellendi!', 'success');
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function deleteUser(email) {{
      if (confirm('Bu kullanıcıyı silmek istediğinizden emin misiniz?\\n' + email)) {{
        fetch('/admin/delete-user', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
          body: 'email=' + encodeURIComponent(email)
        }}).then(r => r.json()).then(data => {{
          if (data.success) location.reload();
          else alert('Hata: ' + data.error);
        }});
      }}
    }}
    
    // ============ DERS ATAMA FONKSİYONLARI ============
    let currentUserEmail = '';
    
    function openUserCoursesModal(email, fullName) {{
      currentUserEmail = email;
      document.getElementById('userCoursesModalTitle').textContent = fullName || email;
      document.getElementById('userCoursesModal').style.display = 'flex';
      loadUserCourses(email);
    }}
    
    function closeUserCoursesModal() {{
      document.getElementById('userCoursesModal').style.display = 'none';
      currentUserEmail = '';
    }}
    
    function loadUserCourses(email) {{
      const container = document.getElementById('userCoursesList');
      container.innerHTML = '<p style="color:#64748b;">Yükleniyor...</p>';
      
      fetch('/api/user-courses/' + encodeURIComponent(email))
        .then(r => r.json())
        .then(data => {{
          if (data.error) {{
            container.innerHTML = '<p style="color:#dc2626;">Hata: ' + data.error + '</p>';
            return;
          }}
          
          if (!data.courses || data.courses.length === 0) {{
            container.innerHTML = '<p style="color:#64748b;">Henüz ders atanmamış.</p>';
            return;
          }}
          
          let html = '<table style="width:100%;font-size:0.85rem;"><thead><tr><th>Kod</th><th>Ders Adı</th><th>İşlem</th></tr></thead><tbody>';
          data.courses.forEach(c => {{
            html += '<tr><td><strong>' + c.course_code + '</strong></td><td>' + (c.course_name || '-') + '</td>';
            html += '<td><button onclick="removeCourseFromUser(\\'' + c.course_code + '\\')" style="background:#dc2626;color:white;border:none;padding:0.25rem 0.5rem;border-radius:4px;cursor:pointer;font-size:0.75rem;">Kaldır</button></td></tr>';
          }});
          html += '</tbody></table>';
          container.innerHTML = html;
        }})
        .catch(err => {{
          container.innerHTML = '<p style="color:#dc2626;">Hata: ' + err.message + '</p>';
        }});
    }}
    
    function assignCourseToUser() {{
      const courseCode = document.getElementById('assignCourseSelect').value;
      if (!courseCode || !currentUserEmail) {{
        alert('Lütfen bir ders seçin');
        return;
      }}
      
      fetch('/api/assign-course', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email: currentUserEmail, course_code: courseCode }})
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Ders atandı!', 'success');
          loadUserCourses(currentUserEmail);
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function removeCourseFromUser(courseCode) {{
      if (!confirm('Bu dersi kullanıcıdan kaldırmak istiyor musunuz?')) return;
      
      fetch('/api/remove-course', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email: currentUserEmail, course_code: courseCode }})
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Ders kaldırıldı!', 'success');
          loadUserCourses(currentUserEmail);
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function filterUsers(query) {{
      const rows = document.querySelectorAll('#usersTable tbody tr');
      query = query.toLowerCase();
      rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
      }});
    }}
    
    function addNewUser(e) {{
      e.preventDefault();
      const form = e.target;
      const data = new FormData(form);
      
      fetch('/admin/add-user', {{
        method: 'POST',
        body: data
      }}).then(r => r.json()).then(result => {{
        if (result.success) {{
          showNotification('Kullanıcı eklendi!', 'success');
          setTimeout(() => location.reload(), 1000);
        }} else {{
          showNotification('Hata: ' + result.error, 'error');
        }}
      }});
    }}
    
    function updateCourseLink(courseCode, link) {{
      fetch('/admin/update-link', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
        body: 'course_code=' + encodeURIComponent(courseCode) + '&bologna_link=' + encodeURIComponent(link)
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Link güncellendi!', 'success');
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function editCourseData(courseCode) {{
      window.location.href = '/profile?course=' + courseCode;
    }}
    
    function addDepartment(e) {{
      e.preventDefault();
      const form = e.target;
      const data = new FormData(form);
      
      fetch('/admin/add-department', {{
        method: 'POST',
        body: data
      }}).then(r => r.json()).then(result => {{
        if (result.success) {{
          showNotification('Bölüm eklendi!', 'success');
          setTimeout(() => location.reload(), 1000);
        }} else {{
          showNotification('Hata: ' + result.error, 'error');
        }}
      }});
    }}
    
    function fetchPeaPocFromBologna(deptId) {{
      showNotification('Bologna\\'dan veriler çekiliyor...', 'info');
      
      fetch('/admin/fetch-pea-poc/' + deptId)
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            // Bu bölüme ait textarea'ları bul
            const card = document.getElementById('dept-card-' + deptId);
            if (card) {{
              const peaTextarea = card.querySelector('[name="peas_text"]');
              const pocTextarea = card.querySelector('[name="pocs_text"]');
              if (peaTextarea && data.pea_text) peaTextarea.value = data.pea_text;
              if (pocTextarea && data.poc_text) pocTextarea.value = data.poc_text;
            }}
            showNotification('PEA ve PÖÇ Bologna\\'dan yüklendi!', 'success');
          }} else {{
            showNotification('Hata: ' + (data.error || 'Veri çekilemedi'), 'error');
          }}
        }});
    }}
    
    function showNotification(message, type) {{
      const div = document.createElement('div');
      div.className = 'alert alert-' + type;
      div.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:9999;min-width:300px;';
      div.textContent = message;
      document.body.appendChild(div);
      setTimeout(() => div.remove(), 3000);
    }}
    
    function deleteDepartment(deptId, deptName) {{
      if (!confirm('Bu bölümü silmek istediğinizden emin misiniz?\\n\\nBölüm: ' + deptName + '\\n\\nBu işlem geri alınamaz!')) {{
        return;
      }}
      
      fetch('/admin/delete-department', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
        body: 'dept_id=' + encodeURIComponent(deptId)
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Bölüm silindi!', 'success');
          document.getElementById('dept-card-' + deptId).remove();
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function editDepartment(deptId) {{
      const editForm = document.getElementById('edit-form-' + deptId);
      if (editForm) {{
        editForm.style.display = editForm.style.display === 'none' ? 'block' : 'none';
      }}
    }}
    
    function cancelDepartmentEdit(deptId) {{
      const editForm = document.getElementById('edit-form-' + deptId);
      if (editForm) {{
        editForm.style.display = 'none';
      }}
    }}
    
    function saveDepartmentEdit(deptId) {{
      const name = document.getElementById('edit-name-' + deptId).value;
      const faculty = document.getElementById('edit-faculty-' + deptId).value;
      const coursesUrl = document.getElementById('edit-courses-url-' + deptId).value;
      const peaUrl = document.getElementById('edit-pea-url-' + deptId).value;
      const pocUrl = document.getElementById('edit-poc-url-' + deptId).value;
      
      const formData = new FormData();
      formData.append('dept_id', deptId);
      formData.append('name', name);
      formData.append('faculty', faculty);
      formData.append('bologna_courses_url', coursesUrl);
      formData.append('bologna_pea_url', peaUrl);
      formData.append('bologna_poc_url', pocUrl);
      
      fetch('/admin/update-department', {{
        method: 'POST',
        body: formData
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Bölüm güncellendi!', 'success');
          setTimeout(() => location.reload(), 1000);
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    // ===== DERS YÖNETİMİ FONKSİYONLARI =====
    
    function toggleCourseForm(deptId) {{
      const form = document.getElementById('course-form-' + deptId);
      if (form) {{
        form.style.display = form.style.display === 'none' ? 'block' : 'none';
      }}
    }}
    
    function addCourse(deptId) {{
      const code = document.getElementById('new-course-code-' + deptId).value.trim();
      const name = document.getElementById('new-course-name-' + deptId).value.trim();
      const semester = document.getElementById('new-course-semester-' + deptId).value;
      const akts = document.getElementById('new-course-akts-' + deptId).value;
      const link = document.getElementById('new-course-link-' + deptId).value.trim();
      
      if (!code || !name) {{
        showNotification('Ders kodu ve adı zorunlu!', 'error');
        return;
      }}
      
      const formData = new FormData();
      formData.append('dept_id', deptId);
      formData.append('course_code', code);
      formData.append('course_name', name);
      formData.append('semester', semester);
      formData.append('akts', akts);
      formData.append('course_type', 'Z');
      formData.append('bologna_link', link);
      
      fetch('/admin/add-course', {{
        method: 'POST',
        body: formData
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Ders eklendi!', 'success');
          toggleCourseForm(deptId);
          loadDepartmentCourses(deptId);
          refreshCourseOptionsInModal();  // Modal'daki ders listesini güncelle
          // Formu temizle
          document.getElementById('new-course-code-' + deptId).value = '';
          document.getElementById('new-course-name-' + deptId).value = '';
          document.getElementById('new-course-link-' + deptId).value = '';
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    function loadDepartmentCourses(deptId) {{
      const container = document.getElementById('courses-list-' + deptId);
      if (!container) return;
      
      container.innerHTML = '<p style="padding:1rem; color:#64748b; text-align:center;">Yükleniyor...</p>';
      
      fetch('/api/department-courses/' + deptId)
        .then(r => r.json())
        .then(data => {{
          if (data.error) {{
            container.innerHTML = '<p style="padding:1rem; color:#dc2626;">Hata: ' + data.error + '</p>';
            return;
          }}
          
          const courses = data.courses || {{}};
          const total = data.total || 0;
          
          if (total === 0) {{
            container.innerHTML = '<p style="padding:1rem; color:#64748b; text-align:center;">Henüz ders eklenmemiş.</p>';
            return;
          }}
          
          let html = '<table style="width:100%; border-collapse:collapse; font-size:0.85rem;">';
          html += '<thead><tr style="background:#e2e8f0;"><th style="padding:0.5rem; text-align:left;">Yarıyıl</th><th style="padding:0.5rem; text-align:left;">Kod</th><th style="padding:0.5rem; text-align:left;">Ders Adı</th><th style="padding:0.5rem; text-align:center;">AKTS</th><th style="padding:0.5rem; text-align:center;">İşlem</th></tr></thead>';
          html += '<tbody>';
          
          // Yarıyıla göre sırala
          const semesters = Object.keys(courses).sort((a, b) => parseInt(a) - parseInt(b));
          for (const sem of semesters) {{
            const semCourses = courses[sem];
            for (const c of semCourses) {{
              html += '<tr style="border-bottom:1px solid #e2e8f0;">';
              html += '<td style="padding:0.5rem;">' + sem + '. Yarıyıl</td>';
              html += '<td style="padding:0.5rem; font-weight:600;">' + c.code + '</td>';
              html += '<td style="padding:0.5rem;">' + c.name + '</td>';
              html += '<td style="padding:0.5rem; text-align:center;">' + c.akts + '</td>';
              html += '<td style="padding:0.5rem; text-align:center;">';
              html += '<button onclick="deleteCourseFromDept(\\'' + c.code + '\\', \\'' + deptId + '\\')" class="btn-icon" title="Sil" style="color:#dc2626; border:none; background:none; cursor:pointer;">🗑️</button>';
              html += '</td>';
              html += '</tr>';
            }}
          }}
          
          html += '</tbody></table>';
          html += '<p style="padding:0.5rem; font-size:0.75rem; color:#64748b; text-align:right;">Toplam: ' + total + ' ders</p>';
          
          container.innerHTML = html;
        }})
        .catch(err => {{
          container.innerHTML = '<p style="padding:1rem; color:#dc2626;">Bağlantı hatası</p>';
        }});
    }}
    
    function fetchCoursesFromBologna(deptId, url) {{
      if (!url) {{
        showNotification('Bologna ders listesi URL\\'si tanımlı değil!', 'error');
        return;
      }}
      
      if (!confirm('Bologna\\'dan ders listesi çekilecek. Bu işlem mevcut dersleri etkilemez, sadece yeni dersler ekler. Devam?')) {{
        return;
      }}
      
      showNotification('Bologna\\'dan dersler çekiliyor...', 'info');
      
      const formData = new FormData();
      formData.append('dept_id', deptId);
      formData.append('url', url);
      
      fetch('/admin/fetch-courses-from-bologna', {{
        method: 'POST',
        body: formData
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Toplam ' + data.total + ' ders bulundu, ' + data.added + ' yeni ders eklendi!', 'success');
          loadDepartmentCourses(deptId);
        }} else {{
          showNotification('Hata: ' + (data.error || 'Dersler çekilemedi'), 'error');
        }}
      }}).catch(err => {{
        showNotification('Bağlantı hatası!', 'error');
      }});
    }}
    
    function deleteCourseFromDept(courseCode, deptId) {{
      if (!confirm('Bu dersi silmek istediğinizden emin misiniz?\\n\\nDers Kodu: ' + courseCode)) {{
        return;
      }}
      
      const formData = new FormData();
      formData.append('course_code', courseCode);
      
      fetch('/admin/delete-course', {{
        method: 'POST',
        body: formData
      }}).then(r => r.json()).then(data => {{
        if (data.success) {{
          showNotification('Ders silindi!', 'success');
          loadDepartmentCourses(deptId);
          refreshCourseOptionsInModal();  // Modal'daki ders listesini güncelle
        }} else {{
          showNotification('Hata: ' + data.error, 'error');
        }}
      }});
    }}
    
    // Modal'daki ders seçeneklerini API'den güncelle
    function refreshCourseOptionsInModal() {{
      const select = document.getElementById('assignCourseSelect');
      if (!select) return;
      
      fetch('/api/all-courses')
        .then(r => r.json())
        .then(data => {{
          select.innerHTML = '<option value="">Ders seçin...</option>';
          const courses = data.courses || {{}};
          
          // Bölümlere göre grupla
          Object.keys(courses).sort().forEach(deptId => {{
            const deptCourses = courses[deptId];
            if (deptCourses && deptCourses.length > 0) {{
              const optgroup = document.createElement('optgroup');
              optgroup.label = '📚 ' + (data.dept_names[deptId] || deptId);
              
              deptCourses.forEach(c => {{
                const opt = document.createElement('option');
                opt.value = c.code;
                const semStr = c.semester ? ' [' + c.semester + '. YY]' : '';
                opt.textContent = c.code + semStr + ' - ' + c.name;
                optgroup.appendChild(opt);
              }});
              
              select.appendChild(optgroup);
            }}
          }});
        }})
        .catch(() => {{}});
    }}
  </script>
  
  <!-- Ders Atama Modal -->
  <div id="userCoursesModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:16px;width:90%;max-width:600px;max-height:80vh;overflow:hidden;box-shadow:0 25px 50px rgba(0,0,0,0.3);">
      <div style="background:#4f46e5;color:white;padding:1.25rem 1.5rem;display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0;font-size:1.1rem;">📚 Ders Yetkileri - <span id="userCoursesModalTitle"></span></h3>
        <button onclick="closeUserCoursesModal()" style="background:rgba(255,255,255,0.2);border:none;color:white;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:1rem;">✕</button>
      </div>
      <div style="padding:1.5rem;">
        <div style="margin-bottom:1.5rem;">
          <label style="display:block;font-size:0.85rem;font-weight:600;color:#64748b;margin-bottom:0.5rem;">Yeni Ders Ata</label>
          <div style="display:flex;gap:0.5rem;">
            <select id="assignCourseSelect" style="flex:1;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px;font-size:0.9rem;">
              <option value="">Ders seçin...</option>
              {course_options}
            </select>
            <button onclick="assignCourseToUser()" style="background:#4f46e5;color:white;border:none;padding:0.6rem 1.25rem;border-radius:8px;font-weight:600;cursor:pointer;">Ata</button>
          </div>
        </div>
        <div>
          <label style="display:block;font-size:0.85rem;font-weight:600;color:#64748b;margin-bottom:0.5rem;">Mevcut Dersler</label>
          <div id="userCoursesList" style="border:1px solid #e2e8f0;border-radius:8px;padding:1rem;max-height:300px;overflow-y:auto;background:#f8fafc;">
            <p style="color:#64748b;">Yükleniyor...</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


# Eski API uyumluluğu için sabitler (deprecated)
BASE_CSS = ""
LOGIN_HTML = ""
SIGNUP_HTML = ""
FORGOT_PASSWORD_HTML = ""
RESET_PASSWORD_HTML = ""
PROFILE_HTML = ""


# ===================== KULLANICI MÜFREDAT VERİLERİ =====================

def save_user_curriculum(email: str, data: dict):
    """Kullanıcının curriculum verilerini kaydet - mevcut verileri koruyarak güncelle"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat()
    
    # Önce mevcut verileri oku
    cur = conn.execute("SELECT * FROM user_curriculum WHERE user_email=?", (email,))
    existing = cur.fetchone()
    existing_data = dict(existing) if existing else {}
    
    # Mevcut verilerin üzerine yeni verileri yaz (sadece boş olmayanları)
    final_data = {}
    all_fields = [
        "tyc_text", "stark_text", "docs_text", "pocs_text", "peas_text",
        "curriculum_text", "bloom_text", "doc_tyc_map_text", "poc_tyc_map_text",
        "pea_stark_map_text", "poc_pea_map_text", "doc_poc_weights_text",
        "curriculum_doc_map_text", "doc_stark_map_text", "doc_pea_map_text",
        "curriculum_tyc_map_text", "curriculum_stark_map_text",
        "curriculum_poc_map_text", "curriculum_pea_map_text",
        "components_text", "thresholds_met", "thresholds_partial", 
        "grading_text", "question_map_text"
    ]
    
    for field in all_fields:
        new_val = data.get(field, "")
        existing_val = existing_data.get(field, "")
        # Eğer yeni değer varsa onu kullan, yoksa mevcut değeri koru
        if new_val and new_val.strip():
            final_data[field] = new_val
        else:
            final_data[field] = existing_val or ""
    
    # Varsayılan eşik değerleri
    if not final_data.get("thresholds_met"):
        final_data["thresholds_met"] = "70"
    if not final_data.get("thresholds_partial"):
        final_data["thresholds_partial"] = "50"
    
    conn.execute("""
        INSERT OR REPLACE INTO user_curriculum 
        (user_email, tyc_text, stark_text, docs_text, pocs_text, peas_text, 
         curriculum_text, bloom_text, doc_tyc_map_text, poc_tyc_map_text, 
         pea_stark_map_text, poc_pea_map_text, doc_poc_weights_text,
         curriculum_doc_map_text, doc_stark_map_text, doc_pea_map_text,
         curriculum_tyc_map_text, curriculum_stark_map_text,
         curriculum_poc_map_text, curriculum_pea_map_text,
         components_text, thresholds_met, thresholds_partial, 
         grading_text, question_map_text, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email,
        final_data.get("tyc_text", ""),
        final_data.get("stark_text", ""),
        final_data.get("docs_text", ""),
        final_data.get("pocs_text", ""),
        final_data.get("peas_text", ""),
        final_data.get("curriculum_text", ""),
        final_data.get("bloom_text", ""),
        final_data.get("doc_tyc_map_text", ""),
        final_data.get("poc_tyc_map_text", ""),
        final_data.get("pea_stark_map_text", ""),
        final_data.get("poc_pea_map_text", ""),
        final_data.get("doc_poc_weights_text", ""),
        final_data.get("curriculum_doc_map_text", ""),
        final_data.get("doc_stark_map_text", ""),
        final_data.get("doc_pea_map_text", ""),
        final_data.get("curriculum_tyc_map_text", ""),
        final_data.get("curriculum_stark_map_text", ""),
        final_data.get("curriculum_poc_map_text", ""),
        final_data.get("curriculum_pea_map_text", ""),
        final_data.get("components_text", ""),
        final_data.get("thresholds_met", "70"),
        final_data.get("thresholds_partial", "50"),
        final_data.get("grading_text", ""),
        final_data.get("question_map_text", ""),
        now
    ))
    conn.commit()
    conn.close()


def get_user_curriculum(email: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM user_curriculum WHERE user_email=?", (email,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return {}


# Veritabanını başlat
init_db()

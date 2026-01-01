"""
HMKU Akreditasyon - Login Module
Güvenli Authentication + Şifre Sıfırlama + Taslak + Rapor Geçmişi
"""
import sqlite3
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).with_name("auth.db")

# Şifre hash'leme
def hash_password(password: str) -> str:
    """SHA-256 ile şifre hash'le"""
    salt = "hmku_akreditasyon_2024"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Şifreyi doğrula"""
    return hash_password(password) == hashed

def init_db():
    conn = sqlite3.connect(DB_PATH)
    
    # Users tablosu
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        full_name TEXT,
        course_code TEXT,
        course_name TEXT,
        term TEXT,
        program_name TEXT,
        instructor TEXT,
        department TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Kullanıcı Müfredat Verileri tablosu (TYÇ, STARK, DÖÇ, PÖÇ, PEA, Bloom, Eşleşmeler)
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
        components_text TEXT,
        thresholds_met TEXT,
        thresholds_partial TEXT,
        grading_text TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    conn.commit()
    
    # Demo kullanıcı
    cur = conn.execute("SELECT password FROM users WHERE email=?", ("demo@example.com",))
    row = cur.fetchone()
    hashed_demo = hash_password("P@ssw0rd!")
    if not row:
        conn.execute("INSERT INTO users (email, password, full_name, course_code, course_name, term, program_name, instructor, department) VALUES (?,?,?,?,?,?,?,?,?)",
            ("demo@example.com", hashed_demo, "Dr. Ahmet Yilmaz", "BM203",
             "Veri Yapilari", "2024-2025 Guz", "Bilgisayar Muh.", "Dr. Ahmet Yilmaz", "Bilgisayar Muh."))
        conn.commit()
    elif row[0] == "P@ssw0rd!":
        conn.execute("UPDATE users SET password=? WHERE email=?", (hashed_demo, "demo@example.com"))
        conn.commit()
    
    conn.close()

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
    conn.execute("INSERT INTO users (email, password, full_name, course_code, course_name, term, program_name, instructor, department) VALUES (?,?,?,?,?,?,?,?,?)",
        (email, hashed, profile.get("full_name",""), profile.get("course_code",""),
         profile.get("course_name",""), profile.get("term",""), profile.get("program_name",""),
         profile.get("instructor",""), profile.get("department","")))
    conn.commit()
    conn.close()

def update_user(email: str, profile: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE users SET full_name=?, course_code=?, course_name=?, 
                    term=?, program_name=?, instructor=?, department=? WHERE email=?""",
        (profile.get("full_name",""), profile.get("course_code",""), profile.get("course_name",""),
         profile.get("term",""), profile.get("program_name",""), profile.get("instructor",""),
         profile.get("department",""), email))
    conn.commit()
    conn.close()

def update_password(email: str, new_password: str):
    conn = sqlite3.connect(DB_PATH)
    hashed = hash_password(new_password)
    conn.execute("UPDATE users SET password=? WHERE email=?", (hashed, email))
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
def save_report(user_email: str, title: str, payload: str, result: str, overall_pct: float) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO report_history (user_email, title, payload, result, overall_pct) VALUES (?,?,?,?,?)",
                       (user_email, title, payload, result, overall_pct))
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id

def get_report_history(user_email: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, title, overall_pct, created_at FROM report_history WHERE user_email=? ORDER BY created_at DESC LIMIT 50", (user_email,))
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


# Template rendering - .format() yerine string replace kullan
def _css():
    return """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --primary: #4f46e5;
  --primary-light: #6366f1;
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

input {
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
input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
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
  <title>HMKU - Giris</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>MKU</span>'">
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
      2026 HMKU Akreditasyon Sistemi
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
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HMKU - Kayit</title>
  <style>
    {_css()}
    .card {{ max-width: 700px; }}
    .steps {{ display: flex; justify-content: center; gap: 0.5rem; margin-bottom: 1.5rem; }}
    .step {{ width: 12px; height: 12px; border-radius: 50%; background: #e2e8f0; transition: all 0.3s; }}
    .step.active {{ background: #3b82f6; transform: scale(1.2); }}
    .step.done {{ background: #10b981; }}
    .step-content {{ display: none; }}
    .step-content.active {{ display: block; }}
    .step-title {{ font-size: 1rem; font-weight: 600; color: #1e293b; margin-bottom: 0.5rem; }}
    .step-desc {{ font-size: 0.8rem; color: #64748b; margin-bottom: 1rem; }}
    .btn-group {{ display: flex; gap: 0.75rem; margin-top: 1rem; }}
    .btn-secondary {{ background: #64748b; color: white; }}
    .btn-secondary:hover {{ background: #475569; }}
    textarea {{ width: 100%; min-height: 100px; padding: 0.75rem; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 0.85rem; font-family: inherit; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }}
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
  </style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>MKU</span>'">
      </div>
      <h1>Hatay Mustafa Kemal Universitesi</h1>
      <p>Akreditasyon Raporlama Sistemi</p>
    </div>
    <div class="card-body">
      <div class="welcome">
        <h2>Kayit Olun</h2>
        <p>Hesap ve müfredat bilgilerinizi girin</p>
      </div>
      
      <div class="steps">
        <div class="step active" data-step="1"></div>
        <div class="step" data-step="2"></div>
      </div>
      
      {error_block}
      <form method="POST" action="/signup" id="signupForm">
        
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
            <label>Program / Bölüm</label>
            <input type="text" name="program_name" id="programName" placeholder="Bilgisayar Mühendisliği" required>
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
        
        <!-- ADIM 2: Müfredat Çıktıları -->
        <div class="step-content" data-step="2">
          <div class="step-title">🎯 Müfredat Çıktıları</div>
          <div class="step-desc">Program ve ders çıktılarını tanımlayın (sonradan değiştirilebilir)</div>
          
          <div class="info-box">
            💡 Her satıra bir çıktı yazın. Format: <strong>KOD - Açıklama</strong><br>
            Bu bilgiler tüm raporlarınızda kullanılacak.
          </div>
          
          <div class="form-group">
            <label class="section-label">🎓 TYÇ Çıktıları (Türkiye Yeterlilikler Çerçevesi)</label>
            <textarea name="tyc_text" placeholder="TYC1 - Bilgi, Kuramsal ve uygulamalı bilgi&#10;TYC2 - Beceri, Bilişsel ve uygulamalı&#10;TYC3 - Yetkinlik, Bağımsız çalışabilme"></textarea>
            <div class="helper">Lisans için TYÇ 6. seviye yeterlilikleri</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🏢 STAR-K Çıktıları (Sektör Standartları)</label>
            <textarea name="stark_text" placeholder="ST1 - Yazılım geliştirme yetkinliği&#10;ST2 - Analitik düşünme becerisi"></textarea>
            <div class="helper">Meslek alanına özgü yeterlilikler</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📘 DÖÇ (Ders Öğrenim Çıktıları)</label>
            <textarea name="docs_text" placeholder="DÖÇ1 - Stack ve Queue yapılarını uygular&#10;DÖÇ2 - Ağaç yapılarını analiz eder&#10;DÖÇ3 - Sıralama algoritmalarını karşılaştırır"></textarea>
            <div class="helper">Dersin öğrenim çıktıları</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📗 PÖÇ (Program Öğrenim Çıktıları)</label>
            <textarea name="pocs_text" placeholder="PÖÇ1 - Mühendislik problemlerini çözer&#10;PÖÇ2 - Algoritma tasarlama becerisi&#10;PÖÇ3 - Analitik düşünme yetkinliği"></textarea>
            <div class="helper">Programın öğrenim çıktıları</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🎯 PEA (Program Eğitim Amaçları)</label>
            <textarea name="peas_text" placeholder="PEA1 - Yazılım sektöründe etkin mezunlar&#10;PEA2 - Araştırma yapabilen mezunlar"></textarea>
            <div class="helper">Mezunların 3-5 yıl sonraki hedefleri</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">📚 Müfredat Çıktıları</label>
            <textarea name="curriculum_text" placeholder="MUC1 - Temel veri yapılarını açıklar&#10;MUC2 - Algoritma karmaşıklığını analiz eder"></textarea>
            <div class="helper">Müfredat düzeyinde çıktılar</div>
          </div>
          
          <div class="form-group">
            <label class="section-label">🧠 Bloom Taksonomisi</label>
            <textarea name="bloom_text" placeholder="Bilgi - Hatırlama düzeyi&#10;Kavrama - Anlama düzeyi&#10;Uygulama - Uygulama düzeyi&#10;Analiz - Çözümleme düzeyi&#10;Sentez - Birleştirme düzeyi&#10;Değerlendirme - Yargılama düzeyi"></textarea>
            <div class="helper">Bilişsel düzeyler (varsayılan 6 seviye önerilir)</div>
          </div>
          
          <div class="btn-group">
            <button type="button" class="btn btn-secondary" onclick="prevStep(1)">← Geri</button>
            <button type="submit" class="btn btn-primary" id="submitBtn">✓ Kayit Ol</button>
          </div>
        </div>
        
      </form>
      <div class="link">
        Hesabiniz var mi? <a href="/login">Giris yapin</a>
      </div>
    </div>
    <div class="card-footer">
      2026 HMKU Akreditasyon Sistemi
    </div>
  </div>
  <script>
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
        const programName = document.getElementById('programName');
        
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
        if (programName.value.trim().length < 2) {{
          alert('Program adı girin');
          programName.focus();
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
      showStep(step);
    }}
    
    function prevStep(step) {{
      showStep(step);
    }}
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
  <title>HMKU - Sifremi Unuttum</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>MKU</span>'">
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
      2026 HMKU Akreditasyon Sistemi
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
  <title>HMKU - Yeni Sifre</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>MKU</span>'">
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
      2026 HMKU Akreditasyon Sistemi
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


def render_profile(message_block: str = "", user_data: dict = None, curriculum_data: dict = None) -> str:
    u = user_data or {}
    c = curriculum_data or {}
    
    full_name = u.get('full_name', '')
    program_name = u.get('program_name', '')
    
    tyc_text = c.get('tyc_text', '')
    stark_text = c.get('stark_text', '')
    docs_text = c.get('docs_text', '')
    pocs_text = c.get('pocs_text', '')
    peas_text = c.get('peas_text', '')
    curriculum_text = c.get('curriculum_text', '')
    bloom_text = c.get('bloom_text', '')
    
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HMKU - Profil</title>
  <style>
    {_css()}
    .card {{ max-width: 700px; }}
    textarea {{ width: 100%; min-height: 80px; padding: 0.75rem; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 0.85rem; font-family: inherit; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }}
    .section-title {{ font-weight: 600; color: #1e293b; margin: 1.5rem 0 0.75rem 0; padding-top: 1rem; border-top: 1px solid #e2e8f0; }}
    .section-title:first-of-type {{ border-top: none; margin-top: 0; padding-top: 0; }}
    .helper {{ font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <div class="logo-box">
        <img src="/assets/logo.png" alt="Logo" onerror="this.outerHTML='<span style=color:white;font-weight:700;font-size:1.2rem>MKU</span>'">
      </div>
      <h1>Profil Ayarlari</h1>
      <p>Bilgilerinizi ve müfredat verilerinizi güncelleyin</p>
    </div>
    <div class="card-body">
      {message_block}
      <form method="POST" action="/profile">
        
        <div class="section-title">👤 Kişisel Bilgiler</div>
        <div class="form-group">
          <label>Ad Soyad</label>
          <input type="text" name="full_name" value="{full_name}">
        </div>
        <div class="form-group">
          <label>Program / Bölüm</label>
          <input type="text" name="program_name" value="{program_name}">
        </div>
        
        <div class="section-title">🎯 Müfredat Çıktıları</div>
        
        <div class="form-group">
          <label>🎓 TYÇ Çıktıları</label>
          <textarea name="tyc_text" placeholder="TYC1 - Açıklama...">{tyc_text}</textarea>
          <div class="helper">Her satıra bir çıktı: KOD - Açıklama</div>
        </div>
        
        <div class="form-group">
          <label>🏢 STAR-K Çıktıları</label>
          <textarea name="stark_text" placeholder="ST1 - Açıklama...">{stark_text}</textarea>
        </div>
        
        <div class="form-group">
          <label>📘 DÖÇ (Ders Öğrenim Çıktıları)</label>
          <textarea name="docs_text" placeholder="DÖÇ1 - Açıklama...">{docs_text}</textarea>
        </div>
        
        <div class="form-group">
          <label>📗 PÖÇ (Program Öğrenim Çıktıları)</label>
          <textarea name="pocs_text" placeholder="PÖÇ1 - Açıklama...">{pocs_text}</textarea>
        </div>
        
        <div class="form-group">
          <label>🎯 PEA (Program Eğitim Amaçları)</label>
          <textarea name="peas_text" placeholder="PEA1 - Açıklama...">{peas_text}</textarea>
        </div>
        
        <div class="form-group">
          <label>📚 Müfredat Çıktıları</label>
          <textarea name="curriculum_text" placeholder="MUC1 - Açıklama...">{curriculum_text}</textarea>
        </div>
        
        <div class="form-group">
          <label>🧠 Bloom Taksonomisi</label>
          <textarea name="bloom_text" placeholder="Bilgi - Hatırlama düzeyi...">{bloom_text}</textarea>
        </div>
        
        <div style="margin-top:1.5rem;">
          <button type="submit" class="btn btn-primary">💾 Kaydet</button>
          <a href="/" class="btn btn-secondary" style="display:inline-block;text-align:center;text-decoration:none;margin-left:0.5rem;">← Ana Sayfaya Dön</a>
        </div>
      </form>
    </div>
    <div class="card-footer">
      2026 HMKU Akreditasyon Sistemi
    </div>
  </div>
</body>
</html>
"""


# Eski API uyumluluğu için sabitler (deprecated, kullanmayın)
BASE_CSS = ""
LOGIN_HTML = ""
SIGNUP_HTML = ""
FORGOT_PASSWORD_HTML = ""


# ===================== KULLANICI MÜFREDAT VERİLERİ =====================

def save_user_curriculum(email: str, data: dict):
    """Kullanıcının müfredat verilerini kaydet (TYÇ, STARK, DÖÇ, PÖÇ, PEA, Bloom, Eşleşmeler)"""
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    
    # Upsert (INSERT OR REPLACE)
    conn.execute("""
        INSERT OR REPLACE INTO user_curriculum 
        (user_email, tyc_text, stark_text, docs_text, pocs_text, peas_text, 
         curriculum_text, bloom_text, doc_tyc_map_text, poc_tyc_map_text, 
         pea_stark_map_text, poc_pea_map_text, doc_poc_weights_text,
         components_text, thresholds_met, thresholds_partial, grading_text, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email,
        data.get("tyc_text", ""),
        data.get("stark_text", ""),
        data.get("docs_text", ""),
        data.get("pocs_text", ""),
        data.get("peas_text", ""),
        data.get("curriculum_text", ""),
        data.get("bloom_text", ""),
        data.get("doc_tyc_map_text", ""),
        data.get("poc_tyc_map_text", ""),
        data.get("pea_stark_map_text", ""),
        data.get("poc_pea_map_text", ""),
        data.get("doc_poc_weights_text", ""),
        data.get("components_text", ""),
        data.get("thresholds_met", "70"),
        data.get("thresholds_partial", "50"),
        data.get("grading_text", ""),
        now
    ))
    conn.commit()
    conn.close()


def get_user_curriculum(email: str) -> dict:
    """Kullanıcının müfredat verilerini getir"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM user_curriculum WHERE user_email=?", (email,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return {}
RESET_PASSWORD_HTML = ""
PROFILE_HTML = ""


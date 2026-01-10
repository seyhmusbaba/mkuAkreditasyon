"""
AkrediX - Flask App
Şifre Hash + Taslak + Rapor Geçmişi + Şifremi Unuttum
"""
from pathlib import Path
from flask import Flask, request, send_file, Response, redirect, jsonify, make_response
import json
import urllib.parse
from uuid import uuid4
from datetime import datetime

import web_server as ws
import login as auth
from sample_payload import build_sample_payload

app = Flask(__name__)
ASSETS_DIR = Path(__file__).parent / "assets"
ACTIVE_TOKENS: set[str] = set()


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    file_path = ASSETS_DIR / filename
    if file_path.exists() and file_path.is_file():
        mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}
        return send_file(str(file_path), mimetype=mime_types.get(file_path.suffix.lower(), 'application/octet-stream'))
    return Response("Not found", status=404)


def _is_auth():
    return request.cookies.get("auth") in ACTIVE_TOKENS


def _redirect_login():
    return redirect("/login", code=302)


def _get_email() -> str:
    raw = request.cookies.get("profile")
    if raw:
        try:
            data = json.loads(urllib.parse.unquote(raw))
            return data.get("email", "")
        except:
            pass
    return ""


def _get_user_info() -> dict:
    raw = request.cookies.get("profile")
    if not raw:
        return {}
    try:
        data = json.loads(urllib.parse.unquote(raw))
        return {
            "full_name": data.get("full_name", data.get("instructor", "")),
            "course_name": data.get("course_name", ""),
            "program_name": data.get("program_name", ""),
            "role": data.get("role", "ogretim_elemani"),
        }
    except:
        return {}


def _get_profile() -> dict:
    raw = request.cookies.get("profile")
    if not raw:
        return {}
    try:
        data = json.loads(urllib.parse.unquote(raw))
        result = {}
        for k in ["course_code", "course_name", "program_name", "term"]:
            if data.get(k):
                result[k] = str(data[k])
        if data.get("full_name"):
            result["instructor"] = str(data["full_name"])
        elif data.get("instructor"):
            result["instructor"] = str(data["instructor"])
        return result
    except:
        return {}


# ============ AUTH ROUTES ============

@app.route("/login", methods=["GET", "POST"])
def login_view():
    if request.method == "GET":
        return Response(auth.render_login(""), mimetype="text/html")
    
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    user = auth.fetch_user(email)
    
    if not user:
        err = "<div class='error'>Hatali e-posta veya sifre</div>"
        return Response(auth.render_login(err), status=401, mimetype="text/html")
    
    # Hash'lenmiş şifre kontrolü
    if not auth.verify_password(password, user.get("password", "")):
        err = "<div class='error'>Hatali e-posta veya sifre</div>"
        return Response(auth.render_login(err), status=401, mimetype="text/html")
    
    token = uuid4().hex
    ACTIVE_TOKENS.add(token)
    resp = redirect("/", code=302)
    resp.set_cookie("auth", token, httponly=True, path="/")
    
    profile = {
        "email": email,
        "full_name": user.get("full_name", ""),
        "course_code": user.get("course_code", ""),
        "course_name": user.get("course_name", ""),
        "term": user.get("term", ""),
        "program_name": user.get("program_name", ""),
        "instructor": user.get("instructor", ""),
        "role": user.get("role", "ogretim_elemani"),
        "department_id": user.get("department_id", ""),
    }
    resp.set_cookie("profile", urllib.parse.quote(json.dumps(profile, ensure_ascii=False)), path="/")
    return resp


@app.route("/logout", methods=["GET"])
def logout_view():
    token = request.cookies.get("auth")
    if token:
        ACTIVE_TOKENS.discard(token)
    resp = redirect("/login", code=302)
    resp.delete_cookie("auth", path="/")
    resp.delete_cookie("profile", path="/")
    return resp


@app.route("/signup", methods=["GET", "POST"])
def signup_view():
    if request.method == "GET":
        return Response(auth.render_signup(""), mimetype="text/html")
    
    try:
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""
        
        if not email or not password:
            err = "<div class='error'>E-posta ve sifre zorunlu</div>"
            return Response(auth.render_signup(err), status=400, mimetype="text/html")
        
        if password != password_confirm:
            err = "<div class='error'>Sifreler eslesmiyor</div>"
            return Response(auth.render_signup(err), status=400, mimetype="text/html")
        
        if len(password) < 6:
            err = "<div class='error'>Sifre en az 6 karakter olmali</div>"
            return Response(auth.render_signup(err), status=400, mimetype="text/html")
        
        if auth.fetch_user(email):
            err = "<div class='error'>Bu e-posta ile kayit mevcut</div>"
            return Response(auth.render_signup(err), status=400, mimetype="text/html")
        
        profile = {
            "full_name": (request.form.get("full_name") or "").strip(),
            "role": (request.form.get("role") or "ogretim_elemani").strip(),
            "department_id": (request.form.get("department_id") or "siyaset_bilimi").strip(),
            "course_code": (request.form.get("course_code") or "").strip(),
            "course_name": (request.form.get("course_name") or "").strip(),
            "term": (request.form.get("term") or "").strip(),
            "program_name": (request.form.get("program_name") or "").strip(),
            "instructor": (request.form.get("full_name") or "").strip(),
            "department": (request.form.get("program_name") or "").strip(),
        }
        
        auth.create_user(email, password, profile)
        
        # Müfredat verilerini kaydet
        bloom_from_form = (request.form.get("bloom_text") or "").strip()
        # Boşsa varsayılan Bloom taksonomisi
        if not bloom_from_form:
            bloom_from_form = "Bilgi | Hatırlama düzeyi\nKavrama | Anlama düzeyi\nUygulama | Uygulama düzeyi\nAnaliz | Çözümleme düzeyi\nSentez | Birleştirme düzeyi\nDeğerlendirme | Yargılama düzeyi"
        
        curriculum_data = {
            "tyc_text": (request.form.get("tyc_text") or "").strip(),
            "stark_text": (request.form.get("stark_text") or "").strip(),
            "docs_text": (request.form.get("docs_text") or "").strip(),
            "pocs_text": (request.form.get("pocs_text") or "").strip(),
            "peas_text": (request.form.get("peas_text") or "").strip(),
            "curriculum_text": (request.form.get("curriculum_text") or "").strip(),
            "bloom_text": bloom_from_form,
            "doc_tyc_map_text": "",
            "poc_tyc_map_text": "",
            "pea_stark_map_text": "",
            "poc_pea_map_text": "",
            "doc_poc_weights_text": "",
            "components_text": "",
            "thresholds_met": "70",
            "thresholds_partial": "50",
            "grading_text": "",
        }
        auth.save_user_curriculum(email, curriculum_data)
        
        # ÖNEMLİ: Ders verilerini course_data tablosuna da kaydet (profil ve ana sayfa buradan okur)
        course_code = profile.get("course_code", "")
        if course_code:
            course_data_to_save = {
                "course_name": profile.get("course_name", ""),
                "tyc_text": (request.form.get("tyc_text") or "").strip(),
                "stark_text": (request.form.get("stark_text") or "").strip(),
                "bloom_text": bloom_from_form,
                "doc_text": (request.form.get("docs_text") or "").strip(),
                "poc_text": (request.form.get("pocs_text") or "").strip(),
                "pea_text": (request.form.get("peas_text") or "").strip(),
                "curriculum_text": (request.form.get("curriculum_text") or "").strip(),
                "bologna_link": "",
            }
            auth.save_course_data(course_code, course_data_to_save, email)
        
        token = uuid4().hex
        ACTIVE_TOKENS.add(token)
        resp = redirect("/", code=302)
        resp.set_cookie("auth", token, httponly=True, path="/")
        profile["email"] = email
        resp.set_cookie("profile", urllib.parse.quote(json.dumps(profile, ensure_ascii=False)), path="/")
        return resp
    except Exception as e:
        err = f"<div class='error'>Kayit hatasi: {str(e)}</div>"
        return Response(auth.render_signup(err), status=500, mimetype="text/html")


# ============ ŞİFREMİ UNUTTUM ============

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_view():
    if request.method == "GET":
        return Response(auth.render_forgot_password(""), mimetype="text/html")
    
    email = (request.form.get("email") or "").strip().lower()
    user = auth.fetch_user(email)
    
    if user:
        token = auth.create_reset_token(email)
        # Gerçek uygulamada e-posta gönderilir, demo için linki gösteriyoruz
        msg = f"<div class='success'>Sifirlama linki: <a href='/reset-password/{token}'>/reset-password/{token}</a></div>"
    else:
        # Güvenlik için kullanıcı yoksa bile aynı mesajı göster
        msg = "<div class='info'>Eger bu e-posta kayitliysa, sifirlama linki gonderildi.</div>"
    
    return Response(auth.render_forgot_password(msg), mimetype="text/html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_view(token):
    email = auth.verify_reset_token(token)
    
    if not email:
        msg = "<div class='error'>Gecersiz veya suresi dolmus link</div>"
        return Response(auth.render_forgot_password(msg), mimetype="text/html")
    
    if request.method == "GET":
        html = auth.render_reset_password(token, "")
        return Response(html, mimetype="text/html")
    
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""
    
    if len(password) < 6:
        msg = "<div class='error'>Sifre en az 6 karakter olmali</div>"
        return Response(auth.render_reset_password(token, msg), mimetype="text/html")
    
    if password != password_confirm:
        msg = "<div class='error'>Sifreler eslesmiyor</div>"
        return Response(auth.render_reset_password(token, msg), mimetype="text/html")
    
    auth.update_password(email, password)
    auth.delete_reset_token(email)
    
    msg = "<div class='success'>Sifreniz degistirildi. <a href='/login'>Giris yapin</a></div>"
    return Response(auth.render_forgot_password(msg), mimetype="text/html")


# ============ PROFILE ============

@app.route("/profile", methods=["GET"])
def profile_view():
    if not _is_auth():
        return _redirect_login()
    
    email = _get_email()
    if not email:
        email = "demo@example.com"
    
    user = auth.fetch_user(email) or {}
    
    # Flash message kontrolü
    success_msg = request.args.get("saved", "")
    message_block = ""
    if success_msg == "1":
        message_block = "<div class='alert alert-success'>✓ Değişiklikler kaydedildi!</div>"
    
    # Query string'den ders kodu al (admin için)
    course_code_param = request.args.get("course", "")
    if course_code_param and user.get('role') in ['admin', 'dekan', 'bolum_baskani']:
        # Geçici olarak user'ın course_code'unu değiştir (sadece görüntüleme için)
        user = dict(user)
        user['course_code'] = course_code_param
        course_data = auth.get_course_data(course_code_param)
        if course_data:
            user['course_name'] = course_data.get('course_name', '')
    
    html = auth.render_profile(user, message_block)
    return Response(html, mimetype="text/html")


@app.route("/profile/course-data", methods=["POST"])
def profile_save_course_data():
    """Ders verilerini kaydet - TYÇ/STARK/Bloom/DÖÇ/Müfredat herkes, PÖÇ/PEA sadece Dekan/BB/Admin"""
    import sys
    
    if not _is_auth():
        return _redirect_login()
    
    email = _get_email()
    user = auth.fetch_user(email) or {}
    role = user.get('role', 'ogretim_elemani')
    
    course_code = request.form.get("course_code", "")
    print(f"[profile/course-data] email: {email}, course_code: {course_code}", file=sys.stderr)
    
    if not course_code:
        return redirect("/profile")
    
    # Mevcut verileri al
    existing = auth.get_course_data(course_code) or {}
    
    # Admin/Dekan/BB program düzeyindeki verileri de değiştirebilir (PÖÇ, PEA)
    can_edit_program = role in ['admin', 'dekan', 'bolum_baskani']
    
    # Herkes değiştirebilir: TYÇ, STARK, Bloom, DÖÇ, Müfredat
    data = {
        "course_name": existing.get('course_name', ''),
        "tyc_text": request.form.get("tyc_text", ""),
        "bloom_text": request.form.get("bloom_text", ""),
        "stark_text": request.form.get("stark_text", ""),
        "doc_text": request.form.get("doc_text", ""),
        "curriculum_text": request.form.get("curriculum_text", ""),
        "bologna_link": existing.get('bologna_link', ''),
    }
    
    print(f"[profile/course-data] tyc_text length: {len(data['tyc_text'])}", file=sys.stderr)
    print(f"[profile/course-data] doc_text length: {len(data['doc_text'])}", file=sys.stderr)
    
    # PÖÇ ve PEA sadece yöneticiler değiştirebilir
    if can_edit_program:
        data["pea_text"] = request.form.get("pea_text", "")
        data["poc_text"] = request.form.get("poc_text", "")
    else:
        data["pea_text"] = existing.get('pea_text', '')
        data["poc_text"] = existing.get('poc_text', '')
    
    auth.save_course_data(course_code, data, email)
    print(f"[profile/course-data] course_data kaydedildi", file=sys.stderr)
    
    # Doğrulama: Kaydedilen veriyi tekrar oku
    verify = auth.get_course_data(course_code)
    print(f"[profile/course-data] Doğrulama - tyc_text length: {len(verify.get('tyc_text', '')) if verify else 0}", file=sys.stderr)
    
    # Kullanıcının aktif dersini de güncelle (user tablosunda)
    auth.update_user_course(email, course_code, existing.get('course_name', ''))
    print(f"[profile/course-data] user tablosu güncellendi", file=sys.stderr)
    
    # Cookie'yi güncelle - ana sayfanın doğru ders kodunu okuması için
    course_name = existing.get('course_name', '')
    profile_data = {
        "email": email,
        "full_name": user.get('full_name', ''),
        "role": role,
        "course_code": course_code,
        "course_name": course_name,
        "program_name": user.get('program_name', ''),
        "term": user.get('term', ''),
        "instructor": user.get('instructor', ''),
    }
    
    resp = make_response(redirect(f"/profile?course={course_code}&saved=1"))
    resp.set_cookie("profile", urllib.parse.quote(json.dumps(profile_data)), 
                  max_age=86400*30, httponly=False, samesite='Lax')
    return resp


@app.route("/api/course-data/<course_code>", methods=["GET"])
def api_get_course_data(course_code):
    """Ders verilerini API olarak getir"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    user_info = _get_user_info()
    role = user_info.get('role', '')
    user_course_code = user_info.get('course_code', '')
    
    # Admin, Dekan, BB her derse erişebilir
    # Öğretim elemanı: yetkili olduğu dersler + kendi ana dersi
    if role not in ['admin', 'dekan', 'bolum_baskani']:
        has_access = auth.user_has_course_access(email, course_code)
        is_own_course = (course_code == user_course_code)
        if not has_access and not is_own_course:
            return jsonify({"error": "Bu derse erişim yetkiniz yok", "success": False}), 403
    
    data = auth.get_course_data(course_code)
    if data:
        # Frontend'in beklediği format: doğrudan alanlar
        return jsonify({
            "success": True,
            "tyc_text": data.get('tyc_text', ''),
            "bloom_text": data.get('bloom_text', ''),
            "stark_text": data.get('stark_text', ''),
            "pea_text": data.get('pea_text', ''),
            "poc_text": data.get('poc_text', ''),
            "doc_text": data.get('doc_text', ''),
            "curriculum_text": data.get('curriculum_text', ''),
            "bologna_link": data.get('bologna_link', ''),
            "course_name": data.get('course_name', ''),
        })
    return jsonify({"success": False, "error": "Ders bulunamadı"}), 404


@app.route("/api/switch-course", methods=["POST"])
def api_switch_course():
    """Kullanıcının aktif dersini değiştir"""
    import sys
    
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    user_info = _get_user_info()
    role = user_info.get('role', '')
    
    print(f"[api/switch-course] email: {email}, role: {role}", file=sys.stderr)
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        new_course_code = data.get('course_code', '').strip()
        
        print(f"[api/switch-course] new_course_code: {new_course_code}", file=sys.stderr)
        
        if not new_course_code:
            return jsonify({"error": "Ders kodu gerekli", "success": False}), 400
        
        # Yetki kontrolü: Admin/Dekan/BB her derse, öğretim elemanı yetkili olduğu derse
        if role not in ['admin', 'dekan', 'bolum_baskani']:
            has_access = auth.user_has_course_access(email, new_course_code)
            current_course = user_info.get('course_code', '')
            if not has_access and new_course_code != current_course:
                return jsonify({"error": "Bu derse erişim yetkiniz yok", "success": False}), 403
        
        # Kullanıcının aktif dersini güncelle
        course_data = auth.get_course_data(new_course_code)
        course_name = course_data.get('course_name', '') if course_data else ''
        
        print(f"[api/switch-course] course_data bulundu: {bool(course_data)}, course_name: {course_name}", file=sys.stderr)
        
        auth.update_user_course(email, new_course_code, course_name)
        print(f"[api/switch-course] user tablosu güncellendi", file=sys.stderr)
        
        # Yeni profile cookie oluştur
        user = auth.fetch_user(email)
        print(f"[api/switch-course] Güncel user.course_code: {user.get('course_code') if user else 'None'}", file=sys.stderr)
        
        if user:
            profile_data = {
                "email": email,
                "full_name": user.get('full_name', ''),
                "role": user.get('role', ''),
                "course_code": new_course_code,
                "course_name": course_name,
                "program_name": user.get('program_name', ''),
                "term": user.get('term', ''),
                "instructor": user.get('instructor', ''),
            }
            
            resp = make_response(jsonify({"success": True, "course_code": new_course_code, "course_name": course_name}))
            resp.set_cookie("profile", urllib.parse.quote(json.dumps(profile_data)), 
                          max_age=86400*30, httponly=False, samesite='Lax')
            return resp
        
        return jsonify({"success": True, "course_code": new_course_code})
    except Exception as e:
        print(f"[api/switch-course] HATA: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/api/fetch-bologna/<course_code>", methods=["GET"])
def api_fetch_bologna(course_code):
    """Bologna'dan DÖÇ ve Müfredat çek"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    # Ders bilgilerini al
    course_data = auth.get_course_data(course_code)
    if not course_data:
        return jsonify({"success": False, "error": "Ders bulunamadı"})
    
    bologna_link = course_data.get('bologna_link', '')
    if not bologna_link:
        return jsonify({"success": False, "error": "Bologna linki tanımlanmamış"})
    
    # Bologna'dan veri çek
    result = auth.fetch_bologna_data(bologna_link)
    result['success'] = bool(result.get('doc_text') or result.get('curriculum_text'))
    
    return jsonify(result)


@app.route("/api/fetch-bologna-signup/<course_code>", methods=["GET"])
def api_fetch_bologna_signup(course_code):
    """Kayıt sırasında Bologna'dan DÖÇ ve Müfredat çek (auth gerektirmez)"""
    # Ders bilgilerini al
    course_data = auth.get_course_data(course_code)
    if not course_data:
        return jsonify({"success": False, "error": "Ders bulunamadı"})
    
    bologna_link = course_data.get('bologna_link', '')
    if not bologna_link:
        return jsonify({"success": False, "error": "Bu ders için Bologna linki tanımlanmamış"})
    
    # Bologna'dan veri çek
    result = auth.fetch_bologna_data(bologna_link)
    result['success'] = bool(result.get('doc_text') or result.get('curriculum_text'))
    
    return jsonify(result)


# ============ ADMIN PANELİ ============

def _get_user_role() -> str:
    """Cookie'den kullanıcı rolünü al"""
    raw = request.cookies.get("profile")
    if raw:
        try:
            data = json.loads(urllib.parse.unquote(raw))
            return data.get("role", "ogretim_elemani")
        except:
            pass
    return "ogretim_elemani"

def _is_admin() -> bool:
    return _get_user_role() == "admin"

def _can_manage_users() -> bool:
    """Admin, Dekan veya Bölüm Başkanı kullanıcı yönetebilir"""
    return _get_user_role() in ["admin", "dekan", "bolum_baskani"]


@app.route("/admin", methods=["GET"])
def admin_panel():
    if not _is_auth():
        return _redirect_login()
    
    # Admin, Dekan ve Bölüm Başkanı erişebilir
    if not _can_manage_users():
        return Response("<h1>Yetkisiz Erişim</h1><p>Bu sayfaya erişim yetkiniz yok.</p><a href='/'>Ana Sayfaya Dön</a>", 
                       status=403, mimetype="text/html")
    
    email = _get_email()
    user = auth.fetch_user(email)
    html = auth.render_admin_panel("", user)
    return Response(html, mimetype="text/html")


@app.route("/admin/role", methods=["POST"])
def admin_update_role():
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    email = request.form.get("email", "")
    new_role = request.form.get("role", "ogretim_elemani")
    
    if new_role not in auth.ROLES:
        return jsonify({"error": "Geçersiz rol"}), 400
    
    auth.update_user_role(email, new_role)
    return jsonify({"success": True})


@app.route("/admin/department", methods=["POST"])
def admin_update_department():
    if not _is_auth() or not _can_manage_users():
        return _redirect_login()
    
    department_id = request.form.get("department_id", "siyaset_bilimi")
    data = {
        "peas_text": request.form.get("peas_text", ""),
        "pocs_text": request.form.get("pocs_text", ""),
    }
    
    email = _get_email()
    auth.save_department_data(department_id, data, email)
    
    msg = "<div class='alert alert-success'>✓ Bölüm verileri güncellendi!</div>"
    user = auth.fetch_user(email)
    html = auth.render_admin_panel(msg, user)
    return Response(html, mimetype="text/html")


@app.route("/admin/delete-user", methods=["POST"])
def admin_delete_user():
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    email = request.form.get("email", "")
    current_email = _get_email()
    
    # Admin kendini silemesin
    if email == current_email:
        return jsonify({"error": "Kendinizi silemezsiniz"}), 400
    
    # Admin kullanıcısını silemesin
    if email == "admin@mku.edu.tr":
        return jsonify({"error": "Ana admin silinemez"}), 400
    
    auth.delete_user(email)
    return jsonify({"success": True})


@app.route("/admin/add-user", methods=["POST"])
def admin_add_user():
    """Yeni kullanıcı ekle"""
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "ogretim_elemani")
    
    if not email or not password:
        return jsonify({"error": "E-posta ve şifre zorunlu"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
    
    if auth.fetch_user(email):
        return jsonify({"error": "Bu e-posta ile kayıtlı kullanıcı var"}), 400
    
    if role not in auth.ROLES:
        return jsonify({"error": "Geçersiz rol"}), 400
    
    success = auth.add_user(email, password, full_name, role)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Kullanıcı eklenemedi"}), 500


@app.route("/admin/update-link", methods=["POST"])
def admin_update_link():
    """Ders Bologna linkini güncelle"""
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    course_code = request.form.get("course_code", "")
    bologna_link = request.form.get("bologna_link", "")
    
    if not course_code:
        return jsonify({"error": "Ders kodu zorunlu"}), 400
    
    email = _get_email()
    auth.update_course_bologna_link(course_code, bologna_link, email)
    
    return jsonify({"success": True})


@app.route("/admin/add-department", methods=["POST"])
def admin_add_department():
    """Yeni bölüm ekle"""
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    dept_id = request.form.get("dept_id", "").strip().lower().replace(" ", "_")
    dept_name = request.form.get("dept_name", "").strip()
    dept_faculty = request.form.get("dept_faculty", "").strip()
    bologna_courses_url = request.form.get("bologna_courses_url", "").strip()
    bologna_pea_url = request.form.get("bologna_pea_url", "").strip()
    bologna_poc_url = request.form.get("bologna_poc_url", "").strip()
    
    if not dept_id or not dept_name:
        return jsonify({"error": "Bölüm ID ve adı zorunlu"}), 400
    
    email = _get_email()
    success = auth.add_department(dept_id, dept_name, dept_faculty, bologna_courses_url, bologna_pea_url, bologna_poc_url, email)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Bu ID ile bölüm zaten mevcut"}), 400


@app.route("/admin/fetch-pea-poc/<dept_id>", methods=["GET"])
def admin_fetch_pea_poc(dept_id):
    """Bologna'dan PEA ve PÖÇ çek"""
    if not _is_auth() or not _is_admin():
        return jsonify({"error": "Yetkisiz"}), 403
    
    # Bölüm bilgilerini al
    dept = auth.get_department(dept_id)
    if not dept:
        return jsonify({"success": False, "error": "Bölüm bulunamadı"})
    
    pea_url = dept.get('bologna_pea_url', '')
    poc_url = dept.get('bologna_poc_url', '')
    
    pea_text = ""
    poc_text = ""
    
    # PEA çek
    if pea_url:
        result = auth.fetch_pea_from_bologna(pea_url)
        pea_text = result.get('pea_text', '')
    
    # PÖÇ çek
    if poc_url:
        result = auth.fetch_poc_from_bologna(poc_url)
        poc_text = result.get('poc_text', '')
    
    return jsonify({
        "success": bool(pea_text or poc_text),
        "pea_text": pea_text,
        "poc_text": poc_text
    })


# ============ KULLANICI-DERS YÖNETİMİ ============

@app.route("/api/user-courses", methods=["GET"])
def api_get_user_courses():
    """Kullanıcının yetkili olduğu dersleri getir"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    courses = auth.get_user_courses(email)
    return jsonify({"courses": courses})


@app.route("/api/user-courses/<target_email>", methods=["GET"])
def api_get_user_courses_admin(target_email):
    """Belirli kullanıcının derslerini getir (admin/dekan/bb için)"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    user_info = _get_user_info()
    role = user_info.get('role', '')
    
    # Admin, Dekan veya Bölüm Başkanı olmalı
    if role not in ['admin', 'dekan', 'bolum_baskani']:
        return jsonify({"error": "Yetkisiz"}), 403
    
    courses = auth.get_user_courses(target_email)
    return jsonify({"courses": courses})


@app.route("/api/assign-course", methods=["POST"])
def api_assign_course():
    """Kullanıcıya ders yetkisi ekle"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    user_info = _get_user_info()
    role = user_info.get('role', '')
    
    # Admin, Dekan veya Bölüm Başkanı olmalı
    if role not in ['admin', 'dekan', 'bolum_baskani']:
        return jsonify({"error": "Yetkisiz"}), 403
    
    try:
        # JSON veya form data'yı al
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
        else:
            data = request.form.to_dict()
        
        target_email = data.get("email", "").strip()
        course_code = data.get("course_code", "").strip()
        
        if not target_email or not course_code:
            return jsonify({"error": "Email ve ders kodu zorunlu", "received": data}), 400
        
        assigned_by = _get_email()
        success = auth.add_user_course(target_email, course_code, assigned_by)
        
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove-course", methods=["POST"])
def api_remove_course():
    """Kullanıcıdan ders yetkisini kaldır"""
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    user_info = _get_user_info()
    role = user_info.get('role', '')
    
    # Admin, Dekan veya Bölüm Başkanı olmalı
    if role not in ['admin', 'dekan', 'bolum_baskani']:
        return jsonify({"error": "Yetkisiz"}), 403
    
    try:
        # JSON veya form data'yı al
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
        else:
            data = request.form.to_dict()
        
        target_email = data.get("email", "").strip()
        course_code = data.get("course_code", "").strip()
        
        if not target_email or not course_code:
            return jsonify({"error": "Email ve ders kodu zorunlu"}), 400
        
        success = auth.remove_user_course(target_email, course_code)
        
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ TASLAK YÖNETİMİ ============

@app.route("/api/drafts", methods=["GET"])
def get_drafts():
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    drafts = auth.get_drafts(email)
    return jsonify({"drafts": drafts})


@app.route("/api/drafts", methods=["POST"])
def save_draft():
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    data = request.get_json()
    name = data.get("name", f"Taslak {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    form_data = json.dumps(data.get("data", {}), ensure_ascii=False)
    
    draft_id = auth.save_draft(email, name, form_data)
    return jsonify({"success": True, "id": draft_id})


@app.route("/api/drafts/<int:draft_id>", methods=["GET"])
def get_draft(draft_id):
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    draft = auth.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Not found"}), 404
    
    return jsonify({"draft": draft, "data": json.loads(draft.get("data", "{}"))})


@app.route("/api/drafts/<int:draft_id>", methods=["PUT"])
def update_draft(draft_id):
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    form_data = json.dumps(data.get("data", {}), ensure_ascii=False)
    auth.update_draft(draft_id, form_data)
    return jsonify({"success": True})


@app.route("/api/drafts/<int:draft_id>", methods=["DELETE"])
def delete_draft(draft_id):
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    auth.delete_draft(draft_id)
    return jsonify({"success": True})


# ============ AUTO-SAVE ============

@app.route("/api/autosave", methods=["POST"])
def autosave():
    import sys
    
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    data = request.get_json()
    
    print(f"[autosave] email: {email}", file=sys.stderr, flush=True)
    
    if not data:
        return jsonify({"error": "No data"}), 400
    
    # user_curriculum tablosuna kaydet - böylece sayfa yenilendiğinde veriler korunur
    curriculum_data = {
        "doc_tyc_map_text": data.get("doc_tyc_map_text", ""),
        "poc_tyc_map_text": data.get("poc_tyc_map_text", ""),
        "pea_stark_map_text": data.get("pea_stark_map_text", ""),
        "poc_pea_map_text": data.get("poc_pea_map_text", ""),
        "doc_poc_weights_text": data.get("doc_poc_weights_text", ""),
        "curriculum_doc_map_text": data.get("curriculum_doc_map_text", ""),
        "doc_stark_map_text": data.get("doc_stark_map_text", ""),
        "doc_pea_map_text": data.get("doc_pea_map_text", ""),
        "curriculum_tyc_map_text": data.get("curriculum_tyc_map_text", ""),
        "curriculum_stark_map_text": data.get("curriculum_stark_map_text", ""),
        "curriculum_poc_map_text": data.get("curriculum_poc_map_text", ""),
        "curriculum_pea_map_text": data.get("curriculum_pea_map_text", ""),
        "components_text": data.get("assessments_text", ""),
        "grading_text": data.get("grading_text", ""),
        "question_map_text": data.get("question_map_text", ""),
        "thresholds_met": data.get("thresholds_met", "70"),
        "thresholds_partial": data.get("thresholds_partial", "50"),
    }
    
    # Boş olmayan alanları kaydet
    has_data = any(v for v in curriculum_data.values() if v and str(v).strip())
    
    if has_data:
        auth.save_user_curriculum(email, curriculum_data)
        print(f"[autosave] user_curriculum kaydedildi", file=sys.stderr, flush=True)
    
    # Taslak olarak da kaydet (eski davranış)
    form_data = json.dumps(data, ensure_ascii=False)
    drafts = auth.get_drafts(email)
    auto_draft = next((d for d in drafts if d["name"] == "Otomatik Kayit"), None)
    
    if auto_draft:
        auth.update_draft(auto_draft["id"], form_data)
        return jsonify({"success": True, "id": auto_draft["id"], "updated": True})
    else:
        draft_id = auth.save_draft(email, "Otomatik Kayit", form_data)
        return jsonify({"success": True, "id": draft_id, "created": True})


# ============ RAPOR GEÇMİŞİ ============

@app.route("/api/reports", methods=["GET"])
def get_reports():
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    reports = auth.get_report_history(email)
    return jsonify({"reports": reports})


@app.route("/api/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    report = auth.get_report(report_id)
    if not report:
        return jsonify({"error": "Not found"}), 404
    
    return jsonify({
        "report": report,
        "payload": json.loads(report.get("payload", "{}")),
        "result": json.loads(report.get("result", "{}"))
    })


@app.route("/api/reports/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    auth.delete_report(report_id)
    return jsonify({"success": True})


@app.route("/api/student-report/<student_id>", methods=["GET"])
def get_student_report(student_id):
    """Öğrenciye özel bireysel rapor API'si"""
    if not _is_auth():
        return jsonify({"error": "Oturum açmanız gerekiyor"}), 401
    
    # Son hesaplama sonucunu al
    result = ws.STATE.get("last_result")
    if not result:
        return jsonify({"error": "Önce hesaplama yapın"})
    
    try:
        html = generate_student_report_html(student_id, result)
        return jsonify({"html": html})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()})


def generate_student_report_html(student_id: str, result: dict) -> str:
    """Öğrenciye özel kapsamlı başarı raporu - Geliştirilmiş Tasarım."""
    from datetime import datetime
    
    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    def get_color(pct):
        if pct >= 70: return "#10b981"
        if pct >= 50: return "#f59e0b"
        return "#ef4444"
    
    def get_bg(pct):
        if pct >= 70: return "#ecfdf5"
        if pct >= 50: return "#fffbeb"
        return "#fef2f2"
    
    def badge(pct):
        if pct >= 70: return '<span class="sr-badge success">✓ Başarılı</span>'
        if pct >= 50: return '<span class="sr-badge warning">△ Kısmen</span>'
        return '<span class="sr-badge danger">✗ Yetersiz</span>'
    
    # ========== VERİLERİ AL ==========
    computed = result.get("computed", {})
    students_data = result.get("students_data", [])
    questions = result.get("input_questions", [])
    scores = result.get("scores", {})
    docs_stats = computed.get("docs", {})
    pocs_stats = computed.get("pocs", {})
    peas_stats = computed.get("peas", {})
    bloom_stats = computed.get("bloom", {})
    course = result.get("course", {})
    assessments = result.get("input_assessments", [])
    tyc_list = result.get("tyc", [])
    stark_list = result.get("stark", [])
    doc_tyc_map = result.get("doc_tyc_map", {})
    pea_stark_map = result.get("pea_stark_map", {})
    question_outcomes = result.get("question_outcomes", {}).get("per_question", {})
    
    # ========== ÖĞRENCİ BUL ==========
    student_info = None
    sid_clean = str(student_id).strip()
    for s in students_data:
        if str(s.get("id", "")).strip() == sid_clean:
            student_info = s
            break
    
    if not student_info:
        ids = [str(s.get("id", "?"))[:15] for s in students_data[:8]]
        return f'''<div style="padding:2rem;text-align:center;">
            <div style="font-size:3rem;margin-bottom:1rem;">🔍</div>
            <h3 style="color:#ef4444;margin:0 0 1rem 0;">Öğrenci Bulunamadı</h3>
            <p style="color:#64748b;">Aranan: <code>{esc(student_id)}</code></p>
            <p style="font-size:0.8rem;color:#94a3b8;">Mevcut: {", ".join(ids)}...</p>
        </div>'''
    
    # ========== ÖĞRENCİ VERİLERİ ==========
    s_name = student_info.get("name", student_id)
    s_pct = float(student_info.get("pct", 0))
    s_grade = student_info.get("grade", "FF")
    is_absent = student_info.get("is_absent", False)
    
    # Scores'dan öğrenci puanlarını al - farklı key formatlarını dene
    s_scores = scores.get(student_id, {})
    if not s_scores:
        s_scores = scores.get(sid_clean, {})
    if not s_scores:
        # Tüm key'leri dene
        for k in scores.keys():
            k_clean = str(k).strip()
            if k_clean == sid_clean:
                s_scores = scores[k]
                break
            # S prefix kontrolü
            if k_clean.startswith("S") and k_clean[1:] == sid_clean:
                s_scores = scores[k]
                break
            if sid_clean.startswith("S") and sid_clean[1:] == k_clean:
                s_scores = scores[k]
                break
    
    # ========== GR KONTROLÜ ==========
    if is_absent:
        return f'''
        <div class="sr-absent-card">
            <div class="sr-absent-icon">🚫</div>
            <h2>SINAVA GİRMEDİ</h2>
            <div class="sr-absent-name">{esc(s_name)}</div>
            <div class="sr-absent-id">{esc(student_id)}</div>
            <p>Bu öğrenci sınava girmemiştir.<br>Performans analizi yapılamaz.</p>
        </div>
        <style>
        .sr-absent-card{{background:linear-gradient(135deg,#475569,#64748b);color:white;padding:3rem 2rem;border-radius:20px;text-align:center;}}
        .sr-absent-icon{{font-size:4rem;margin-bottom:1rem;filter:grayscale(1);}}
        .sr-absent-card h2{{margin:0 0 1.5rem 0;font-size:1.4rem;letter-spacing:1px;}}
        .sr-absent-name{{font-size:1.3rem;font-weight:600;}}
        .sr-absent-id{{font-size:0.9rem;opacity:0.7;margin:0.5rem 0 1.5rem 0;}}
        .sr-absent-card p{{margin:0;opacity:0.8;line-height:1.7;}}
        </style>'''
    
    # ========== SINIF İSTATİSTİKLERİ ==========
    attending = [x for x in students_data if not x.get('is_absent')]
    all_pcts = sorted([float(x.get("pct", 0)) for x in attending], reverse=True)
    total_students = len(all_pcts) or 1
    
    # Sıralama bul
    rank = 1
    for i, p in enumerate(all_pcts):
        if abs(p - s_pct) < 0.01:
            rank = i + 1
            break
    
    percentile = 100 - (rank / total_students * 100)
    class_avg = float(computed.get("overall", {}).get("success_pct", 0))
    diff = s_pct - class_avg
    
    # Toplam puan
    total_got = 0
    total_max = 0
    for q in questions:
        qid = q.get("id", "")
        got = float(s_scores.get(qid, 0))
        maxp = float(q.get("max_points", 0))
        total_got += got
        total_max += maxp
    total_max = total_max or 1
    
    # Başarılı soru
    success_q = sum(1 for q in questions if float(s_scores.get(q.get("id",""), 0)) >= float(q.get("max_points", 1)) * 0.6)
    
    # ========== PERFORMANS HESAPLAMALARI ==========
    # DÖÇ
    doc_perf = {}
    for q in questions:
        qid = q.get("id", "")
        doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
        maxp = float(q.get("max_points", 0))
        got = float(s_scores.get(qid, 0))
        n = len(doc_ids) or 1
        for d in doc_ids:
            if d:
                doc_perf.setdefault(d, {"got": 0, "max": 0})
                doc_perf[d]["got"] += got / n
                doc_perf[d]["max"] += maxp / n
    
    # PÖÇ
    poc_perf = {}
    for q in questions:
        qid = q.get("id", "")
        pocs = q.get("poc_list", [])
        maxp = float(q.get("max_points", 0))
        got = float(s_scores.get(qid, 0))
        n = len(pocs) or 1
        for p in pocs:
            if p:
                poc_perf.setdefault(p, {"got": 0, "max": 0})
                poc_perf[p]["got"] += got / n
                poc_perf[p]["max"] += maxp / n
    
    # PEA
    pea_perf = {}
    for q in questions:
        qid = q.get("id", "")
        peas = q.get("pea_list", [])
        maxp = float(q.get("max_points", 0))
        got = float(s_scores.get(qid, 0))
        n = len(peas) or 1
        for a in peas:
            if a:
                pea_perf.setdefault(a, {"got": 0, "max": 0})
                pea_perf[a]["got"] += got / n
                pea_perf[a]["max"] += maxp / n
    
    # Bloom
    bloom_perf = {}
    for q in questions:
        qid = q.get("id", "")
        blooms = q.get("bloom_list") or ([q.get("bloom")] if q.get("bloom") else [])
        maxp = float(q.get("max_points", 0))
        got = float(s_scores.get(qid, 0))
        n = len(blooms) or 1
        for b in blooms:
            if b:
                bloom_perf.setdefault(b, {"got": 0, "max": 0})
                bloom_perf[b]["got"] += got / n
                bloom_perf[b]["max"] += maxp / n
    
    # TYÇ (DÖÇ üzerinden)
    tyc_perf = {}
    for d, p in doc_perf.items():
        for t in doc_tyc_map.get(d, []):
            tyc_perf.setdefault(t, {"got": 0, "max": 0})
            tyc_perf[t]["got"] += p["got"]
            tyc_perf[t]["max"] += p["max"]
    
    # STAR-K (PEA üzerinden)
    stark_perf = {}
    for a, p in pea_perf.items():
        for s in pea_stark_map.get(a, []):
            stark_perf.setdefault(s, {"got": 0, "max": 0})
            stark_perf[s]["got"] += p["got"]
            stark_perf[s]["max"] += p["max"]
    
    # Bileşen (Vize, Final)
    comp_perf = {}
    for q in questions:
        qid = q.get("id", "")
        cid = q.get("component_id", "")
        maxp = float(q.get("max_points", 0))
        got = float(s_scores.get(qid, 0))
        if cid:
            comp_perf.setdefault(cid, {"got": 0, "max": 0, "name": cid})
            comp_perf[cid]["got"] += got
            comp_perf[cid]["max"] += maxp
    for a in (assessments or []):
        aid = a.get("id", "")
        if aid in comp_perf:
            comp_perf[aid]["name"] = a.get("name", aid)
    
    # Güçlü/Zayıf
    strong = [(d, (p["got"]/p["max"]*100) if p["max"] else 0) for d, p in doc_perf.items() if p["max"] and (p["got"]/p["max"]*100) >= 70]
    weak = [(d, (p["got"]/p["max"]*100) if p["max"] else 0) for d, p in doc_perf.items() if p["max"] and (p["got"]/p["max"]*100) < 50]
    strong.sort(key=lambda x: -x[1])
    weak.sort(key=lambda x: x[1])
    
    # Renkler
    main_clr = get_color(s_pct)
    grade_clr = "#10b981" if s_grade in ["AA","BA","BB"] else "#f59e0b" if s_grade in ["CB","CC","DC","DD"] else "#ef4444"
    
    # ========== CSS ==========
    css = '''<style>
    .sr{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1e293b;line-height:1.6;}
    .sr-header{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#1d4ed8 100%);color:white;padding:1.75rem;border-radius:16px;margin-bottom:1.25rem;position:relative;overflow:hidden;}
    .sr-header::after{content:'';position:absolute;top:-30%;right:-10%;width:50%;height:160%;background:radial-gradient(circle,rgba(255,255,255,0.08) 0%,transparent 70%);pointer-events:none;}
    .sr-header h2{margin:0;font-size:1.25rem;font-weight:700;display:flex;align-items:center;gap:0.5rem;}
    .sr-header-sub{opacity:0.85;font-size:0.9rem;margin-top:0.25rem;}
    .sr-header-meta{display:flex;flex-wrap:wrap;gap:1.5rem;margin-top:1rem;font-size:0.82rem;}
    .sr-header-meta span{display:flex;align-items:center;gap:0.35rem;}
    
    .sr-stats{display:grid;grid-template-columns:repeat(6,1fr);gap:0.6rem;margin-bottom:1.25rem;}
    .sr-stat{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:1rem 0.5rem;text-align:center;transition:all 0.2s;}
    .sr-stat:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.08);}
    .sr-stat.primary{border-width:2px;}
    .sr-stat-val{font-size:1.5rem;font-weight:800;line-height:1.1;}
    .sr-stat-label{font-size:0.6rem;color:#64748b;margin-top:0.3rem;text-transform:uppercase;letter-spacing:0.5px;}
    .sr-stat-sub{font-size:0.7rem;color:#94a3b8;}
    
    .sr-compare{display:flex;align-items:center;gap:1rem;padding:1rem 1.25rem;border-radius:12px;margin-bottom:1.25rem;border-left:4px solid;}
    .sr-compare-icon{font-size:1.75rem;}
    .sr-compare-text{flex:1;font-size:0.9rem;}
    
    .sr-section{margin-bottom:1.25rem;}
    .sr-section-title{font-size:0.85rem;font-weight:700;color:#0f172a;margin-bottom:0.6rem;padding-bottom:0.4rem;border-bottom:3px solid;display:flex;align-items:center;gap:0.4rem;}
    
    .sr-chips{display:flex;flex-wrap:wrap;gap:0.5rem;}
    .sr-chip{display:inline-flex;align-items:center;gap:0.5rem;padding:0.6rem 1rem;border-radius:10px;font-size:0.8rem;border:1px solid #e2e8f0;background:white;}
    .sr-chip-label{color:#64748b;font-size:0.7rem;}
    .sr-chip-val{font-weight:700;font-size:1rem;}
    .sr-chip-sub{font-size:0.65rem;color:#94a3b8;}
    
    .sr-table{width:100%;border-collapse:separate;border-spacing:0;font-size:0.78rem;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;}
    .sr-table th{background:#f8fafc;padding:0.65rem 0.5rem;text-align:left;font-weight:600;color:#475569;font-size:0.72rem;}
    .sr-table td{padding:0.6rem 0.5rem;border-top:1px solid #f1f5f9;}
    .sr-table tr:hover td{background:#fafafa;}
    .sr-table .center{text-align:center;}
    .sr-table .bold{font-weight:700;}
    
    .sr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:0.5rem;}
    .sr-grid-item{text-align:center;padding:0.75rem 0.5rem;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;}
    .sr-grid-item:hover{background:#fff;border-color:#cbd5e1;}
    .sr-grid-item-label{font-size:0.65rem;color:#64748b;margin-bottom:0.2rem;}
    .sr-grid-item-val{font-size:1.2rem;font-weight:700;}
    .sr-grid-item-sub{font-size:0.6rem;color:#94a3b8;}
    
    .sr-two-col{display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1.25rem;}
    .sr-box{padding:1rem;border-radius:12px;border:1px solid;}
    .sr-box h4{margin:0 0 0.6rem 0;font-size:0.8rem;display:flex;align-items:center;gap:0.4rem;}
    .sr-box ul{margin:0;padding-left:1.1rem;font-size:0.78rem;}
    .sr-box li{margin-bottom:0.35rem;}
    .sr-box.good{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border-color:#a7f3d0;}
    .sr-box.good h4{color:#059669;}
    .sr-box.good li{color:#047857;}
    .sr-box.bad{background:linear-gradient(135deg,#fef2f2,#fee2e2);border-color:#fecaca;}
    .sr-box.bad h4{color:#dc2626;}
    .sr-box.bad li{color:#b91c1c;}
    
    .sr-eval{padding:1rem 1.25rem;border-radius:12px;border-left:4px solid;margin-bottom:0.75rem;}
    .sr-eval.success{background:#ecfdf5;border-color:#10b981;}
    .sr-eval.warning{background:#fffbeb;border-color:#f59e0b;}
    .sr-eval.danger{background:#fef2f2;border-color:#ef4444;}
    
    .sr-footer{text-align:center;padding-top:1rem;border-top:2px solid #e2e8f0;font-size:0.7rem;color:#94a3b8;margin-top:1rem;}
    
    .sr-badge{padding:0.2rem 0.5rem;border-radius:6px;font-size:0.65rem;font-weight:600;}
    .sr-badge.success{background:#dcfce7;color:#16a34a;}
    .sr-badge.warning{background:#fef3c7;color:#d97706;}
    .sr-badge.danger{background:#fee2e2;color:#dc2626;}
    
    @media(max-width:640px){.sr-stats{grid-template-columns:repeat(3,1fr);}.sr-two-col{grid-template-columns:1fr;}}
    </style>'''
    
    # ========== HTML ==========
    html = css + f'''<div class="sr">
    
    <!-- HEADER -->
    <div class="sr-header">
        <h2>📋 Bireysel Başarı Raporu</h2>
        <div class="sr-header-sub">{esc(course.get("course_code",""))} - {esc(course.get("course_name","Ders"))}</div>
        <div class="sr-header-meta">
            <span>👤 <strong>{esc(s_name)}</strong></span>
            <span>🔢 {esc(student_id)}</span>
            <span>📅 {esc(course.get("term",""))}</span>
            <span>👨‍🏫 {esc(course.get("instructor",""))}</span>
        </div>
    </div>
    
    <!-- ÖZET KARTLARI -->
    <div class="sr-stats">
        <div class="sr-stat primary" style="border-color:{main_clr};background:linear-gradient(135deg,{main_clr}08,white);">
            <div class="sr-stat-val" style="color:{main_clr};">%{s_pct:.1f}</div>
            <div class="sr-stat-label">Başarı</div>
        </div>
        <div class="sr-stat primary" style="border-color:{grade_clr};background:linear-gradient(135deg,{grade_clr}08,white);">
            <div class="sr-stat-val" style="color:{grade_clr};">{s_grade}</div>
            <div class="sr-stat-label">Harf Notu</div>
        </div>
        <div class="sr-stat">
            <div class="sr-stat-val" style="color:#3b82f6;">{rank}<span style="font-size:0.85rem;color:#94a3b8;">/{total_students}</span></div>
            <div class="sr-stat-label">Sıralama</div>
            <div class="sr-stat-sub">İlk %{100-percentile:.0f}</div>
        </div>
        <div class="sr-stat">
            <div class="sr-stat-val">{total_got:.0f}<span style="font-size:0.85rem;color:#94a3b8;">/{total_max:.0f}</span></div>
            <div class="sr-stat-label">Puan</div>
        </div>
        <div class="sr-stat">
            <div class="sr-stat-val" style="color:#8b5cf6;">{success_q}<span style="font-size:0.85rem;color:#94a3b8;">/{len(questions)}</span></div>
            <div class="sr-stat-label">Başarılı Soru</div>
        </div>
        <div class="sr-stat" style="background:{get_bg(s_pct)};">
            <div class="sr-stat-val" style="color:{'#10b981' if diff >= 0 else '#ef4444'};">{'+' if diff >= 0 else ''}{diff:.1f}</div>
            <div class="sr-stat-label">Ort. Farkı</div>
        </div>
    </div>
    
    <!-- SINIF KARŞILAŞTIRMASI -->
    <div class="sr-compare" style="background:{get_bg(s_pct)};border-color:{main_clr};">
        <div class="sr-compare-icon">{'🏆' if percentile >= 80 else '📈' if percentile >= 50 else '📊'}</div>
        <div class="sr-compare-text">
            Sınıf ortalaması <strong>%{class_avg:.1f}</strong>. Bu öğrenci ortalamanın 
            <strong style="color:{main_clr};">{'üzerinde ↑' if diff >= 0 else 'altında ↓'}</strong> 
            ve sınıfın <strong>en iyi %{100-percentile:.0f}</strong>'lik diliminde.
        </div>
    </div>'''
    
    # BİLEŞEN PERFORMANSI
    if comp_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#6366f1;">📝 Değerlendirme Bileşenleri</div><div class="sr-chips">'
        for cid, p in sorted(comp_perf.items()):
            pct = (p["got"]/p["max"]*100) if p["max"] else 0
            html += f'<div class="sr-chip" style="border-left:3px solid {get_color(pct)};"><div><div class="sr-chip-label">{esc(p["name"])}</div><div class="sr-chip-val" style="color:{get_color(pct)};">%{pct:.0f}</div></div><div class="sr-chip-sub">{p["got"]:.1f}/{p["max"]:.0f}</div></div>'
        html += '</div></div>'
    
    # DÖÇ
    if doc_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#10b981;">🎯 DÖÇ Performansı</div><table class="sr-table"><tr><th>DÖÇ</th><th class="center">Öğrenci</th><th class="center">Sınıf</th><th class="center">Fark</th><th class="center">Durum</th></tr>'
        for d, p in sorted(doc_perf.items()):
            pct = (p["got"]/p["max"]*100) if p["max"] else 0
            c_avg = float(docs_stats.get(d, {}).get("success_pct", 0))
            df = pct - c_avg
            html += f'<tr><td><strong>{esc(d)}</strong></td><td class="center bold" style="color:{get_color(pct)};">%{pct:.0f}</td><td class="center">%{c_avg:.0f}</td><td class="center" style="color:{"#10b981" if df >= 0 else "#ef4444"};">{df:+.0f}</td><td class="center">{badge(pct)}</td></tr>'
        html += '</table></div>'
    
    # PÖÇ
    if poc_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#3b82f6;">🏆 PÖÇ Performansı</div><table class="sr-table"><tr><th>PÖÇ</th><th class="center">Öğrenci</th><th class="center">Sınıf</th><th class="center">Durum</th></tr>'
        for pid, p in sorted(poc_perf.items()):
            pct = (p["got"]/p["max"]*100) if p["max"] else 0
            c_avg = float(pocs_stats.get(pid, {}).get("success_pct", 0))
            html += f'<tr><td><strong>{esc(pid)}</strong></td><td class="center bold" style="color:{get_color(pct)};">%{pct:.0f}</td><td class="center">%{c_avg:.0f}</td><td class="center">{badge(pct)}</td></tr>'
        html += '</table></div>'
    
    # PEA
    if pea_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#8b5cf6;">🎓 PEA Performansı</div><table class="sr-table"><tr><th>PEA</th><th class="center">Öğrenci</th><th class="center">Sınıf</th><th class="center">Durum</th></tr>'
        for aid, p in sorted(pea_perf.items()):
            pct = (p["got"]/p["max"]*100) if p["max"] else 0
            c_avg = float(peas_stats.get(aid, {}).get("success_pct", 0))
            html += f'<tr><td><strong>{esc(aid)}</strong></td><td class="center bold" style="color:{get_color(pct)};">%{pct:.0f}</td><td class="center">%{c_avg:.0f}</td><td class="center">{badge(pct)}</td></tr>'
        html += '</table></div>'
    
    # TYÇ & STAR-K
    if tyc_perf or stark_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#f59e0b;">🌐 Ulusal Yeterlilikler</div><div class="sr-grid">'
        for t in tyc_list:
            tid = t.get("id", "")
            if tid in tyc_perf:
                p = tyc_perf[tid]
                pct = (p["got"]/p["max"]*100) if p["max"] else 0
                html += f'<div class="sr-grid-item" style="background:#fffbeb;border-color:#fcd34d;"><div class="sr-grid-item-label">TYÇ {esc(tid)}</div><div class="sr-grid-item-val" style="color:{get_color(pct)};">%{pct:.0f}</div></div>'
        for s in stark_list:
            sid = s.get("id", "")
            if sid in stark_perf:
                p = stark_perf[sid]
                pct = (p["got"]/p["max"]*100) if p["max"] else 0
                html += f'<div class="sr-grid-item" style="background:#ecfeff;border-color:#67e8f9;"><div class="sr-grid-item-label">STAR-K {esc(sid)}</div><div class="sr-grid-item-val" style="color:{get_color(pct)};">%{pct:.0f}</div></div>'
        html += '</div></div>'
    
    # BLOOM
    if bloom_perf:
        html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#ec4899;">🧠 Bloom Taksonomisi</div><div class="sr-grid">'
        order = ["Bilgi", "Kavrama", "Uygulama", "Analiz", "Sentez", "Değerlendirme"]
        shown = set()
        for b in order:
            if b in bloom_perf:
                shown.add(b)
                p = bloom_perf[b]
                pct = (p["got"]/p["max"]*100) if p["max"] else 0
                c_avg = float(bloom_stats.get(b, {}).get("success_pct", 0))
                html += f'<div class="sr-grid-item" style="background:#fdf4ff;border-color:#f0abfc;"><div class="sr-grid-item-label">{esc(b)}</div><div class="sr-grid-item-val" style="color:{get_color(pct)};">%{pct:.0f}</div><div class="sr-grid-item-sub">Sınıf: %{c_avg:.0f}</div></div>'
        for b, p in sorted(bloom_perf.items()):
            if b not in shown:
                pct = (p["got"]/p["max"]*100) if p["max"] else 0
                c_avg = float(bloom_stats.get(b, {}).get("success_pct", 0))
                html += f'<div class="sr-grid-item" style="background:#fdf4ff;border-color:#f0abfc;"><div class="sr-grid-item-label">{esc(b)}</div><div class="sr-grid-item-val" style="color:{get_color(pct)};">%{pct:.0f}</div><div class="sr-grid-item-sub">Sınıf: %{c_avg:.0f}</div></div>'
        html += '</div></div>'
    
    # GÜÇLÜ / ZAYIF
    html += '<div class="sr-two-col">'
    html += '<div class="sr-box good"><h4>💪 Güçlü Yönler</h4>'
    if strong:
        html += '<ul>'
        for d, pct in strong[:5]:
            html += f'<li><strong>{esc(d)}</strong>: %{pct:.0f}</li>'
        html += '</ul>'
    else:
        html += '<p style="color:#6b7280;font-size:0.8rem;margin:0;">Henüz belirlenmedi</p>'
    html += '</div>'
    html += '<div class="sr-box bad"><h4>⚠️ Geliştirilmesi Gereken</h4>'
    if weak:
        html += '<ul>'
        for d, pct in weak[:5]:
            html += f'<li><strong>{esc(d)}</strong>: %{pct:.0f}</li>'
        html += '</ul>'
    else:
        html += '<p style="color:#6b7280;font-size:0.8rem;margin:0;">Tüm alanlarda yeterli</p>'
    html += '</div></div>'
    
    # SORU BAZLI
    html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#64748b;">📝 Soru Bazlı Performans</div><table class="sr-table"><tr><th>Soru</th><th>DÖÇ</th><th>Bloom</th><th class="center">Alınan</th><th class="center">Max</th><th class="center">%</th><th class="center">Sınıf</th></tr>'
    for q in questions:
        qid = q.get("id", "")
        got = float(s_scores.get(qid, 0))
        maxp = float(q.get("max_points", 1)) or 1
        pct = (got / maxp * 100)
        doc_ids = q.get("doc_ids") or ([q.get("doc_id")] if q.get("doc_id") else [])
        blooms = q.get("bloom_list") or ([q.get("bloom")] if q.get("bloom") else [])
        q_out = question_outcomes.get(qid, {})
        c_avg = (float(q_out.get("avg_score", 0)) / maxp * 100) if maxp else 0
        html += f'<tr style="background:{get_bg(pct)};"><td><strong>{esc(qid)}</strong></td><td style="font-size:0.7rem;">{esc(", ".join(doc_ids[:2]))}</td><td style="font-size:0.7rem;">{esc(", ".join(blooms[:1]))}</td><td class="center bold">{got:.1f}</td><td class="center">{maxp:.0f}</td><td class="center bold" style="color:{get_color(pct)};">%{pct:.0f}</td><td class="center">%{c_avg:.0f}</td></tr>'
    html += '</table></div>'
    
    # DEĞERLENDİRME
    html += '<div class="sr-section"><div class="sr-section-title" style="border-color:#6366f1;">💡 Değerlendirme</div>'
    if s_pct >= 70:
        html += '<div class="sr-eval success"><strong>✅ Tebrikler!</strong> Bu öğrenci dersi başarıyla tamamlamıştır. Tüm öğrenme çıktılarında beklenen performansı sergilemiştir.</div>'
    elif s_pct >= 50:
        html += '<div class="sr-eval warning"><strong>⚠️ Koşullu Başarı:</strong> Bu öğrenci kısmen başarılı olmuştur. Yukarıda belirtilen zayıf alanlarda ek çalışma yapması önerilir.</div>'
    else:
        html += '<div class="sr-eval danger"><strong>❌ Dikkat:</strong> Bu öğrenci başarı kriterlerini karşılamamaktadır. Zayıf alanlarda destek ve telafi çalışması gereklidir.</div>'
    html += '</div>'
    
    # FOOTER
    html += f'<div class="sr-footer">Bu rapor {datetime.now().strftime("%d.%m.%Y %H:%M")} tarihinde otomatik olarak oluşturulmuştur.</div>'
    html += '</div>'
    
    return html


# ============ RAPOR GEÇMİŞİ GÖRÜNTÜLEME ============

@app.route("/report-history/<int:report_id>", methods=["GET"])
def view_report_history(report_id):
    """Kayıtlı raporu görüntüle"""
    if not _is_auth():
        return _redirect_login()
    
    report = auth.get_report(report_id)
    if not report:
        return Response("<h1>Rapor bulunamadı</h1><p><a href='/'>Ana sayfaya dön</a></p>", status=404, mimetype="text/html")
    
    try:
        result = json.loads(report.get("result", "{}"))
        # V2 raporu göster (daha kapsamlı)
        html = ws.render_v2_report(result, show_toolbar=True, report_id=report_id)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return Response(f"<h1>Rapor Hatası</h1><p>{e}</p><p><a href='/'>Ana sayfaya dön</a></p>", status=500, mimetype="text/html")


@app.route("/report-history/<int:report_id>/standard", methods=["GET"])
def view_report_standard(report_id):
    """Kayıtlı raporun standart versiyonunu görüntüle"""
    if not _is_auth():
        return _redirect_login()
    
    report = auth.get_report(report_id)
    if not report:
        return Response("<h1>Rapor bulunamadı</h1>", status=404, mimetype="text/html")
    
    try:
        result = json.loads(report.get("result", "{}"))
        html = ws.render_tables(result, standalone=True, report_id=report_id)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return Response(f"<h1>Rapor Hatası</h1><p>{e}</p>", status=500, mimetype="text/html")


@app.route("/report-history/<int:report_id>/pdf", methods=["GET"])
def download_report_pdf(report_id):
    """Kayıtlı raporun PDF'ini indir"""
    if not _is_auth():
        return _redirect_login()
    
    report = auth.get_report(report_id)
    if not report:
        return Response("Rapor bulunamadı", status=404)
    
    try:
        result = json.loads(report.get("result", "{}"))
        html = ws.render_tables(result, standalone=True)
        
        # Geçici PDF oluştur
        pdf_path = Path(__file__).parent / f"temp_report_{report_id}.pdf"
        ws.export_pdf_from_html(html, pdf_path) or ws.legacy_pdf(result, str(pdf_path))
        
        if pdf_path.exists():
            response = send_file(str(pdf_path), mimetype="application/pdf", as_attachment=True, 
                               download_name=f"rapor_{report_id}.pdf")
            return response
        else:
            return Response("PDF oluşturulamadı", status=500)
    except Exception as e:
        return Response(f"Hata: {e}", status=500)


@app.route("/report-history/<int:report_id>/pdf-v2", methods=["GET"])
def download_report_pdf_v2(report_id):
    """Kayıtlı raporun V2 PDF'ini indir"""
    if not _is_auth():
        return _redirect_login()
    
    report = auth.get_report(report_id)
    if not report:
        return Response("Rapor bulunamadı", status=404)
    
    try:
        result = json.loads(report.get("result", "{}"))
        html = ws.render_v2_report(result)
        
        # Geçici PDF oluştur
        pdf_path = Path(__file__).parent / f"temp_report_v2_{report_id}.pdf"
        ws.export_pdf_from_html(html, pdf_path) or ws.legacy_pdf(result, str(pdf_path))
        
        if pdf_path.exists():
            response = send_file(str(pdf_path), mimetype="application/pdf", as_attachment=True, 
                               download_name=f"rapor_v2_{report_id}.pdf")
            return response
        else:
            return Response("PDF oluşturulamadı", status=500)
    except Exception as e:
        return Response(f"Hata: {e}", status=500)


@app.route("/load-report/<int:report_id>", methods=["GET"])
def load_report(report_id):
    """Eski raporu yükle ve form'a doldur"""
    if not _is_auth():
        return _redirect_login()
    
    report = auth.get_report(report_id)
    if not report:
        return redirect("/", code=302)
    
    # Payload'ı STATE'e yükle
    payload = json.loads(report.get("payload", "{}"))
    result = json.loads(report.get("result", "{}"))
    
    ws.STATE["last_result"] = result
    ws.STATE["last_payload_text"] = report.get("payload", "{}")
    ws.STATE["loaded_report_id"] = report_id
    
    return redirect("/", code=302)


# ============ ANA SAYFA VE HESAPLAMA ============

@app.route("/", methods=["GET"])
def index():
    import sys
    
    print(f"[index] ==================== ANA SAYFA YÜKLEME ====================", file=sys.stderr, flush=True)
    
    if not _is_auth():
        print(f"[index] Auth yok, login'e yönlendiriliyor", file=sys.stderr, flush=True)
        return _redirect_login()
    
    # Boş form ile başla
    defaults = ws.get_empty_form_defaults()
    
    email = _get_email()
    print(f"[index] email: {email}", file=sys.stderr, flush=True)
    
    user = None
    course_code = ""
    course_name = ""
    
    if email:
        user = auth.fetch_user(email)
        print(f"[index] user bulundu: {bool(user)}", file=sys.stderr, flush=True)
        
        if user:
            course_code = user.get('course_code', '') or ''
            course_name = user.get('course_name', '') or ''
            
            print(f"[index] user.course_code: '{course_code}'", file=sys.stderr, flush=True)
            
            # 1. ÖNCE: Ders bazlı ÇIKTI verilerini yükle (course_data tablosundan - profilde düzenlenen)
            if course_code:
                course_data = auth.get_course_data(course_code)
                print(f"[index] course_data bulundu: {bool(course_data)}", file=sys.stderr, flush=True)
                
                if course_data:
                    # Çıktı verileri: TYÇ, STARK, DÖÇ, PÖÇ, PEA, Müfredat, Bloom
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
                        val = course_data.get(src_key, '') or ''
                        if val:
                            defaults[dst_key] = val
                            print(f"[index] course_data -> {dst_key} = {len(val)} karakter", file=sys.stderr, flush=True)
                    
                    if course_data.get('course_name'):
                        course_name = course_data['course_name']
            
            # 2. SONRA: Kullanıcının EŞLEŞTİRME ve SORU verilerini yükle (user_curriculum tablosundan)
            curriculum_data = auth.get_user_curriculum(email)
            if curriculum_data:
                print(f"[index] user_curriculum bulundu", file=sys.stderr, flush=True)
                
                # Eşleştirme verileri - TÜM mapping alanları
                mapping_fields = [
                    "doc_tyc_map_text", "poc_tyc_map_text", "pea_stark_map_text", 
                    "poc_pea_map_text", "doc_poc_weights_text", "curriculum_doc_map_text",
                    "doc_stark_map_text", "doc_pea_map_text",
                    "curriculum_tyc_map_text", "curriculum_stark_map_text",
                    "curriculum_poc_map_text", "curriculum_pea_map_text"
                ]
                for key in mapping_fields:
                    if curriculum_data.get(key):
                        defaults[key] = curriculum_data[key]
                        print(f"[index] user_curriculum -> {key} = {len(curriculum_data[key])} karakter", file=sys.stderr, flush=True)
                
                # Bileşenler (components -> assessments)
                if curriculum_data.get("components_text"):
                    defaults["assessments_text"] = curriculum_data["components_text"]
                    print(f"[index] user_curriculum -> assessments_text = {len(curriculum_data['components_text'])} karakter", file=sys.stderr, flush=True)
                
                # Notlandırma
                if curriculum_data.get("grading_text"):
                    defaults["grading_text"] = curriculum_data["grading_text"]
                
                # Soru eşleştirmeleri
                if curriculum_data.get("question_map_text"):
                    defaults["question_map_text"] = curriculum_data["question_map_text"]
                    print(f"[index] user_curriculum -> question_map_text = {len(curriculum_data['question_map_text'])} karakter", file=sys.stderr, flush=True)
                
                # Eşik değerleri
                if curriculum_data.get("thresholds_met"):
                    defaults["thresholds_met"] = curriculum_data["thresholds_met"]
                if curriculum_data.get("thresholds_partial"):
                    defaults["thresholds_partial"] = curriculum_data["thresholds_partial"]
            else:
                print(f"[index] user_curriculum BOŞ!", file=sys.stderr, flush=True)
            
            # 3. Ders bilgilerini defaults'a ekle
            defaults['course_code'] = course_code
            defaults['course_name'] = course_name
            defaults['program_name'] = user.get('program_name', '') or ''
            defaults['term'] = user.get('term', '') or ''
            defaults['instructor'] = user.get('instructor', '') or user.get('full_name', '') or ''
    
    print(f"[index] SONUÇ: tyc={len(defaults.get('tyc_text',''))}, docs={len(defaults.get('docs_text',''))}, assessments={len(defaults.get('assessments_text',''))}", file=sys.stderr, flush=True)
    print(f"[index] SONUÇ: question_map={len(defaults.get('question_map_text',''))}", file=sys.stderr, flush=True)
    print(f"[index] ================================================================", file=sys.stderr, flush=True)
    
    # Profil bilgilerini ekle (cookie'den - ama üzerine yazmayacak şekilde)
    profile = _get_profile()
    for k, v in profile.items():
        if v and not defaults.get(k):
            defaults[k] = v
    
    user_info = _get_user_info()
    
    # Taslak ve rapor geçmişi
    drafts = auth.get_drafts(email) if email else []
    reports = auth.get_report_history(email) if email else []
    
    # Kullanıcının yetkili olduğu dersler
    user_courses = auth.get_user_courses(email) if email else []
    if email and user:
        main_course = user.get('course_code', '') or ''
        if main_course:
            course_codes = [uc.get('course_code') for uc in user_courses]
            if main_course not in course_codes:
                user_courses.insert(0, {
                    'course_code': main_course,
                    'course_name': user.get('course_name', '') or ''
                })
    
    body = ws.build_page(defaults, result_html=None, user_info=user_info, drafts=drafts, reports=reports, user_courses=user_courses)
    return Response(body, mimetype="text/html")


@app.route("/compute", methods=["POST"])
def compute():
    if not _is_auth():
        return _redirect_login()
    
    user_info = _get_user_info()
    email = _get_email()
    values = {k: request.form.get(k, "") for k in ws.FORM_KEYS}
    
    drafts = auth.get_drafts(email) if email else []
    reports = auth.get_report_history(email) if email else []
    user_courses = auth.get_user_courses(email) if email else []
    
    try:
        payload, defaults = ws.build_payload_from_form(values)
    except Exception as e:
        body = ws.build_page(ws.ensure_form_defaults(values), None, f"Hata: {e}", user_info=user_info, drafts=drafts, reports=reports, user_courses=user_courses)
        return Response(body, status=400, mimetype="text/html")
    
    try:
        result = ws.compute(payload)
        out_pdf = Path(__file__).parent / "web_report.pdf"
        out_pdf_v2 = Path(__file__).parent / "web_report_v2.pdf"
        
        html_main = ws.render_tables(result, standalone=True)
        html_v2 = ws.render_v2_report(result)
        
        ws.export_pdf_from_html(html_main, out_pdf) or ws.legacy_pdf(result, str(out_pdf))
        ws.export_pdf_from_html(html_v2, out_pdf_v2) or ws.legacy_pdf(result, str(out_pdf_v2))
        
        result["curriculum"] = payload.get("curriculum", [])
        result["tyc"] = payload.get("tyc", [])
        result["stark"] = payload.get("stark", [])
        result["doc_tyc_map"] = payload.get("doc_tyc_map", {})
        result["poc_tyc_map"] = payload.get("poc_tyc_map", {})
        result["pea_stark_map"] = payload.get("pea_stark_map", {})
        result["doc_poc_weights"] = payload.get("doc_poc_weights", {})
        result["poc_pea_map"] = payload.get("poc_pea_map", {})
        result["input_questions"] = payload.get("questions", [])
        result["input_students"] = payload.get("students", [])
        result["input_assessments"] = payload.get("assessments", [])
        result["scores"] = payload.get("scores", {})
        result["grading"] = payload.get("grading", {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0})
        result["coverage"] = ws.compute_coverage(payload.get("questions", []))
        result["question_outcomes"] = ws.compute_question_outcomes(payload.get("questions", []), payload.get("scores", {}))
        result["course"] = payload.get("course", {})
        result["students_data"] = ws.compute_student_results(payload.get("questions", []), payload.get("scores", {}), payload.get("students", []), payload.get("assessments", []))
        result["weekly_coverage"] = ws.compute_weekly_coverage(payload.get("questions", []))
        
        ws.STATE["last_result"] = result
        ws.STATE["last_payload_text"] = json.dumps(payload, ensure_ascii=False, indent=2)
        ws.STATE["last_pdf_path"] = str(out_pdf)
        ws.STATE["last_v2_pdf_path"] = str(out_pdf_v2)
        
        # Rapor geçmişine kaydet
        if email:
            overall_pct = result.get("computed", {}).get("overall", {}).get("success_pct", 0)
            user_name = user_info.get("full_name", "").strip() or email.split("@")[0]
            title = f"{datetime.now().strftime('%d.%m.%Y %H:%M')} - {user_name}"
            auth.save_report(email, title, json.dumps(payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False), overall_pct)
            reports = auth.get_report_history(email)
            
            # Kullanıcının eşleştirme ve soru verilerini kaydet (sonraki girişlerde otomatik yüklenecek)
            curriculum_data = {
                "doc_tyc_map_text": values.get("doc_tyc_map_text", ""),
                "poc_tyc_map_text": values.get("poc_tyc_map_text", ""),
                "pea_stark_map_text": values.get("pea_stark_map_text", ""),
                "poc_pea_map_text": values.get("poc_pea_map_text", ""),
                "doc_poc_weights_text": values.get("doc_poc_weights_text", ""),
                "curriculum_doc_map_text": values.get("curriculum_doc_map_text", ""),
                "doc_stark_map_text": values.get("doc_stark_map_text", ""),
                "doc_pea_map_text": values.get("doc_pea_map_text", ""),
                "curriculum_tyc_map_text": values.get("curriculum_tyc_map_text", ""),
                "curriculum_stark_map_text": values.get("curriculum_stark_map_text", ""),
                "curriculum_poc_map_text": values.get("curriculum_poc_map_text", ""),
                "curriculum_pea_map_text": values.get("curriculum_pea_map_text", ""),
                "components_text": values.get("assessments_text", ""),
                "thresholds_met": values.get("thresholds_met", "70"),
                "thresholds_partial": values.get("thresholds_partial", "50"),
                "grading_text": values.get("grading_text", ""),
                "question_map_text": values.get("question_map_text", ""),
            }
            auth.save_user_curriculum(email, curriculum_data)
        
        # defaults'u values ile güncelle - hesaplama sonrası form verileri korunsun
        for k, v in values.items():
            if v:
                defaults[k] = v
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        body = ws.build_page(ws.ensure_form_defaults(values), None, f"Hesaplama hatasi: {e}", user_info=user_info, drafts=drafts, reports=reports, user_courses=user_courses)
        return Response(body, status=500, mimetype="text/html")
    
    # Hesaplama sonucu gösterirken DEFAULTS kullan (values değil!) - payload'dan oluşturulmuş veriler
    return Response(ws.build_page(defaults, ws.render_tables(result), user_info=user_info, drafts=drafts, reports=reports, user_courses=user_courses), mimetype="text/html")


@app.route("/download.pdf", methods=["GET"])
def download_pdf():
    if not _is_auth():
        return _redirect_login()
    pdf_path = ws.STATE.get("last_pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return Response("PDF yok", status=404)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name="akreditasyon_raporu.pdf")


@app.route("/download-v2.pdf", methods=["GET"])
def download_pdf_v2():
    if not _is_auth():
        return _redirect_login()
    pdf_path = ws.STATE.get("last_v2_pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return Response("V2 PDF yok", status=404)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name="akreditasyon_raporu_v2.pdf")


@app.route("/report-v2", methods=["GET"])
def report_v2():
    if not _is_auth():
        return _redirect_login()
    result = ws.STATE.get("last_result")
    if not result:
        return Response("<h1>Henuz hesaplama yapilmadi</h1><p><a href='/'>Ana sayfaya don</a></p>", status=404, mimetype="text/html")
    try:
        html = ws.render_v2_report(result)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return Response(f"<h1>V2 Rapor Hatasi</h1><p>{e}</p><p><a href='/'>Ana sayfaya don</a></p>", status=500, mimetype="text/html")


@app.route("/report-standalone", methods=["GET"])
def report_standalone():
    """Son hesaplanan standart raporu standalone sayfada göster"""
    if not _is_auth():
        return _redirect_login()
    result = ws.STATE.get("last_result")
    if not result:
        return Response("<h1>Henuz hesaplama yapilmadi</h1><p><a href='/'>Ana sayfaya don</a></p>", status=404, mimetype="text/html")
    try:
        html = ws.render_tables(result, standalone=True)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return Response(f"<h1>Rapor Hatasi</h1><p>{e}</p><p><a href='/'>Ana sayfaya don</a></p>", status=500, mimetype="text/html")


@app.route("/sample-data", methods=["GET"])
def sample_data():
    if not _is_auth():
        return Response("{}", mimetype="application/json")
    payload = build_sample_payload()
    defaults = ws.form_defaults_from_payload(payload)
    return Response(json.dumps(defaults, ensure_ascii=False), mimetype="application/json")


@app.route("/download-form", methods=["GET"])
def download_form():
    """Öğrenci veri giriş Excel formunu indir"""
    if not _is_auth():
        return _redirect_login()
    form_path = Path(__file__).parent / "assets" / "ogrenciForm.xlsx"
    if not form_path.exists():
        return Response("Form dosyası bulunamadı", status=404)
    return send_file(str(form_path), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                     as_attachment=True, download_name="ogrenciForm.xlsx")


@app.route("/test-ai", methods=["GET"])
def test_ai():
    """Claude AI bağlantısını test et"""
    if not _is_auth():
        return _redirect_login()
    
    import ssl
    
    # API key kontrolü
    api_key = ws.CLAUDE_API_KEY
    api_key_masked = api_key[:20] + "..." + api_key[-10:] if len(api_key) > 30 else api_key
    
    # Test verisi ile öneri al
    test_result = {
        "computed": {
            "overall": {"success_pct": 62.5, "status": "Kısmen Sağlandı"},
            "docs": {"DÖÇ-1": {"success_pct": 75}, "DÖÇ-2": {"success_pct": 55}, "DÖÇ-3": {"success_pct": 48}},
            "pocs": {"PÖÇ-1": {"success_pct": 68}, "PÖÇ-2": {"success_pct": 58}},
            "peas": {},
            "bloom": {"Hatırlama": {"success_pct": 82}, "Anlama": {"success_pct": 65}, "Uygulama": {"success_pct": 52}, "Analiz": {"success_pct": 38}}
        },
        "coverage": {"doc": []},
        "course": {"course_name": "Test Dersi"},
        "students_data": [],
        "thresholds": {"met": 70, "partially": 50}
    }
    
    try:
        print("=" * 50)
        print("[TEST-AI] Test başlatılıyor...")
        print(f"[TEST-AI] API Key: {api_key_masked}")
        print(f"[TEST-AI] SSL Version: {ssl.OPENSSL_VERSION}")
        
        suggestions = ws.generate_ai_suggestions(test_result)
        
        if suggestions:
            html = f"""
            <html>
            <head><title>AI Test</title></head>
            <body style="font-family:sans-serif;padding:2rem;max-width:900px;margin:auto;background:#f8fafc;">
            <div style="background:white;padding:2rem;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            <h1 style="color:#10b981;">✅ Claude AI Çalışıyor!</h1>
            <p><strong>Model:</strong> claude-3-haiku-20240307</p>
            <p><strong>API Key:</strong> <code>{api_key_masked}</code></p>
            
            <h3>Test Önerileri ({len(suggestions)} adet):</h3>
            <ul style="background:#f1f5f9;padding:1rem 2rem;border-radius:8px;">
            {"".join(f"<li style='margin:0.5rem 0;'>{s}</li>" for s in suggestions)}
            </ul>
            
            <p style="margin-top:2rem;"><a href="/" style="color:#3b82f6;">← Ana Sayfaya Dön</a></p>
            </div>
            </body>
            </html>
            """
            return Response(html, mimetype="text/html")
        else:
            html = f"""
            <html>
            <head><title>AI Test</title></head>
            <body style="font-family:sans-serif;padding:2rem;max-width:900px;margin:auto;background:#f8fafc;">
            <div style="background:white;padding:2rem;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            <h1 style="color:#ef4444;">❌ AI Bağlantı Hatası</h1>
            <p><strong>API Key:</strong> <code>{api_key_masked}</code></p>
            <p><strong>SSL:</strong> {ssl.OPENSSL_VERSION}</p>
            
            <p style="margin-top:1rem;">Claude API'ye bağlanılamadı. Sunucu loglarını kontrol edin.</p>
            
            <h4>Olası Sebepler:</h4>
            <ul style="background:#fef2f2;padding:1rem 2rem;border-radius:8px;color:#b91c1c;">
            <li>API key geçersiz veya süresi dolmuş</li>
            <li>Sunucudan api.anthropic.com adresine erişim engelli (firewall)</li>
            <li>SSL sertifika sorunu</li>
            <li>API kredisi bitmiş</li>
            </ul>
            
            <h4>Kontrol Adımları:</h4>
            <ol>
            <li>Sunucu loglarına bakın: <code>tail -f logs/error.log</code></li>
            <li>Terminal'den test edin: <code>curl https://api.anthropic.com</code></li>
            <li>API key'i kontrol edin: <a href="https://console.anthropic.com" target="_blank">Anthropic Console</a></li>
            </ol>
            
            <p style="margin-top:2rem;"><a href="/" style="color:#3b82f6;">← Ana Sayfaya Dön</a></p>
            </div>
            </body>
            </html>
            """
            return Response(html, mimetype="text/html")
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        html = f"""
        <html>
        <head><title>AI Test</title></head>
        <body style="font-family:sans-serif;padding:2rem;max-width:900px;margin:auto;background:#f8fafc;">
        <div style="background:white;padding:2rem;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
        <h1 style="color:#ef4444;">❌ Exception Hatası</h1>
        <p><strong>API Key:</strong> <code>{api_key_masked}</code></p>
        <p><strong>Hata Tipi:</strong> {type(e).__name__}</p>
        <p><strong>Hata:</strong> {str(e)}</p>
        <pre style="background:#1e293b;color:#e2e8f0;padding:1rem;overflow:auto;font-size:0.75rem;border-radius:8px;">{tb}</pre>
        <p style="margin-top:2rem;"><a href="/" style="color:#3b82f6;">← Ana Sayfaya Dön</a></p>
        </div>
        </body>
        </html>
        """
        return Response(html, mimetype="text/html")


# Uygulama başlarken DB'yi hazırla
auth.init_db()

if __name__ == "__main__":
    print("AkrediX Sistemi")
    print("http://0.0.0.0:8000")
    print("Demo: demo@example.com / P@ssw0rd!")
    app.run(host="0.0.0.0", port=8000, debug=True)

"""
HMKU Akreditasyon - Flask App
Şifre Hash + Taslak + Rapor Geçmişi + Şifremi Unuttum
"""
from pathlib import Path
from flask import Flask, request, send_file, Response, redirect, jsonify
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
            "course_code": "",
            "course_name": "",
            "term": "",
            "program_name": (request.form.get("program_name") or "").strip(),
            "instructor": (request.form.get("full_name") or "").strip(),
            "department": (request.form.get("program_name") or "").strip(),
        }
        
        auth.create_user(email, password, profile)
        
        # Müfredat verilerini kaydet
        bloom_from_form = (request.form.get("bloom_text") or "").strip()
        # Boşsa varsayılan Bloom taksonomisi
        if not bloom_from_form:
            bloom_from_form = "Bilgi - Hatırlama düzeyi\nKavrama - Anlama düzeyi\nUygulama - Uygulama düzeyi\nAnaliz - Çözümleme düzeyi\nSentez - Birleştirme düzeyi\nDeğerlendirme - Yargılama düzeyi"
        
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

@app.route("/profile", methods=["GET", "POST"])
def profile_view():
    if not _is_auth():
        return _redirect_login()
    
    email = _get_email()
    if not email:
        email = "demo@example.com"
    
    user = auth.fetch_user(email) or {}
    curriculum = auth.get_user_curriculum(email) or {}
    
    # Flash message kontrolü
    success_msg = request.args.get("saved", "")
    message_block = ""
    if success_msg == "1":
        message_block = "<div class='success' style='background:#dcfce7;color:#166534;padding:0.75rem;border-radius:8px;margin-bottom:1rem;'>✓ Bilgileriniz başarıyla kaydedildi!</div>"
    
    if request.method == "GET":
        html = auth.render_profile(
            message_block=message_block,
            user_data=user,
            curriculum_data=curriculum
        )
        return Response(html, mimetype="text/html")
    
    try:
        # Kullanıcı bilgilerini güncelle
        profile = {
            "full_name": (request.form.get("full_name") or "").strip(),
            "course_code": user.get("course_code", ""),
            "course_name": user.get("course_name", ""),
            "term": user.get("term", ""),
            "program_name": (request.form.get("program_name") or "").strip(),
            "instructor": (request.form.get("full_name") or "").strip(),
            "department": (request.form.get("program_name") or "").strip(),
        }
        auth.update_user(email, profile)
        
        # Müfredat verilerini güncelle
        curriculum_data = {
            "tyc_text": (request.form.get("tyc_text") or "").strip(),
            "stark_text": (request.form.get("stark_text") or "").strip(),
            "docs_text": (request.form.get("docs_text") or "").strip(),
            "pocs_text": (request.form.get("pocs_text") or "").strip(),
            "peas_text": (request.form.get("peas_text") or "").strip(),
            "curriculum_text": (request.form.get("curriculum_text") or "").strip(),
            "bloom_text": (request.form.get("bloom_text") or "").strip(),
            # Mevcut eşleşmeleri koru
            "doc_tyc_map_text": curriculum.get("doc_tyc_map_text", ""),
            "poc_tyc_map_text": curriculum.get("poc_tyc_map_text", ""),
            "pea_stark_map_text": curriculum.get("pea_stark_map_text", ""),
            "poc_pea_map_text": curriculum.get("poc_pea_map_text", ""),
            "doc_poc_weights_text": curriculum.get("doc_poc_weights_text", ""),
            "components_text": curriculum.get("components_text", ""),
            "thresholds_met": curriculum.get("thresholds_met", "70"),
            "thresholds_partial": curriculum.get("thresholds_partial", "50"),
            "grading_text": curriculum.get("grading_text", ""),
        }
        auth.save_user_curriculum(email, curriculum_data)
        
        resp = redirect("/profile?saved=1", code=302)
        profile["email"] = email
        resp.set_cookie("profile", urllib.parse.quote(json.dumps(profile, ensure_ascii=False)), path="/")
        return resp
    except Exception as e:
        html = auth.render_profile(
            message_block=f"<div class='error'>Hata: {e}</div>",
            user_data=user,
            curriculum_data=curriculum
        )
        return Response(html, status=500, mimetype="text/html")


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
    if not _is_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    email = _get_email()
    data = request.get_json()
    form_data = json.dumps(data, ensure_ascii=False)
    
    # "Otomatik Kayit" isimli taslağı güncelle veya oluştur
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
    if not _is_auth():
        return _redirect_login()
    
    # Boş form ile başla
    defaults = ws.get_empty_form_defaults()
    
    # Kullanıcının kaydedilmiş müfredat verilerini yükle
    email = _get_email()
    if email:
        curriculum_data = auth.get_user_curriculum(email)
        if curriculum_data:
            for key in ["tyc_text", "stark_text", "docs_text", "pocs_text", "peas_text",
                       "curriculum_text", "bloom_text", "doc_tyc_map_text", "poc_tyc_map_text",
                       "pea_stark_map_text", "poc_pea_map_text", "doc_poc_weights_text",
                       "grading_text"]:
                if curriculum_data.get(key):
                    defaults[key] = curriculum_data[key]
            # Assessments (components)
            if curriculum_data.get("components_text"):
                defaults["assessments_text"] = curriculum_data["components_text"]
            # Eşik değerleri
            if curriculum_data.get("thresholds_met"):
                defaults["thresholds_met"] = curriculum_data["thresholds_met"]
            if curriculum_data.get("thresholds_partial"):
                defaults["thresholds_partial"] = curriculum_data["thresholds_partial"]
    
    # Profil bilgilerini ekle
    defaults.update(_get_profile())
    user_info = _get_user_info()
    
    # Taslak ve rapor geçmişi
    drafts = auth.get_drafts(email) if email else []
    reports = auth.get_report_history(email) if email else []
    
    body = ws.build_page(defaults, result_html=None, user_info=user_info, drafts=drafts, reports=reports)
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
    
    try:
        payload, defaults = ws.build_payload_from_form(values)
    except Exception as e:
        body = ws.build_page(ws.ensure_form_defaults(values), None, f"Hata: {e}", user_info=user_info, drafts=drafts, reports=reports)
        return Response(body, status=400, mimetype="text/html")
    
    try:
        result = ws.compute(payload)
        out_pdf = Path(__file__).parent / "web_report.pdf"
        out_pdf_v2 = Path(__file__).parent / "web_report_v2.pdf"
        
        html_main = ws.render_tables(result)
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
        result["coverage"] = ws.compute_coverage(payload.get("questions", []))
        result["question_outcomes"] = ws.compute_question_outcomes(payload.get("questions", []), payload.get("scores", {}))
        result["course"] = payload.get("course", {})
        result["students_data"] = ws.compute_student_results(payload.get("questions", []), payload.get("scores", {}), payload.get("students", []))
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
            
            # Kullanıcının müfredat verilerini kaydet (sonraki girişlerde otomatik yüklenecek)
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
            auth.save_user_curriculum(email, curriculum_data)
        
    except Exception as e:
        body = ws.build_page(defaults, None, f"Hesaplama hatasi: {e}", user_info=user_info, drafts=drafts, reports=reports)
        return Response(body, status=500, mimetype="text/html")
    
    return Response(ws.build_page(defaults, ws.render_tables(result), user_info=user_info, drafts=drafts, reports=reports), mimetype="text/html")


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


@app.route("/sample-data", methods=["GET"])
def sample_data():
    if not _is_auth():
        return Response("{}", mimetype="application/json")
    payload = build_sample_payload()
    defaults = ws.form_defaults_from_payload(payload)
    return Response(json.dumps(defaults, ensure_ascii=False), mimetype="application/json")


# Uygulama başlarken DB'yi hazırla
auth.init_db()

if __name__ == "__main__":
    print("HMKU Akreditasyon Sistemi")
    print("http://0.0.0.0:8000")
    print("Demo: demo@example.com / P@ssw0rd!")
    app.run(host="0.0.0.0", port=8000, debug=True)

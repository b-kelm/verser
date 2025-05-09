import streamlit as st
import os
import json
import random
import math
import bcrypt
import re
import time
import uuid # Für eindeutige Team-IDs und Codes
from difflib import SequenceMatcher

# --- Konstanten ---
USER_DATA_DIR = "user_data"
USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")
PUBLIC_VERSES_FILE = os.path.join(USER_DATA_DIR, "public_verses.json")
TEAM_DATA_FILE = os.path.join(USER_DATA_DIR, "teams.json")
ADMIN_PASSWORD = "bibelfeld" # Admin-Passwort

MAX_CHUNKS = 8
COLS_PER_ROW = 4
LEADERBOARD_SIZE = 7
AUTO_ADVANCE_DELAY = 2 # Sekunden

LANGUAGES = {
    "DE": "🇩🇪 Deutsch",
    "EN": "🇬🇧 English",
}
DEFAULT_LANGUAGE = "DE"
PUBLIC_MARKER = "[P]" # Für Texte, die nur öffentlich existieren und noch nicht kopiert wurden
COMPLETED_MARKER = "✅"
VERSE_EMOJI = "📖"

# --- Hilfsfunktionen ---
os.makedirs(USER_DATA_DIR, exist_ok=True)

# --- Parser für Bibeltexte ---
def parse_verses_from_text(raw_text):
    lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
    parsed_verses = []
    if not lines: return parsed_verses
    first_line_match_new_format = re.match(r"^\s*([\w\s]+\.?)\s*(\d+)\s*$", lines[0])
    if first_line_match_new_format and len(lines) > 1:
        current_book = first_line_match_new_format.group(1).strip()
        current_chapter = first_line_match_new_format.group(2).strip()
        second_line_verse_match = re.match(r"^\s*(\d+[a-z]*(?:-\d+[a-z]*)?)\s+", lines[1])
        if second_line_verse_match:
            for line_new_format in lines[1:]:
                verse_match_new_format = re.match(r"^\s*(\d+[a-z]*(?:-\d+[a-z]*)?)\s+(.*)", line_new_format)
                if verse_match_new_format:
                    verse_num = verse_match_new_format.group(1); text_content = verse_match_new_format.group(2)
                    ref = f"{current_book} {current_chapter}:{verse_num}"
                    parsed_verses.append({"ref": ref.strip(), "text": text_content.strip()})
            if parsed_verses: return parsed_verses
    if not parsed_verses:
        for line_old_format in lines:
            match_old_format = re.match(r"\d+\)\s*([\w\s]+\.?\s*\d+:\d+[\-\d]*[a-z]?)\s+(.*)", line_old_format)
            if match_old_format:
                ref_old, text_old = match_old_format.groups()
                parsed_verses.append({"ref": ref_old.strip(), "text": text_old.strip()})
    return parsed_verses

# --- Passwort-, User-, Team-, Vers-Datenmanagement ---
def hash_password(password):
    pw_bytes = password.encode('utf-8'); salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

def verify_password(stored_hash, provided_password):
    try: return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
    except ValueError: return False

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding='utf-8') as f: data = json.load(f)
            for username_key in data:
                data[username_key].setdefault('points', 0); data[username_key].setdefault('team_id', None)
                data[username_key].setdefault('learning_time_seconds', 0); data[username_key].setdefault('total_verses_learned', 0)
                data[username_key].setdefault('total_words_learned', 0)
            return data
        except (json.JSONDecodeError, IOError): st.error("Benutzerdatei korrupt."); return {}
    return {}

def save_users(users_data_to_save):
    try:
        with open(USERS_FILE, "w", encoding='utf-8') as f: json.dump(users_data_to_save, f, indent=2, ensure_ascii=False)
    except IOError: st.error("Fehler beim Speichern der Benutzerdaten.")

def load_teams():
    if os.path.exists(TEAM_DATA_FILE):
        try:
            with open(TEAM_DATA_FILE, "r", encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, IOError): st.error("Teamdatei korrupt."); return {}
    return {}

def save_teams(teams_data_to_save):
    try:
        with open(TEAM_DATA_FILE, "w", encoding='utf-8') as f: json.dump(teams_data_to_save, f, indent=2, ensure_ascii=False)
    except IOError: st.error("Fehler beim Speichern der Teamdaten.")

def generate_team_code(): return str(uuid.uuid4().hex[:6].upper())

def get_user_verse_file(username_param):
    safe_username = "".join(c for c in username_param if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_username: safe_username = f"user_{random.randint(1000, 9999)}"
    return os.path.join(USER_DATA_DIR, f"{safe_username}_verses_v2.json")

def load_user_verses(username_param, language_code_param): # Lädt private und kopierte öffentliche Texte
    filepath = get_user_verse_file(username_param)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f: all_lang_data = json.load(f)
            lang_data = all_lang_data.get(language_code_param, {})
            for title, details in lang_data.items():
                details['language'] = language_code_param # Sicherstellen
                # 'public' Flag in user_verses ist jetzt eher 'is_copy_of_public' oder irrelevant,
                # da alle Texte im User File für den User "privat" in der Behandlung sind.
                # Wir können es auf False lassen oder ein `original_public_source: True` hinzufügen.
                details.setdefault('public', False) # Kopien sind nicht mehr 'public' im Sinne der globalen Liste
                
                if details.get("mode") == "random":
                    text_specific_key_base = f"{language_code_param}_{title}"
                    details.setdefault("random_pass_indices_order", [])
                    details.setdefault("random_pass_current_position", 0)
                    details.setdefault("random_pass_shown_count", 0)
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = details["random_pass_indices_order"]
                    st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = details["random_pass_current_position"]
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = details["random_pass_shown_count"]
            return lang_data
        except (json.JSONDecodeError, IOError): st.warning(f"Private Versdatei ({username_param}) korrupt."); return {}
    return {}

def persist_user_text_progress(username_param, language_code_param, text_actual_title_to_save, text_details_to_save):
    # Diese Funktion speichert einen bestimmten Text (privat oder Kopie eines öffentlichen) in der User-Datei
    user_verse_file = get_user_verse_file(username_param)
    all_user_verses_data = {}; lang_specific_data = {}
    if os.path.exists(user_verse_file):
        try:
            with open(user_verse_file, "r", encoding='utf-8') as f: all_user_verses_data = json.load(f)
            lang_specific_data = all_user_verses_data.get(language_code_param, {})
        except (json.JSONDecodeError, IOError): pass 
    
    if text_details_to_save.get("mode") == "random":
        text_specific_key_base = f"{language_code_param}_{text_actual_title_to_save}"
        text_details_to_save["random_pass_indices_order"] = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}', [])
        text_details_to_save["random_pass_current_position"] = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
        text_details_to_save["random_pass_shown_count"] = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}', 0)
        
    lang_specific_data[text_actual_title_to_save] = text_details_to_save
    all_user_verses_data[language_code_param] = lang_specific_data
    try:
        with open(user_verse_file, "w", encoding='utf-8') as f:
            json.dump(all_user_verses_data, f, indent=2, ensure_ascii=False)
    except IOError as e: st.error(f"Fehler beim Speichern des Fortschritts für '{text_actual_title_to_save}': {e}")

def load_public_verses(language_code_param): # Lädt nur die globale Liste öffentlicher Texte
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f: all_lang_data = json.load(f)
            lang_data = all_lang_data.get(language_code_param, {})
            for title, details in lang_data.items(): details['public'] = True; details['language'] = language_code_param
            return lang_data
        except (json.JSONDecodeError, IOError): st.warning("Öffentliche Versdatei korrupt."); return {}
    return {}

def save_public_verses(language_code_param, lang_specific_data_param): # Speichert in die globale Liste
    all_data = {};
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f: all_data = json.load(f)
        except (json.JSONDecodeError, IOError): pass
    all_data[language_code_param] = {title: details for title, details in lang_specific_data_param.items() if details.get('public', True)} # Sicherstellen, dass public=True
    try:
        with open(PUBLIC_VERSES_FILE, "w", encoding='utf-8') as f: json.dump(all_data, f, indent=2, ensure_ascii=False)
    except IOError as e: st.error(f"Fehler beim Speichern öffentlicher Verse: {e}")

# --- UI Hilfsfunktionen ---
def is_format_likely_correct(text_param):
    if not text_param or not isinstance(text_param, str): return False
    lines = [line.strip() for line in text_param.strip().split("\n") if line.strip()]
    if not lines: return False
    first_line_match_new = re.match(r"^\s*([\w\s]+\.?)\s*(\d+)\s*$", lines[0])
    if first_line_match_new and len(lines) > 1 and re.match(r"^\s*(\d+[a-z]*(?:-\d+[a-z]*)?)\s+", lines[1]): return True
    if re.match(r"^\s*\d+\)\s+", lines[0]): return True
    return False

def contains_forbidden_content(text_param):
    if not text_param or not isinstance(text_param, str): return False
    text_lower = text_param.lower(); forbidden_keywords = ["sex","porn","gamble","kill","drogen","nazi","hitler","idiot","arschloch","fick"]
    return any(keyword in text_lower for keyword in forbidden_keywords)

def group_words_into_chunks(words_param, max_chunks_param=MAX_CHUNKS):
    n_words = len(words_param); chunks_list = []
    if n_words == 0: return chunks_list
    num_chunks = min(n_words, max_chunks_param); base_chunk_size = n_words // num_chunks
    remainder = n_words % num_chunks; current_idx_gwic = 0
    for i in range(num_chunks):
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        chunks_list.append(" ".join(words_param[current_idx_gwic : current_idx_gwic + chunk_size])); current_idx_gwic += chunk_size
    return chunks_list

def display_leaderboard_in_sidebar(users_map_param, teams_map_param):
    st.subheader(f"🏆 Einzelspieler Top {LEADERBOARD_SIZE}")
    if users_map_param:
        sorted_users = sorted(users_map_param.items(), key=lambda item: item[1].get('points', 0), reverse=True)
        for i, (username_lb, data_lb) in enumerate(sorted_users[:LEADERBOARD_SIZE]):
            st.markdown(f"<p style='margin-bottom: 0.1rem; line-height: 1.2;'>{i+1}. <b>{username_lb}</b>: {data_lb.get('points', 0)} P.</p>", unsafe_allow_html=True)
    else: st.write("Keine Benutzer.")
    st.subheader(f"🤝 Teams Top {LEADERBOARD_SIZE}")
    if teams_map_param:
        teams_with_calc_points = [{"id": t_id, "name": t_data.get('name', 'N/A'), "points": sum(users_map_param.get(m, {}).get("points", 0) for m in t_data.get("members", []))} for t_id, t_data in teams_map_param.items()]
        sorted_teams = sorted(teams_with_calc_points, key=lambda x: x["points"], reverse=True)
        for i, team_info in enumerate(sorted_teams[:LEADERBOARD_SIZE]):
            st.markdown(f"<p style='margin-bottom: 0.1rem; line-height: 1.2;'>{i+1}. <b>{team_info['name']}</b>: {team_info['points']} P.</p>", unsafe_allow_html=True)
    else: st.write("Keine Teams.")

def highlight_errors(selected_chunks_param, correct_chunks_param):
    html_output = []; matcher = SequenceMatcher(None, correct_chunks_param, selected_chunks_param)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal': html_output.append(" ".join(selected_chunks_param[j1:j2]))
        elif tag == 'replace' or tag == 'insert': html_output.append(f"<span style='color:red; font-weight:bold;'>{' '.join(selected_chunks_param[j1:j2])}</span>")
    return " ".join(filter(None, html_output))

# --- App Setup ---
st.set_page_config(layout="wide", page_title="Vers-Lern-App")
if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
if "admin_logged_in" not in st.session_state: st.session_state.admin_logged_in = False # NEU für Admin
# ... (weitere Session State Initialisierungen) ...
if "login_error" not in st.session_state: st.session_state.login_error = None
if "register_error" not in st.session_state: st.session_state.register_error = None
if "selected_language" not in st.session_state: st.session_state.selected_language = DEFAULT_LANGUAGE


users = load_users(); teams = load_teams()

# --- Hauptanwendung ---
if st.session_state.logged_in_user:
    username = st.session_state.logged_in_user
    st.sidebar.title(f"Hallo {username}!")
    user_data_global = users.get(username, {})
    st.sidebar.markdown(f"**🏆 Punkte: {user_data_global.get('points', 0)}**")

    if st.sidebar.button("🔒 Logout"):
        current_language_logout = st.session_state.selected_language
        session_title_key_logout = f"selected_display_title_{current_language_logout}"
        if session_title_key_logout in st.session_state:
            current_display_title_logout = st.session_state.get(session_title_key_logout)
            if current_display_title_logout:
                _user_verses = load_user_verses(username, current_language_logout)
                _actual_title = current_display_title_logout.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                if _actual_title in _user_verses: # Es muss im User-Profil sein (entweder privat oder kopiert öffentlich)
                    persist_user_text_progress(username, current_language_logout, _actual_title, _user_verses[_actual_title].copy())
        
        for key_to_clear in list(st.session_state.keys()): del st.session_state[key_to_clear]
        st.session_state.logged_in_user = None; st.session_state.selected_language = DEFAULT_LANGUAGE
        st.session_state.admin_logged_in = False # Admin auch ausloggen
        st.rerun()

    # --- Sidebar Widgets ---
    with st.sidebar.expander("🤝 Teams", expanded=True):
        # ... (Team UI - unverändert) ...
        user_team_id = user_data_global.get('team_id'); current_team_name = "Kein Team"
        if user_team_id and user_team_id in teams:
            current_team_name = teams[user_team_id].get('name', 'N/A')
            st.markdown(f"Team: **{current_team_name}** (`{teams[user_team_id].get('code')}`)")
            if st.button("Verlassen", key="leave_team_btn_sb_v4"):
                old_team_id = users[username]['team_id']; users[username]['team_id'] = None
                if old_team_id and old_team_id in teams and username in teams[old_team_id].get('members', []):
                    teams[old_team_id]['members'].remove(username)
                save_users(users); save_teams(teams); st.success("Team verlassen."); st.rerun()
        else:
            st.markdown(f"Team: {current_team_name}")
            st.write("Erstellen:"); new_team_name = st.text_input("Teamname", key="new_team_name_sb_v5")
            if st.button("Ok", key="create_team_btn_sb_v5"):
                if new_team_name:
                    team_id = str(uuid.uuid4()); team_code = generate_team_code()
                    teams[team_id] = {"name": new_team_name, "code": team_code, "members": [username], "points": 0}
                    users[username]['team_id'] = team_id; save_teams(teams); save_users(users)
                    st.success(f"'{new_team_name}' erstellt! Code: {team_code}"); st.rerun()
                else: st.error("Name fehlt.")
            st.write("Beitreten:"); join_code = st.text_input("Team-Code", key="join_code_sb_v5").upper()
            if st.button("Ok", key="join_team_btn_sb_v5"):
                found_id = next((tid for tid, tdata in teams.items() if tdata.get('code') == join_code), None)
                if found_id:
                    users[username]['team_id'] = found_id
                    if username not in teams[found_id].get('members', []): teams[found_id]['members'].append(username)
                    save_users(users); save_teams(teams); st.success(f"'{teams[found_id]['name']}' beigetreten!"); st.rerun()
                else: st.error("Code ungültig.")

    with st.sidebar.expander("🏆 Leaderboard", expanded=False):
        display_leaderboard_in_sidebar(users, teams)
    
    with st.sidebar.expander("📊 Statistiken", expanded=False):
        st.subheader("Deine Statistiken"); st.markdown(f"⏳ Zeit: {user_data_global.get('learning_time_seconds', 0)} Sek.")
        st.markdown(f"📖 Verse: {user_data_global.get('total_verses_learned', 0)}")
        st.markdown(f"✍️ Wörter: {user_data_global.get('total_words_learned', 0)}")

    # MODIFIED: "Öffentlich" Option entfernt, nur private Texte durch User
    with st.sidebar.expander(f"📥 Eigenen Text hinzufügen", expanded=False):
        new_title_sidebar = st.text_input("Titel", key=f"new_title_sidebar_v6_{st.session_state.selected_language}").strip()
        new_text_sidebar = st.text_area("Textinhalt", height=150, key=f"new_text_sidebar_v6_{st.session_state.selected_language}", help="Format: '1) Ref Text...' ODER 'Buch Kapt.\\n1 Text...'").strip()
        if st.button("Privaten Text speichern", key=f"save_btn_sidebar_v6_{st.session_state.selected_language}"):
            current_lang_for_save = st.session_state.selected_language
            if not new_title_sidebar: st.sidebar.error("Titel fehlt.")
            elif not new_text_sidebar: st.sidebar.error("Text fehlt.")
            elif not is_format_likely_correct(new_text_sidebar): st.sidebar.error(f"Format? [Hilfe](...)")
            elif contains_forbidden_content(new_text_sidebar): st.sidebar.error("Inhalt? Prüfen.")
            else:
                try:
                    parsed_verses = parse_verses_from_text(new_text_sidebar)
                    if parsed_verses:
                        _user_verses_private_sidebar = load_user_verses(username, current_lang_for_save)
                        if new_title_sidebar in _user_verses_private_sidebar: st.sidebar.warning("Privater Text wird überschrieben.")
                        _user_verses_private_sidebar[new_title_sidebar] = {"verses": parsed_verses, "mode": "linear", "last_index": 0, "completed_linear": False, "public": False, "language": current_lang_for_save}
                        # Speichere alle privaten Texte für diese Sprache direkt in der User-Datei
                        persist_user_text_progress(username, current_lang_for_save, new_title_sidebar, _user_verses_private_sidebar[new_title_sidebar])
                        st.sidebar.success("Privater Text gespeichert!"); st.rerun()
                    else: st.sidebar.error("Text konnte nicht geparsed werden (Format?).")
                except Exception as e_sidebar: st.sidebar.error(f"Fehler: {e_sidebar}")

    # NEU: Admin Bereich
    with st.sidebar.expander("🔑 Admin", expanded=False):
        if not st.session_state.admin_logged_in:
            admin_pw_input = st.text_input("Admin-Passwort", type="password", key="admin_pw_input")
            if st.button("Admin Login", key="admin_login_btn"):
                if admin_pw_input == ADMIN_PASSWORD:
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.error("Falsches Admin-Passwort.")
        
        if st.session_state.admin_logged_in:
            st.success("Admin eingeloggt.")
            st.subheader("Öffentlichen Bibeltext hinzufügen")
            admin_new_title = st.text_input("Titel (öffentlich)", key="admin_new_title").strip()
            admin_new_text = st.text_area("Textinhalt (öffentlich)", height=150, key="admin_new_text", help="Format: '1) Ref Text...' ODER 'Buch Kapt.\\n1 Text...'").strip()
            admin_lang_options = list(LANGUAGES.keys())
            admin_lang_display = [LANGUAGES[k] for k in admin_lang_options]
            admin_selected_lang_idx = admin_lang_options.index(st.session_state.selected_language) if st.session_state.selected_language in admin_lang_options else 0
            admin_selected_lang_display = st.selectbox("Sprache für öffentlichen Text", admin_lang_display, index=admin_selected_lang_idx, key="admin_lang_select")
            admin_selected_lang_key = next(key for key, value in LANGUAGES.items() if value == admin_selected_lang_display)

            if st.button("Öffentlichen Text speichern", key="admin_save_public_text"):
                if not admin_new_title: st.error("Titel fehlt.")
                elif not admin_new_text: st.error("Text fehlt.")
                elif not is_format_likely_correct(admin_new_text): st.error("Format?")
                # Keine Inhaltsprüfung für Admin? Oder doch? Vorerst nicht.
                else:
                    try:
                        parsed_admin_verses = parse_verses_from_text(admin_new_text)
                        if parsed_admin_verses:
                            _public_verses_admin = load_public_verses(admin_selected_lang_key)
                            if admin_new_title in _public_verses_admin: st.error(f"Öffentlicher Titel '{admin_new_title}' existiert.")
                            else:
                                _public_verses_admin[admin_new_title] = {"verses": parsed_admin_verses, "public": True, "language": admin_selected_lang_key}
                                save_public_verses(admin_selected_lang_key, _public_verses_admin)
                                st.success("Öffentlicher Text durch Admin gespeichert!"); 
                                # Kein Rerun, damit Admin ggf. weitere Texte eingeben kann
                        else: st.error("Text (Admin) konnte nicht geparsed werden.")
                    except Exception as e_admin: st.error(f"Admin Fehler: {e_admin}")
            if st.button("Admin Logout", key="admin_logout_btn"):
                st.session_state.admin_logged_in = False
                st.rerun()
    
    # --- Hauptbereich (Lernen) ---
    st.title("📖 Vers-Lern-App") 
    sel_col1, sel_col2, sel_col3 = st.columns([1, 2, 1]) 

    with sel_col1: # Sprache
        lang_options = list(LANGUAGES.keys()); lang_display = [LANGUAGES[k] for k in lang_options]
        idx_lang = lang_options.index(st.session_state.selected_language)
        selected_lang_display = st.selectbox("Sprache", lang_display, index=idx_lang, key="main_lang_select_v7")
        selected_lang_key = next(key for key, value in LANGUAGES.items() if value == selected_lang_display)
        if selected_lang_key != st.session_state.selected_language:
            old_lang = st.session_state.selected_language; old_title_key = f"selected_display_title_{old_lang}"
            if old_title_key in st.session_state:
                old_title = st.session_state.get(old_title_key)
                if old_title:
                    _user_verses = load_user_verses(username, old_lang)
                    _actual = old_title.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                    if _actual in _user_verses : # Nur speichern, wenn es im User-Profil ist
                        persist_user_text_progress(username, old_lang, _actual, _user_verses[_actual].copy())
            st.session_state.selected_language = selected_lang_key
            for k in list(st.session_state.keys()):
                if k not in ['logged_in_user', 'selected_language', 'admin_logged_in']: del st.session_state[k]
            st.rerun()

    current_language = st.session_state.selected_language
    user_verses_private = load_user_verses(username, current_language) # Enthält jetzt private und kopierte öffentliche
    public_verses_global = load_public_verses(current_language) # Globale Liste für die Auswahl

    available_texts_map = {}; display_titles_list = []
    # 1. Private (inkl. kopierte öffentliche) Texte des Nutzers
    for title, data in user_verses_private.items():
        prefix = f"{COMPLETED_MARKER} " if data.get("completed_linear", False) else ""
        display_titles_list.append(f"{prefix}{title}"); 
        available_texts_map[f"{prefix}{title}"] = {**data, 'source': 'user_profile', 'original_title': title} # Quelle ist jetzt 'user_profile'
    # 2. Rein öffentliche Texte, die der Nutzer noch nicht in seinem Profil hat
    for title, data in public_verses_global.items():
        if title not in user_verses_private: # Nur anzeigen, wenn noch keine Kopie existiert
             display_titles_list.append(f"{PUBLIC_MARKER} {title}"); 
             available_texts_map[f"{PUBLIC_MARKER} {title}"] = {**data, 'source': 'public_global', 'original_title': title}
    
    sorted_display_titles = sorted(list(set(display_titles_list))) # set() zur Vermeidung von Duplikaten, falls Logik Fehler hat

    with sel_col2: # Text
        selected_display_title = None
        if not available_texts_map: st.warning(f"Keine Texte für {LANGUAGES[current_language]}.")
        else:
            session_title_key = f"selected_display_title_{current_language}"
            old_display_title = st.session_state.get(session_title_key)
            current_idx = 0
            if old_display_title in sorted_display_titles: current_idx = sorted_display_titles.index(old_display_title)
            elif sorted_display_titles: st.session_state[session_title_key] = sorted_display_titles[0]

            selected_display_title = st.selectbox("Bibeltext", sorted_display_titles, index=current_idx, key=f"main_selectbox_v7_{username}_{current_language}")
            
            # Logik zum Kopieren öffentlicher Texte ins Nutzerprofil beim ersten Auswählen
            if selected_display_title and selected_display_title in available_texts_map:
                selected_text_info_for_copy = available_texts_map[selected_display_title]
                actual_title_for_copy = selected_text_info_for_copy['original_title']
                
                if selected_text_info_for_copy['source'] == 'public_global' and actual_title_for_copy not in user_verses_private:
                    # st.info(f"'{actual_title_for_copy}' wird ins Profil kopiert...") # DEBUG
                    copied_text_data = {
                        "verses": selected_text_info_for_copy["verses"],
                        "mode": "linear", "last_index": 0, "completed_linear": False,
                        "public": False, # Ist jetzt eine "private" Kopie im User-File
                        "original_public_source": True, # Markierung der Herkunft
                        "language": current_language
                    }
                    user_verses_private[actual_title_for_copy] = copied_text_data
                    persist_user_text_progress(username, current_language, actual_title_for_copy, copied_text_data)
                    # Wichtig: UI muss aktualisiert werden, damit der Text jetzt als User-Text erscheint
                    st.session_state[session_title_key] = actual_title_for_copy # Zeige den "unmarkierten" Titel an
                    st.rerun() # Damit der Text neu geladen wird und ohne [P] erscheint


            if selected_display_title != old_display_title and old_display_title is not None:
                if old_display_title in available_texts_map:
                    old_info = available_texts_map[old_display_title]
                    # Speichere Fortschritt des alten Textes, wenn er aus dem Nutzerprofil kam
                    if old_info['source'] == 'user_profile':
                        old_actual = old_info['original_title']
                        if old_actual in user_verses_private: 
                             persist_user_text_progress(username, current_language, old_actual, user_verses_private[old_actual].copy())
                st.session_state[session_title_key] = selected_display_title
                for k in list(st.session_state.keys()): # State Reset
                    if k not in ['logged_in_user', 'selected_language', session_title_key, 'admin_logged_in']: del st.session_state[k]
                st.rerun()
            elif selected_display_title is not None and session_title_key not in st.session_state :
                 st.session_state[session_title_key] = selected_display_title
    
    actual_title, source_type, total_verses, verses_learn, completed = None, None, 0, [], False
    selected_title = st.session_state.get(f"selected_display_title_{current_language}")
    if selected_title and selected_title in available_texts_map:
        info = available_texts_map[selected_title]
        source_type = info['source'] # 'user_profile' oder 'public_global'
        actual_title = info.get('original_title', selected_title.replace(f"{COMPLETED_MARKER} ", "").replace(f"{PUBLIC_MARKER} ", ""))
        
        # Lerne immer aus user_verses_private, wenn vorhanden (d.h. es ist privat oder eine Kopie)
        if actual_title in user_verses_private:
            current_text_data_to_learn = user_verses_private[actual_title]
            source_type = 'user_profile' # Überschreiben, da wir jetzt die User-Kopie nehmen
        elif source_type == 'public_global' and actual_title in public_verses_global: # Fallback auf globale öffentliche Liste (sollte durch Kopierlogik selten sein)
            current_text_data_to_learn = public_verses_global[actual_title]
        else: # Sollte nicht passieren, wenn selected_title valide ist
            current_text_data_to_learn = {}

        verses_learn = current_text_data_to_learn.get("verses", []); total_verses = len(verses_learn)
        if source_type == 'user_profile': # Completion-Status nur für Texte im User-Profil relevant
            completed = current_text_data_to_learn.get("completed_linear", False)


    with sel_col3: # Modus
        opts = {"linear": "Linear", "random": "Zufällig"}; display_opts = list(opts.values())
        default = "linear"; mode = default
        if selected_title and actual_title:
            current_text_for_mode = user_verses_private.get(actual_title) if actual_title in user_verses_private else {}
            default = current_text_for_mode.get("mode", "linear") if current_text_for_mode else "linear"
                
            key = f"selected_mode_{current_language}_{selected_title}"; old_mode = st.session_state.get(key)
            if key not in st.session_state: st.session_state[key] = default
            current_mode_display = opts.get(st.session_state[key], opts["linear"]) # Sicherer Zugriff
            selected_display = st.selectbox("Modus", display_opts, index=display_opts.index(current_mode_display), key=f"mode_sel_v7_{username}_{current_language}_{selected_title}")
            internal_mode = next(k for k, v in opts.items() if v == selected_display)
            if internal_mode != old_mode and old_mode is not None :
                 st.session_state[key] = internal_mode
                 if actual_title in user_verses_private: # Modus wird nur für Texte im Userprofil gespeichert
                     details = user_verses_private[actual_title].copy(); details["mode"] = internal_mode
                     if internal_mode == "random":
                         rand_key = f"{current_language}_{actual_title}"
                         st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                         st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
                     persist_user_text_progress(username, current_language, actual_title, details)
                 # State Reset
                 for k in list(st.session_state.keys()):
                     if k not in ['logged_in_user', 'selected_language', f"selected_display_title_{current_language}", key, 'admin_logged_in']: del st.session_state[k]
                 st.rerun()
            mode = st.session_state.get(key, default)
    
    idx = 0; idx_key = f"current_verse_index_{current_language}_{selected_title}"
    if selected_title and total_verses > 0 and actual_title:
        # ... (idx Bestimmung - wie zuvor, aber sicherstellen, dass 'user_verses_private' für 'completed' und 'last_index' verwendet wird, wenn Text dort ist) ...
        current_text_for_idx = user_verses_private.get(actual_title) if actual_title in user_verses_private else {}
        if mode == 'linear':
            start = 0
            if current_text_for_idx: # Text ist im User-Profil (privat oder kopiert öffentlich)
                is_comp = current_text_for_idx.get("completed_linear", False)
                if is_comp:
                    msg_key = f"completed_msg_shown_{current_language}_{actual_title}"
                    if not st.session_state.get(msg_key, False):
                        st.success("Super Big Amen! Text abgeschlossen."); st.session_state[msg_key] = True
                    start = 0 
                else:
                    start = current_text_for_idx.get("last_index", 0)
                    msg_key_else = f"completed_msg_shown_{current_language}_{actual_title}"
                    if msg_key_else in st.session_state: del st.session_state[msg_key_else]
            else: # Rein öffentlicher Text, der noch nicht kopiert wurde (sollte selten sein durch Kopierlogik)
                start = st.session_state.get(idx_key, 0) # Session-basierter Index für rein öffentliche
            idx = st.session_state.get(idx_key, start)
            idx = max(0, min(idx, total_verses - 1)) if total_verses > 0 else 0
            st.session_state[idx_key] = idx
        elif mode == 'random':
            # ... (Random idx Logik - unverändert) ...
            rand_key = f"{current_language}_{actual_title}"
            if f'random_pass_indices_order_{rand_key}' not in st.session_state or \
               (not st.session_state.get(f'random_pass_indices_order_{rand_key}') and total_verses > 0) :
                st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
            pos = st.session_state.get(f'random_pass_current_position_{rand_key}', 0)
            order = st.session_state.get(f'random_pass_indices_order_{rand_key}', [])
            if pos >= len(order) and total_verses > 0 : # Pass Ende oder leere Liste
                order = random.sample(range(total_verses), total_verses); pos = 0
                st.session_state[f'random_pass_indices_order_{rand_key}'] = order
                st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
            idx = order[pos] if order and pos < len(order) else 0 
            st.session_state[idx_key] = idx


    # --- Fortschrittsbalken ---
    if selected_title and total_verses > 0 and actual_title:
        progress_bar_completed_ui = False
        # 'completed' bezieht sich auf den Status im user_verses_private (für private und kopierte öffentliche)
        if mode == 'linear' and completed: progress_bar_completed_ui = True
        
        if progress_bar_completed_ui:
            progress_html = """<div style="background-color:#e6ffed;border:1px solid #b3e6c5;border-radius:5px;padding:2px;margin-bottom:5px;"><div style="background-color:#4CAF50;width:100%;height:10px;border-radius:3px;"></div></div><div style="text-align:center;font-size:0.9em;color:#4CAF50;">Abgeschlossen!</div>"""
            st.markdown(progress_html, unsafe_allow_html=True)
        elif mode == 'linear':
            st.progress((idx + 1) / total_verses if total_verses > 0 else 0, text=f"Linear: {idx + 1}/{total_verses}")
        elif mode == 'random':
            rand_key_pb = f"{current_language}_{actual_title}"; num_shown_pb = min(st.session_state.get(f'random_pass_shown_count_{rand_key_pb}', 0), total_verses)
            st.progress(num_shown_pb / total_verses if total_verses > 0 else 0, text=f"Zufällig: {num_shown_pb}/{total_verses}")
    
    # --- Lernlogik ---
    if selected_title and verses_learn and total_verses > 0 and actual_title:
        # ... (Lernlogik, aber mit angepasster Persistenz und Auto-Advance) ...
        if not (0 <= idx < total_verses): idx = 0 
        if total_verses == 0 and idx == 0 : st.info("Keine Verse."); st.stop()
        verse = verses_learn[idx]; tokens = verse.get("text", "").split(); chunks = group_words_into_chunks(tokens); n_chunks = len(chunks)
        if not tokens or not chunks:
             st.warning(f"Vers '{verse.get('ref', '')}' leer/ungültig.")
             if st.button("Nächsten laden", key=f"skip_v7_{idx}"): st.rerun()
        else: 
            key_base_learn = f"{current_language}_{actual_title}_{verse.get('ref', idx)}" # Eindeutiger Key
            if f"s_chunks_{key_base_learn}" not in st.session_state or st.session_state.get("current_ref") != verse.get("ref"):
                st.session_state[f"s_chunks_{key_base_learn}"]=random.sample(chunks,n_chunks); st.session_state[f"sel_chunks_{key_base_learn}"]=[]
                st.session_state[f"used_chunks_{key_base_learn}"]=[False]*n_chunks; st.session_state[f"feedback_{key_base_learn}"]=False
                st.session_state["current_ref"]=verse.get("ref"); st.session_state["cv_data"]={"ref":verse.get("ref"),"text":verse.get("text"),"o_chunks":chunks,"tokens":tokens}
                st.session_state[f"pts_awarded_{key_base_learn}"]=False; st.session_state[f"start_time_{key_base_learn}"]=time.time()

            s_chunks = st.session_state[f"s_chunks_{key_base_learn}"]
            sel_chunks = st.session_state[f"sel_chunks_{key_base_learn}"]
            used = st.session_state[f"used_chunks_{key_base_learn}"]
            
            st.markdown(f"### {VERSE_EMOJI} {verse.get('ref')}")
            
            btn_idx = 0
            for r in range(math.ceil(n_chunks / COLS_PER_ROW)):
                cols = st.columns(COLS_PER_ROW)
                for c in range(COLS_PER_ROW):
                    if btn_idx < n_chunks:
                        disp_idx = btn_idx; txt = s_chunks[disp_idx]; is_used = used[disp_idx]
                        btn_key = f"btn_v7_{disp_idx}_{key_base_learn}"
                        with cols[c]:
                            if is_used: st.button(f"~~{txt}~~",key=btn_key,disabled=True,use_container_width=True)
                            else:
                                if st.button(txt,key=btn_key,use_container_width=True):
                                    sel_chunks.append((txt,disp_idx));used[disp_idx]=True
                                    st.session_state[f"sel_chunks_{key_base_learn}"]=sel_chunks;st.session_state[f"used_chunks_{key_base_learn}"]=used
                                    if len(sel_chunks)==n_chunks:st.session_state[f"feedback_{key_base_learn}"]=True
                                    st.rerun()
                        btn_idx += 1
            st.markdown("---"); cols_sel = st.columns([5,1])
            with cols_sel[0]: st.markdown(f"```{' '.join([i[0] for i in sel_chunks]) if sel_chunks else '*Auswählen...*'}```")
            with cols_sel[1]:
                 if st.button("↩️",key=f"undo_v7_{key_base_learn}",help="Zurück",disabled=not sel_chunks):
                      if sel_chunks:
                          _,orig_idx=sel_chunks.pop();used[orig_idx]=False
                          st.session_state[f"sel_chunks_{key_base_learn}"]=sel_chunks;st.session_state[f"used_chunks_{key_base_learn}"]=used
                          if st.session_state.get(f"feedback_{key_base_learn}",False) and len(sel_chunks)<n_chunks:st.session_state[f"feedback_{key_base_learn}"]=False
                          st.rerun()
            st.markdown("---")

            feedback = st.session_state.get(f"feedback_{key_base_learn}", False)
            if feedback:
                u_chunks=[i[0] for i in sel_chunks];u_text=" ".join(u_chunks)
                cv_data=st.session_state.get("cv_data",{});correct_txt=cv_data.get("text","");correct_chunks=cv_data.get("o_chunks",[])
                tokens_count=len(cv_data.get("tokens",[]));is_correct=(u_text==correct_txt)

                if is_correct:
                    pts_awarded = st.session_state.get(f"pts_awarded_{key_base_learn}", False)
                    is_last_verse = (idx == total_verses - 1)
                    
                    if not pts_awarded: # Punkte und Stats nur einmalig
                        users[username]["points"] = users[username].get("points",0) + tokens_count
                        start = st.session_state.get(f"start_time_{key_base_learn}", time.time()); duration = time.time() - start
                        users[username]['learning_time_seconds'] += int(duration); users[username]['total_verses_learned'] += 1
                        users[username]['total_words_learned'] += tokens_count
                        team_id = users[username].get('team_id')
                        if team_id and team_id in teams: teams[team_id]['points'] = teams[team_id].get('points',0) + tokens_count; save_teams(teams)
                        save_users(users); st.session_state[f"pts_awarded_{key_base_learn}"] = True
                    
                    st.success("✅ Richtig!") # Erfolgsmeldung immer anzeigen
                    st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'><b>{correct_txt}</b></div>", unsafe_allow_html=True)

                    # --- PERSISTENZ & COMPLETION ---
                    text_completed_this_turn = False
                    current_text_details_for_save = None

                    if actual_title in user_verses_private: # Nur für Texte im User-Profil (private oder kopierte öffentliche)
                        _latest_user_verses = load_user_verses(username, current_language) # Immer frische Daten laden
                        if actual_title in _latest_user_verses:
                            current_text_details_for_save = _latest_user_verses[actual_title] # Direkte Referenz für Modifikation

                            if mode == 'linear':
                                if is_last_verse:
                                    if not current_text_details_for_save.get("completed_linear", False):
                                        current_text_details_for_save["completed_linear"] = True
                                        current_text_details_for_save["last_index"] = 0 
                                        st.session_state[f"completed_msg_shown_{current_language}_{actual_title}"] = False # Damit Meldung neu kommt
                                        completed = True # Für UI-Update in diesem Lauf (Balken)
                                        text_completed_this_turn = True
                                        st.success("Super Big Amen! Text abgeschlossen!")
                                        if not pts_awarded: st.balloons() # Ballons nur wenn auch Punkte vergeben
                                elif not current_text_details_for_save.get("completed_linear"): # Normaler Fortschritt
                                    current_text_details_for_save["last_index"] = (idx + 1) % total_verses
                            
                            persist_user_text_progress(username, current_language, actual_title, current_text_details_for_save)

                    # --- Auto-Advance Handling (MODIFIED) ---
                    if not is_last_verse: # Nur auto-advancen, wenn NICHT der letzte Vers war
                        st.markdown("➡️ Nächster Vers...")
                        time.sleep(AUTO_ADVANCE_DELAY)
                    # Ansonsten (letzter Vers) wird der Timer übersprungen, Meldung wurde oben angezeigt
                    
                    # --- Finales Speichern (Random) & Rerun ---
                    next_idx_ui_final = idx # Für UI-Update
                    if actual_title in user_verses_private and mode == 'random': # Random-Fortschritt immer für User-Texte speichern
                        _final_verses_rand = load_user_verses(username, current_language)
                        if actual_title in _final_verses_rand:
                            final_details_rand = _final_verses_rand[actual_title]
                            rand_key_final = f"{current_language}_{actual_title}"
                            pos = st.session_state.get(f'random_pass_current_position_{rand_key_final}', 0)
                            shown = st.session_state.get(f'random_pass_shown_count_{rand_key_final}',0)
                            order = st.session_state.get(f'random_pass_indices_order_{rand_key_final}',[])
                            if pos < len(order): st.session_state[f'random_pass_shown_count_{rand_key_final}'] = shown + 1
                            st.session_state[f'random_pass_current_position_{rand_key_final}'] = pos + 1
                            persist_user_text_progress(username, current_language, actual_title, final_details_rand)
                    
                    if mode == 'linear': # UI Index für nächsten Lauf setzen
                        next_idx_ui_final = 0 if is_last_verse else (idx + 1) % total_verses
                    
                    st.session_state[idx_key] = next_idx_ui_final 

                    for k_del in list(st.session_state.keys()):
                         if key_base_learn in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                    st.rerun() # Immer Rerun nach korrekt

                else: # Falsche Antwort
                    st.error("❌ Leider falsch.")
                    highlighted = highlight_errors(u_chunks, correct_chunks)
                    st.markdown("<b>Deine Eingabe:</b>", unsafe_allow_html=True)
                    st.markdown(f"<div style='background-color:#ffebeb; color:#8b0000; padding:10px; border-radius:5px;'>{highlighted}</div>", unsafe_allow_html=True)
                    st.markdown("<b>Korrekt wäre:</b>", unsafe_allow_html=True)
                    st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'>{correct_txt}</div>", unsafe_allow_html=True)
                    st.session_state[f"pts_awarded_{key_base_learn}"] = False

                    cols_fb = st.columns([1,1.5,1])
                    with cols_fb[0]: 
                        show_prev = (mode == 'linear' and total_verses > 1 and idx > 0)
                        if st.button("⬅️ Zurück", key=f"prev_v7_{key_base_learn}", disabled=not show_prev, use_container_width=True):
                            next_idx_prev = idx - 1
                            if actual_title in user_verses_private and mode == 'linear':
                                details = load_user_verses(username, current_language).get(actual_title, {}).copy()
                                if details: details["last_index"] = next_idx_prev; persist_user_text_progress(username, current_language, actual_title, details)
                            st.session_state[idx_key] = next_idx_prev
                            for k_del in list(st.session_state.keys()):
                                 if key_base_learn in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                            st.rerun()
                    with cols_fb[2]: 
                        if st.button("➡️ Nächster", key=f"next_v7_{key_base_learn}", use_container_width=True):
                            next_idx_ui_next = idx 
                            if actual_title in user_verses_private: # Gilt für private und kopierte öffentliche
                                details = load_user_verses(username, current_language).get(actual_title, {}).copy()
                                if details:
                                    if mode == 'linear': next_idx_ui_next = (idx + 1) % total_verses; details["last_index"] = next_idx_ui_next
                                    elif mode == 'random': 
                                        rand_key_fb = f"{current_language}_{actual_title}"; pos = st.session_state.get(f'random_pass_current_position_{rand_key_fb}', 0)
                                        shown = st.session_state.get(f'random_pass_shown_count_{rand_key_fb}',0); order = st.session_state.get(f'random_pass_indices_order_{rand_key_fb}',[])
                                        if pos < len(order): st.session_state[f'random_pass_shown_count_{rand_key_fb}'] = shown + 1
                                        st.session_state[f'random_pass_current_position_{rand_key_fb}'] = pos + 1; next_idx_ui_next = idx 
                                    persist_user_text_progress(username, current_language, actual_title, details)
                            elif mode == 'linear': next_idx_ui_next = (idx + 1) % total_verses # Für rein öffentliche Texte ohne User-Kopie
                            st.session_state[idx_key] = next_idx_ui_next
                            for k_del in list(st.session_state.keys()):
                                 if key_base_learn in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                            st.rerun()
else: # Nicht eingeloggt
    st.sidebar.title("🔐 Anmeldung"); login_tab, register_tab = st.sidebar.tabs(["Login", "Registrieren"])
    with login_tab:
        st.subheader("Login"); login_user = st.text_input("Benutzername", key="li_user_v8")
        login_pw = st.text_input("Passwort", type="password", key="li_pw_v8")
        if st.button("Login", key="li_btn_v8"):
            user_data = users.get(login_user)
            if user_data and verify_password(user_data.get("password_hash", ""), login_pw):
                st.session_state.logged_in_user = login_user; st.session_state.login_error = None
                if "register_error" in st.session_state: del st.session_state.register_error
                st.session_state.selected_language = DEFAULT_LANGUAGE; st.session_state.admin_logged_in = False; st.rerun()
            else: st.session_state.login_error = "Name/Passwort ungültig."
            if st.session_state.login_error : st.error(st.session_state.login_error)
    with register_tab:
        st.subheader("Registrieren"); reg_user = st.text_input("Benutzername", key="reg_user_v8")
        reg_pw = st.text_input("Passwort (min. 6 Z.)", type="password", key="reg_pw_v8")
        reg_confirm = st.text_input("Passwort bestätigen", type="password", key="reg_confirm_v8")
        if st.button("Registrieren", key="reg_btn_v8"):
            if not reg_user or not reg_pw or not reg_confirm: st.session_state.register_error = "Alle Felder ausfüllen."
            elif reg_pw != reg_confirm: st.session_state.register_error = "Passwörter ungleich."
            elif reg_user in users: st.session_state.register_error = "Name vergeben."
            elif len(reg_pw) < 6: st.session_state.register_error = "Passwort zu kurz."
            else:
                 pw_hash = hash_password(reg_pw)
                 users[reg_user] = {"password_hash": pw_hash, "points": 0, "team_id": None, "learning_time_seconds": 0, "total_verses_learned": 0, "total_words_learned": 0}
                 save_users(users); st.session_state.logged_in_user = reg_user; st.session_state.register_error = None
                 if "login_error" in st.session_state: del st.session_state.login_error
                 st.session_state.selected_language = DEFAULT_LANGUAGE; st.session_state.admin_logged_in = False; 
                 st.success("Registriert & angemeldet!"); st.rerun()
            if st.session_state.register_error : st.error(st.session_state.register_error)
    st.title("📖 Vers-Lern-App")
    st.markdown("Bitte melde dich an oder registriere dich.")
    with st.sidebar.expander("🏆 Leaderboard", expanded=False): display_leaderboard_in_sidebar(users, teams)
    with st.sidebar.expander("📊 Statistiken", expanded=False): st.write("Melde dich an für Statistiken.")
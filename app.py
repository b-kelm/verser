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

MAX_CHUNKS = 8
COLS_PER_ROW = 4
LEADERBOARD_SIZE = 7
AUTO_ADVANCE_DELAY = 2 # Sekunden

LANGUAGES = {
    "DE": "🇩🇪 Deutsch",
    "EN": "🇬🇧 English",
}
DEFAULT_LANGUAGE = "DE"
PUBLIC_MARKER = "[P]"
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

def load_user_verses(username_param, language_code_param):
    filepath = get_user_verse_file(username_param)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f: all_lang_data = json.load(f)
            lang_data = all_lang_data.get(language_code_param, {})
            for title, details in lang_data.items():
                details['public'] = False; details['language'] = language_code_param
                if details.get("mode") == "random":
                    text_specific_key_base = f"{language_code_param}_{title}"
                    details.setdefault("random_pass_indices_order", [])
                    details.setdefault("random_pass_current_position", 0)
                    details.setdefault("random_pass_shown_count", 0)
                    # Load into session state only if not already present or different? 
                    # For simplicity, load always, might override mid-session changes if not careful.
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = details["random_pass_indices_order"]
                    st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = details["random_pass_current_position"]
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = details["random_pass_shown_count"]
            return lang_data
        except (json.JSONDecodeError, IOError): st.warning(f"Private Versdatei für {username_param} korrupt."); return {}
    return {}

def persist_current_private_text_progress(username_param, language_code_param, text_actual_title_to_save, text_details_to_save):
    """Speichert die übergebenen text_details für einen spezifischen privaten Text."""
    if text_details_to_save.get('public', False): return # Safety check
    user_verse_file = get_user_verse_file(username_param)
    all_user_verses_data = {}; lang_specific_data = {}
    if os.path.exists(user_verse_file):
        try:
            with open(user_verse_file, "r", encoding='utf-8') as f: all_user_verses_data = json.load(f)
            lang_specific_data = all_user_verses_data.get(language_code_param, {})
        except (json.JSONDecodeError, IOError): pass 
    
    # Update Random-Pass-Details aus Session State direkt vor dem Speichern
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
    except IOError as e: st.error(f"Fehler beim Speichern des Fortschritts: {e}")

def load_public_verses(language_code_param):
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f: all_lang_data = json.load(f)
            lang_data = all_lang_data.get(language_code_param, {})
            for title, details in lang_data.items(): details['public'] = True; details['language'] = language_code_param
            return lang_data
        except (json.JSONDecodeError, IOError): st.warning("Öffentliche Versdatei korrupt."); return {}
    return {}

def save_public_verses(language_code_param, lang_specific_data_param):
    all_data = {};
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f: all_data = json.load(f)
        except (json.JSONDecodeError, IOError): pass
    all_data[language_code_param] = {title: details for title, details in lang_specific_data_param.items() if details.get('public', False)}
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

# --- Session State Initialisierung ---
if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
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
                _user_verses = load_user_verses(username, current_language_logout) # Load fresh before potential save
                _actual_title = current_display_title_logout.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                if _actual_title in _user_verses and not _user_verses[_actual_title].get('public'):
                    persist_current_private_text_progress(username, current_language_logout, _actual_title, _user_verses[_actual_title].copy())
        for key_to_clear in list(st.session_state.keys()): del st.session_state[key_to_clear]
        st.session_state.logged_in_user = None; st.session_state.selected_language = DEFAULT_LANGUAGE
        st.rerun()

    # --- Sidebar Widgets ---
    with st.sidebar.expander("🤝 Teams", expanded=True):
        user_team_id = user_data_global.get('team_id'); current_team_name = "Kein Team"
        if user_team_id and user_team_id in teams:
            current_team_name = teams[user_team_id].get('name', 'N/A')
            st.markdown(f"Team: **{current_team_name}** (`{teams[user_team_id].get('code')}`)")
            if st.button("Verlassen", key="leave_team_btn_sb_v2"):
                old_team_id = users[username]['team_id']; users[username]['team_id'] = None
                if old_team_id and old_team_id in teams and username in teams[old_team_id].get('members', []):
                    teams[old_team_id]['members'].remove(username)
                save_users(users); save_teams(teams); st.success("Team verlassen."); st.rerun()
        else:
            st.markdown(f"Team: {current_team_name}")
            st.write("Erstellen:"); new_team_name = st.text_input("Teamname", key="new_team_name_sb_v3")
            if st.button("Ok", key="create_team_btn_sb_v3"):
                if new_team_name:
                    team_id = str(uuid.uuid4()); team_code = generate_team_code()
                    teams[team_id] = {"name": new_team_name, "code": team_code, "members": [username], "points": 0}
                    users[username]['team_id'] = team_id; save_teams(teams); save_users(users)
                    st.success(f"'{new_team_name}' erstellt! Code: {team_code}"); st.rerun()
                else: st.error("Name fehlt.")
            st.write("Beitreten:"); join_code = st.text_input("Team-Code", key="join_code_sb_v3").upper()
            if st.button("Ok", key="join_team_btn_sb_v3"):
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

    with st.sidebar.expander(f"📥 Text hinzufügen", expanded=False):
        title = st.text_input("Titel", key=f"title_sb_v4_{st.session_state.selected_language}").strip()
        text = st.text_area("Textinhalt", height=150, key=f"text_sb_v4_{st.session_state.selected_language}", help="Format: '1) Ref Text...' ODER 'Buch Kapt.\\n1 Text...'").strip()
        public = st.checkbox("Öffentlich?", key=f"public_cb_v4_{st.session_state.selected_language}", value=False)
        if st.button("Speichern", key=f"save_btn_sb_v4_{st.session_state.selected_language}"):
            lang = st.session_state.selected_language
            if not title: st.sidebar.error("Titel fehlt."); st.stop()
            if not text: st.sidebar.error("Text fehlt."); st.stop()
            if not is_format_likely_correct(text): st.sidebar.error(f"Format? [Hilfe](...)"); st.stop()
            if contains_forbidden_content(text): st.sidebar.error("Inhalt? Prüfen."); st.stop()
            try:
                parsed = parse_verses_from_text(text)
                if parsed:
                    if public:
                        _public = load_public_verses(lang)
                        if title in _public: st.sidebar.error(f"Titel existiert."); st.stop()
                        _public[title] = {"verses": parsed, "public": True, "added_by": username, "language": lang}
                        save_public_verses(lang, _public); st.sidebar.success("Öffentlich gespeichert!"); st.rerun()
                    else: 
                        _private = load_user_verses(username, lang)
                        if title in _private: st.sidebar.warning("Überschrieben.")
                        _private[title] = {"verses": parsed, "mode": "linear", "last_index": 0, "completed_linear": False, "public": False, "language": lang}
                        file = get_user_verse_file(username); all_data = {}
                        if os.path.exists(file):
                             with open(file, "r", encoding='utf-8') as f: all_data = json.load(f)
                        all_data[lang] = _private
                        with open(file, "w", encoding='utf-8') as f: json.dump(all_data, f, indent=2, ensure_ascii=False)
                        st.sidebar.success("Privat gespeichert!"); st.rerun()
                else: st.sidebar.error("Parsen fehlgeschlagen.")
            except Exception as e: st.sidebar.error(f"Fehler: {e}")
    
    # --- Hauptbereich (Lernen) ---
    st.title("📖 Vers-Lern-App") 
    sel_col1, sel_col2, sel_col3 = st.columns([1, 2, 1]) 

    with sel_col1: # Sprache
        lang_options = list(LANGUAGES.keys()); lang_display = [LANGUAGES[k] for k in lang_options]
        idx_lang = lang_options.index(st.session_state.selected_language) # Sicherstellen, dass Index gültig ist
        selected_lang_display = st.selectbox("Sprache", lang_display, index=idx_lang, key="main_lang_select_v5")
        selected_lang_key = next(key for key, value in LANGUAGES.items() if value == selected_lang_display)
        if selected_lang_key != st.session_state.selected_language:
            old_lang = st.session_state.selected_language; old_title_key = f"selected_display_title_{old_lang}"
            if old_title_key in st.session_state:
                old_title = st.session_state.get(old_title_key)
                if old_title:
                    _verses = load_user_verses(username, old_lang); _actual = old_title.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                    if _actual in _verses and not _verses[_actual].get('public'): persist_current_private_text_progress(username, old_lang, _actual, _verses[_actual].copy())
            st.session_state.selected_language = selected_lang_key
            for k in list(st.session_state.keys()): # State Reset
                if k not in ['logged_in_user', 'selected_language']: del st.session_state[k]
            st.rerun()

    current_language = st.session_state.selected_language
    user_verses_private = load_user_verses(username, current_language)
    public_verses = load_public_verses(current_language)
    available_texts_map = {}; display_titles_list = []
    for title, data in user_verses_private.items():
        prefix = f"{COMPLETED_MARKER} " if data.get("completed_linear", False) else ""
        display_titles_list.append(f"{prefix}{title}"); available_texts_map[f"{prefix}{title}"] = {**data, 'source': 'private', 'original_title': title}
    for title, data in public_verses.items():
        display_titles_list.append(f"{PUBLIC_MARKER} {title}"); available_texts_map[f"{PUBLIC_MARKER} {title}"] = {**data, 'source': 'public', 'original_title': title}
    sorted_display_titles = sorted(display_titles_list)

    with sel_col2: # Text
        selected_display_title = None
        if not available_texts_map: st.warning(f"Keine Texte für {LANGUAGES[current_language]}.")
        else:
            session_title_key = f"selected_display_title_{current_language}"
            old_display_title = st.session_state.get(session_title_key)
            current_idx = 0
            if old_display_title in sorted_display_titles: current_idx = sorted_display_titles.index(old_display_title)
            elif sorted_display_titles: st.session_state[session_title_key] = sorted_display_titles[0] # Fallback wenn alter Titel weg ist

            selected_display_title = st.selectbox("Bibeltext", sorted_display_titles, index=current_idx, key=f"main_selectbox_v5_{username}_{current_language}")
            if selected_display_title != old_display_title and old_display_title is not None:
                if old_display_title in available_texts_map:
                    old_info = available_texts_map[old_display_title]
                    if old_info['source'] == 'private':
                        old_actual = old_info['original_title']
                        if old_actual in user_verses_private: persist_current_private_text_progress(username, current_language, old_actual, user_verses_private[old_actual].copy())
                st.session_state[session_title_key] = selected_display_title
                # State Reset Logik (vereinfacht)
                for k in list(st.session_state.keys()):
                    if k not in ['logged_in_user', 'selected_language', session_title_key]: del st.session_state[k]
                st.rerun()
            elif selected_display_title is not None and session_title_key not in st.session_state :
                 st.session_state[session_title_key] = selected_display_title
    
    actual_title, is_public, total_verses, verses_learn, completed = None, False, 0, [], False # Umbenannt 'is_public_text', 'current_text_is_completed_linear'
    selected_title = st.session_state.get(f"selected_display_title_{current_language}") # Immer den aktuellen Titel holen
    if selected_title and selected_title in available_texts_map:
        info = available_texts_map[selected_title]
        is_public = info['source'] == 'public'
        actual_title = info.get('original_title', selected_title.replace(f"{COMPLETED_MARKER} ", "").replace(f"{PUBLIC_MARKER} ", ""))
        verses_learn = info.get("verses", []); total_verses = len(verses_learn)
        if not is_public and actual_title in user_verses_private: completed = user_verses_private[actual_title].get("completed_linear", False)

    with sel_col3: # Modus
        opts = {"linear": "Linear", "random": "Zufällig"}; display_opts = list(opts.values())
        default = "linear"; mode = default
        if selected_title and actual_title:
            if not is_public and actual_title in user_verses_private: default = user_verses_private[actual_title].get("mode", "linear")
            key = f"selected_mode_{current_language}_{selected_title}"; old_mode = st.session_state.get(key)
            if key not in st.session_state: st.session_state[key] = default
            current = opts.get(st.session_state[key], opts["linear"])
            selected = st.selectbox("Modus", display_opts, index=display_opts.index(current), key=f"mode_sel_v5_{username}_{current_language}_{selected_title}")
            internal = next(k for k, v in opts.items() if v == selected)
            if internal != old_mode and old_mode is not None :
                 st.session_state[key] = internal
                 if not is_public and actual_title in user_verses_private:
                     details = user_verses_private[actual_title].copy(); details["mode"] = internal
                     if internal == "random": # Reset random state on switch TO random
                         rand_key = f"{current_language}_{actual_title}"
                         st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                         st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
                     persist_current_private_text_progress(username, current_language, actual_title, details)
                 # State Reset Logik (vereinfacht)
                 for k in list(st.session_state.keys()):
                     if k not in ['logged_in_user', 'selected_language', f"selected_display_title_{current_language}", key]: del st.session_state[k]
                 st.rerun()
            mode = st.session_state.get(key, default)
    
    idx = 0; idx_key = f"current_verse_index_{current_language}_{selected_title}"
    if selected_title and total_verses > 0 and actual_title:
        if mode == 'linear':
            start = 0
            if not is_public and actual_title in user_verses_private:
                details = user_verses_private[actual_title]; is_comp = details.get("completed_linear", False)
                if is_comp:
                    msg_key = f"completed_msg_shown_{current_language}_{actual_title}"
                    if not st.session_state.get(msg_key, False):
                        st.success("Super Big Amen! Text abgeschlossen."); st.session_state[msg_key] = True
                    start = 0 
                else:
                    start = details.get("last_index", 0)
                    msg_key_else = f"completed_msg_shown_{current_language}_{actual_title}"
                    if msg_key_else in st.session_state: del st.session_state[msg_key_else]
            else: start = st.session_state.get(idx_key, 0)
            idx = st.session_state.get(idx_key, start)
            idx = max(0, min(idx, total_verses - 1)) if total_verses > 0 else 0
            st.session_state[idx_key] = idx
        elif mode == 'random':
            rand_key = f"{current_language}_{actual_title}"
            if f'random_pass_indices_order_{rand_key}' not in st.session_state or \
               (not st.session_state.get(f'random_pass_indices_order_{rand_key}') and total_verses > 0) :
                st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
            pos = st.session_state.get(f'random_pass_current_position_{rand_key}', 0)
            order = st.session_state.get(f'random_pass_indices_order_{rand_key}', [])
            if pos >= len(order) and total_verses > 0 :
                order = random.sample(range(total_verses), total_verses)
                st.session_state[f'random_pass_indices_order_{rand_key}'] = order; pos = 0
                st.session_state[f'random_pass_current_position_{rand_key}'] = 0; st.session_state[f'random_pass_shown_count_{rand_key}'] = 0
            idx = order[pos] if order and pos < len(order) else 0 
            st.session_state[idx_key] = idx

    if selected_title and total_verses > 0 and actual_title:
        if mode == 'linear' and completed:
            progress_html = """<div style="background-color: #e6ffed;border:1px solid #b3e6c5;border-radius:5px;padding:2px;margin-bottom:5px;"><div style="background-color:#4CAF50;width:100%;height:10px;border-radius:3px;"></div></div><div style="text-align:center;font-size:0.9em;color:#4CAF50;">Abgeschlossen!</div>"""
            st.markdown(progress_html, unsafe_allow_html=True)
        elif mode == 'linear':
            st.progress((idx + 1) / total_verses if total_verses > 0 else 0, text=f"Linear: {idx + 1}/{total_verses}")
        elif mode == 'random':
            rand_key = f"{current_language}_{actual_title}"; num_shown = min(st.session_state.get(f'random_pass_shown_count_{rand_key}', 0), total_verses)
            st.progress(num_shown / total_verses if total_verses > 0 else 0, text=f"Zufällig: {num_shown}/{total_verses}")
    
    if selected_title and verses_learn and total_verses > 0 and actual_title:
        if not (0 <= idx < total_verses): idx = 0 
        if total_verses == 0 and idx == 0 : st.info("Keine Verse."); st.stop()
        verse = verses_learn[idx]; tokens = verse.get("text", "").split(); chunks = group_words_into_chunks(tokens); n_chunks = len(chunks)
        if not tokens or not chunks:
             st.warning(f"Vers '{verse.get('ref', '')}' leer/ungültig.")
             if st.button("Nächsten laden", key=f"skip_v5_{idx}"): st.rerun() # Einfaches Rerun löst nächste Index-Bestimmung aus
        else: 
            key = f"{current_language}_{actual_title}_{verse.get('ref', idx)}"
            if f"s_chunks_{key}" not in st.session_state or st.session_state.get("current_ref") != verse.get("ref"):
                st.session_state[f"s_chunks_{key}"] = random.sample(chunks, n_chunks); st.session_state[f"sel_chunks_{key}"] = []
                st.session_state[f"used_chunks_{key}"] = [False]*n_chunks; st.session_state[f"feedback_{key}"] = False
                st.session_state["current_ref"] = verse.get("ref"); st.session_state["cv_data"] = {"ref": verse.get("ref"), "text": verse.get("text"), "o_chunks": chunks, "tokens": tokens}
                st.session_state[f"pts_awarded_{key}"] = False; st.session_state[f"start_time_{key}"] = time.time()

            s_chunks = st.session_state[f"s_chunks_{key}"]
            sel_chunks = st.session_state[f"sel_chunks_{key}"]
            used = st.session_state[f"used_chunks_{key}"]
            feedback = st.session_state.get(f"feedback_{key}", False)
            pts_awarded = st.session_state.get(f"pts_awarded_{key}", False)

            st.markdown(f"### {VERSE_EMOJI} {verse.get('ref')}")
            
            btn_idx = 0
            for r in range(math.ceil(n_chunks / COLS_PER_ROW)):
                cols = st.columns(COLS_PER_ROW)
                for c in range(COLS_PER_ROW):
                    if btn_idx < n_chunks:
                        disp_idx = btn_idx; txt = s_chunks[disp_idx]; is_used = used[disp_idx]
                        btn_key = f"btn_v5_{disp_idx}_{key}"
                        with cols[c]:
                            if is_used: st.button(f"~~{txt}~~", key=btn_key, disabled=True, use_container_width=True)
                            else:
                                if st.button(txt, key=btn_key, use_container_width=True):
                                    sel_chunks.append((txt, disp_idx)); used[disp_idx] = True
                                    st.session_state[f"sel_chunks_{key}"] = sel_chunks; st.session_state[f"used_chunks_{key}"] = used
                                    if len(sel_chunks) == n_chunks: st.session_state[f"feedback_{key}"] = True
                                    st.rerun()
                        btn_idx += 1
            st.markdown("---")
            cols_sel = st.columns([5,1])
            with cols_sel[0]: st.markdown(f"```{' '.join([i[0] for i in sel_chunks]) if sel_chunks else '*Auswählen...*'}```")
            with cols_sel[1]:
                 if st.button("↩️", key=f"undo_v5_{key}", help="Zurück", disabled=not sel_chunks):
                      if sel_chunks:
                          _, orig_idx = sel_chunks.pop(); used[orig_idx] = False
                          st.session_state[f"sel_chunks_{key}"] = sel_chunks; st.session_state[f"used_chunks_{key}"] = used
                          if st.session_state.get(f"feedback_{key}",False) and len(sel_chunks)<n_chunks: st.session_state[f"feedback_{key}"] = False
                          st.rerun()
            st.markdown("---")

            feedback = st.session_state.get(f"feedback_{key}", False) # Erneut holen
            if feedback:
                u_chunks = [i[0] for i in sel_chunks]; u_text = " ".join(u_chunks)
                cv_data = st.session_state.get("cv_data", {}); correct_txt = cv_data.get("text", ""); correct_chunks = cv_data.get("o_chunks", [])
                tokens_count = len(cv_data.get("tokens", [])); is_correct = (u_text == correct_txt)

                if is_correct:
                    if not pts_awarded: # Nur einmal Punkte/Stats pro erfolgreichem Aufruf dieses Verses
                        st.success("✅ Richtig!") # Erfolgsmeldung verschoben
                        users[username]["points"] = users[username].get("points",0) + tokens_count
                        start = st.session_state.get(f"start_time_{key}", time.time()); duration = time.time() - start
                        users[username]['learning_time_seconds'] += int(duration); users[username]['total_verses_learned'] += 1
                        users[username]['total_words_learned'] += tokens_count
                        team_id = users[username].get('team_id')
                        if team_id and team_id in teams: teams[team_id]['points'] = teams[team_id].get('points',0) + tokens_count; save_teams(teams)
                        save_users(users); st.session_state[f"pts_awarded_{key}"] = True; st.balloons()
                    else: # Wenn schon Punkte vergeben wurden, nur die Erfolgsmeldung
                         st.success("✅ Richtig!")

                    st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'><b>{correct_txt}</b></div>", unsafe_allow_html=True)
                    
                    # --- PERSISTENZ nach KORREKTER Antwort (Optimiert) ---
                    force_rerun_on_complete = False
                    if not is_public and actual_title in user_verses_private:
                        _latest_verses = load_user_verses(username, current_language)
                        if actual_title in _latest_verses:
                            details = _latest_verses[actual_title] # Direkte Referenz
                            persist_needed = False
                            if mode == 'linear':
                                if idx == total_verses - 1: # Letzter Vers abgeschlossen
                                    if not details.get("completed_linear", False):
                                        details["completed_linear"] = True; details["last_index"] = 0
                                        st.session_state[f"completed_msg_shown_{current_language}_{actual_title}"] = False
                                        completed = True # Update UI flag for next run check
                                        persist_needed = True; force_rerun_on_complete = True
                                elif not details.get("completed_linear"): # Normaler linearer Fortschritt
                                    details["last_index"] = (idx + 1) % total_verses
                                    persist_needed = True
                            # Random mode wird unten gespeichert
                            if persist_needed:
                                persist_current_private_text_progress(username, current_language, actual_title, details)

                    if force_rerun_on_complete: # Bei Abschluss SOFORT neu laden
                        # Clear state for current verse before rerun
                        for k_del in list(st.session_state.keys()):
                             if key in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                        st.rerun()
                    
                    # Normaler Auto-Advance
                    st.markdown("➡️ Nächster Vers...")
                    time.sleep(AUTO_ADVANCE_DELAY) 
                    
                    # Finaler Fortschritt und UI Update VOR Rerun
                    next_idx_ui = idx
                    if not is_public and actual_title in user_verses_private:
                        _final_verses = load_user_verses(username, current_language) # Letzten Stand holen
                        if actual_title in _final_verses:
                            final_details = _final_verses[actual_title]
                            if mode == 'linear': next_idx_ui = final_details.get("last_index", 0)
                            elif mode == 'random':
                                rand_key_final = f"{current_language}_{actual_title}"
                                pos = st.session_state.get(f'random_pass_current_position_{rand_key_final}', 0)
                                shown = st.session_state.get(f'random_pass_shown_count_{rand_key_final}',0)
                                order = st.session_state.get(f'random_pass_indices_order_{rand_key_final}',[])
                                if pos < len(order): st.session_state[f'random_pass_shown_count_{rand_key_final}'] = shown + 1
                                st.session_state[f'random_pass_current_position_{rand_key_final}'] = pos + 1
                                persist_current_private_text_progress(username, current_language, actual_title, final_details) # Random state sichern
                                next_idx_ui = idx # Random idx wird oben neu bestimmt
                    elif mode == 'linear': next_idx_ui = (idx + 1) % total_verses
                    
                    st.session_state[idx_key] = next_idx_ui # Setze Index für nächsten Lauf

                    # Cleanup verse-specific states
                    for k_del in list(st.session_state.keys()):
                         if key in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                    st.rerun()

                else: # Falsche Antwort
                    st.error("❌ Leider falsch.")
                    highlighted = highlight_errors(u_chunks, correct_chunks)
                    st.markdown("<b>Deine Eingabe:</b>", unsafe_allow_html=True)
                    st.markdown(f"<div style='background-color:#ffebeb; color:#8b0000; padding:10px; border-radius:5px;'>{highlighted}</div>", unsafe_allow_html=True)
                    st.markdown("<b>Korrekt wäre:</b>", unsafe_allow_html=True)
                    st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'>{correct_txt}</div>", unsafe_allow_html=True)
                    st.session_state[f"pts_awarded_{key}"] = False

                    cols_fb = st.columns([1,1.5,1])
                    with cols_fb[0]: 
                        show_prev = (mode == 'linear' and total_verses > 1 and idx > 0)
                        if st.button("⬅️ Zurück", key=f"prev_v5_{key}", disabled=not show_prev, use_container_width=True):
                            next_idx_prev = idx - 1
                            if not is_public and actual_title in user_verses_private and mode == 'linear':
                                details = load_user_verses(username, current_language).get(actual_title, {}).copy()
                                if details: details["last_index"] = next_idx_prev; persist_current_private_text_progress(username, current_language, actual_title, details)
                            st.session_state[idx_key] = next_idx_prev
                            for k_del in list(st.session_state.keys()): # Reset state
                                 if key in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                            st.rerun()
                    with cols_fb[2]: 
                        if st.button("➡️ Nächster", key=f"next_v5_{key}", use_container_width=True):
                            next_idx_ui = idx 
                            if not is_public and actual_title in user_verses_private:
                                details = load_user_verses(username, current_language).get(actual_title, {}).copy()
                                if details:
                                    if mode == 'linear': next_idx_ui = (idx + 1) % total_verses; details["last_index"] = next_idx_ui
                                    elif mode == 'random': 
                                        rand_key_fb = f"{current_language}_{actual_title}"; pos = st.session_state.get(f'random_pass_current_position_{rand_key_fb}', 0)
                                        shown = st.session_state.get(f'random_pass_shown_count_{rand_key_fb}',0); order = st.session_state.get(f'random_pass_indices_order_{rand_key_fb}',[])
                                        if pos < len(order): st.session_state[f'random_pass_shown_count_{rand_key_fb}'] = shown + 1 # Zählen als gezeigt, auch wenn falsch
                                        st.session_state[f'random_pass_current_position_{rand_key_fb}'] = pos + 1; next_idx_ui = idx # UI bleibt
                                    persist_current_private_text_progress(username, current_language, actual_title, details)
                            elif mode == 'linear': next_idx_ui = (idx + 1) % total_verses
                            st.session_state[idx_key] = next_idx_ui
                            for k_del in list(st.session_state.keys()): # Reset state
                                 if key in k_del or k_del in ["current_ref", "cv_data"]: del st.session_state[k_del]
                            st.rerun()
else: # Nicht eingeloggt
    st.sidebar.title("🔐 Anmeldung"); login_tab, register_tab = st.sidebar.tabs(["Login", "Registrieren"])
    with login_tab:
        st.subheader("Login")
        login_user = st.text_input("Benutzername", key="li_user_v6")
        login_pw = st.text_input("Passwort", type="password", key="li_pw_v6")
        if st.button("Login", key="li_btn_v6"):
            user_data = users.get(login_user)
            if user_data and verify_password(user_data.get("password_hash", ""), login_pw):
                st.session_state.logged_in_user = login_user; st.session_state.login_error = None
                if "register_error" in st.session_state: del st.session_state.register_error
                st.session_state.selected_language = DEFAULT_LANGUAGE; st.rerun()
            else: st.session_state.login_error = "Name/Passwort ungültig."
            if st.session_state.login_error : st.error(st.session_state.login_error)
    with register_tab:
        st.subheader("Registrieren")
        reg_user = st.text_input("Benutzername", key="reg_user_v6")
        reg_pw = st.text_input("Passwort (min. 6 Z.)", type="password", key="reg_pw_v6")
        reg_confirm = st.text_input("Passwort bestätigen", type="password", key="reg_confirm_v6")
        if st.button("Registrieren", key="reg_btn_v6"):
            if not reg_user or not reg_pw or not reg_confirm: st.session_state.register_error = "Alle Felder ausfüllen."
            elif reg_pw != reg_confirm: st.session_state.register_error = "Passwörter ungleich."
            elif reg_user in users: st.session_state.register_error = "Name vergeben."
            elif len(reg_pw) < 6: st.session_state.register_error = "Passwort zu kurz."
            else:
                 pw_hash = hash_password(reg_pw)
                 users[reg_user] = {"password_hash": pw_hash, "points": 0, "team_id": None, "learning_time_seconds": 0, "total_verses_learned": 0, "total_words_learned": 0}
                 save_users(users); st.session_state.logged_in_user = reg_user; st.session_state.register_error = None
                 if "login_error" in st.session_state: del st.session_state.login_error
                 st.session_state.selected_language = DEFAULT_LANGUAGE; st.success("Registriert & angemeldet!"); st.rerun()
            if st.session_state.register_error : st.error(st.session_state.register_error)
    st.title("📖 Vers-Lern-App")
    st.markdown("Bitte melde dich an oder registriere dich.")
    with st.sidebar.expander("🏆 Leaderboard", expanded=False): display_leaderboard_in_sidebar(users, teams)
    with st.sidebar.expander("📊 Statistiken", expanded=False): st.write("Melde dich an für Statistiken.")
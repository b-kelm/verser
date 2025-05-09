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
import pandas as pd # NEU für Altair Diagramme
import altair as alt # NEU für Altair Diagramme

# --- Konstanten ---
USER_DATA_DIR = "user_data"
USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")
PUBLIC_VERSES_FILE = os.path.join(USER_DATA_DIR, "public_verses.json")
TEAM_DATA_FILE = os.path.join(USER_DATA_DIR, "teams.json")
ADMIN_PASSWORD = "bibelfeld" 

MAX_CHUNKS = 8
COLS_PER_ROW = 4
LEADERBOARD_SIZE = 7
AUTO_ADVANCE_DELAY = 2 
COMPLETION_PAUSE_DELAY = 6 

LANGUAGES = { "DE": "🇩🇪 Deutsch", "EN": "🇬🇧 English" }
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

def load_data(file_path, default_value={}):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, IOError): 
            st.error(f"Datei '{os.path.basename(file_path)}' korrupt oder nicht lesbar."); return default_value
    return default_value

def save_data(file_path, data_to_save):
    try:
        with open(file_path, "w", encoding='utf-8') as f: json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    except IOError: st.error(f"Fehler beim Speichern von '{os.path.basename(file_path)}'.")


def load_users():
    users_data = load_data(USERS_FILE)
    for username_key in users_data:
        users_data[username_key].setdefault('points', 0); users_data[username_key].setdefault('team_id', None)
        users_data[username_key].setdefault('learning_time_seconds', 0); users_data[username_key].setdefault('total_verses_learned', 0)
        users_data[username_key].setdefault('total_words_learned', 0)
    return users_data

def save_users(users_data_to_save): save_data(USERS_FILE, users_data_to_save)
def load_teams(): return load_data(TEAM_DATA_FILE)
def save_teams(teams_data_to_save): save_data(TEAM_DATA_FILE, teams_data_to_save)
def generate_team_code(): return str(uuid.uuid4().hex[:6].upper())

def get_user_verse_file(username_param):
    safe_username = "".join(c for c in username_param if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_username: safe_username = f"user_{random.randint(1000, 9999)}"
    return os.path.join(USER_DATA_DIR, f"{safe_username}_verses_v2.json")

def load_user_verses(username_param, language_code_param):
    filepath = get_user_verse_file(username_param)
    all_lang_data = load_data(filepath) # Verwendet generische Ladefunktion
    lang_data = all_lang_data.get(language_code_param, {})
    for title, details in lang_data.items():
        details['language'] = language_code_param; details.setdefault('public', False)
        details.setdefault('original_public_source', False)
        if details.get("mode") == "random":
            text_specific_key_base = f"{language_code_param}_{title}"
            details.setdefault("random_pass_indices_order", []); details.setdefault("random_pass_current_position", 0)
            details.setdefault("random_pass_shown_count", 0)
            st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = details["random_pass_indices_order"]
            st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = details["random_pass_current_position"]
            st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = details["random_pass_shown_count"]
    return lang_data

def persist_user_text_progress(username_param, language_code_param, text_actual_title_to_save, text_details_to_save):
    user_verse_file = get_user_verse_file(username_param)
    all_user_verses_data = load_data(user_verse_file)
    lang_specific_data = all_user_verses_data.get(language_code_param, {})
    if text_details_to_save.get("mode") == "random":
        text_specific_key_base = f"{language_code_param}_{text_actual_title_to_save}"
        text_details_to_save["random_pass_indices_order"] = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}', [])
        text_details_to_save["random_pass_current_position"] = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
        text_details_to_save["random_pass_shown_count"] = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}', 0)
    lang_specific_data[text_actual_title_to_save] = text_details_to_save
    all_user_verses_data[language_code_param] = lang_specific_data
    save_data(user_verse_file, all_user_verses_data)

def load_public_verses(language_code_param):
    all_lang_data = load_data(PUBLIC_VERSES_FILE)
    lang_data = all_lang_data.get(language_code_param, {})
    for title, details in lang_data.items(): details['public'] = True; details['language'] = language_code_param
    return lang_data

def save_public_verses(language_code_param, lang_specific_data_param):
    all_data = load_data(PUBLIC_VERSES_FILE)
    all_data[language_code_param] = {title: details for title, details in lang_specific_data_param.items() if details.get('public', True)}
    save_data(PUBLIC_VERSES_FILE, all_data)

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
    # Einzelspieler Leaderboard
    st.subheader(f"🏆 Einzelspieler Top {LEADERBOARD_SIZE}")
    if users_map_param:
        user_points_list = [{"Spieler": username_lb, "Punkte": data_lb.get('points', 0)} 
                            for username_lb, data_lb in users_map_param.items()]
        sorted_users_df = pd.DataFrame(user_points_list).sort_values(by="Punkte", ascending=False).head(LEADERBOARD_SIZE)
        if not sorted_users_df.empty:
            chart_users = alt.Chart(sorted_users_df).mark_bar().encode(
                x=alt.X('Punkte:Q', axis=alt.Axis(title='Punkte')),
                y=alt.Y('Spieler:N', sort='-x', axis=alt.Axis(title='Spieler')),
                tooltip=['Spieler', 'Punkte']
            ).properties(height=alt.Step(20)) # Kompakte Höhe
            st.altair_chart(chart_users, use_container_width=True)
        else: st.write("Keine Benutzerdaten für Leaderboard.")
    else: st.write("Keine Benutzer.")

    # Team Leaderboard
    st.subheader(f"🤝 Teams Top {LEADERBOARD_SIZE}")
    if teams_map_param:
        teams_with_calc_points = []
        for team_id_calc, team_data_calc in teams_map_param.items():
            member_points_total = sum(users_map_param.get(member_username, {}).get("points", 0) 
                                      for member_username in team_data_calc.get("members", []))
            teams_with_calc_points.append({"Team": team_data_calc.get('name', 'N/A'), "Punkte": member_points_total})
        
        sorted_teams_df = pd.DataFrame(teams_with_calc_points).sort_values(by="Punkte", ascending=False).head(LEADERBOARD_SIZE)
        if not sorted_teams_df.empty:
            chart_teams = alt.Chart(sorted_teams_df).mark_bar().encode(
                x=alt.X('Punkte:Q', axis=alt.Axis(title='Punkte')),
                y=alt.Y('Team:N', sort='-x', axis=alt.Axis(title='Team')),
                tooltip=['Team', 'Punkte']
            ).properties(height=alt.Step(20)) # Kompakte Höhe
            st.altair_chart(chart_teams, use_container_width=True)
        else: st.write("Keine Teamdaten für Leaderboard.")
    else: st.write("Keine Teams.")


def highlight_errors(selected_chunks_param, correct_chunks_param):
    html_output = []; matcher = SequenceMatcher(None, correct_chunks_param, selected_chunks_param)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal': html_output.append(" ".join(selected_chunks_param[j1:j2]))
        elif tag == 'replace' or tag == 'insert': html_output.append(f"<span style='color:red;font-weight:bold;'>{' '.join(selected_chunks_param[j1:j2])}</span>")
    return " ".join(filter(None, html_output))

# --- App Setup ---
st.set_page_config(layout="wide", page_title="Vers-Lern-App")
if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
if "admin_logged_in" not in st.session_state: st.session_state.admin_logged_in = False
# ... (weitere Session State Initialisierungen) ...

users = load_users(); teams = load_teams()

# --- Hauptanwendung ---
if st.session_state.logged_in_user:
    username = st.session_state.logged_in_user
    st.sidebar.title(f"Hallo {username}!")
    user_data_global = users.get(username, {})
    st.sidebar.markdown(f"**🏆 Punkte: {user_data_global.get('points', 0)}**")

    if st.sidebar.button("🔒 Logout"):
        # ... (Logout Logik - Persistenz des aktuellen Textes) ...
        current_language_logout = st.session_state.selected_language
        session_title_key_logout = f"selected_display_title_{current_language_logout}"
        if session_title_key_logout in st.session_state:
            current_display_title_logout = st.session_state.get(session_title_key_logout)
            if current_display_title_logout:
                _user_verses = load_user_verses(username, current_language_logout) 
                _actual_title = current_display_title_logout.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                if _actual_title in _user_verses: 
                    persist_user_text_progress(username, current_language_logout, _actual_title, _user_verses[_actual_title].copy())
        for key_to_clear in list(st.session_state.keys()): del st.session_state[key_to_clear]
        st.session_state.logged_in_user = None; st.session_state.selected_language = DEFAULT_LANGUAGE
        st.session_state.admin_logged_in = False; st.rerun()

    # --- Sidebar Widgets ---
    with st.sidebar.expander("🤝 Teams", expanded=True):
        # ... (Team UI) ...
        user_team_id = user_data_global.get('team_id'); current_team_name = "Kein Team"
        if user_team_id and user_team_id in teams:
            current_team_name = teams[user_team_id].get('name', 'N/A')
            st.markdown(f"Team: **{current_team_name}** (`{teams[user_team_id].get('code')}`)")
            if st.button("Verlassen", key="leave_team_btn_sb_v6"):
                old_team_id = users[username]['team_id']; users[username]['team_id'] = None
                if old_team_id and old_team_id in teams and username in teams[old_team_id].get('members', []):
                    teams[old_team_id]['members'].remove(username)
                save_users(users); save_teams(teams); st.success("Team verlassen."); st.rerun()
        else:
            st.markdown(f"Team: {current_team_name}")
            st.write("Erstellen:"); new_team_name = st.text_input("Teamname", key="new_team_name_sb_v7")
            if st.button("Ok", key="create_team_btn_sb_v7"):
                if new_team_name:
                    team_id = str(uuid.uuid4()); team_code = generate_team_code()
                    teams[team_id] = {"name": new_team_name, "code": team_code, "members": [username], "points": 0}
                    users[username]['team_id'] = team_id; save_teams(teams); save_users(users)
                    st.success(f"'{new_team_name}' erstellt! Code: {team_code}"); st.rerun()
                else: st.error("Name fehlt.")
            st.write("Beitreten:"); join_code = st.text_input("Team-Code", key="join_code_sb_v7").upper()
            if st.button("Ok", key="join_team_btn_sb_v7"):
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

    with st.sidebar.expander(f"📥 Eigenen Text hinzufügen", expanded=False): # Nur private Texte
        title = st.text_input("Titel (Privat)", key=f"title_sb_v8_{st.session_state.selected_language}").strip()
        text = st.text_area("Textinhalt (Privat)", height=150, key=f"text_sb_v8_{st.session_state.selected_language}", help="Format...").strip()
        if st.button("Privaten Text speichern", key=f"save_btn_sb_v8_{st.session_state.selected_language}"):
            lang = st.session_state.selected_language
            if not title: st.sidebar.error("Titel fehlt."); st.stop() # Frühzeitiger Abbruch
            # ... (Validierungen) ...
            try:
                parsed = parse_verses_from_text(text)
                if parsed:
                    _private = load_user_verses(username, lang) # Lade die Struktur für die aktuelle Sprache
                    if title in _private: st.sidebar.warning("Wird überschrieben.")
                    new_text_data = {"verses": parsed, "mode": "linear", "last_index": 0, "completed_linear": False, 
                                     "public": False, "language": lang, "original_public_source": False}
                    _private[title] = new_text_data 
                    # Speichere das gesamte Sprachobjekt mit dem neuen/überschriebenen Text
                    user_verse_file = get_user_verse_file(username); all_user_data = load_data(user_verse_file)
                    all_user_data[lang] = _private
                    save_data(user_verse_file, all_user_data)
                    st.sidebar.success("Privater Text gespeichert!"); st.rerun()
                else: st.sidebar.error("Parsen fehlgeschlagen.")
            except Exception as e: st.sidebar.error(f"Fehler: {e}")

    with st.sidebar.expander("🔑 Admin", expanded=False):
        if not st.session_state.get("admin_logged_in", False): # Sicherer Zugriff
            admin_pw = st.text_input("Admin-Passwort", type="password", key="admin_pw_v3")
            if st.button("Admin Login", key="admin_login_btn_v3"):
                if admin_pw == ADMIN_PASSWORD: st.session_state.admin_logged_in = True; st.rerun()
                else: st.error("Falsches Passwort.")
        if st.session_state.get("admin_logged_in", False):
            st.success("Admin eingeloggt."); st.subheader("Öffentlichen Bibeltext hinzufügen")
            admin_title = st.text_input("Titel (Öffentlich)", key="admin_title_v3").strip()
            admin_text = st.text_area("Text (Öffentlich)", height=150, key="admin_text_v3", help="Format...").strip()
            admin_lang_key = st.selectbox("Sprache", list(LANGUAGES.keys()), format_func=lambda k:LANGUAGES[k], key="admin_lang_v3")
            if st.button("Öffentlichen Text speichern", key="admin_save_v3"):
                if not admin_title or not admin_text: st.error("Titel/Text fehlt.")
                elif not is_format_likely_correct(admin_text): st.error("Format?")
                else:
                    try:
                        parsed_admin = parse_verses_from_text(admin_text)
                        if parsed_admin:
                            _public_verses_admin = load_public_verses(admin_lang_key)
                            if admin_title in _public_verses_admin: st.error(f"Titel '{admin_title}' existiert.")
                            else:
                                _public_verses_admin[admin_title] = {"verses": parsed_admin, "public": True, "language": admin_lang_key}
                                save_public_verses(admin_lang_key, _public_verses_admin)
                                st.success("Öffentlicher Text durch Admin gespeichert!")
                        else: st.error("Text (Admin) parsen fehlgeschlagen.")
                    except Exception as e: st.error(f"Admin Fehler: {e}")
            
            st.markdown("---"); st.subheader("Gefährliche Admin Aktionen")
            if st.checkbox("Lösch-/Reset-Aktionen anzeigen", key="show_admin_danger_zone"):
                if st.button("⚠️ Alle öffentlichen Texte löschen", key="admin_delete_all_public"):
                    if st.checkbox("Ja, ich bin sicher, ALLE öffentlichen Texte zu löschen.", key="admin_confirm_delete_public"):
                        save_public_verses(st.session_state.selected_language, {}) # Leeres Dict für aktuelle Sprache
                        # Um wirklich alle Sprachen zu leeren:
                        save_data(PUBLIC_VERSES_FILE, {})
                        st.success("Alle öffentlichen Texte wurden gelöscht!"); st.rerun()
                if st.button("⚠️ Alle Benutzerpunkte zurücksetzen", key="admin_reset_all_points"):
                    if st.checkbox("Ja, ich bin sicher, ALLE Benutzerpunkte auf 0 zu setzen.", key="admin_confirm_reset_points"):
                        current_users = load_users()
                        for u_name in current_users: current_users[u_name]['points'] = 0
                        save_users(current_users)
                        # Team-Punkte werden dynamisch berechnet, keine separate Aktion nötig
                        st.success("Alle Benutzerpunkte wurden zurückgesetzt!"); st.rerun()

            st.markdown("---"); st.subheader("Datenexport")
            if st.button("Punktestände als PDF exportieren (Konzept)", key="admin_pdf_export_btn_v2"):
                st.info("PDF Export-Funktion. Benötigt FPDF & Matplotlib/Plotly.")
                # ... (Konzeptueller Code-Block für PDF-Export - unverändert) ...

            if st.button("Admin Logout", key="admin_logout_btn_v3"): st.session_state.admin_logged_in = False; st.rerun()
    
    # --- Hauptbereich (Lernen) ---
    st.title("📖 Vers-Lern-App") 
    sel_col1, sel_col2, sel_col3 = st.columns([1, 2, 1]) 

    with sel_col1: # Sprache
        # ... (Sprachauswahl) ...
        lang_options = list(LANGUAGES.keys()); lang_display = [LANGUAGES[k] for k in lang_options]
        idx_lang = lang_options.index(st.session_state.selected_language) if st.session_state.selected_language in lang_options else 0
        selected_lang_display = st.selectbox("Sprache", lang_display, index=idx_lang, key="main_language_select_v9")
        selected_lang_key = next(key for key, value in LANGUAGES.items() if value == selected_lang_display)
        if selected_lang_key != st.session_state.selected_language:
            old_lang = st.session_state.selected_language; old_title_key = f"selected_display_title_{old_lang}"
            if old_title_key in st.session_state:
                old_title = st.session_state.get(old_title_key)
                if old_title:
                    _user_verses = load_user_verses(username, old_lang); _actual = old_title.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                    if _actual in _user_verses : persist_user_text_progress(username, old_lang, _actual, _user_verses[_actual].copy())
            st.session_state.selected_language = selected_lang_key
            for k in list(st.session_state.keys()):
                if k not in ['logged_in_user', 'selected_language', 'admin_logged_in']: del st.session_state[k]
            st.rerun()

    current_language = st.session_state.selected_language
    user_verses_private_main = load_user_verses(username, current_language) 
    public_verses_global = load_public_verses(current_language)
    available_texts_map = {}; display_titles_list = []
    for title, data in user_verses_private_main.items():
        prefix = ""
        if data.get("completed_linear", False): prefix += f"{COMPLETED_MARKER} "
        if data.get("original_public_source", False): prefix += f"{PUBLIC_MARKER} " # [P] für kopierte beibehalten
        full_display_title = f"{prefix}{title}"
        display_titles_list.append(full_display_title); 
        available_texts_map[full_display_title] = {**data, 'source': 'user_profile', 'original_title': title}
    for title, data in public_verses_global.items():
        if title not in user_verses_private_main: 
             display_titles_list.append(f"{PUBLIC_MARKER} {title}"); 
             available_texts_map[f"{PUBLIC_MARKER} {title}"] = {**data, 'source': 'public_global', 'original_title': title}
    sorted_display_titles = sorted(list(set(display_titles_list)))

    with sel_col2: # Text
        selected_display_title = None
        if not available_texts_map: st.warning(f"Keine Texte für {LANGUAGES[current_language]}.")
        else:
            session_title_key = f"selected_display_title_{current_language}"
            old_display_title = st.session_state.get(session_title_key)
            current_idx_sel = 0
            if old_display_title in sorted_display_titles: current_idx_sel = sorted_display_titles.index(old_display_title)
            elif sorted_display_titles: st.session_state[session_title_key] = sorted_display_titles[0]

            selected_display_title = st.selectbox("Bibeltext", sorted_display_titles, index=current_idx_sel, key=f"main_selectbox_v9_{username}_{current_language}")
            
            if selected_display_title and selected_display_title in available_texts_map:
                selected_text_info_for_copy = available_texts_map[selected_display_title]
                actual_title_for_copy = selected_text_info_for_copy['original_title']
                if selected_text_info_for_copy['source'] == 'public_global' and actual_title_for_copy not in user_verses_private_main:
                    copied_text_data = {"verses":selected_text_info_for_copy["verses"],"mode":"linear","last_index":0,"completed_linear":False,"public":False,"original_public_source":True,"language":current_language}
                    user_verses_private_main[actual_title_for_copy] = copied_text_data
                    persist_user_text_progress(username, current_language, actual_title_for_copy, copied_text_data)
                    st.session_state[session_title_key] = f"{PUBLIC_MARKER} {actual_title_for_copy}" # Zeige mit [P] bis es gelernt wird
                    st.rerun()

            if selected_display_title != old_display_title and old_display_title is not None:
                if old_display_title in available_texts_map:
                    old_info = available_texts_map[old_display_title]
                    if old_info['source'] == 'user_profile':
                        old_actual = old_info['original_title']
                        if old_actual in user_verses_private_main: 
                             persist_user_text_progress(username, current_language, old_actual, user_verses_private_main[old_actual].copy())
                st.session_state[session_title_key] = selected_display_title
                for k in list(st.session_state.keys()):
                    if k not in ['logged_in_user','selected_language',session_title_key,'admin_logged_in']: del st.session_state[k]
                st.rerun()
            elif selected_display_title is not None and session_title_key not in st.session_state :
                 st.session_state[session_title_key] = selected_display_title
    
    actual_title, source_type, total_verses, verses_learn, completed_status_ui = None, None, 0, [], False
    selected_title_for_logic = st.session_state.get(f"selected_display_title_{current_language}")
    if selected_title_for_logic and selected_title_for_logic in available_texts_map:
        info = available_texts_map[selected_title_for_logic]
        actual_title = info.get('original_title', selected_title_for_logic.replace(f"{COMPLETED_MARKER} ", "").replace(f"{PUBLIC_MARKER} ", ""))
        
        # Lerne immer aus user_verses_private_main, wenn der actual_title dort existiert
        if actual_title in user_verses_private_main:
            current_text_data_to_learn = user_verses_private_main[actual_title]
            source_type = 'user_profile' 
        elif info['source'] == 'public_global' and actual_title in public_verses_global:
            current_text_data_to_learn = public_verses_global[actual_title]
            source_type = 'public_global' # Wird aber gleich kopiert, wenn ausgewählt
        else: current_text_data_to_learn = {}

        verses_learn = current_text_data_to_learn.get("verses", []); total_verses = len(verses_learn)
        if source_type == 'user_profile': completed_status_ui = current_text_data_to_learn.get("completed_linear", False)

    with sel_col3: # Modus
        opts = {"linear":"Linear","random":"Zufällig"}; display_opts=list(opts.values()); default_mode="linear"; current_mode=default_mode
        if selected_title_for_logic and actual_title:
            text_data_for_mode = user_verses_private_main.get(actual_title) if actual_title in user_verses_private_main else {}
            default_mode = text_data_for_mode.get("mode", "linear") if text_data_for_mode else "linear"
            mode_key = f"selected_mode_{current_language}_{selected_title_for_logic}"; old_mode_val = st.session_state.get(mode_key)
            if mode_key not in st.session_state: st.session_state[mode_key] = default_mode
            current_mode_display_val = opts.get(st.session_state[mode_key], opts["linear"])
            selected_mode_display_val = st.selectbox("Modus", display_opts, index=display_opts.index(current_mode_display_val), key=f"mode_sel_v9_{username}_{current_language}_{selected_title_for_logic}")
            internal_mode_val = next(k for k, v in opts.items() if v == selected_mode_display_val)
            if internal_mode_val != old_mode_val and old_mode_val is not None :
                 st.session_state[mode_key] = internal_mode_val
                 if actual_title in user_verses_private_main: 
                     details = user_verses_private_main[actual_title].copy(); details["mode"] = internal_mode_val
                     if internal_mode_val == "random":
                         rand_key = f"{current_language}_{actual_title}"
                         st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses),total_verses) if total_verses >0 else []
                         st.session_state[f'random_pass_current_position_{rand_key}']=0; st.session_state[f'random_pass_shown_count_{rand_key}']=0
                     persist_user_text_progress(username, current_language, actual_title, details)
                 for k in list(st.session_state.keys()):
                     if k not in ['logged_in_user','selected_language',f"selected_display_title_{current_language}",mode_key,'admin_logged_in']: del st.session_state[k]
                 st.rerun()
            current_mode = st.session_state.get(mode_key, default_mode)
    
    idx = 0; idx_key_main_learn = f"current_verse_index_{current_language}_{selected_title_for_logic}"
    if selected_title_for_logic and total_verses > 0 and actual_title:
        # ... (idx Bestimmung - wie zuvor) ...
        text_data_for_idx = user_verses_private_main.get(actual_title) if actual_title in user_verses_private_main else {}
        if current_mode == 'linear':
            start_idx_val = 0
            if text_data_for_idx: # Text ist im User-Profil
                is_comp_idx = text_data_for_idx.get("completed_linear", False)
                if is_comp_idx:
                    msg_key_idx = f"completed_msg_shown_{current_language}_{actual_title}"
                    if not st.session_state.get(msg_key_idx, False): st.success("Super Big Amen!"); st.session_state[msg_key_idx] = True
                    start_idx_val = 0 
                else:
                    start_idx_val = text_data_for_idx.get("last_index", 0)
                    msg_key_idx_else = f"completed_msg_shown_{current_language}_{actual_title}"
                    if msg_key_idx_else in st.session_state: del st.session_state[msg_key_idx_else]
            else: start_idx_val = st.session_state.get(idx_key_main_learn, 0)
            idx = st.session_state.get(idx_key_main_learn, start_idx_val)
            idx = max(0, min(idx, total_verses - 1)) if total_verses > 0 else 0
            st.session_state[idx_key_main_learn] = idx
        elif current_mode == 'random':
            rand_key = f"{current_language}_{actual_title}"
            if f'random_pass_indices_order_{rand_key}' not in st.session_state or \
               (not st.session_state.get(f'random_pass_indices_order_{rand_key}') and total_verses > 0) :
                st.session_state[f'random_pass_indices_order_{rand_key}'] = random.sample(range(total_verses),total_verses) if total_verses >0 else []
                st.session_state[f'random_pass_current_position_{rand_key}']=0; st.session_state[f'random_pass_shown_count_{rand_key}']=0
            pos=st.session_state.get(f'random_pass_current_position_{rand_key}',0);order=st.session_state.get(f'random_pass_indices_order_{rand_key}',[])
            if pos>=len(order) and total_verses>0 :
                order=random.sample(range(total_verses),total_verses) if total_verses >0 else [];pos=0
                st.session_state[f'random_pass_indices_order_{rand_key}']=order;st.session_state[f'random_pass_current_position_{rand_key}']=0;st.session_state[f'random_pass_shown_count_{rand_key}']=0
            idx = order[pos] if order and pos < len(order) else 0 
            st.session_state[idx_key_main_learn] = idx

    # --- Fortschrittsbalken ---
    if selected_title_for_logic and total_verses > 0 and actual_title:
        # ... (Fortschrittsbalken Logik mit 'completed_status_ui') ...
        if current_mode == 'linear' and completed_status_ui: 
            progress_html = """<div style="background-color:#e6ffed;border:1px solid #b3e6c5;border-radius:5px;padding:2px;margin-bottom:5px;"><div style="background-color:#4CAF50;width:100%;height:10px;border-radius:3px;"></div></div><div style="text-align:center;font-size:0.9em;color:#4CAF50;">Abgeschlossen!</div>"""
            st.markdown(progress_html, unsafe_allow_html=True)
        elif current_mode == 'linear':
            st.progress((idx + 1) / total_verses if total_verses > 0 else 0, text=f"Linear: {idx + 1}/{total_verses}")
        elif current_mode == 'random':
            rand_key_pb = f"{current_language}_{actual_title}"; num_shown_pb = min(st.session_state.get(f'random_pass_shown_count_{rand_key_pb}', 0), total_verses)
            st.progress(num_shown_pb / total_verses if total_verses > 0 else 0, text=f"Zufällig: {num_shown_pb}/{total_verses}")
    
    # --- Lernlogik ---
    if selected_title_for_logic and verses_learn and total_verses > 0 and actual_title:
        if not (0 <= idx < total_verses): idx = 0 
        if total_verses == 0 and idx == 0 : st.info("Keine Verse."); st.stop()
        verse = verses_learn[idx]; tokens = verse.get("text", "").split(); chunks = group_words_into_chunks(tokens); n_chunks = len(chunks)
        if not tokens or not chunks:
             st.warning(f"Vers '{verse.get('ref', '')}' leer/ungültig.")
             if st.button("Nächsten laden", key=f"skip_v9_{idx}"): st.rerun()
        else: 
            key_base_learn = f"{current_language}_{actual_title}_{verse.get('ref', idx)}"
            if f"s_chunks_{key_base_learn}" not in st.session_state or st.session_state.get("current_ref") != verse.get("ref"):
                st.session_state[f"s_chunks_{key_base_learn}"]=random.sample(chunks,n_chunks); st.session_state[f"sel_chunks_{key_base_learn}"]=[]
                st.session_state[f"used_chunks_{key_base_learn}"]=[False]*n_chunks; st.session_state[f"feedback_{key_base_learn}"]=False
                st.session_state["current_ref"]=verse.get("ref"); st.session_state["cv_data"]={"ref":verse.get("ref"),"text":verse.get("text"),"o_chunks":chunks,"tokens":tokens}
                st.session_state[f"pts_awarded_{key_base_learn}"]=False; st.session_state[f"start_time_{key_base_learn}"]=time.time()

            s_chunks=st.session_state[f"s_chunks_{key_base_learn}"]; sel_chunks=st.session_state[f"sel_chunks_{key_base_learn}"]; used=st.session_state[f"used_chunks_{key_base_learn}"]
            st.markdown(f"### {VERSE_EMOJI} {verse.get('ref')}")
            
            btn_idx=0
            for r in range(math.ceil(n_chunks/COLS_PER_ROW)):
                cols=st.columns(COLS_PER_ROW)
                for c in range(COLS_PER_ROW):
                    if btn_idx < n_chunks:
                        disp_idx=btn_idx;txt=s_chunks[disp_idx];is_used=used[disp_idx]; btn_key=f"btn_v9_{disp_idx}_{key_base_learn}"
                        with cols[c]:
                            if is_used: st.button(f"~~{txt}~~",key=btn_key,disabled=True,use_container_width=True)
                            else:
                                if st.button(txt,key=btn_key,use_container_width=True):
                                    sel_chunks.append((txt,disp_idx));used[disp_idx]=True
                                    st.session_state[f"sel_chunks_{key_base_learn}"]=sel_chunks;st.session_state[f"used_chunks_{key_base_learn}"]=used
                                    if len(sel_chunks)==n_chunks:st.session_state[f"feedback_{key_base_learn}"]=True
                                    st.rerun()
                        btn_idx += 1
            st.markdown("---");cols_sel=st.columns([5,1])
            with cols_sel[0]:st.markdown(f"```{' '.join([i[0] for i in sel_chunks]) if sel_chunks else '*Auswählen...*'}```")
            with cols_sel[1]:
                 if st.button("↩️",key=f"undo_v9_{key_base_learn}",help="Zurück",disabled=not sel_chunks):
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
                    
                    if not pts_awarded:
                        users[username]["points"]=users[username].get("points",0)+tokens_count
                        start=st.session_state.get(f"start_time_{key_base_learn}",time.time());duration=time.time()-start
                        users[username]['learning_time_seconds']+=int(duration);users[username]['total_verses_learned']+=1
                        users[username]['total_words_learned']+=tokens_count
                        team_id=users[username].get('team_id')
                        if team_id and team_id in teams:teams[team_id]['points']=teams[team_id].get('points',0)+tokens_count;save_teams(teams)
                        save_users(users);st.session_state[f"pts_awarded_{key_base_learn}"]=True
                    
                    st.success("✅ Richtig!")
                    st.markdown(f"<div style='background-color:#e6ffed;color:#094d21;padding:10px;border-radius:5px;'><b>{correct_txt}</b></div>",unsafe_allow_html=True)
                    
                    text_completed_this_run_flag = False # Flag, ob Abschluss in diesem Durchlauf stattfand
                    if current_mode == 'linear' and actual_title in user_verses_private_main: # Completion nur für User-Texte
                        _latest_verses = load_user_verses(username, current_language) # Immer frische Daten
                        if actual_title in _latest_verses:
                            details = _latest_verses[actual_title]
                            if is_last_verse: 
                                if not details.get("completed_linear", False):
                                    details["completed_linear"] = True; details["last_index"] = 0
                                    persist_user_text_progress(username, current_language, actual_title, details) 
                                    st.session_state[f"completed_msg_shown_{current_language}_{actual_title}"] = False 
                                    completed_status_ui = True; text_completed_this_run_flag = True
                                    st.balloons(); st.markdown("<h2 style='text-align:center;color:green;'>Super Big AMEN!</h2>",unsafe_allow_html=True)
                            elif not details.get("completed_linear"): # Normaler Fortschritt, nur wenn nicht schon abgeschlossen
                                details["last_index"] = (idx + 1) % total_verses
                                persist_user_text_progress(username, current_language, actual_title, details)
                    
                    # --- Auto-Advance Handling ---
                    if not is_last_verse: # Nur auto-advancen, wenn NICHT der letzte Vers war
                        st.markdown("➡️ Nächster Vers...")
                        time.sleep(AUTO_ADVANCE_DELAY)
                    elif is_last_verse: # Letzter Vers wurde abgeschlossen
                        time.sleep(COMPLETION_PAUSE_DELAY) 
                    
                    # --- Finales Speichern (Random) & Rerun ---
                    next_idx_ui_final = idx 
                    if actual_title in user_verses_private_main and current_mode == 'random':
                        _final_verses_rand = load_user_verses(username, current_language)
                        if actual_title in _final_verses_rand:
                            final_details_rand = _final_verses_rand[actual_title]
                            rand_key_final=f"{current_language}_{actual_title}";pos=st.session_state.get(f'random_pass_current_position_{rand_key_final}',0)
                            shown=st.session_state.get(f'random_pass_shown_count_{rand_key_final}',0);order=st.session_state.get(f'random_pass_indices_order_{rand_key_final}',[])
                            if pos<len(order):st.session_state[f'random_pass_shown_count_{rand_key_final}']=shown+1
                            st.session_state[f'random_pass_current_position_{rand_key_final}']=pos+1
                            persist_user_text_progress(username,current_language,actual_title,final_details_rand)
                    
                    if current_mode=='linear':next_idx_ui_final=0 if is_last_verse else (idx+1)%total_verses
                    st.session_state[idx_key_main_learn]=next_idx_ui_final 
                    for k_del in list(st.session_state.keys()):
                         if key_base_learn in k_del or k_del in ["current_ref","cv_data"]:del st.session_state[k_del]
                    st.rerun()
                else: # Falsche Antwort
                    st.error("❌ Leider falsch.")
                    highlighted=highlight_errors(u_chunks,correct_chunks)
                    st.markdown("<b>Deine Eingabe:</b>",unsafe_allow_html=True);st.markdown(f"<div style='background-color:#ffebeb;color:#8b0000;padding:10px;border-radius:5px;'>{highlighted}</div>",unsafe_allow_html=True)
                    st.markdown("<b>Korrekt wäre:</b>",unsafe_allow_html=True);st.markdown(f"<div style='background-color:#e6ffed;color:#094d21;padding:10px;border-radius:5px;'>{correct_txt}</div>",unsafe_allow_html=True)
                    st.session_state[f"pts_awarded_{key_base_learn}"]=False
                    cols_fb=st.columns([1,1.5,1])
                    with cols_fb[0]: 
                        show_prev=(current_mode=='linear' and total_verses>1 and idx>0)
                        if st.button("⬅️ Zurück",key=f"prev_v9_{key_base_learn}",disabled=not show_prev,use_container_width=True):
                            next_idx_prev=idx-1
                            if actual_title in user_verses_private_main and current_mode=='linear':
                                details=load_user_verses(username,current_language).get(actual_title,{}).copy()
                                if details:details["last_index"]=next_idx_prev;persist_user_text_progress(username,current_language,actual_title,details)
                            st.session_state[idx_key_main_learn]=next_idx_prev
                            for k_del in list(st.session_state.keys()):
                                 if key_base_learn in k_del or k_del in ["current_ref","cv_data"]:del st.session_state[k_del]
                            st.rerun()
                    with cols_fb[2]: 
                        if st.button("➡️ Nächster",key=f"next_v9_{key_base_learn}",use_container_width=True):
                            next_idx_ui=idx 
                            if actual_title in user_verses_private_main:
                                details=load_user_verses(username,current_language).get(actual_title,{}).copy()
                                if details:
                                    if current_mode=='linear':next_idx_ui=(idx+1)%total_verses;details["last_index"]=next_idx_ui
                                    elif current_mode=='random': 
                                        rand_key_fb=f"{current_language}_{actual_title}";pos=st.session_state.get(f'random_pass_current_position_{rand_key_fb}',0)
                                        shown=st.session_state.get(f'random_pass_shown_count_{rand_key_fb}',0);order=st.session_state.get(f'random_pass_indices_order_{rand_key_fb}',[])
                                        if pos<len(order):st.session_state[f'random_pass_shown_count_{rand_key_fb}'] = shown+1
                                        st.session_state[f'random_pass_current_position_{rand_key_fb}']=pos+1;next_idx_ui=idx 
                                    persist_user_text_progress(username,current_language,actual_title,details)
                            elif current_mode=='linear':next_idx_ui=(idx+1)%total_verses
                            st.session_state[idx_key_main_learn]=next_idx_ui
                            for k_del in list(st.session_state.keys()):
                                 if key_base_learn in k_del or k_del in ["current_ref","cv_data"]:del st.session_state[k_del]
                            st.rerun()
else: # Nicht eingeloggt
    st.sidebar.title("🔐 Anmeldung"); login_tab, register_tab = st.sidebar.tabs(["Login", "Registrieren"])
    with login_tab:
        st.subheader("Login"); login_user = st.text_input("Benutzername", key="li_user_v10")
        login_pw = st.text_input("Passwort", type="password", key="li_pw_v10")
        if st.button("Login", key="li_btn_v10"):
            user_data = users.get(login_user)
            if user_data and verify_password(user_data.get("password_hash", ""), login_pw):
                st.session_state.logged_in_user=login_user;st.session_state.login_error=None
                if "register_error" in st.session_state:del st.session_state.register_error
                st.session_state.selected_language=DEFAULT_LANGUAGE;st.session_state.admin_logged_in=False;st.rerun()
            else:st.session_state.login_error="Name/Passwort ungültig."
            if st.session_state.login_error:st.error(st.session_state.login_error)
    with register_tab:
        st.subheader("Registrieren"); reg_user=st.text_input("Benutzername",key="reg_user_v10")
        reg_pw=st.text_input("Passwort (min. 6 Z.)",type="password",key="reg_pw_v10")
        reg_confirm=st.text_input("Passwort bestätigen",type="password",key="reg_confirm_v10")
        if st.button("Registrieren",key="reg_btn_v10"):
            if not reg_user or not reg_pw or not reg_confirm:st.session_state.register_error="Alle Felder ausfüllen."
            elif reg_pw!=reg_confirm:st.session_state.register_error="Passwörter ungleich."
            elif reg_user in users:st.session_state.register_error="Name vergeben."
            elif len(reg_pw)<6:st.session_state.register_error="Passwort zu kurz."
            else:
                 pw_hash=hash_password(reg_pw)
                 users[reg_user]={"password_hash":pw_hash,"points":0,"team_id":None,"learning_time_seconds":0,"total_verses_learned":0,"total_words_learned":0}
                 save_users(users);st.session_state.logged_in_user=reg_user;st.session_state.register_error=None
                 if "login_error" in st.session_state:del st.session_state.login_error
                 st.session_state.selected_language=DEFAULT_LANGUAGE;st.session_state.admin_logged_in=False;
                 st.success("Registriert & angemeldet!");st.rerun()
            if st.session_state.register_error:st.error(st.session_state.register_error)
    st.title("📖 Vers-Lern-App");st.markdown("Bitte melde dich an oder registriere dich.")
    with st.sidebar.expander("🏆 Leaderboard",expanded=False):display_leaderboard_in_sidebar(users,teams)
    with st.sidebar.expander("📊 Statistiken",expanded=False):st.write("Melde dich an für Statistiken.")
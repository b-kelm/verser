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
TEAM_DATA_FILE = os.path.join(USER_DATA_DIR, "teams.json") # NEU für Teams

MAX_CHUNKS = 8
COLS_PER_ROW = 4
LEADERBOARD_SIZE = 7 # Geändert auf TOP 7
AUTO_ADVANCE_DELAY = 2 # Sekunden

LANGUAGES = {
    "DE": "🇩🇪 Deutsch",
    "EN": "🇬🇧 English",
}
DEFAULT_LANGUAGE = "DE"
PUBLIC_MARKER = "[P]"
COMPLETED_MARKER = "✅" # Für abgeschlossene Texte

# --- Hilfsfunktionen ---
os.makedirs(USER_DATA_DIR, exist_ok=True)

# --- Inhalt von verses.py hier integriert ---
def parse_verses_from_text(raw_text):
    lines = raw_text.strip().split("\n")
    verses_data = []
    for line in lines:
        # Verbesserte Regex für Referenzen wie "1. Kor." oder "Offb 22:1-5" oder "1 Mose"
        match = re.match(r"\d+\)\s*([\w\s]+\.?\s*\d+:\d+[\-\d]*[a-z]?)\s+(.*)", line.strip())
        if match:
            ref, text = match.groups()
            verses_data.append({"ref": ref.strip(), "text": text.strip()})
    return verses_data
# --- Ende Inhalt von verses.py ---

def hash_password(password):
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

def verify_password(stored_hash, provided_password):
    stored_hash_bytes = stored_hash.encode('utf-8')
    provided_password_bytes = provided_password.encode('utf-8')
    try:
        return bcrypt.checkpw(provided_password_bytes, stored_hash_bytes)
    except ValueError: # Catches "Invalid salt" or other potential bcrypt errors
        return False

# --- Benutzerdaten-Funktionen ---
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                for username_key in data:
                    if 'points' not in data[username_key]: data[username_key]['points'] = 0
                    if 'team_id' not in data[username_key]: data[username_key]['team_id'] = None
                    if 'learning_time_seconds' not in data[username_key]: data[username_key]['learning_time_seconds'] = 0
                    if 'total_verses_learned' not in data[username_key]: data[username_key]['total_verses_learned'] = 0
                    if 'total_words_learned' not in data[username_key]: data[username_key]['total_words_learned'] = 0
                return data
        except (json.JSONDecodeError, IOError):
            st.error("Benutzerdatei konnte nicht gelesen werden. Eine neue wird erstellt.")
            return {}
    return {}

def save_users(users_data_to_save):
    try:
        with open(USERS_FILE, "w", encoding='utf-8') as f:
            json.dump(users_data_to_save, f, indent=2, ensure_ascii=False)
    except IOError:
        st.error("Fehler beim Speichern der Benutzerdaten.")

# --- Teamdaten-Funktionen ---
def load_teams():
    if os.path.exists(TEAM_DATA_FILE):
        try:
            with open(TEAM_DATA_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            st.error("Teamdatei konnte nicht gelesen werden. Eine neue wird erstellt.")
            return {}
    return {}

def save_teams(teams_data_to_save):
    try:
        with open(TEAM_DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(teams_data_to_save, f, indent=2, ensure_ascii=False)
    except IOError:
        st.error("Fehler beim Speichern der Teamdaten.")

def generate_team_code():
    return str(uuid.uuid4().hex[:6].upper())

# --- Versdaten-Funktionen ---
def get_user_verse_file(username_param):
    safe_username = "".join(c for c in username_param if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_username: # Sollte nicht passieren bei existierenden Usern
        safe_username = f"user_{random.randint(1000, 9999)}"
    return os.path.join(USER_DATA_DIR, f"{safe_username}_verses_v2.json")

def load_user_verses(username_param, language_code_param):
    filepath = get_user_verse_file(username_param)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                all_lang_data = json.load(f)
                lang_data = all_lang_data.get(language_code_param, {})
                for title, details in lang_data.items(): # title ist hier der actual_title
                    details['public'] = False
                    details['language'] = language_code_param
                    if details.get("mode") == "random" and not details.get("public"):
                        text_specific_key_base = f"{language_code_param}_{title}"
                        st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = details.get("random_pass_indices_order", [])
                        st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = details.get("random_pass_current_position", 0)
                        st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = details.get("random_pass_shown_count", 0)
                return lang_data
        except (json.JSONDecodeError, IOError):
             st.warning(f"Private Versdatei für {username_param} konnte nicht gelesen werden oder ist korrupt.")
             return {}
    return {}

def persist_current_private_text_progress(username_param, language_code_param, text_actual_title_to_save, text_details_to_save):
    if text_details_to_save.get('public', False): # Sollte hier nicht passieren, da nur private Texte diese Funktion nutzen
        return

    user_verse_file = get_user_verse_file(username_param)
    all_user_verses_data = {}
    if os.path.exists(user_verse_file):
        try:
            with open(user_verse_file, "r", encoding='utf-8') as f: # Sicherstellen, dass die Datei existiert
                all_user_verses_data = json.load(f)
        except (json.JSONDecodeError, IOError): # Bei Fehler leeres Dict verwenden
            all_user_verses_data = {} 
            st.warning(f"Konnte existierende Versdatei für {username_param} nicht laden, erstelle neu/überschreibe Sprache.")
    
    lang_specific_data = all_user_verses_data.get(language_code_param, {})
    
    # Update random pass details from session state right before saving
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
        # st.toast(f"Fortschritt für '{text_actual_title_to_save}' gespeichert!", icon="💾") # DEBUG
    except IOError as e:
        st.error(f"Fehler beim Speichern des Fortschritts für '{text_actual_title_to_save}': {e}")

def load_public_verses(language_code_param):
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f:
                all_lang_data = json.load(f)
                lang_data = all_lang_data.get(language_code_param, {})
                for title, details in lang_data.items():
                    details['public'] = True
                    details['language'] = language_code_param
                return lang_data
        except (json.JSONDecodeError, IOError):
            st.warning("Öffentliche Versdatei konnte nicht gelesen werden.")
            return {}
    return {}

def save_public_verses(language_code_param, lang_specific_data_param):
    all_data = {}
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            st.warning("Konnte alte öffentliche Daten nicht laden, überschreibe evtl.")
    all_data[language_code_param] = {title: details for title, details in lang_specific_data_param.items() if details.get('public', False)}
    try:
        with open(PUBLIC_VERSES_FILE, "w", encoding='utf-8') as f:
             json.dump(all_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Fehler beim Speichern der öffentlichen Verse: {e}")

# --- UI Hilfsfunktionen ---
def is_format_likely_correct(text_param): # Renamed
    if not text_param or not isinstance(text_param, str): return False
    lines = text_param.strip().split('\n')
    if not lines: return False
    first_line = lines[0].strip()
    match = re.match(r"^\s*\d+\)\s+", first_line)
    return match is not None

def contains_forbidden_content(text_param): # Renamed
    if not text_param or not isinstance(text_param, str): return False
    text_lower = text_param.lower()
    forbidden_keywords = ["sex", "porn", "gamble", "kill", "drogen", "nazi", "hitler", "idiot", "arschloch", "fick"] # Beispiel-Liste
    for keyword in forbidden_keywords:
        if keyword in text_lower:
            return True
    return False

def group_words_into_chunks(words_param, max_chunks_param=MAX_CHUNKS): # Renamed
    n_words = len(words_param)
    if n_words == 0: return []
    num_chunks = min(n_words, max_chunks_param)
    base_chunk_size = n_words // num_chunks
    remainder = n_words % num_chunks
    chunks_list = [] # Renamed
    current_idx_gwic = 0 # Renamed
    for i in range(num_chunks):
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        chunk_words = words_param[current_idx_gwic : current_idx_gwic + chunk_size]
        chunks_list.append(" ".join(chunk_words))
        current_idx_gwic += chunk_size
    return chunks_list

def display_leaderboard(users_map_param, teams_map_param): # Renamed
    st.subheader(f"🏆 Einzelspieler Top {LEADERBOARD_SIZE}")
    if not users_map_param:
        st.write("Noch keine Benutzer registriert.")
    else:
        sorted_users = sorted(
            users_map_param.items(),
            key=lambda item: item[1].get('points', 0),
            reverse=True
        )
        for i, (username_lb, data_lb) in enumerate(sorted_users[:LEADERBOARD_SIZE]): # Renamed
            points_lb = data_lb.get('points', 0) # Renamed
            st.markdown(f"{i+1}. **{username_lb}**: {points_lb} Punkte")

    st.subheader(f"🤝 Teams Top {LEADERBOARD_SIZE}")
    if not teams_map_param:
        st.write("Noch keine Teams erstellt.")
    else:
        # Team-Punkte müssen hier noch korrekt berechnet werden (Summe der Mitgliederpunkte)
        # Vorerst Anzeige der gespeicherten Teampunkte
        teams_with_calculated_points = []
        for team_id_calc, team_data_calc in teams_map_param.items(): # Renamed
            member_points_total = 0
            for member_username in team_data_calc.get("members", []):
                member_points_total += users_map_param.get(member_username, {}).get("points", 0)
            teams_with_calculated_points.append(
                {"id": team_id_calc, "name": team_data_calc.get('name', 'N/A'), "points": member_points_total}
            )
        
        sorted_teams = sorted(teams_with_calculated_points, key=lambda x: x["points"], reverse=True)
        
        for i, team_info in enumerate(sorted_teams[:LEADERBOARD_SIZE]):
            st.markdown(f"{i+1}. **{team_info['name']}**: {team_info['points']} Punkte")


def highlight_errors(selected_chunks_param, correct_chunks_param): # Renamed
    html_output = []
    matcher = SequenceMatcher(None, correct_chunks_param, selected_chunks_param) # Reihenfolge getauscht für korrekte Fehleranzeige
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            html_output.append(" ".join(selected_chunks_param[j1:j2]))
        elif tag == 'replace' or tag == 'insert': # Was der User zu viel/falsch hat
            html_output.append(f"<span style='color:red; font-weight:bold;'>{' '.join(selected_chunks_param[j1:j2])}</span>")
        # 'delete' würde anzeigen, was in der korrekten Version fehlt, aber in der User-Eingabe nicht da ist.
        # Für die Anzeige der User-Eingabe ist das nicht direkt relevant, außer man will es komplexer machen.
    return " ".join(filter(None, html_output))


# --- App Setup ---
st.set_page_config(layout="wide", page_title="Vers-Lern-App")

# --- Session State Initialisierung ---
if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
if "login_error" not in st.session_state: st.session_state.login_error = None
if "register_error" not in st.session_state: st.session_state.register_error = None
if "selected_language" not in st.session_state:
    st.session_state.selected_language = DEFAULT_LANGUAGE

# --- Globale Daten laden ---
users = load_users()
teams = load_teams()

# --- Hauptanwendung ---
if st.session_state.logged_in_user:
    username = st.session_state.logged_in_user
    st.sidebar.success(f"Angemeldet als: **{username}**")
    user_points = users.get(username, {}).get("points", 0)
    st.sidebar.markdown(f"**🏆 Deine Punkte: {user_points}**")

    if st.sidebar.button("🔒 Logout"):
        # Persist progress of the currently selected private text before logging out
        current_language_logout = st.session_state.selected_language
        session_title_key_logout = f"selected_display_title_{current_language_logout}"
        if session_title_key_logout in st.session_state:
            current_display_title_logout = st.session_state[session_title_key_logout]
            if current_display_title_logout: # Sicherstellen, dass ein Titel ausgewählt war
                _user_verses_private_logout = load_user_verses(username, current_language_logout)
                _actual_title_logout = current_display_title_logout.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                if _actual_title_logout in _user_verses_private_logout and not _user_verses_private_logout[_actual_title_logout].get('public'):
                    text_details_to_persist = _user_verses_private_logout[_actual_title_logout].copy()
                    persist_current_private_text_progress(username, current_language_logout, _actual_title_logout, text_details_to_persist)

        keys_to_clear_on_logout = list(st.session_state.keys()) # Renamed
        for key_to_clear in keys_to_clear_on_logout:
            del st.session_state[key_to_clear]
        st.session_state.logged_in_user = None
        st.session_state.selected_language = DEFAULT_LANGUAGE # Sprache zurücksetzen
        st.rerun()

    # --- Team Management UI in der Sidebar ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("🤝 Teams", expanded=True):
        user_team_id = users.get(username, {}).get('team_id')
        current_team_name = "Kein Team"
        if user_team_id and user_team_id in teams:
            current_team_name = teams[user_team_id].get('name', 'Unbekanntes Team')
            st.markdown(f"Aktuelles Team: **{current_team_name}** (`{teams[user_team_id].get('code')}`)")
            if st.button("Team verlassen"):
                old_team_id_leave = users[username]['team_id'] # Renamed
                users[username]['team_id'] = None
                if old_team_id_leave and old_team_id_leave in teams:
                    if username in teams[old_team_id_leave].get('members', []):
                        teams[old_team_id_leave]['members'].remove(username)
                save_users(users)
                save_teams(teams) # Speichert die aktualisierte Mitgliederliste
                st.success("Team verlassen.")
                st.rerun()
        else:
            st.markdown(f"Aktuelles Team: {current_team_name}")
            st.subheader("Team erstellen")
            new_team_name_input = st.text_input("Teamname", key="new_team_name") # Renamed
            if st.button("Team erstellen"):
                if new_team_name_input:
                    team_id_new = str(uuid.uuid4()) # Renamed
                    team_code_new = generate_team_code() # Renamed
                    teams[team_id_new] = {"name": new_team_name_input, "code": team_code_new, "members": [username], "points": 0}
                    users[username]['team_id'] = team_id_new
                    save_teams(teams)
                    save_users(users)
                    st.success(f"Team '{new_team_name_input}' erstellt! Code: {team_code_new}")
                    st.rerun()
                else:
                    st.error("Bitte einen Teamnamen eingeben.")

            st.subheader("Team beitreten")
            join_team_code_input = st.text_input("Team-Code", key="join_team_code").upper() # Renamed
            if st.button("Beitreten"):
                found_team_id_join = None # Renamed
                for t_id, t_data in teams.items():
                    if t_data.get('code') == join_team_code_input:
                        found_team_id_join = t_id
                        break
                if found_team_id_join:
                    users[username]['team_id'] = found_team_id_join
                    if username not in teams[found_team_id_join].get('members', []):
                         teams[found_team_id_join]['members'].append(username)
                    save_users(users)
                    save_teams(teams)
                    st.success(f"Team '{teams[found_team_id_join]['name']}' beigetreten!")
                    st.rerun()
                else:
                    st.error("Ungültiger Team-Code.")
    
    # --- Text hinzufügen ---
    st.sidebar.markdown("---")
    with st.sidebar.expander(f"📥 Text für aktuelle Sprache hinzufügen", expanded=False):
        new_title_sidebar = st.text_input("Titel des neuen Textes", key=f"new_title_input_sidebar_{st.session_state.selected_language}").strip()
        new_text_sidebar = st.text_area("Textinhalt (Format: `1) Ref...`)", height=150, key=f"new_text_input_sidebar_{st.session_state.selected_language}").strip()
        share_publicly_sidebar = st.checkbox("Öffentlich freigeben?", key=f"share_checkbox_sidebar_{st.session_state.selected_language}", value=False)

        if st.button("Neuen Text speichern", key=f"save_button_sidebar_{st.session_state.selected_language}"):
            current_lang_for_save = st.session_state.selected_language # Explizit machen
            if not new_title_sidebar: st.sidebar.error("Bitte Titel eingeben.")
            elif not new_text_sidebar: st.sidebar.error("Bitte Text eingeben.")
            elif not is_format_likely_correct(new_text_sidebar):
                 st.sidebar.error(f"Format nicht korrekt. [Hilfe](https://bible.benkelm.de/frames.htm?listv.htm)")
            elif contains_forbidden_content(new_text_sidebar):
                 st.sidebar.error("Inhalt unzulässig. Bitte prüfe den Text.")
            else:
                try:
                    parsed_verses = parse_verses_from_text(new_text_sidebar)
                    if parsed_verses:
                        if share_publicly_sidebar:
                            _public_verses = load_public_verses(current_lang_for_save)
                            if new_title_sidebar in _public_verses:
                                st.sidebar.error(f"Öffentlicher Titel '{new_title_sidebar}' existiert bereits.")
                            else:
                                _public_verses[new_title_sidebar] = {"verses": parsed_verses, "public": True, "added_by": username, "language": current_lang_for_save}
                                save_public_verses(current_lang_for_save, _public_verses)
                                st.sidebar.success("Öffentlicher Text gespeichert!")
                                st.rerun()
                        else: 
                            _user_verses_private_sidebar = load_user_verses(username, current_lang_for_save)
                            if new_title_sidebar in _user_verses_private_sidebar: st.sidebar.warning("Privater Text wird überschrieben.")
                            _user_verses_private_sidebar[new_title_sidebar] = {"verses": parsed_verses, "mode": "linear", "last_index": 0, "completed_linear": False, "public": False, "language": current_lang_for_save}
                            
                            # Um nur die aktuelle Sprache zu speichern und nicht andere zu überschreiben
                            user_verse_file = get_user_verse_file(username)
                            all_user_data_sidebar = {}
                            if os.path.exists(user_verse_file):
                                with open(user_verse_file, "r", encoding='utf-8') as f:
                                    all_user_data_sidebar = json.load(f)
                            all_user_data_sidebar[current_lang_for_save] = _user_verses_private_sidebar # Update specific language
                            with open(user_verse_file, "w", encoding='utf-8') as f:
                                json.dump(all_user_data_sidebar, f, indent=2, ensure_ascii=False)

                            st.sidebar.success("Privater Text gespeichert!")
                            st.rerun()
                    else:
                        st.sidebar.error("Text konnte nicht geparsed werden. Prüfe das Format.")
                except Exception as e_sidebar:
                    st.sidebar.error(f"Fehler beim Speichern: {e_sidebar}")

    # --- Hauptbereich (Lernen) ---
    main_col, right_utils_col = st.columns([3, 1]) # Layout schon oben definiert

    with main_col:
        st.title("📖 Vers-Lern-App")
        sel_col1, sel_col2, sel_col3 = st.columns([1, 2, 1]) # Angepasste Spaltenbreiten

        with sel_col1: # Sprachauswahl
            lang_options = list(LANGUAGES.keys())
            lang_display = [LANGUAGES[k] for k in lang_options]
            selected_lang_display = st.selectbox(
                "Sprache", lang_display,
                index=lang_options.index(st.session_state.selected_language),
                key="main_language_select" # Eindeutiger Key
            )
            selected_lang_key = next(key for key, value in LANGUAGES.items() if value == selected_lang_display)
            if selected_lang_key != st.session_state.selected_language:
                # Persist progress of current text in old language before switching
                old_lang_on_switch = st.session_state.selected_language
                old_session_title_key = f"selected_display_title_{old_lang_on_switch}"
                if old_session_title_key in st.session_state:
                    old_display_title_on_switch = st.session_state[old_session_title_key]
                    if old_display_title_on_switch:
                        _user_verses_old_lang = load_user_verses(username, old_lang_on_switch)
                        _actual_title_old_lang = old_display_title_on_switch.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
                        if _actual_title_old_lang in _user_verses_old_lang and not _user_verses_old_lang[_actual_title_old_lang].get('public'):
                            persist_current_private_text_progress(username, old_lang_on_switch, _actual_title_old_lang, _user_verses_old_lang[_actual_title_old_lang].copy())
                
                st.session_state.selected_language = selected_lang_key
                # Gezielter Reset für sprachabhängige States
                keys_to_reset_lang_change = [k for k in st.session_state if st.session_state.selected_language not in k and (k.startswith("selected_display_title_") or k.startswith("selected_mode_") or k.startswith("current_verse_index_") or "random_pass" in k or "completed_message_shown" in k or "verse_start_time" in k)]
                keys_to_reset_lang_change.extend(["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "points_awarded_for_current_verse"])
                for key_del_lc in keys_to_reset_lang_change:
                    if key_del_lc in st.session_state: del st.session_state[key_del_lc]
                st.rerun()

        current_language = st.session_state.selected_language
        user_verses_private = load_user_verses(username, current_language)
        public_verses = load_public_verses(current_language)

        available_texts_map = {}
        display_titles_list = []
        for title_priv, data_priv in user_verses_private.items():
            display_title_val = title_priv
            if data_priv.get("completed_linear", False):
                display_title_val = f"{COMPLETED_MARKER} {title_priv}"
            available_texts_map[display_title_val] = {**data_priv, 'source': 'private', 'original_title': title_priv}
            display_titles_list.append(display_title_val)
        for title_pub, data_pub in public_verses.items():
            display_title_val_pub = f"{PUBLIC_MARKER} {title_pub}"
            available_texts_map[display_title_val_pub] = {**data_pub, 'source': 'public', 'original_title': title_pub}
            display_titles_list.append(display_title_val_pub)
        sorted_display_titles = sorted(display_titles_list)

        with sel_col2: # Textauswahl
            selected_display_title = None
            if not available_texts_map:
                st.warning(f"Keine Texte für {LANGUAGES[current_language]} verfügbar.")
            else:
                session_title_key = f"selected_display_title_{current_language}"
                old_display_title_before_select = st.session_state.get(session_title_key)
                
                current_selection_idx = 0
                if st.session_state.get(session_title_key) in sorted_display_titles:
                    current_selection_idx = sorted_display_titles.index(st.session_state[session_title_key])
                elif sorted_display_titles: # Fallback, falls alter Titel nicht mehr da (z.B. nach Löschen)
                     st.session_state[session_title_key] = sorted_display_titles[0]
                     current_selection_idx = 0
                
                selected_display_title = st.selectbox(
                    "Bibeltext auswählen", sorted_display_titles,
                    index=current_selection_idx,
                    key=f"main_selectbox_text_{username}_{current_language}" # Eindeutiger Key
                )

                if selected_display_title != old_display_title_before_select and old_display_title_before_select is not None:
                    if old_display_title_before_select in available_texts_map: # Sicherstellen, dass alter Titel valide war
                        old_text_info = available_texts_map[old_display_title_before_select]
                        if old_text_info['source'] == 'private':
                            old_actual_title = old_text_info['original_title']
                            if old_actual_title in user_verses_private: # Sicherstellen, dass es noch existiert
                                persist_current_private_text_progress(username, current_language, old_actual_title, user_verses_private[old_actual_title].copy())
                    
                    st.session_state[session_title_key] = selected_display_title
                    # Reset für text-spezifische states
                    keys_to_reset_text_sel = [k for k in st.session_state if k.startswith("selected_mode_") or k.startswith("current_verse_index_") or "random_pass" in k or "completed_message_shown" in k or "verse_start_time" in k]
                    keys_to_reset_text_sel.extend(["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "points_awarded_for_current_verse"])
                    for key_del_ts in keys_to_reset_text_sel:
                        if key_del_ts in st.session_state: del st.session_state[key_del_ts]
                    st.rerun()
                elif selected_display_title is not None and session_title_key not in st.session_state : # Initialauswahl
                     st.session_state[session_title_key] = selected_display_title
        
        # Definitionen für Lernlogik holen
        actual_title = None
        is_public_text = False
        total_verses = 0
        verses_learn = [] # Umbenannt, um Konflikt mit globalem 'verses' zu vermeiden
        current_text_is_completed_linear = False

        if selected_display_title and selected_display_title in available_texts_map:
            selected_text_info = available_texts_map[selected_display_title]
            is_public_text = selected_text_info['source'] == 'public'
            actual_title = selected_text_info.get('original_title', selected_display_title.replace(f"{COMPLETED_MARKER} ", "").replace(f"{PUBLIC_MARKER} ", ""))
            verses_learn = selected_text_info.get("verses", [])
            total_verses = len(verses_learn)
            if not is_public_text and actual_title in user_verses_private:
                current_text_is_completed_linear = user_verses_private[actual_title].get("completed_linear", False)

        with sel_col3: # Modusauswahl
            mode_options_map = {"linear": "Linear", "random": "Zufällig"}
            mode_display_options = list(mode_options_map.values())
            default_mode_internal = "linear"
            mode = default_mode_internal # Fallback

            if selected_display_title and actual_title: # Nur wenn Text ausgewählt
                if not is_public_text and actual_title in user_verses_private:
                     default_mode_internal = user_verses_private[actual_title].get("mode", "linear")

                session_mode_key = f"selected_mode_{current_language}_{selected_display_title}" # Key mit display_title
                old_mode_before_select = st.session_state.get(session_mode_key)

                if session_mode_key not in st.session_state:
                     st.session_state[session_mode_key] = default_mode_internal
                
                current_selected_mode_display = mode_options_map.get(st.session_state[session_mode_key], mode_options_map["linear"])
                selected_mode_display_val = st.selectbox(
                    "Lernmodus", mode_display_options,
                    index=mode_display_options.index(current_selected_mode_display),
                    key=f"main_mode_select_{username}_{current_language}_{selected_display_title}" # Eindeutiger Key
                )
                selected_mode_internal = next(key for key, value in mode_options_map.items() if value == selected_mode_display_val)
                
                if selected_mode_internal != old_mode_before_select and old_mode_before_select is not None :
                     st.session_state[session_mode_key] = selected_mode_internal
                     if not is_public_text and actual_title in user_verses_private:
                         text_details_to_persist_mode = user_verses_private[actual_title].copy()
                         text_details_to_persist_mode["mode"] = selected_mode_internal
                         
                         if selected_mode_internal == "random": # Beim Wechsel zu Random neu initialisieren
                             text_specific_key_base_rm = f"{current_language}_{actual_title}"
                             st.session_state[f'random_pass_indices_order_{text_specific_key_base_rm}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                             st.session_state[f'random_pass_current_position_{text_specific_key_base_rm}'] = 0
                             st.session_state[f'random_pass_shown_count_{text_specific_key_base_rm}'] = 0
                         
                         persist_current_private_text_progress(username, current_language, actual_title, text_details_to_persist_mode)
                     
                     # Reset verse-specific states
                     keys_to_reset_mode_sel = [k for k in st.session_state if k.startswith("current_verse_index_") or "verse_start_time" in k] # Gezielter Reset
                     keys_to_reset_mode_sel.extend(["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "points_awarded_for_current_verse"])
                     for key_del_ms in keys_to_reset_mode_sel:
                        if key_del_ms in st.session_state: del st.session_state[key_del_ms]
                     st.rerun()
                mode = st.session_state.get(session_mode_key, default_mode_internal)
        
        # --- Index (idx) Bestimmung für aktuellen Vers ---
        idx = 0 
        # current_verse_index_key sollte mit selected_display_title gebildet werden für Eindeutigkeit
        current_verse_idx_key_learn = f"current_verse_index_{current_language}_{selected_display_title}" # Renamed

        if selected_display_title and total_verses > 0 and actual_title:
            if mode == 'linear':
                start_idx = 0
                if not is_public_text and actual_title in user_verses_private:
                    text_details_idx = user_verses_private[actual_title] # Renamed
                    is_completed_idx = text_details_idx.get("completed_linear", False) # Renamed
                    if is_completed_idx:
                        session_completed_msg_key_idx = f"completed_message_shown_{current_language}_{actual_title}" # Renamed
                        if not st.session_state.get(session_completed_msg_key_idx, False):
                            st.success("Du hast diesen Bibeltext schon vollständig bearbeitet, Super Big Amen!")
                            st.session_state[session_completed_msg_key_idx] = True
                        start_idx = 0 
                    else:
                        start_idx = text_details_idx.get("last_index", 0)
                        session_completed_msg_key_idx_else = f"completed_message_shown_{current_language}_{actual_title}" # Renamed
                        if session_completed_msg_key_idx_else in st.session_state:
                             del st.session_state[session_completed_msg_key_idx_else]
                else: 
                    start_idx = st.session_state.get(current_verse_idx_key_learn, 0)
                
                idx = st.session_state.get(current_verse_idx_key_learn, start_idx)
                idx = max(0, min(idx, total_verses - 1)) if total_verses > 0 else 0
                st.session_state[current_verse_idx_key_learn] = idx

            elif mode == 'random':
                text_specific_key_base_idx_rand = f"{current_language}_{actual_title}" # Renamed
                if f'random_pass_indices_order_{text_specific_key_base_idx_rand}' not in st.session_state or \
                   (not st.session_state[f'random_pass_indices_order_{text_specific_key_base_idx_rand}'] and total_verses > 0) :
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base_idx_rand}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                    st.session_state[f'random_pass_current_position_{text_specific_key_base_idx_rand}'] = 0
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base_idx_rand}'] = 0
                
                current_pos_idx_rand = st.session_state.get(f'random_pass_current_position_{text_specific_key_base_idx_rand}', 0) # Renamed
                indices_order_idx_rand = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base_idx_rand}', []) # Renamed

                if current_pos_idx_rand >= len(indices_order_idx_rand) and total_verses > 0 :
                    indices_order_idx_rand = random.sample(range(total_verses), total_verses)
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base_idx_rand}'] = indices_order_idx_rand
                    current_pos_idx_rand = 0
                    st.session_state[f'random_pass_current_position_{text_specific_key_base_idx_rand}'] = 0
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base_idx_rand}'] = 0
                
                if indices_order_idx_rand and current_pos_idx_rand < len(indices_order_idx_rand): # Check bounds
                    idx = indices_order_idx_rand[current_pos_idx_rand]
                else: # Fallback
                    idx = 0 
                st.session_state[current_verse_idx_key_learn] = idx # Store idx for consistency

        # --- Fortschrittsbalken ---
        if selected_display_title and total_verses > 0 and actual_title:
            if mode == 'linear' and current_text_is_completed_linear:
                progress_html = """
                <div style="background-color: #e6ffed; border: 1px solid #b3e6c5; border-radius: 5px; padding: 2px; margin-bottom: 5px;">
                  <div style="background-color: #4CAF50; width: 100%; height: 10px; border-radius: 3px;"></div>
                </div>
                <div style="text-align: center; font-size: 0.9em; color: #4CAF50;">Abgeschlossen!</div>"""
                st.markdown(progress_html, unsafe_allow_html=True)
            elif mode == 'linear':
                progress_value = (idx + 1) / total_verses if total_verses > 0 else 0
                st.progress(progress_value, text=f"Linear: Vers {idx + 1} von {total_verses}")
            elif mode == 'random':
                text_specific_key_base_prog_rand = f"{current_language}_{actual_title}" # Renamed
                num_shown_in_pass = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base_prog_rand}', 0)
                num_shown_in_pass = min(num_shown_in_pass, total_verses)
                progress_value = num_shown_in_pass / total_verses if total_verses > 0 else 0
                st.progress(progress_value, text=f"Zufällig: {num_shown_in_pass} / {total_verses} (Dieser Durchlauf)")
        
        # --- Lernlogik ---
        if selected_display_title and verses_learn and total_verses > 0 and actual_title:
            # Sicherstellen, dass idx im gültigen Bereich ist, bevor auf verses_learn zugegriffen wird
            if not (0 <= idx < total_verses):
                # Dieser Fall sollte durch die vorherige idx-Logik abgefangen werden.
                # st.error("Interner Fehler: Ungültiger Vers-Index. Bitte Text neu auswählen.") # DEBUG
                idx = 0 # Sicherer Fallback
                if total_verses == 0: # Wenn keine Verse da sind, nicht weitermachen
                    st.stop()


            current_verse_to_learn = verses_learn[idx] # Renamed
            tokens = current_verse_to_learn.get("text", "").split()
            original_chunks = group_words_into_chunks(tokens, MAX_CHUNKS)
            num_chunks = len(original_chunks)

            if not tokens or not original_chunks:
                 st.warning(f"Vers '{current_verse_to_learn.get('ref', '')}' ist leer oder konnte nicht verarbeitet werden.")
                 # Minimalistische Navigation für leere Verse
                 if st.button("Nächsten Vers laden", key=f"skip_empty_{idx}"):
                    # Logik zum Vorrücken und Persistieren, ähnlich wie bei falscher Antwort
                    if mode == 'linear':
                        next_idx_empty = (idx + 1) % total_verses
                        st.session_state[current_verse_idx_key_learn] = next_idx_empty # Update globalen idx state
                        if not is_public_text and actual_title in user_verses_private:
                            details_empty = user_verses_private[actual_title].copy()
                            details_empty["last_index"] = next_idx_empty
                            persist_current_private_text_progress(username, current_language, actual_title, details_empty)
                    elif mode == 'random':
                        text_specific_key_base_empty = f"{current_language}_{actual_title}"
                        current_pos_empty = st.session_state.get(f'random_pass_current_position_{text_specific_key_base_empty}', 0)
                        st.session_state[f'random_pass_current_position_{text_specific_key_base_empty}'] = current_pos_empty + 1
                        # Hier shown_count nicht erhöhen, da Vers nicht gelernt/angezeigt wurde
                        if not is_public_text and actual_title in user_verses_private:
                             details_empty_rand = user_verses_private[actual_title].copy()
                             persist_current_private_text_progress(username, current_language, actual_title, details_empty_rand)
                    st.rerun()

            else: # Reguläre Lernlogik
                verse_state_base_key = f"{current_language}_{actual_title}_{current_verse_to_learn.get('ref', idx)}"
                
                if f"shuffled_chunks_{verse_state_base_key}" not in st.session_state or \
                   st.session_state.get("current_ref") != current_verse_to_learn.get("ref"):
                    st.session_state[f"shuffled_chunks_{verse_state_base_key}"] = random.sample(original_chunks, num_chunks)
                    st.session_state[f"selected_chunks_{verse_state_base_key}"] = []
                    st.session_state[f"used_chunks_{verse_state_base_key}"] = [False] * num_chunks
                    st.session_state[f"feedback_given_{verse_state_base_key}"] = False
                    st.session_state["current_ref"] = current_verse_to_learn.get("ref")
                    st.session_state["current_verse_data"] = {
                        "ref": current_verse_to_learn.get("ref"), "text": current_verse_to_learn.get("text"),
                        "original_chunks": original_chunks, "tokens": tokens
                    }
                    st.session_state[f"points_awarded_{verse_state_base_key}"] = False
                    st.session_state[f"verse_start_time_{verse_state_base_key}"] = time.time()

                shuffled_chunks = st.session_state[f"shuffled_chunks_{verse_state_base_key}"]
                selected_chunks_list = st.session_state[f"selected_chunks_{verse_state_base_key}"]
                used_chunks_state = st.session_state[f"used_chunks_{verse_state_base_key}"] # Renamed
                feedback_given = st.session_state.get(f"feedback_given_{verse_state_base_key}", False)
                points_awarded = st.session_state.get(f"points_awarded_{verse_state_base_key}", False)

                st.markdown(f"### 📌 {current_verse_to_learn.get('ref')}")
                st.markdown(f"🧩 Wähle die Textbausteine in korrekter Reihenfolge:")
                
                num_rows_learn = math.ceil(num_chunks / COLS_PER_ROW) # Renamed
                button_idx_learn = 0 # Renamed
                for r_learn in range(num_rows_learn): # Renamed
                    cols_buttons_learn = st.columns(COLS_PER_ROW) # Renamed
                    for c_learn in range(COLS_PER_ROW): # Renamed
                        if button_idx_learn < num_chunks:
                            chunk_display_idx = button_idx_learn
                            chunk_text = shuffled_chunks[chunk_display_idx]
                            is_chunk_used = used_chunks_state[chunk_display_idx] # Renamed
                            btn_key_learn = f"chunk_btn_{chunk_display_idx}_{verse_state_base_key}" # Renamed
                            with cols_buttons_learn[c_learn]:
                                if is_chunk_used:
                                    st.button(f"~~{chunk_text}~~", key=btn_key_learn, disabled=True, use_container_width=True)
                                else:
                                    if st.button(chunk_text, key=btn_key_learn, use_container_width=True):
                                        selected_chunks_list.append((chunk_text, chunk_display_idx))
                                        used_chunks_state[chunk_display_idx] = True
                                        st.session_state[f"selected_chunks_{verse_state_base_key}"] = selected_chunks_list
                                        st.session_state[f"used_chunks_{verse_state_base_key}"] = used_chunks_state
                                        if len(selected_chunks_list) == num_chunks:
                                            st.session_state[f"feedback_given_{verse_state_base_key}"] = True
                                        st.rerun()
                            button_idx_learn += 1
                
                st.markdown("---")
                sel_chunks_display_cols = st.columns([5,1]) # Renamed
                with sel_chunks_display_cols[0]:
                     display_text_sel = " ".join([item[0] for item in selected_chunks_list]) if selected_chunks_list else "*Noch nichts ausgewählt.*" # Renamed
                     st.markdown(f"```{display_text_sel}```")
                with sel_chunks_display_cols[1]:
                     if st.button("↩️", key=f"undo_btn_{verse_state_base_key}", help="Letzten Baustein zurücknehmen", disabled=not selected_chunks_list): # Renamed
                          if selected_chunks_list:
                              last_chunk_text_undo, last_original_idx_undo = selected_chunks_list.pop() # Renamed
                              used_chunks_state[last_original_idx_undo] = False
                              st.session_state[f"selected_chunks_{verse_state_base_key}"] = selected_chunks_list
                              st.session_state[f"used_chunks_{verse_state_base_key}"] = used_chunks_state
                              if st.session_state.get(f"feedback_given_{verse_state_base_key}",False) and len(selected_chunks_list) < num_chunks:
                                   st.session_state[f"feedback_given_{verse_state_base_key}"] = False
                              st.rerun()
                st.markdown("---")
                
                feedback_given = st.session_state.get(f"feedback_given_{verse_state_base_key}", False) # Erneut holen

                if feedback_given:
                    user_input_chunks = [item[0] for item in selected_chunks_list]
                    user_input_text = " ".join(user_input_chunks)
                    cv_data_learn = st.session_state.get("current_verse_data", {}) # Renamed
                    correct_text_learn = cv_data_learn.get("text", "") # Renamed
                    correct_chunks_orig_learn = cv_data_learn.get("original_chunks", []) # Renamed
                    original_tokens_count_learn = len(cv_data_learn.get("tokens", [])) # Renamed
                    is_correct = (user_input_text == correct_text_learn)

                    if is_correct:
                        st.success("✅ Richtig!")
                        if not points_awarded:
                            current_points_user = users.get(username, {}).get("points", 0) # Renamed
                            users[username]["points"] = current_points_user + original_tokens_count_learn
                            
                            verse_start_time = st.session_state.get(f"verse_start_time_{verse_state_base_key}", time.time())
                            learning_duration = time.time() - verse_start_time
                            users[username]['learning_time_seconds'] = users[username].get('learning_time_seconds',0) + int(learning_duration)
                            users[username]['total_verses_learned'] = users[username].get('total_verses_learned',0) + 1
                            users[username]['total_words_learned'] = users[username].get('total_words_learned',0) + original_tokens_count_learn
                            
                            user_team_id_pts = users[username].get('team_id') # Renamed
                            if user_team_id_pts and user_team_id_pts in teams:
                                teams[user_team_id_pts]['points'] = teams[user_team_id_pts].get('points',0) + original_tokens_count_learn
                                save_teams(teams) # Team-Punkte speichern

                            save_users(users) # User-Daten (Punkte, Statistiken) speichern
                            st.session_state[f"points_awarded_{verse_state_base_key}"] = True
                            st.balloons()
                        
                        st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'><b>{correct_text_learn}</b></div>", unsafe_allow_html=True)
                        
                        # Persistenz nach korrektem Lösen, VOR dem Timer
                        if not is_public_text and actual_title in user_verses_private:
                            details_after_correct = user_verses_private[actual_title].copy()
                            if mode == 'linear':
                                if idx == total_verses - 1: # Letzter Vers im linearen Modus
                                    if not details_after_correct.get("completed_linear", False):
                                        details_after_correct["completed_linear"] = True
                                        details_after_correct["last_index"] = 0 
                                        st.session_state[f"completed_message_shown_{current_language}_{actual_title}"] = False 
                                        current_text_is_completed_linear = True # UI Update für Balken
                                        # st.toast("Text abgeschlossen!", icon="🎉") # DEBUG
                                else: # Nicht der letzte Vers
                                    details_after_correct["last_index"] = (idx + 1) % total_verses
                            # Für Random Mode wird der Fortschritt direkt vor dem Rerun aktualisiert und gespeichert
                            persist_current_private_text_progress(username, current_language, actual_title, details_after_correct)
                        
                        st.markdown("➡️ Nächster Vers in Kürze...")
                        time.sleep(AUTO_ADVANCE_DELAY) 
                        
                        # Fortschritt für Random Mode hier finalisieren und speichern
                        if mode == 'random':
                            text_specific_key_base_rand_adv = f"{current_language}_{actual_title}" # Renamed
                            current_pos_rand_adv = st.session_state.get(f'random_pass_current_position_{text_specific_key_base_rand_adv}', 0) # Renamed
                            shown_count_rand_adv = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base_rand_adv}',0) # Renamed
                            
                            if current_pos_rand_adv < len(st.session_state.get(f'random_pass_indices_order_{text_specific_key_base_rand_adv}',[])):
                                 st.session_state[f'random_pass_shown_count_{text_specific_key_base_rand_adv}'] = shown_count_rand_adv + 1
                            
                            next_random_pos_final = current_pos_rand_adv + 1 # Renamed
                            st.session_state[f'random_pass_current_position_{text_specific_key_base_rand_adv}'] = next_random_pos_final
                            
                            if not is_public_text and actual_title in user_verses_private:
                                details_rand_adv = user_verses_private[actual_title].copy() # Renamed
                                persist_current_private_text_progress(username, current_language, actual_title, details_rand_adv)
                        elif mode == 'linear': # Nächsten Index für UI setzen
                            st.session_state[current_verse_idx_key_learn] = (idx + 1) % total_verses
                            if current_text_is_completed_linear: # Wenn gerade abgeschlossen, auf 0 setzen für UI
                                 st.session_state[current_verse_idx_key_learn] = 0


                        keys_to_clear_atext = [k_atext for k_atext in st.session_state if verse_state_base_key in k_atext] # Renamed
                        keys_to_clear_atext.extend(["current_ref", "current_verse_data"]) # current_verse_data auch löschen
                        for key_del_atext in keys_to_clear_atext: # Renamed
                            if key_del_atext in st.session_state: del st.session_state[key_del_atext]
                        st.rerun()

                    else: # Falsche Antwort
                        st.error("❌ Leider falsch.")
                        highlighted_input_err = highlight_errors(user_input_chunks, correct_chunks_orig_learn) # Renamed
                        st.markdown("<b>Deine Eingabe (Fehler markiert):</b>", unsafe_allow_html=True)
                        st.markdown(f"<div style='background-color:#ffebeb; color:#8b0000; padding:10px; border-radius:5px;'>{highlighted_input_err}</div>", unsafe_allow_html=True)
                        st.markdown("<b>Korrekt wäre:</b>", unsafe_allow_html=True)
                        st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px;'>{correct_text_learn}</div>", unsafe_allow_html=True)
                        st.session_state[f"points_awarded_{verse_state_base_key}"] = False # Keine Punkte für diesen Versuch

                        nav_cols_feedback = st.columns([1,1.5,1]) # Buttonbreiten angepasst
                        with nav_cols_feedback[0]: 
                            show_prev_button_fb = (mode == 'linear' and total_verses > 1 and idx > 0) # Renamed
                            if st.button("⬅️ Zurück", key=f"prev_btn_fb_{verse_state_base_key}", disabled=not show_prev_button_fb, use_container_width=True): # Renamed
                                if not is_public_text and actual_title in user_verses_private and mode == 'linear': # Nur für private, lineare Texte
                                    details_nav_fb = user_verses_private[actual_title].copy() # Renamed
                                    details_nav_fb["last_index"] = idx - 1
                                    persist_current_private_text_progress(username, current_language, actual_title, details_nav_fb)
                                st.session_state[current_verse_idx_key_learn] = idx -1
                                st.rerun()

                        with nav_cols_feedback[2]: 
                            if st.button("➡️ Nächster Vers", key=f"next_btn_fb_{verse_state_base_key}", use_container_width=True): # Renamed
                                if not is_public_text and actual_title in user_verses_private:
                                    details_nav_fb_next = user_verses_private[actual_title].copy() # Renamed
                                    if mode == 'linear':
                                        details_nav_fb_next["last_index"] = (idx + 1) % total_verses
                                    elif mode == 'random': 
                                        text_specific_key_base_fb_next = f"{current_language}_{actual_title}" # Renamed
                                        current_pos_fb_next = st.session_state.get(f'random_pass_current_position_{text_specific_key_base_fb_next}', 0) # Renamed
                                        shown_count_fb_next = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base_fb_next}',0) # Renamed
                                        if current_pos_fb_next < len(st.session_state.get(f'random_pass_indices_order_{text_specific_key_base_fb_next}',[])):
                                            st.session_state[f'random_pass_shown_count_{text_specific_key_base_fb_next}'] = shown_count_fb_next + 1
                                        st.session_state[f'random_pass_current_position_{text_specific_key_base_fb_next}'] = current_pos_fb_next + 1
                                    persist_current_private_text_progress(username, current_language, actual_title, details_nav_fb_next)
                                
                                if mode == 'linear': # UI Index für linear updaten
                                    st.session_state[current_verse_idx_key_learn] = (idx + 1) % total_verses
                                
                                keys_to_clear_fb_next = [k_fb_next for k_fb_next in st.session_state if verse_state_base_key in k_fb_next] # Renamed
                                keys_to_clear_fb_next.extend(["current_ref", "current_verse_data"])
                                for key_del_fb_next in keys_to_clear_fb_next: # Renamed
                                    if key_del_fb_next in st.session_state: del st.session_state[key_del_fb_next]
                                st.rerun()
else: # Nicht eingeloggt
    st.sidebar.title("🔐 Anmeldung")
    login_tab, register_tab = st.sidebar.tabs(["Login", "Registrieren"])
    with login_tab:
        st.subheader("Login")
        login_username = st.text_input("Benutzername", key="login_user_input") # Eindeutiger Key
        login_password = st.text_input("Passwort", type="password", key="login_pw_input") # Eindeutiger Key
        if st.button("Login", key="login_main_button"): # Eindeutiger Key
            user_data_login = users.get(login_username)
            if user_data_login and verify_password(user_data_login.get("password_hash", ""), login_password):
                st.session_state.logged_in_user = login_username
                st.session_state.login_error = None
                if "register_error" in st.session_state: del st.session_state.register_error
                st.session_state.selected_language = DEFAULT_LANGUAGE
                st.rerun()
            else:
                st.session_state.login_error = "Ungültiger Benutzername oder Passwort."
                st.error(st.session_state.login_error)
        elif st.session_state.login_error: # Fehler anzeigen, wenn er existiert
             st.error(st.session_state.login_error)

    with register_tab:
        st.subheader("Registrieren")
        reg_username = st.text_input("Neuer Benutzername", key="reg_user_input") # Eindeutiger Key
        reg_password = st.text_input("Passwort (min. 6 Zeichen)", type="password", key="reg_pw_input") # Eindeutiger Key
        reg_password_confirm = st.text_input("Passwort bestätigen", type="password", key="reg_pw_confirm_input") # Eindeutiger Key
        if st.button("Registrieren", key="register_main_button"): # Eindeutiger Key
            if not reg_username or not reg_password or not reg_password_confirm:
                 st.session_state.register_error = "Bitte alle Felder ausfüllen."
            elif reg_password != reg_password_confirm:
                 st.session_state.register_error = "Passwörter stimmen nicht überein."
            elif reg_username in users:
                 st.session_state.register_error = "Benutzername bereits vergeben."
            elif len(reg_password) < 6:
                 st.session_state.register_error = "Passwort muss mindestens 6 Zeichen lang sein."
            else:
                 password_hash_reg = hash_password(reg_password) # Renamed
                 users[reg_username] = {
                     "password_hash": password_hash_reg, 
                     "points": 0,
                     "team_id": None,
                     "learning_time_seconds": 0,
                     "total_verses_learned": 0,
                     "total_words_learned": 0
                 }
                 save_users(users)
                 st.session_state.logged_in_user = reg_username
                 st.session_state.register_error = None
                 if "login_error" in st.session_state: del st.session_state.login_error
                 st.session_state.selected_language = DEFAULT_LANGUAGE
                 st.success(f"Benutzer '{reg_username}' erfolgreich registriert & angemeldet!")
                 st.rerun()
            if st.session_state.register_error: # Fehler anzeigen, wenn er existiert
                st.error(st.session_state.register_error)
        elif st.session_state.register_error: # Fehler auch anzeigen, wenn Button nicht geklickt, aber Fehler da ist
             st.error(st.session_state.register_error)

    st.title("📖 Vers-Lern-App")
    st.markdown("Bitte melde dich an oder registriere dich, um die App zu nutzen.")
    st.markdown("---")
    # Leaderboard und Statistiken auch für nicht eingeloggte User anzeigen (aber Statistiken sind leer)
    main_col_guest, right_utils_col_guest = st.columns([3, 1]) # Renamed
    with right_utils_col_guest:
        with st.expander("🏆 Leaderboard", expanded=False):
            display_leaderboard(users, teams)
        with st.expander("📊 Statistiken", expanded=False):
            st.write("Melde dich an, um deine persönlichen Statistiken zu sehen.")
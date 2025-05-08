import streamlit as st
import os
import json
import random
import math
import bcrypt
import re
import time
from difflib import SequenceMatcher

# --- Konstanten ---
USER_DATA_DIR = "user_data"
USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")
PUBLIC_VERSES_FILE = os.path.join(USER_DATA_DIR, "public_verses.json")
MAX_CHUNKS = 8
COLS_PER_ROW = 4
LEADERBOARD_SIZE = 10
BIBLE_FORMAT_HELP_URL = "https://bible.benkelm.de/frames.htm?listv.htm"
AUTO_ADVANCE_DELAY = 2

LANGUAGES = {
    "DE": "🇩🇪 Deutsch",
    "EN": "🇬🇧 English",
}
DEFAULT_LANGUAGE = "DE"
PUBLIC_MARKER = "[P]"
COMPLETED_MARKER = "✅" # NEW: Marker für abgeschlossene Texte

# --- Hilfsfunktionen ---
os.makedirs(USER_DATA_DIR, exist_ok=True)

# NEW: Inhalt von verses.py hier integriert
def parse_verses_from_text(raw_text):
    lines = raw_text.strip().split("\n")
    verses_data = [] # Renamed to avoid conflict with global 'verses'
    for line in lines:
        match = re.match(r"\d+\)\s*([\w\s]+\.?\s*\d+:\d+[\-\d]*[a-z]?)\s+(.*)", line.strip()) # Verbesserte Regex für Referenzen wie "1. Kor." oder "Offb 22:1-5"
        if match:
            ref, text = match.groups()
            verses_data.append({"ref": ref.strip(), "text": text.strip()})
    return verses_data
# END NEW: Inhalt von verses.py

def hash_password(password):
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

def verify_password(stored_hash, provided_password):
    stored_hash_bytes = stored_hash.encode('utf-8')
    provided_password_bytes = provided_password.encode('utf-8')
    try:
        return bcrypt.checkpw(provided_password_bytes, stored_hash_bytes)
    except ValueError:
        return False

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                for user, details in data.items():
                    if 'points' not in details or not isinstance(details['points'], (int, float)):
                        data[user]['points'] = 0
                return data
        except (json.JSONDecodeError, IOError):
            st.error("Benutzerdatei konnte nicht gelesen werden.")
            return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except IOError:
        st.error("Fehler beim Speichern der Benutzerdaten.")

def get_user_verse_file(username):
    safe_username = "".join(c for c in username if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_username:
        safe_username = f"user_{random.randint(1000, 9999)}"
    return os.path.join(USER_DATA_DIR, f"{safe_username}_verses_v2.json")

def load_user_verses(username, language_code):
    filepath = get_user_verse_file(username)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                all_lang_data = json.load(f)
                lang_data = all_lang_data.get(language_code, {})
                for title, details in lang_data.items():
                    details['public'] = False
                    details['language'] = language_code
                    if details.get("mode") == "random" and not details.get("public"):
                        text_specific_key_base = f"{details.get('language', language_code)}_{title}"
                        st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = details.get("random_pass_indices_order", [])
                        st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = details.get("random_pass_current_position", 0)
                        st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = details.get("random_pass_shown_count", 0)
                return lang_data
        except (json.JSONDecodeError, IOError):
             st.warning(f"Private Versdatei für {username} konnte nicht gelesen werden.")
             return {}
    return {}

def save_user_verses(username, language_code, lang_specific_data_to_save):
    # This function now expects lang_specific_data_to_save to be the data for the specific language
    filepath = get_user_verse_file(username)
    all_data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            st.warning(f"Konnte alte Daten für {username} nicht laden, überschreibe evtl.")

    # Update die spezifische Sprache mit den aufbereiteten Daten
    # Sicherstellen, dass nur private Daten hier landen und Random-Fortschritt aus SessionState kommt
    prepared_lang_data = {}
    for title, details in lang_specific_data_to_save.items():
        if not details.get('public', False):
            # Wenn es ein privater Text im Zufallsmodus ist, hole den aktuellen Fortschritt aus dem Session State
            if details.get("mode") == "random":
                text_specific_key_base = f"{details.get('language', language_code)}_{title}" # Hier ist title der 'actual_title'
                details["random_pass_indices_order"] = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}', [])
                details["random_pass_current_position"] = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
                details["random_pass_shown_count"] = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}', 0)
            prepared_lang_data[title] = details

    all_data[language_code] = prepared_lang_data

    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Fehler beim Speichern der privaten Verse für {username}: {e}")

# Hilfsfunktion zum Speichern des Fortschritts eines einzelnen privaten Textes
def persist_current_private_text_progress(username, language_code, text_title_to_save, text_details_to_save):
    if text_details_to_save.get('public', False):
        return # Nur private Texte

    user_verse_file = get_user_verse_file(username)
    all_user_verses_data = {}
    if os.path.exists(user_verse_file):
        with open(user_verse_file, "r", encoding='utf-8') as f:
            all_user_verses_data = json.load(f)
    
    lang_specific_data = all_user_verses_data.get(language_code, {})
    
    # Update specific text details, including random progress from session state if applicable
    if text_details_to_save.get("mode") == "random":
        text_specific_key_base = f"{language_code}_{text_title_to_save}"
        text_details_to_save["random_pass_indices_order"] = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}', [])
        text_details_to_save["random_pass_current_position"] = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
        text_details_to_save["random_pass_shown_count"] = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}', 0)
        
    lang_specific_data[text_title_to_save] = text_details_to_save
    all_user_verses_data[language_code] = lang_specific_data

    try:
        with open(user_verse_file, "w", encoding='utf-8') as f:
            json.dump(all_user_verses_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Fehler beim Speichern des Fortschritts für '{text_title_to_save}': {e}")


def load_public_verses(language_code):
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f:
                all_lang_data = json.load(f)
                lang_data = all_lang_data.get(language_code, {})
                for title, details in lang_data.items():
                    details['public'] = True
                    details['language'] = language_code
                return lang_data
        except (json.JSONDecodeError, IOError):
            st.warning("Öffentliche Versdatei konnte nicht gelesen werden.")
            return {}
    return {}

def save_public_verses(language_code, lang_specific_data):
    all_data = {}
    if os.path.exists(PUBLIC_VERSES_FILE):
        try:
            with open(PUBLIC_VERSES_FILE, "r", encoding='utf-8') as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            st.warning("Konnte alte öffentliche Daten nicht laden, überschreibe evtl.")

    all_data[language_code] = {title: details for title, details in lang_specific_data.items() if details.get('public', False)}

    try:
        with open(PUBLIC_VERSES_FILE, "w", encoding='utf-8') as f:
             json.dump(all_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Fehler beim Speichern der öffentlichen Verse: {e}")

def is_format_likely_correct(text):
    if not text or not isinstance(text, str): return False
    lines = text.strip().split('\n')
    if not lines: return False
    first_line = lines[0].strip()
    match = re.match(r"^\s*\d+\)\s+", first_line)
    return match is not None

def contains_forbidden_content(text):
    if not text or not isinstance(text, str):
        return False
    text_lower = text.lower()
    forbidden_keywords = ["sex", "porn", "gamble", "kill", "drogen", "nazi", "hitler", "idiot", "arschloch", "fick"]
    for keyword in forbidden_keywords:
        if keyword in text_lower:
            return True
    return False

def group_words_into_chunks(words, max_chunks=MAX_CHUNKS):
    n_words = len(words)
    if n_words == 0: return []
    num_chunks = min(n_words, max_chunks)
    base_chunk_size = n_words // num_chunks
    remainder = n_words % num_chunks
    chunks = []
    current_index = 0
    for i in range(num_chunks):
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        chunk_words = words[current_index : current_index + chunk_size]
        chunks.append(" ".join(chunk_words))
        current_index += chunk_size
    return chunks

def display_leaderboard(users_data): # Renamed parameter to avoid conflict
    # st.markdown("---") # Entfernt, da der Expander schon eine Linie hat
    # st.subheader("🏆 Leaderboard") # Titel kommt vom Expander
    if not users_data:
        st.write("Noch keine Benutzer registriert.")
        return
    sorted_users = sorted(
        users_data.items(),
        key=lambda item: item[1].get('points', 0) if isinstance(item[1].get('points'), (int, float)) else 0,
        reverse=True
    )
    for i, (username_lb, data) in enumerate(sorted_users[:LEADERBOARD_SIZE]): # Renamed username to username_lb
        points = data.get('points', 0)
        st.markdown(f"{i+1}. **{username_lb}**: {points} Punkte")

def highlight_errors(selected_chunks, correct_chunks):
    html_output = []
    matcher = SequenceMatcher(None, correct_chunks, selected_chunks)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            html_output.append(" ".join(selected_chunks[j1:j2]))
        elif tag == 'replace' or tag == 'insert':
            html_output.append(f"<span style='color:red; font-weight:bold;'>{' '.join(selected_chunks[j1:j2])}</span>")
    return " ".join(filter(None, html_output))

# --- App Setup ---
st.set_page_config(layout="wide")

if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
if "login_error" not in st.session_state: st.session_state.login_error = None
if "register_error" not in st.session_state: st.session_state.register_error = None
if "selected_language" not in st.session_state:
    st.session_state.selected_language = DEFAULT_LANGUAGE

# Globale User-Daten einmal laden
users = load_users()

if st.session_state.logged_in_user:
    st.sidebar.success(f"Angemeldet als: **{st.session_state.logged_in_user}**")
    user_points = users.get(st.session_state.logged_in_user, {}).get("points", 0)
    st.sidebar.markdown(f"**🏆 Deine Punkte: {user_points}**")

    if st.sidebar.button("🔒 Logout"):
        username_logout = st.session_state.logged_in_user # Renamed to avoid conflict
        current_language_logout = st.session_state.selected_language # Renamed

        # Persist progress of the currently selected private text before logging out
        session_title_key_logout = f"selected_display_title_{current_language_logout}"
        if session_title_key_logout in st.session_state:
            current_display_title_logout = st.session_state[session_title_key_logout]
            
            # Temporär user_verses laden, um Details zu bekommen
            _user_verses_private_logout = load_user_verses(username_logout, current_language_logout)
            _actual_title_logout = current_display_title_logout.replace(f"{PUBLIC_MARKER} ", "").replace(f"{COMPLETED_MARKER} ", "")
            
            if _actual_title_logout in _user_verses_private_logout and not _user_verses_private_logout[_actual_title_logout].get('public'):
                text_details_to_persist = _user_verses_private_logout[_actual_title_logout].copy() # Wichtig: Kopie!
                persist_current_private_text_progress(username_logout, current_language_logout, _actual_title_logout, text_details_to_persist)

        keys_to_clear = list(st.session_state.keys())
        for key in keys_to_clear:
            del st.session_state[key]
        st.session_state.logged_in_user = None
        st.session_state.selected_language = DEFAULT_LANGUAGE
        st.rerun()

    username = st.session_state.logged_in_user
    # MODIFIED: Layout für Leaderboard als rechte Spalte
    main_col, right_leaderboard_col = st.columns([3, 1])

    with right_leaderboard_col: # NEW: Rechte Spalte für Leaderboard
        with st.expander("🏆 Leaderboard", expanded=False): # MODIFIED: Standardmäßig eingeklappt
            display_leaderboard(users)

    with main_col:
        st.title("📖 Vers-Lern-App")
        sel_col1, sel_col2, sel_col3 = st.columns([1, 3, 1])

        with sel_col1:
            lang_options = list(LANGUAGES.keys())
            lang_display = [LANGUAGES[k] for k in lang_options]
            selected_lang_display = st.selectbox(
                "Sprache",
                lang_display,
                index=lang_options.index(st.session_state.selected_language),
                key="language_select"
            )
            selected_lang_key = next(key for key, value in LANGUAGES.items() if value == selected_lang_display)
            if selected_lang_key != st.session_state.selected_language:
                st.session_state.selected_language = selected_lang_key
                keys_to_delete = [k for k in st.session_state if k.startswith("selected_display_title_") or k.startswith("selected_mode_") or k.startswith("current_verse_index_") or "random_pass" in k or "completed_message_shown" in k]
                keys_to_delete.extend(["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "points_awarded_for_current_verse"])
                for key in keys_to_delete:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()

        current_language = st.session_state.selected_language
        user_verses_private = load_user_verses(username, current_language)
        public_verses = load_public_verses(current_language)

        available_texts_map = {} # Using a map for easier lookup of original data
        display_titles_list = []

        for title, data in user_verses_private.items():
            display_title_val = title # Renamed
            if data.get("completed_linear", False): # NEW: Grüner Marker für abgeschlossene Texte
                display_title_val = f"{COMPLETED_MARKER} {title}"
            available_texts_map[display_title_val] = {**data, 'source': 'private', 'original_title': title}
            display_titles_list.append(display_title_val)

        for title, data in public_verses.items():
            display_title_val = f"{PUBLIC_MARKER} {title}" # Renamed
            available_texts_map[display_title_val] = {**data, 'source': 'public', 'original_title': title}
            display_titles_list.append(display_title_val)
        
        sorted_display_titles = sorted(display_titles_list)


        with sel_col2:
            selected_display_title = None
            if not available_texts_map:
                st.warning(f"Keine Texte für {LANGUAGES[current_language]} verfügbar.")
            else:
                session_title_key = f"selected_display_title_{current_language}"

                # Store old title details before changing
                old_display_title = st.session_state.get(session_title_key)
                
                if session_title_key not in st.session_state or st.session_state[session_title_key] not in sorted_display_titles:
                    st.session_state[session_title_key] = sorted_display_titles[0] if sorted_display_titles else None

                selected_display_title = st.selectbox(
                    "Bibeltext",
                    sorted_display_titles,
                    index=sorted_display_titles.index(st.session_state[session_title_key]) if st.session_state.get(session_title_key) in sorted_display_titles else 0,
                    key=f"selectbox_{username}_{current_language}"
                )

                if selected_display_title != old_display_title and old_display_title is not None:
                    # Persist progress of the previously selected private text
                    if old_display_title in available_texts_map:
                        old_text_info = available_texts_map[old_display_title]
                        if old_text_info['source'] == 'private':
                            old_actual_title = old_text_info['original_title']
                            # Details müssen frisch aus user_verses_private geholt werden, um korrekten Stand zu haben
                            if old_actual_title in user_verses_private:
                                text_details_to_persist = user_verses_private[old_actual_title].copy()
                                persist_current_private_text_progress(username, current_language, old_actual_title, text_details_to_persist)
                    
                    st.session_state[session_title_key] = selected_display_title
                    keys_to_delete = ["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "current_verse_index", "points_awarded_for_current_verse"]
                    keys_to_delete.extend([k for k in st.session_state if k.startswith("selected_mode_") or k.startswith("current_verse_index_") or "random_pass" in k or "completed_message_shown" in k])
                    for key in keys_to_delete:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()
                elif selected_display_title is not None and session_title_key not in st.session_state: # Initial selection
                     st.session_state[session_title_key] = selected_display_title


        actual_title = None
        is_public_text = False
        total_verses = 0
        verses = []
        current_text_is_completed_linear = False # NEW

        if selected_display_title and selected_display_title in available_texts_map:
            selected_text_info = available_texts_map[selected_display_title]
            is_public_text = selected_text_info['source'] == 'public'
            actual_title = selected_text_info.get('original_title', selected_display_title.replace(f"{COMPLETED_MARKER} ", "").replace(f"{PUBLIC_MARKER} ", ""))
            verses = selected_text_info.get("verses", [])
            total_verses = len(verses)
            if not is_public_text and actual_title in user_verses_private: # NEW: Check completion status
                current_text_is_completed_linear = user_verses_private[actual_title].get("completed_linear", False)


        with sel_col3:
            mode_options_map = {"linear": "Linear", "random": "Zufällig"}
            mode_display_options = list(mode_options_map.values())
            default_mode_internal = "linear"
            mode = default_mode_internal

            if selected_display_title and actual_title:
                if not is_public_text and actual_title in user_verses_private:
                     default_mode_internal = user_verses_private[actual_title].get("mode", "linear")

                session_mode_key = f"selected_mode_{current_language}_{selected_display_title}" # Use display_title for unique key
                
                old_mode = st.session_state.get(session_mode_key)

                if session_mode_key not in st.session_state:
                     st.session_state[session_mode_key] = default_mode_internal
                
                current_selected_mode_display = mode_options_map.get(st.session_state[session_mode_key], mode_options_map["linear"])
                selected_mode_display_val = st.selectbox(
                    "Lernmodus",
                    mode_display_options,
                    index=mode_display_options.index(current_selected_mode_display),
                    key=f"mode_select_{username}_{current_language}_{selected_display_title}"
                )
                selected_mode_internal = next(key for key, value in mode_options_map.items() if value == selected_mode_display_val)
                
                if selected_mode_internal != old_mode and old_mode is not None:
                     st.session_state[session_mode_key] = selected_mode_internal
                     if not is_public_text:
                         # Persist mode change and potentially initialize/reset random pass state
                         if actual_title in user_verses_private:
                             text_details_to_persist = user_verses_private[actual_title].copy()
                             text_details_to_persist["mode"] = selected_mode_internal # Update mode
                             
                             if selected_mode_internal == "random": # Initialize random pass for this text
                                 text_specific_key_base_mode_change = f"{current_language}_{actual_title}"
                                 st.session_state[f'random_pass_indices_order_{text_specific_key_base_mode_change}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                                 st.session_state[f'random_pass_current_position_{text_specific_key_base_mode_change}'] = 0
                                 st.session_state[f'random_pass_shown_count_{text_specific_key_base_mode_change}'] = 0
                             
                             persist_current_private_text_progress(username, current_language, actual_title, text_details_to_persist)
                         else:
                              st.warning(f"Konnte privaten Text '{actual_title}' zum Speichern des Modus nicht finden.")
                     
                     keys_to_delete_mode_change = ["shuffled_chunks", "selected_chunks", "used_chunks", "feedback_given", "current_ref", "current_verse_data", "current_verse_index", "points_awarded_for_current_verse"]
                     keys_to_delete_mode_change.extend([k for k in st.session_state if k.startswith("current_verse_index_")])
                     for key in keys_to_delete_mode_change:
                         if key in st.session_state: del st.session_state[key]
                     st.rerun()
                mode = st.session_state.get(session_mode_key, default_mode_internal)


        idx = 0
        current_verse_index_key = f"current_verse_index_{current_language}_{selected_display_title}"

        if selected_display_title and total_verses > 0 and actual_title: # Ensure actual_title is set
            if mode == 'linear':
                start_idx = 0
                if not is_public_text and actual_title in user_verses_private:
                    text_details = user_verses_private[actual_title]
                    is_completed = text_details.get("completed_linear", False)
                    if is_completed:
                        session_completed_msg_key = f"completed_message_shown_{current_language}_{actual_title}"
                        if not st.session_state.get(session_completed_msg_key, False):
                            st.success("Du hast diesen Bibeltext schon vollständig bearbeitet, Super Big Amen!")
                            st.session_state[session_completed_msg_key] = True
                        start_idx = 0 
                    else:
                        start_idx = text_details.get("last_index", 0)
                        session_completed_msg_key = f"completed_message_shown_{current_language}_{actual_title}"
                        if session_completed_msg_key in st.session_state:
                             del st.session_state[session_completed_msg_key]
                else:
                    start_idx = st.session_state.get(current_verse_index_key, 0)
                
                idx = st.session_state.get(current_verse_index_key, start_idx)
                idx = max(0, min(idx, total_verses - 1)) if total_verses > 0 else 0
                st.session_state[current_verse_index_key] = idx

            elif mode == 'random':
                text_specific_key_base = f"{current_language}_{actual_title}"
                if f'random_pass_indices_order_{text_specific_key_base}' not in st.session_state or \
                   not st.session_state[f'random_pass_indices_order_{text_specific_key_base}']: # Check if empty list
                    # Initialize if not loaded or if list is empty (e.g. new text, or text with 0 verses previously)
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = random.sample(range(total_verses), total_verses) if total_verses > 0 else []
                    st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = 0
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = 0
                
                current_pos = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
                indices_order = st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}', [])

                if not indices_order and total_verses > 0: # If list is empty but should not be
                    indices_order = random.sample(range(total_verses), total_verses)
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = indices_order
                    current_pos = 0
                    st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = 0
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = 0
                elif current_pos >= len(indices_order) and total_verses > 0: # Pass complete
                    indices_order = random.sample(range(total_verses), total_verses)
                    st.session_state[f'random_pass_indices_order_{text_specific_key_base}'] = indices_order
                    current_pos = 0
                    st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = 0
                    st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = 0 # Reset shown count for new pass
                
                if indices_order:
                    idx = indices_order[current_pos]
                else:
                    idx = 0
                st.session_state[current_verse_index_key] = idx

        # --- Fortschrittsbalken ---
        if selected_display_title and total_verses > 0 and actual_title:
            # NEW: Grüner Fortschrittsbalken bei Abschluss
            if mode == 'linear' and current_text_is_completed_linear:
                progress_html = """
                <div style="background-color: #e6ffed; border: 1px solid #b3e6c5; border-radius: 5px; padding: 2px; margin-bottom: 5px;">
                  <div style="background-color: #4CAF50; width: 100%; height: 10px; border-radius: 3px; text-align: center; color: white; font-weight: bold; line-height:10px; font-size:0.7em;">
                  </div>
                </div>
                <div style="text-align: center; font-size: 0.9em; color: #4CAF50;">Abgeschlossen!</div>
                """
                st.markdown(progress_html, unsafe_allow_html=True)
            elif mode == 'linear':
                progress_value = (idx + 1) / total_verses
                st.progress(progress_value, text=f"Linear: Vers {idx + 1} von {total_verses}")
            elif mode == 'random':
                text_specific_key_base = f"{current_language}_{actual_title}"
                num_shown_in_pass = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}', 0)
                num_shown_in_pass = min(num_shown_in_pass, total_verses)
                progress_value = num_shown_in_pass / total_verses if total_verses > 0 else 0
                st.progress(progress_value, text=f"Zufällig: {num_shown_in_pass} / {total_verses} (Dieser Durchlauf)")
        else:
            idx = 0

        st.sidebar.markdown("---")
        with st.sidebar.expander(f"📥 Text für {LANGUAGES[current_language]} hinzufügen", expanded=False):
            new_title = st.sidebar.text_input("Titel", key=f"new_title_input_{current_language}").strip()
            new_text = st.sidebar.text_area("Text (`1) Ref...`)", key=f"new_text_input_{current_language}").strip()
            share_publicly = st.sidebar.checkbox("Öffentlich freigeben", key=f"share_checkbox_{current_language}", value=False)

            if st.sidebar.button("📌 Speichern", key=f"save_button_{current_language}"):
                if not new_title: st.sidebar.error("Bitte Titel eingeben.")
                elif not new_text: st.sidebar.error("Bitte Text eingeben.")
                elif not is_format_likely_correct(new_text):
                     st.sidebar.error(f"Format nicht korrekt. [Hilfe]({BIBLE_FORMAT_HELP_URL})")
                elif contains_forbidden_content(new_text):
                     st.sidebar.error("Inhalt unzulässig. Bitte prüfe den Text.")
                else:
                    try:
                        parsed = parse_verses_from_text(new_text)
                        if parsed:
                            if share_publicly:
                                all_public_verses = load_public_verses(current_language)
                                if new_title in all_public_verses:
                                    st.sidebar.error(f"Öffentlicher Titel '{new_title}' existiert bereits in dieser Sprache.")
                                else:
                                    all_public_verses[new_title] = {"verses": parsed, "public": True, "added_by": username, "language": current_language}
                                    save_public_verses(current_language, all_public_verses)
                                    st.sidebar.success("Öffentlicher Text gespeichert!")
                                    st.rerun()
                            else: # Privat
                                _user_verses_private = load_user_verses(username, current_language) # Renamed
                                if new_title in _user_verses_private: st.sidebar.warning("Privater Text wird überschrieben.")
                                _user_verses_private[new_title] = {"verses": parsed, "mode": "linear", "last_index": 0, "completed_linear": False, "public": False, "language": current_language}
                                # Statt save_user_verses direkt, persist_current_private_text_progress für den neuen Text
                                # Da save_user_verses das gesamte Sprachobjekt erwartet.
                                # Hier einfacher, direkt die all_user_verses_data zu manipulieren und zu speichern
                                user_verse_file = get_user_verse_file(username)
                                all_user_data = {}
                                if os.path.exists(user_verse_file):
                                    with open(user_verse_file, "r", encoding='utf-8') as f:
                                        all_user_data = json.load(f)
                                all_user_data[current_language] = _user_verses_private
                                with open(user_verse_file, "w", encoding='utf-8') as f:
                                    json.dump(all_user_data, f, indent=2, ensure_ascii=False)

                                st.sidebar.success("Privater Text gespeichert!")
                                st.rerun()
                        else:
                            st.sidebar.error("Text konnte nicht geparsed werden.")
                    except Exception as e:
                        st.sidebar.error(f"Fehler: {e}")

        if selected_display_title and verses and total_verses > 0 and actual_title:
                current_verse = verses[idx]
                tokens = current_verse.get("text", "").split()
                original_chunks = group_words_into_chunks(tokens, MAX_CHUNKS)
                num_chunks = len(original_chunks)

                if not tokens or not original_chunks:
                     st.warning(f"Vers {current_verse.get('ref', '')} ist leer oder konnte nicht verarbeitet werden.")
                     nav_cols = st.columns(5) # Keep nav_cols for layout consistency
                     # ... (Logik für Überspringen/Zurück bei leerem Vers, ggf. anpassen) ...
                else:
                    verse_state_base_key = f"{current_language}_{actual_title}_{current_verse.get('ref', idx)}" # Use actual_title
                    if f"shuffled_chunks_{verse_state_base_key}" not in st.session_state or st.session_state.get("current_ref") != current_verse["ref"]:
                        st.session_state[f"shuffled_chunks_{verse_state_base_key}"] = random.sample(original_chunks, num_chunks)
                        st.session_state[f"selected_chunks_{verse_state_base_key}"] = []
                        st.session_state[f"used_chunks_{verse_state_base_key}"] = [False] * num_chunks
                        st.session_state[f"feedback_given_{verse_state_base_key}"] = False
                        st.session_state["current_ref"] = current_verse["ref"]
                        st.session_state["current_verse_data"] = {
                            "ref": current_verse["ref"], "text": current_verse["text"],
                            "original_chunks": original_chunks, "tokens": tokens
                        }
                        st.session_state[f"points_awarded_{verse_state_base_key}"] = False

                    shuffled_chunks = st.session_state[f"shuffled_chunks_{verse_state_base_key}"]
                    selected_chunks_list = st.session_state[f"selected_chunks_{verse_state_base_key}"]
                    used_chunks = st.session_state[f"used_chunks_{verse_state_base_key}"]
                    feedback_given = st.session_state[f"feedback_given_{verse_state_base_key}"]
                    points_awarded = st.session_state[f"points_awarded_{verse_state_base_key}"]

                    st.markdown(f"### 📌 {current_verse['ref']}")
                    st.markdown(f"🧩 Wähle die Textbausteine:")
                    num_rows = math.ceil(num_chunks / COLS_PER_ROW)
                    button_index = 0
                    for r in range(num_rows):
                        cols_buttons = st.columns(COLS_PER_ROW) # Renamed
                        for c_idx in range(COLS_PER_ROW):
                            if button_index < num_chunks:
                                chunk_display_index = button_index
                                chunk_text = shuffled_chunks[chunk_display_index]
                                is_used = used_chunks[chunk_display_index]
                                button_key = f"chunk_btn_{chunk_display_index}_{verse_state_base_key}" # More specific key
                                with cols_buttons[c_idx]:
                                    if is_used:
                                        st.button(f"~~{chunk_text}~~", key=button_key, disabled=True, use_container_width=True)
                                    else:
                                        if st.button(chunk_text, key=button_key, use_container_width=True):
                                            selected_chunks_list.append((chunk_text, chunk_display_index))
                                            used_chunks[chunk_display_index] = True
                                            st.session_state[f"selected_chunks_{verse_state_base_key}"] = selected_chunks_list
                                            st.session_state[f"used_chunks_{verse_state_base_key}"] = used_chunks
                                            if len(selected_chunks_list) == num_chunks:
                                                st.session_state[f"feedback_given_{verse_state_base_key}"] = True
                                                # feedback_given = True # Wird im nächsten Block geholt
                                            st.rerun()
                                button_index += 1
                    st.markdown("---")
                    sel_chunks_cols = st.columns([5, 1])
                    with sel_chunks_cols[0]:
                         display_text = " ".join([item[0] for item in selected_chunks_list]) if selected_chunks_list else "*Noch nichts ausgewählt.*"
                         st.markdown(f"```{display_text}```")
                    with sel_chunks_cols[1]:
                         if st.button("↩️", key=f"undo_last_{verse_state_base_key}", help="Letzten Baustein zurücknehmen", disabled=not selected_chunks_list):
                              if selected_chunks_list:
                                  last_chunk_text, last_original_index = selected_chunks_list.pop()
                                  used_chunks[last_original_index] = False
                                  st.session_state[f"selected_chunks_{verse_state_base_key}"] = selected_chunks_list
                                  st.session_state[f"used_chunks_{verse_state_base_key}"] = used_chunks
                                  if st.session_state[f"feedback_given_{verse_state_base_key}"] and len(selected_chunks_list) < num_chunks:
                                       st.session_state[f"feedback_given_{verse_state_base_key}"] = False
                                  st.rerun()
                    st.markdown("---")
                    
                    # Holen des feedback_given Status erneut, falls er durch Undo geändert wurde
                    feedback_given = st.session_state[f"feedback_given_{verse_state_base_key}"]


                    if feedback_given:
                        user_input_chunks = [item[0] for item in selected_chunks_list]
                        user_input_text = " ".join(user_input_chunks)
                        correct_text = st.session_state["current_verse_data"].get("text", "")
                        correct_chunks_original = st.session_state["current_verse_data"].get("original_chunks", [])
                        original_tokens_count = len(st.session_state["current_verse_data"].get("tokens", []))
                        is_correct = (user_input_text == correct_text)

                        if is_correct:
                            st.success("✅ Richtig!")
                            if not points_awarded:
                                current_points = users.get(username, {}).get("points", 0)
                                users[username]["points"] = current_points + original_tokens_count
                                save_users(users) # User-Punkte speichern
                                st.session_state[f"points_awarded_{verse_state_base_key}"] = True
                                st.balloons()
                            st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px; border: 1px solid #b3e6c5;'><b>{correct_text}</b></div>", unsafe_allow_html=True)
                            
                            if mode == 'linear' and not is_public_text and idx == total_verses - 1:
                                if actual_title in user_verses_private:
                                    text_details_to_complete = user_verses_private[actual_title].copy()
                                    text_details_to_complete["completed_linear"] = True
                                    text_details_to_complete["last_index"] = 0 
                                    persist_current_private_text_progress(username, current_language, actual_title, text_details_to_complete)
                                    st.session_state[f"completed_message_shown_{current_language}_{actual_title}"] = False # Damit es direkt angezeigt wird
                                    current_text_is_completed_linear = True # Update für sofortige Anzeige des grünen Balkens

                            st.markdown("➡️ Nächster Vers in Kürze...")
                            time.sleep(AUTO_ADVANCE_DELAY)
                            
                            # --- Nächster Vers Logik (Auto-Advance) ---
                            next_idx_val = idx # Platzhalter
                            if mode == 'linear':
                                next_idx_val = (idx + 1) % total_verses
                                st.session_state[current_verse_index_key] = next_idx_val
                                if not is_public_text and actual_title in user_verses_private:
                                    text_details_update = user_verses_private[actual_title].copy()
                                    if not text_details_update.get("completed_linear") or next_idx_val != 0: # Nur updaten, wenn nicht gerade completed und auf 0 gesetzt
                                        text_details_update["last_index"] = next_idx_val
                                    persist_current_private_text_progress(username, current_language, actual_title, text_details_update)

                            elif mode == 'random':
                                text_specific_key_base = f"{current_language}_{actual_title}"
                                current_pos = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
                                shown_count = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}',0)
                                
                                # Nur erhöhen, wenn der aktuelle Vers auch wirklich aus der Liste stammt
                                if current_pos < len(st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}',[])):
                                     st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = shown_count + 1
                                
                                next_random_pos = current_pos + 1
                                st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = next_random_pos
                                
                                if not is_public_text and actual_title in user_verses_private:
                                    text_details_update = user_verses_private[actual_title].copy()
                                    persist_current_private_text_progress(username, current_language, actual_title, text_details_update)


                            keys_to_clear_after_verse = [k for k in st.session_state if verse_state_base_key in k]
                            keys_to_clear_after_verse.extend(["current_ref", "current_verse_data"])
                            for key in keys_to_clear_after_verse:
                                if key in st.session_state: del st.session_state[key]
                            st.rerun()

                        else: # Falsche Antwort
                            st.error("❌ Leider falsch.")
                            highlighted_input = highlight_errors(user_input_chunks, correct_chunks_original)
                            st.markdown("<b>Deine Eingabe (Fehler markiert):</b>", unsafe_allow_html=True)
                            st.markdown(f"<div style='background-color:#ffebeb; color:#8b0000; padding:10px; border-radius:5px; border: 1px solid #f5c6cb;'>{highlighted_input}</div>", unsafe_allow_html=True)
                            st.markdown("<b>Korrekt wäre:</b>", unsafe_allow_html=True)
                            st.markdown(f"<div style='background-color:#e6ffed; color:#094d21; padding:10px; border-radius:5px; border: 1px solid #b3e6c5; margin-top: 5px;'>{correct_text}</div>", unsafe_allow_html=True)
                            st.session_state[f"points_awarded_{verse_state_base_key}"] = False

                            nav_cols_feedback = st.columns([1,3,1])
                            with nav_cols_feedback[0]: # Zurück Button
                                show_prev_button = (mode == 'linear' and total_verses > 1 and idx > 0)
                                if st.button("⬅️ Zurück", key=f"prev_verse_button_feedback_{verse_state_base_key}", disabled=not show_prev_button):
                                    prev_idx = idx - 1
                                    st.session_state[current_verse_index_key] = prev_idx
                                    if not is_public_text and actual_title in user_verses_private:
                                        text_details_update = user_verses_private[actual_title].copy()
                                        text_details_update["last_index"] = prev_idx
                                        persist_current_private_text_progress(username, current_language, actual_title, text_details_update)
                                    # Reset states für aktuellen Vers...
                                    st.rerun()
                            with nav_cols_feedback[2]: # Nächster Vers Button
                                if st.button("➡️ Nächster Vers", key=f"next_verse_button_feedback_{verse_state_base_key}"):
                                    if mode == 'linear':
                                        next_idx_manual = (idx + 1) % total_verses
                                        st.session_state[current_verse_index_key] = next_idx_manual
                                        if not is_public_text and actual_title in user_verses_private:
                                            text_details_update = user_verses_private[actual_title].copy()
                                            text_details_update["last_index"] = next_idx_manual
                                            persist_current_private_text_progress(username, current_language, actual_title, text_details_update)
                                    elif mode == 'random':
                                        text_specific_key_base = f"{current_language}_{actual_title}"
                                        current_pos = st.session_state.get(f'random_pass_current_position_{text_specific_key_base}', 0)
                                        shown_count = st.session_state.get(f'random_pass_shown_count_{text_specific_key_base}',0)
                                        if current_pos < len(st.session_state.get(f'random_pass_indices_order_{text_specific_key_base}',[])):
                                            st.session_state[f'random_pass_shown_count_{text_specific_key_base}'] = shown_count + 1
                                        
                                        next_random_pos = current_pos + 1
                                        st.session_state[f'random_pass_current_position_{text_specific_key_base}'] = next_random_pos
                                        
                                        if not is_public_text and actual_title in user_verses_private:
                                            text_details_update = user_verses_private[actual_title].copy()
                                            persist_current_private_text_progress(username, current_language, actual_title, text_details_update)
                                    
                                    keys_to_clear_after_verse = [k for k in st.session_state if verse_state_base_key in k]
                                    keys_to_clear_after_verse.extend(["current_ref", "current_verse_data"])
                                    for key in keys_to_clear_after_verse:
                                        if key in st.session_state: del st.session_state[key]
                                    st.rerun()
else: # Nicht eingeloggt
    st.sidebar.title("🔐 Anmeldung")
    login_tab, register_tab = st.sidebar.tabs(["Login", "Registrieren"])
    with login_tab:
        st.subheader("Login")
        login_username = st.text_input("Benutzername", key="login_user")
        login_password = st.text_input("Passwort", type="password", key="login_pw")
        if st.button("Login", key="login_button"):
            user_data = users.get(login_username)
            if user_data and verify_password(user_data.get("password_hash", ""), login_password):
                st.session_state.logged_in_user = login_username
                st.session_state.login_error = None
                if "register_error" in st.session_state: del st.session_state.register_error
                st.session_state.selected_language = DEFAULT_LANGUAGE
                st.rerun()
            else:
                st.session_state.login_error = "Ungültiger Benutzername oder Passwort."
                st.error(st.session_state.login_error)
        elif st.session_state.login_error:
             st.error(st.session_state.login_error)

    with register_tab:
        st.subheader("Registrieren")
        reg_username = st.text_input("Neuer Benutzername", key="reg_user")
        reg_password = st.text_input("Passwort", type="password", key="reg_pw")
        reg_password_confirm = st.text_input("Passwort bestätigen", type="password", key="reg_pw_confirm")
        if st.button("Registrieren", key="register_button"):
            if not reg_username or not reg_password or not reg_password_confirm:
                 st.session_state.register_error = "Bitte alle Felder ausfüllen."
            elif reg_password != reg_password_confirm:
                 st.session_state.register_error = "Passwörter stimmen nicht überein."
            elif reg_username in users:
                 st.session_state.register_error = "Benutzername bereits vergeben."
            elif len(reg_password) < 6:
                 st.session_state.register_error = "Passwort muss mind. 6 Zeichen lang sein."
            else:
                 password_hash = hash_password(reg_password)
                 users[reg_username] = {"password_hash": password_hash, "points": 0}
                 save_users(users)
                 st.session_state.logged_in_user = reg_username
                 st.session_state.register_error = None
                 if "login_error" in st.session_state: del st.session_state.login_error
                 st.session_state.selected_language = DEFAULT_LANGUAGE
                 st.success(f"Benutzer '{reg_username}' registriert & angemeldet!")
                 st.rerun()
            if st.session_state.register_error:
                st.error(st.session_state.register_error)
        elif st.session_state.register_error:
             st.error(st.session_state.register_error)

    st.title("📖 Vers-Lern-App")
    st.markdown("Bitte melde dich an oder registriere dich.")
    st.markdown("---")
    with st.expander("🏆 Leaderboard", expanded=False): # MODIFIED: Standardmäßig eingeklappt
        display_leaderboard(users)
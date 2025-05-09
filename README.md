# Vers-Lern-App

Eine interaktive Webanwendung zum Lernen und Verwalten von Bibelversen, gebaut mit Streamlit.

## Kurzbeschreibung

Diese App ermöglicht es Benutzern, eigene Bibeltext-Sammlungen zu erstellen und zu lernen, ihren Fortschritt zu verfolgen und sich mit anderen in Teams zu messen. Sie bietet verschiedene Lernmodi, eine detaillierte Benutzerverwaltung und Admin-Funktionen zur Pflege öffentlicher Textsammlungen. Ziel ist es, ein motivierendes und effektives Werkzeug für das Auswendiglernen von Bibelversen bereitzustellen.

## Setup & Installation

1.  **Python:** Stellen Sie sicher, dass Python 3.8 oder höher installiert ist.
2.  **Bibliotheken installieren:** Die App benötigt folgende Python-Pakete. Erstellen Sie eine `requirements.txt`-Datei mit diesem Inhalt:
    ```txt
    streamlit
    bcrypt
    ```
    Installieren Sie die Abhängigkeiten mit pip:
    ```bash
    pip install -r requirements.txt
    # Oder einzeln:
    # pip install streamlit bcrypt
    ```
3.  **Datenverzeichnis:** Die App erstellt beim ersten Start automatisch ein Verzeichnis namens `user_data` im selben Ordner, in dem `app.py` ausgeführt wird. Hier werden alle Benutzerdaten, Teams und Vers-Sammlungen gespeichert.

## Ausführen der App

1.  Navigieren Sie im Terminal zum Verzeichnis, in dem sich die `app.py`-Datei befindet.
2.  Führen Sie folgenden Befehl aus:
    ```bash
    streamlit run app.py
    ```
3.  Die App sollte sich dann in Ihrem Standard-Webbrowser öffnen.

## Hauptfunktionen

### 1. Verseingabe & -verwaltung
* **Eigene Bibeltext-Sammlungen:** Benutzer können eigene Sammlungen von Bibeltexten hinzufügen, jeweils mit einem Titel und dem Textinhalt.
* **Eingabeformat für Texte:**
    * **Format 1 (Nummerierung pro Vers):** Jeder Vers beginnt mit einer Zahl, gefolgt von einer Klammer, der Bibelstellenreferenz (z.B. Buch Kapitel:Vers) und dem eigentlichen Vers-Text.
        ```
        1) Joh 3:16 Denn so sehr hat Gott die Welt geliebt...
        2) Röm 8:28 Wir wissen aber, dass denen, die Gott lieben...
        ```
    * **Format 2 (Buch und Kapitel vorweg):** Die erste Zeile enthält das Buch und das Kapitel (z.B. "Johannes 3"). Die folgenden Zeilen beginnen direkt mit der Versnummer und dem Text.
        ```
        Johannes 3
        16 Denn so sehr hat Gott die Welt geliebt...
        17 Denn Gott hat seinen Sohn nicht in die Welt gesandt...

        Matthäus 5
        3 Selig sind die geistlich Armen...
        ```
    * Die Bibelstellen-Erkennung ist flexibel für gängige Abkürzungen (z.B. "1. Kor.", "Offb") und Versbereiche (z.B. "22:1-5").
* **Format-Validierung:** Eine automatische Prüfung stellt sicher, dass das eingegebene Format wahrscheinlich korrekt ist, bevor gespeichert wird. Bei Fehlern wird eine Meldung mit einem Link zur Format-Hilfe ([BibleServer Format Hilfe](https://bible.benkelm.de/frames.htm?listv.htm)) angezeigt.
* **Inhaltsprüfung (Basis):** Eine grundlegende Filterung auf eine Liste unangemessener Schlüsselwörter (z.B. zu den Themen Illegales, Schimpfwörter) erfolgt vor dem Speichern. *Hinweis: Echte Inhaltsmoderation ist ein komplexes Feld und diese Prüfung dient nur als Basis-Schutz.*
* **Sprachunterstützung:**
    * Texte werden einer Sprache zugeordnet (z.B. Deutsch, Englisch), wählbar über ein Flaggen-Emoji.
    * Die Speicherung, Auswahl und das Lernen von Texten erfolgt sprachspezifisch.
* **Private Texte:** Standardmäßig sind alle von Benutzern hinzugefügten Texte "privat" und nur für sie selbst sichtbar und lernbar.
* **Öffentliche Texte (Admin-Funktion):**
    * Ein Administrator kann über einen passwortgeschützten Bereich öffentliche Texte hinzufügen.
    * Öffentliche Texte sind für alle Nutzer sichtbar und auswählbar. Wenn ein Nutzer einen öffentlichen Text lernt, wird eine "personalisierte Kopie" in seinem Profil angelegt, für die der Lernfortschritt individuell gespeichert wird.
    * Im Auswahlmenü werden ursprünglich öffentliche Texte, die der Nutzer bereits bearbeitet (und somit kopiert) hat, mit einem `[P]` (Public Origin) und ggf. einem `✅` (Abgeschlossen) Marker versehen. Rein öffentliche, noch nicht bearbeitete Texte erscheinen nur mit `[P]`.

### 2. Lern-Interface & -Funktionalität
* **Textbausteine:** Der Text des aktuellen Verses wird in kleinere, zusammenhängende Wortgruppen (Textbausteine) zerlegt (maximal 8 Blöcke pro Vers).
* **Interaktives Zusammensetzen:** Diese Bausteine werden in zufälliger Reihenfolge als klickbare Buttons angezeigt, verteilt über mehrere Zeilen (maximal 4 pro Zeile).
* **Korrekte Reihenfolge:** Der Benutzer klickt die Buttons in der ursprünglichen, korrekten Reihenfolge des Verses an.
* **Rückgängig-Button (`↩️`):** Erlaubt das Zurücknehmen des zuletzt ausgewählten Textbausteins.
* **Feedback (Richtig):**
    * Bei korrekter Reihenfolge erscheint eine Erfolgsmeldung ("✅ Richtig!").
    * Eine Ballons-Animation wird ausgelöst.
    * Der korrekte, vollständige Vers wird zur Bestätigung angezeigt.
    * **Automatischer Wechsel (außer letzter Vers):** Nach einer kurzen Verzögerung (ca. 2 Sekunden) wird automatisch zum nächsten Vers gewechselt. Es ist kein "Weiter"-Button nötig.
    * **Abschluss eines Textes:** Wenn der letzte Vers eines Textes korrekt gelöst wurde, erscheint eine deutliche Erfolgsmeldung ("Super Big AMEN! Text abgeschlossen!"). Es erfolgt **kein** automatischer Wechsel zu einem anderen Text. Stattdessen gibt es eine längere Pause (6 Sekunden), und der Text wird für einen erneuten Durchlauf auf Vers 1 zurückgesetzt.
* **Feedback (Falsch):**
    * Bei falscher Reihenfolge (nachdem alle Bausteine gewählt wurden) erscheint eine Fehlermeldung ("❌ Leider falsch.").
    * Die vom Benutzer gewählte (fehlerhafte) Reihenfolge wird angezeigt, wobei die falsch platzierten Bausteine rot hervorgehoben werden.
    * Darunter wird der korrekte, vollständige Vers angezeigt.
* **Navigation (bei falscher Antwort):** Es erscheinen Buttons, um manuell zum nächsten Vers ("➡️ Nächster Vers") oder (im linearen Modus) zum vorherigen Vers ("⬅️ Zurück") zu springen.

### 3. Lernmodi & Fortschritt
* **Modusauswahl:** Benutzer können pro Bibeltext zwischen den Modi "Linear" und "Zufällig" wählen.
* **Linearer Modus:**
    * Verse werden in der Reihenfolge des ursprünglichen Textes angezeigt.
    * **Persistenter Fortschritt:** Der Index des nächsten zu lernenden Verses (`last_index`) wird pro Benutzer und pro Text (private Texte und personalisierte Kopien öffentlicher Texte) gespeichert, auch über Logout/Login hinweg. Beim erneuten Öffnen wird an dieser Stelle weitergelernt.
    * **Abschluss-Logik:** Wenn der letzte Vers eines Textes im linearen Modus korrekt abgeschlossen wurde, wird dies gespeichert (`completed_linear: True`). Beim nächsten Öffnen des Textes wird die Erfolgsmeldung ("Super Big AMEN!") angezeigt, und das Lernen beginnt wieder bei Vers 1 (Index 0). Der `last_index` wird bei Abschluss auf 0 gesetzt. Das ✅-Abzeichen erscheint im Auswahlmenü.
* **Zufälliger Modus:**
    * Verse werden in zufälliger Reihenfolge angezeigt.
    * **Einmaliger Durchlauf:** Alle Verse der Sammlung werden genau einmal angezeigt, bevor sich die Reihenfolge wiederholt. Der Fortschritt dieses Durchlaufs (welche Verse schon kamen und welche noch ausstehen) wird pro Benutzer und Text gespeichert und über Sitzungen hinweg beibehalten.
* **Fortschrittsbalken:** Unterhalb der Textauswahl wird ein Fortschrittsbalken angezeigt:
    * **Linear:** Zeigt `Aktueller Vers / Gesamtverse` an. Bei abgeschlossenen Texten wird ein grüner Balken mit "Abgeschlossen!" angezeigt.
    * **Zufällig:** Zeigt `Anzahl gelernter einzigartiger Verse (in diesem Durchlauf) / Gesamtverse` an.

### 4. Benutzerverwaltung & Community-Features
* **Benutzerkonten:**
    * Login/Registrierung mit Benutzername und Passwort.
    * Passwörter werden sicher mit bcrypt gehasht gespeichert.
    * *Hinweis: Echter persistenter Login über Browsersitzungen hinweg (z.B. mit "Angemeldet bleiben"-Checkbox) ist mit dem aktuellen Setup nicht sicher implementierbar und daher nicht enthalten. Der Login gilt nur für die aktuelle Browsersitzung.*
* **Statistiken (Sidebar, Ausklappbar):**
    * Pro Benutzer werden folgende Statistiken erfasst und angezeigt:
        * Gesamte Lernzeit (approximativ, basierend auf der Zeit pro Vers).
        * Anzahl insgesamt korrekt gelernter Verse.
        * Anzahl insgesamt korrekt gelernter Wörter.
* **Teams (Sidebar, Ausklappbar):**
    * Benutzer können Teams erstellen (Teamname eingeben -> einzigartiger Team-Code wird generiert).
    * Benutzer können existierenden Teams per Team-Code beitreten.
    * Benutzer können ihr aktuelles Team verlassen.
    * Die Team-Zugehörigkeit wird pro Benutzer gespeichert.
    * Anzeige des aktuellen Teams und der Optionen zum Erstellen/Beitreten/Verlassen.
* **Leaderboard (Sidebar, Ausklappbar):**
    * Zeigt die Top 7 Einzelspieler nach Gesamtpunkten.
    * Zeigt die Top 7 Teams nach Gesamtpunkten aller Teammitglieder.
    * (Darstellung als Textliste zur Optimierung der Performance).

### 5. Admin-Funktionen (Sidebar, Ausklappbar)
* **Passwortschutz:** Zugriff nur nach Eingabe des Admin-Passworts.
* **Öffentliche Texte verwalten:** Administratoren können neue öffentliche Bibeltexte für alle Sprachen hinzufügen. Diese werden in einer globalen Datei (`public_verses.json`) gespeichert.
* **Gefährliche Aktionen (mit Bestätigung):**
    * Alle öffentlichen Texte löschen.
    * Alle Benutzerpunkte auf 0 zurücksetzen.
* **PDF-Export (Konzept):** Ein Platzhalter für eine Funktion zum Exportieren von Punkteständen als PDF. Die Implementierung würde externe Bibliotheken wie FPDF und Matplotlib/Plotly erfordern.

### 6. UI/Layout & Refactoring
* **Layout:**
    * Linke Sidebar für Login/Logout, Benutzer-Informationen, Aktionen (Teams, Leaderboard, Statistiken, Texteingabe, Admin).
    * Hauptbereich für Auswahl-Widgets (Sprache, Text, Modus) und das Lern-Interface.
* **Ausklappbare Bereiche (`st.expander`):** Die Sektionen "Teams", "Leaderboard", "Statistiken", "Eigenen Text hinzufügen" und "Admin" in der Sidebar sind ausklappbar, um die Übersichtlichkeit zu wahren.
* **Konsolidierte Auswahl:** Im Hauptbereich werden Sprache, Textauswahl und Modusauswahl kompakt nebeneinander dargestellt.
* **Emoji-Nutzung:** Für eine freundlichere und intuitivere Bedienung (z.B. 📖 für Verse).

## Datenablage

Alle anwendungsbezogenen Daten werden lokal im Unterverzeichnis `user_data` gespeichert:

* `users.json`: Enthält Benutzerkontoinformationen (Benutzername, gehashtes Passwort), erreichte Punkte, Teamzugehörigkeit und persönliche Lernstatistiken.
* `teams.json`: Speichert Informationen über erstellte Teams (ID, Name, Beitrittscode, Mitgliederliste).
* `public_verses.json`: Eine globale Sammlung von Bibeltexten, die von Administratoren hinzugefügt wurden und allen Benutzern zur Verfügung stehen.
* `<username>_verses_v2.json`: Für jeden registrierten Benutzer wird eine Datei angelegt, die seine privaten Bibeltext-Sammlungen sowie personalisierte Kopien von ursprünglich öffentlichen Texten enthält. Hier wird auch der individuelle Lernfortschritt (letzter gelernter Vers, Abschluss-Status, Zufallsmodus-Status) für jeden dieser Texte gespeichert.

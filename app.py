import streamlit as st
import pandas as pd
import json
import urllib.request
import random
import imaplib
import email
import io
import zipfile
import re

# Configuration de l'application
st.set_page_config(page_title="Réserves & Stocks GL", page_icon="📦", layout="wide")

st.title("📦 Application Interne - Logistique & Moteur de Stock")
st.markdown("---")

# Récupération sécurisée des accès
try:
    SPREADSHEET_ID = st.secrets["DRIVE_SHEET_ID"]
    user_email = st.secrets["EMAIL_UTILISATEUR"]
    app_password = st.secrets["MOT_DE_PASSE_EMAIL"]
except Exception:
    st.error("❌ Erreur de configuration des clés secrètes sur le serveur Streamlit.")
    st.stop()

# Fonction de conversion Google Drive vers lien brut d'affichage web (lh3)
def optimiser_lien_drive(url):
    if not isinstance(url, str) or not url.startswith("http"):
        return url
    if "drive.google.com" in url:
        # Recherche précise de l'ID unique de 25 à 50 caractères
        match = re.search(r"(?:id=|/d/|/file/d/)([a-zA-Z0-9_-]{25,50})", url)
        if match:
            file_id = match.group(1)
            # Format d'affichage direct web officiel et sécurisé de Google
            return f"https://lh3.googleusercontent.com/d/{file_id}"
    return url

# Extracteur strict pour éviter la confusion entre colonnes de Texte et colonnes d'Images
def extraire_colonne(row, exact_name, keys_contain, keys_exclude=[]):
    # 1. Tentative de correspondance exacte en priorité
    for col in row.index:
        if str(col).strip().lower() == exact_name.lower():
            val = str(row[col]).strip()
            return val if val and val.lower() != "nan" else "Non renseigné"
            
    # 2. Recherche par mots-clés si non trouvé précisément
    for col in row.index:
        col_clean = str(col).lower().replace("é", "e").replace("è", "e").replace("à", "a").strip()
        if any(k in col_clean for k in keys_contain):
            if not any(x in col_clean for x in keys_exclude):
                val = str(row[col]).strip()
                return val if val and val.lower() != "nan" else "Non renseigné"
    return "Non renseigné"

# Moteur d'extraction des stocks depuis Gmail
@st.cache_data(ttl=10)
def fetch_stock_from_gmail(username, password):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password.replace(" ", ""))
        mail.select("inbox")
        status, messages = mail.search(None, 'ALL')
        if status != "OK" or not messages[0]:
            return None
        mail_ids = messages[0].split()
        for mail_id in reversed(mail_ids[-15:]):
            status, data = mail.fetch(mail_id, "(RFC822)")
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            sujet = str(msg.get("Subject", "")).lower()
            expediteur = str(msg.get("From", "")).lower()
            
            if "microstrategy" in expediteur or "stocks" in sujet:
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    filename = part.get_filename()
                    if filename:
                        filename_lower = filename.lower()
                        if filename_lower.endswith('.zip'):
                            zip_data = part.get_payload(decode=True)
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                                for zname in z.namelist():
                                    if zname.lower().endswith('.csv') or zname.lower().endswith('.txt'):
                                        bytes_content = z.read(zname)
                                        for encoding in ['utf-16', 'utf-16-le', 'latin-1', 'utf-8']:
                                            for sep in ['\t', ';', ',']:
                                                for skip in range(0, 6):
                                                    try:
                                                        df = pd.read_csv(io.BytesIO(bytes_content), sep=sep, engine='python', encoding=encoding, skiprows=skip, on_bad_lines='skip')
                                                        df.columns = [str(c).strip().replace('\x00', '') for c in df.columns]
                                                        if len(df.columns) > 4 and not any('STOCKS' in str(c).upper() for c in df.columns[:2]):
                                                            for col in df.columns:
                                                                df[col] = df[col].astype(str).str.replace('\x00', '', regex=False).str.strip()
                                                            return df
                                                    except:
                                                        continue
                        elif filename_lower.endswith('.csv') or filename_lower.endswith('.txt'):
                            csv_data = part.get_payload(decode=True)
                            for encoding in ['utf-16', 'utf-16-le', 'latin-1', 'utf-8']:
                                for sep in ['\t', ';', ',']:
                                    for skip in range(0, 6):
                                        try:
                                            df = pd.read_csv(io.BytesIO(csv_data), sep=sep, engine='python', encoding=encoding, skiprows=skip, on_bad_lines='skip')
                                            df.columns = [str(c).strip().replace('\x00', '') for c in df.columns]
                                            if len(df.columns) > 4 and not any('STOCKS' in str(c).upper() for c in df.columns[:2]):
                                                for col in df.columns:
                                                    df[col] = df[col].astype(str).str.replace('\x00', '', regex=False).str.strip()
                                                return df
                                        except:
                                            continue
        return None
    except:
        return None

# Moteur de lecture Google Sheets
def load_data_via_json_live(sheet_name):
    try:
        random_cache_buster = random.randint(1, 999999)
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:json&sheet={sheet_name}&cb={random_cache_buster}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_data = response.read().decode('utf-8')
            start = raw_data.find("google.visualization.Query.setResponse(") + len("google.visualization.Query.setResponse(")
            end = raw_data.rfind(");")
            json_data = json.loads(raw_data[start:end])
            columns = [col['label'].strip() if col['label'] else f"Col_{i}" for i, col in enumerate(json_data['table']['cols'])]
            rows = []
            for row in json_data['table']['rows']:
                cells = [cell['v'] if cell and 'v' in cell else None for cell in row['c']]
                rows.append(cells)
            return pd.DataFrame(rows, columns=columns)
    except:
        return None

# Chargement initial
df_marques = load_data_via_json_live("marques")
df_stock = fetch_stock_from_gmail(user_email, app_password)

if df_marques is not None:
    df_marques.columns = [str(c).strip() for c in df_marques.columns]
    
    st.subheader("1️⃣ Filtrer par Marque")
    col_marque_sheet = df_marques.columns[0]
    for c in df_marques.columns:
        if "marque" in c.lower():
            col_marque_sheet = c
            break
            
    recherche_marque = st.text_input("Entrez le nom d'une marque (ex: Ralph, Jacquemus, Carhartt...) :", key="search_brand").strip()
    
    if recherche_marque:
        brand_match = df_marques[df_marques[col_marque_sheet].astype(str).str.contains(recherche_marque, case=False, na=False)]
        
        if not brand_match.empty:
            infos_marque = brand_match.iloc[0]
            nom_marque_officiel = str(infos_marque[col_marque_sheet]).upper()
            
            # --- APPLICATON DE VOS NOUVELLES COLONNES EXACTES ---
            nom_reserve = extraire_colonne(infos_marque, "Nom de RESERVE", ["nom de reserve", "reserve"])
            ex_reserve = extraire_colonne(infos_marque, "ex RESERVE", ["ex reserve"])
            niveau_reserve = extraire_colonne(infos_marque, "niveau reserve", ["niveau reserve", "niveau"])
            groupe_rayon = extraire_colonne(infos_marque, "Groupe", ["groupe"])
            etage_floor = extraire_colonne(infos_marque, "etage floor", ["etage floor", "etage"])
            
            # Responsables (Données Textuelles)
            stockiste_nom = extraire_colonne(infos_marque, "Stockiste REFERENT", ["stockiste referent"], keys_exclude=["visuel", "image"])
            manager_nom = extraire_colonne(infos_marque, "Manager Vente", ["manager vente", "manager"], keys_exclude=["visuel", "image"])
            
            # Liens Médias
            plan_url = extraire_colonne(infos_marque, "PLAN", ["plan"])
            logo_reserve_url = extraire_colonne(infos_marque, "Logo Reserve", ["logo reserve"])
            video_url = extraire_colonne(infos_marque, "video du CHEMIN", ["video"])
            visuel_stockiste_url = extraire_colonne(infos_marque, "VISUEL Stockiste REFERENT", ["visuel stockiste"])
            image_manager_url = extraire_colonne(infos_marque, "image manager vente", ["image manager"])
            
            # Nettoyage pour retirer le ".0" des chiffres d'étages ou niveaux
            if niveau_reserve.endswith(".0"): niveau_reserve = niveau_reserve[:-2]
            if etage_floor.endswith(".0"): etage_floor = etage_floor[:-2]
            
            # --- AFFICHAGE DE LA FICHE ---
            st.success(f"📌 FICHE TECHNIQUE LOGISTIQUE : **{nom_marque_officiel}**")
            
            # Section 1 : Localisation
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.markdown(f"📦 **Nom de RÉSERVE :** `{nom_reserve}`")
                st.markdown(f"🕰️ **Ancienne Réserve (ex) :** {ex_reserve}")
            with col_info2:
                st.markdown(f"📐 **Niveau Réserve :** {niveau_reserve}")
                st.markdown(f"🏢 **Étage Floor :** {etage_floor}")
            with col_info3:
                st.markdown(f"🏷️ **Groupe / Rayon :** {groupe_rayon}")
            
            st.markdown("---")
            
            # Section 2 : Trombinoscope (Contacts Référents)
            st.markdown("### 👥 Contacts Référents")
            col_stk_txt, col_stk_img, col_mngr_txt, col_mngr_img = st.columns([2, 1, 2, 1])
            
            with col_stk_txt:
                st.markdown(f"👤 **Stockiste RÉFÉRENT :**")
                st.info(stockiste_nom)
            with col_stk_img:
                if visuel_stockiste_url.startswith("http"):
                    st.image(optimiser_lien_drive(visuel_stockiste_url), caption="Stockiste", width=130)
                else:
                    st.caption("🚫 Aucun visuel")
                    
            with col_mngr_txt:
                st.markdown(f"💼 **Manager Vente :**")
                st.info(manager_nom)
            with col_mngr_img:
                if image_manager_url.startswith("http"):
                    st.image(optimiser_lien_drive(image_manager_url), caption="Manager Vente", width=130)
                else:
                    st.caption("🚫 Aucun visuel")
            
            st.markdown("---")
            
            # Section 3 : Visualisation direct des Médias (Zéro boutons images)
            st.markdown("### 🗺️ Visualisation Directe de la Réserve")
            col_plan_view, col_logo_view, col_video_view = st.columns(3)
            
            with col_plan_view:
                st.markdown("#### 📐 Plan de la Réserve")
                if plan_url.startswith("http"):
                    st.image(optimiser_lien_drive(plan_url), use_container_width=True)
                else:
                    st.caption("❌ Aucun plan disponible")
                    
            with col_logo_view:
                st.markdown("#### 🪧 Enseigne / Logo Réserve")
                if logo_reserve_url.startswith("http"):
                    st.image(optimiser_lien_drive(logo_reserve_url), use_container_width=True)
                else:
                    st.caption("❌ Aucun logo disponible")
                    
            with col_video_view:
                st.markdown("#### 🎥 Chemin d'Orientation Vidéo")
                if video_url.startswith("http"):
                    st.video(video_url)
                else:
                    st.caption("❌ Aucune vidéo configurée")

            st.markdown("---")
            
            # --- BARRE DE RECHERCHE ARTICLES ---
            st.subheader(f"2️⃣ Préciser la recherche d'articles chez {nom_marque_officiel}")
            recherche_ref = st.text_input("Entrez un code EAN, une UG ou un mot-clé (ex: casquette, polo...) :", key="search_ref").strip().lower()
            
            if recherche_ref:
                if df_stock is None:
                    st.error("⚠️ Fichier de stock global introuvable.")
                else:
                    condition_marque_erp = False
                    for col in df_stock.columns:
                        condition_marque_erp |= df_stock[col].astype(str).str.contains(recherche_marque, case=False, na=False)
                    df_stock_marque = df_stock[condition_marque_erp]
                    
                    if df_stock_marque.empty:
                        df_stock_marque = df_stock
                    
                    keywords = recherche_ref.split()
                    combined_condition = True
                    for kw in keywords:
                        local_condition = False
                        for col in df_stock_marque.columns:
                            local_condition |= df_stock_marque[col].astype(str).str.lower().str.contains(kw, na=False)
                        combined_condition &= local_condition
                        
                    results = df_stock_marque[combined_condition]
                    
                    if not results.empty:
                        st.write(f"📊 {len(results)} référence(s) trouvée(s) :")
                        st.dataframe(results, use_container_width=True, hide_index=True)
                    else:
                        st.error(f"❌ Aucun article correspondant trouvé.")

import streamlit as st
import pandas as pd
import json
import urllib.request
import random
import imaplib
import email
import io
import zipfile

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

# Fonction de lecture automatique du stock (Gmail ZIP/TXT/CSV)
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

# Fonction de lecture Google Sheets
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

# Chargement initial des bases de données
df_marques = load_data_via_json_live("marques")
df_reserves = load_data_via_json_live("reserves")
df_stock = fetch_stock_from_gmail(user_email, app_password)

if df_marques is not None:
    # --- BARRE DE RECHERCHE 1 : LA MARQUE ---
    st.subheader("1️⃣ Filtrer par Marque")
    col_marque_sheet = 'Marques' if 'Marques' in df_marques.columns else df_marques.columns[0]
    
    recherche_marque = st.text_input("Entrez le nom d'une marque (ex: Ralph, Jacquemus, Carhartt...) :", key="search_brand").strip()
    
    if recherche_marque:
        # Recherche de la marque dans le Google Sheet
        brand_match = df_marques[df_marques[col_marque_sheet].astype(str).str.contains(recherche_marque, case=False, na=False)]
        
        if not brand_match.empty:
            infos_marque = brand_match.iloc[0]
            nom_marque_officiel = str(infos_marque[col_marque_sheet]).upper()
            
            # --- AFFICHAGE DE LA FICHE LOGISTIQUE ---
            st.success(f"📌 FICHE LOGISTIQUE : **{nom_marque_officiel}**")
            
            # Création de colonnes visuelles pour la présentation
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("📍 Emplacement", infos_marque.get('Nom de RESERVE', 'Non renseigné'))
                st.metric("🏢 Étage Floor", infos_marque.get('Étage floor', infos_marque.get('Etage', 'Non renseigné')))
            with c2:
                st.metric("👤 Stockiste Référent", infos_marque.get('Stockiste référent', infos_marque.get('Referent', 'Non renseigné')))
                st.metric("📐 Niveau Réserve", infos_marque.get('Niveau de la reserve', infos_marque.get('Niveau', 'Non renseigné')))
            with c3:
                # Affichage des photos / plans / vidéos si présents sous forme de liens
                for lien_col in ['Plan de la reserve', 'Plan', 'Photo du stockiste', 'Chemin video vers cette reserve dediée', 'Video']:
                    if lien_col in infos_marque and str(infos_marque[lien_col]).startswith('http'):
                        st.markdown(f"🔗 **[{lien_col}]({infos_marque[lien_col]})**")

            st.markdown("---")
            
            # --- BARRE DE RECHERCHE 2 : LA RÉFÉRENCE AU SEIN DE CETTE MARQUE ---
            st.subheader(f"2️⃣ Préciser la recherche chez {nom_marque_officiel}")
            recherche_ref = st.text_input("Entrez un code EAN, une UG ou un mot-clé (ex: casquette, polo, 370094...) :", key="search_ref").strip().lower()
            
            if recherche_ref:
                if df_stock is None:
                    st.error("⚠️ Fichier de stock global introuvable ou indisponible pour le moment.")
                else:
                    # 1. On filtre le stock pour ne garder QUE les lignes de cette marque
                    condition_marque_erp = False
                    for col in df_stock.columns:
                        condition_marque_erp |= df_stock[col].astype(str).str.contains(recherche_marque, case=False, na=False)
                    df_stock_marque = df_stock[condition_marque_erp]
                    
                    if df_stock_marque.empty:
                        # Si le filtre strict par marque ne donne rien, on cherche dans tout le stock pour ne rien rater
                        df_stock_marque = df_stock
                    
                    # 2. On applique la recherche de la référence
                    keywords = recherche_ref.split()
                    combined_condition = True
                    for kw in keywords:
                        local_condition = False
                        for col in df_stock_marque.columns:
                            local_condition |= df_stock_marque[col].astype(str).str.lower().str.contains(kw, na=False)
                        combined_condition &= local_condition
                        
                    results = df_stock_marque[combined_condition]
                    
                    if not results.empty:
                        st.write(f"📊 {len(results)} référence(s) trouvée(s) pour votre recherche :")
                        st.dataframe(results, use_container_width=True, hide_index=True)
                    else:
                        st.error(f"❌ Aucun article correspondant à '{recherche_ref}' trouvé pour la marque {nom_marque_officiel}.")
        else:
            st.error(f"❌ La marque '{recherche_marque}' est introuvable dans votre base Google Sheet.")
else:
    st.error("❌ Impossible de charger l'onglet 'marques' de votre Google Sheet.")

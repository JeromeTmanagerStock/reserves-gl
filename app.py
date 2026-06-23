import streamlit as st
import pandas as pd
import json
import urllib.request
import random
import imaplib
import email
import io
import re
import zipfile

# Configuration de l'application
st.set_page_config(page_title="Réserves & Stocks GL", page_icon="📦", layout="centered")

st.title("📦 Application Interne - Moteur de Recherche Stocks & Réserves")
st.markdown("---")

# Récupération sécurisée des accès
try:
    SPREADSHEET_ID = st.secrets["DRIVE_SHEET_ID"]
    user_email = st.secrets["EMAIL_UTILISATEUR"]
    app_password = st.secrets["MOT_DE_PASSE_EMAIL"]
except Exception:
    st.error("❌ Erreur de configuration des clés secrètes sur le serveur Streamlit.")
    st.stop()

# Fonction de lecture automatique compatible ZIP et CSV (via pièces jointes ou liens Drive)
@st.cache_data(ttl=10)
def fetch_stock_from_gmail(username, password):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password.replace(" ", ""))
        mail.select("inbox")
        
        status, messages = mail.search(None, '(SUBJECT "STOCKS AUTOMATIQUES")')
        if status != "OK" or not messages[0]:
            return None
            
        mail_ids = messages[0].split()
        for mail_id in reversed(mail_ids):
            status, data = mail.fetch(mail_id, "(RFC822)")
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # 1. Extraction du texte pour chercher un lien Google Drive (cas des fichiers lourds de l'ERP)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type in ["text/plain", "text/html"]:
                        try:
                            body += part.get_payload(decode=True).decode('utf-8')
                        except:
                            pass
            else:
                body = msg.get_payload(decode=True).decode('utf-8')
                
            # Recherche d'un ID de fichier Google Drive
            drive_match = re.search(r'https://drive\.google\.com/file/d/([a-zA-Z0-9-_]+)', body)
            if drive_match:
                file_id = drive_match.group(1)
                # On tente d'abord de le télécharger comme un fichier brut
                download_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
                try:
                    req = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response:
                        file_bytes = response.read()
                    
                    # Est-ce un fichier ZIP ?
                    if zipfile.is_zipfile(io.BytesIO(file_bytes)):
                        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                            # On prend le premier fichier CSV présent dans le ZIP
                            for zname in z.namelist():
                                if zname.lower().endswith('.csv'):
                                    with z.open(zname) as f:
                                        df = pd.read_csv(f, sep=',', encoding='utf-8', skiprows=1)
                                        df.columns = [c.strip() for c in df.columns]
                                        return df
                    else:
                        # C'est un CSV direct
                        df = pd.read_csv(io.BytesIO(file_bytes), sep=',', encoding='utf-8', skiprows=1)
                        df.columns = [c.strip() for c in df.columns]
                        return df
                except:
                    # Si l'export direct Google Sheet échoue (car c'est un vrai binaire ZIP stocké sur Drive)
                    # On utilise l'URL de téléchargement direct des fichiers Drive
                    alt_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    req = urllib.request.Request(alt_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response:
                        file_bytes = response.read()
                    if zipfile.is_zipfile(io.BytesIO(file_bytes)):
                        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                            for zname in z.namelist():
                                if zname.lower().endswith('.csv'):
                                    with z.open(zname) as f:
                                        df = pd.read_csv(f, sep=',', encoding='utf-8', skiprows=1)
                                        df.columns = [c.strip() for c in df.columns]
                                        return df

            # 2. Secours : Si l'ERP l'envoie en pièce jointe standard (sans lien Drive)
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                filename = part.get_filename()
                if filename:
                    filename_lower = filename.lower()
                    # Pièce jointe ZIP standard
                    if filename_lower.endswith('.zip'):
                        zip_data = part.get_payload(decode=True)
                        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                            for zname in z.namelist():
                                if zname.lower().endswith('.csv'):
                                    with z.open(zname) as f:
                                        df = pd.read_csv(f, sep=',', encoding='utf-8', skiprows=1)
                                        df.columns = [c.strip() for c in df.columns]
                                        return df
                    # Pièce jointe CSV standard
                    elif filename_lower.endswith('.csv'):
                        csv_data = part.get_payload(decode=True)
                        df = pd.read_csv(io.BytesIO(csv_data), sep=',', encoding='utf-8', skiprows=1)
                        df.columns = [c.strip() for c in df.columns]
                        return df
        return None
    except Exception:
        return None

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

df_marques = load_data_via_json_live("marques")
df_reserves = load_data_via_json_live("reserves")
df_stock = fetch_stock_from_gmail(user_email, app_password)

if df_marques is not None and df_reserves is not None:
    st.subheader("🔍 Barre de recherche unique (EAN, UG ou Désignation)")
    search_query = st.text_input("Entrez un code EAN ou des mots-clés (ex: polo gris ralph, carhartt...) :", placeholder="Tapez ici...")
    
    if search_query:
        search_query = search_query.strip().lower()
        
        if df_stock is None:
            st.error("⚠️ Fichier de stock introuvable. Assurez-vous que le mail automatique contient bien le fichier ou son lien Drive, et que l'accès au lien est ouvert.")
        else:
            if search_query.isdigit():
                results = df_stock[df_stock['EAN (Principal)'].astype(str).str.contains(search_query, na=False)]
            else:
                keywords = search_query.split()
                condition = True
                for kw in keywords:
                    condition &= (df_stock['Article'].astype(str).str.lower().str.contains(kw, na=False) | 
                                  df_stock['Famille'].astype(str).str.lower().str.contains(kw, na=False))
                results = df_stock[condition]
                
            if not results.empty:
                st.write(f"📊 {len(results)} référence(s) trouvée(s) :")
                display_cols = ['Marché', 'Famille', 'Article', 'EAN (Principal)', 'Stock fin (Qté)']
                available_cols = [c for c in display_cols if c in results.columns]
                st.dataframe(results[available_cols], use_container_width=True, hide_index=True)
                
                premiere_marque = results.iloc[0]['Famille'].strip()
                col_marque = 'Marques' if 'Marques' in df_marques.columns else df_marques.columns[0]
                brand_match = df_marques[df_marques[col_marque].astype(str).str.contains(premiere_marque, case=False, na=False)]
                
                if not brand_match.empty:
                    brand_row = brand_match.iloc[0]
                    nom_reserve = brand_row['Nom de RESERVE'] if 'Nom de RESERVE' in brand_row else "Non spécifiée"
                    st.markdown("---")
                    st.subheader(f"📍 Localisation Logistique : Réserve **{nom_reserve}**")
                    st.info(f"Cette marque est rattachée à la réserve {nom_reserve}.")
            else:
                st.error("❌ Aucun article correspondant dans le stock actuel.")

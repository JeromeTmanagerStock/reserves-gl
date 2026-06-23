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

# Fonction de lecture avec affichage des étapes de diagnostic
def fetch_stock_from_gmail(username, password):
    logs = []
    try:
        logs.append("🔌 Connexion à imap.gmail.com...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        
        logs.append(f"🔐 Tentative de connexion avec {username}...")
        mail.login(username, password.replace(" ", ""))
        
        logs.append("📂 Ouverture de la boîte de réception (INBOX)...")
        mail.select("inbox")
        
        status, messages = mail.search(None, 'ALL')
        if status != "OK" or not messages[0]:
            logs.append("⚠️ Aucun message trouvé dans la boîte de réception.")
            return None, logs
            
        mail_ids = messages[0].split()
        logs.append(f"📧 Nombre total de mails détectés : {len(mail_ids)}. Inspection des 15 derniers...")
        
        for mail_id in reversed(mail_ids[-15:]):
            status, data = mail.fetch(mail_id, "(RFC822)")
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            sujet = str(msg.get("Subject", "")).lower()
            expediteur = str(msg.get("From", "")).lower()
            
            if "microstrategy" in expediteur or "stocks" in sujet:
                logs.append(f"✅ Mail trouvé ! Sujet: '{msg.get('Subject')}' de {msg.get('From')}")
                
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    filename = part.get_filename()
                    if filename:
                        filename_lower = filename.lower()
                        logs.append(f"📎 Pièce jointe détectée : {filename}")
                        
                        if filename_lower.endswith('.zip'):
                            logs.append("📦 Analyse du fichier compressé ZIP...")
                            zip_data = part.get_payload(decode=True)
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                                logs.append(f"🗂️ Contenu du ZIP : {z.namelist()}")
                                for zname in z.namelist():
                                    if zname.lower().endswith('.csv') or zname.lower().endswith('.txt'):
                                        logs.append(f"📖 Lecture du fichier interne : {zname}")
                                        with z.open(zname) as f:
                                            df = pd.read_csv(f, sep=None, engine='python', encoding='utf-8', skiprows=1, on_bad_lines='skip')
                                            df.columns = [c.strip() for c in df.columns]
                                            logs.append("🎉 Données chargées avec succès depuis le ZIP !")
                                            return df, logs
                        
                        elif filename_lower.endswith('.csv') or filename_lower.endswith('.txt'):
                            logs.append("📖 Lecture du fichier CSV direct...")
                            csv_data = part.get_payload(decode=True)
                            df = pd.read_csv(io.BytesIO(csv_data), sep=None, engine='python', encoding='utf-8', skiprows=1, on_bad_lines='skip')
                            df.columns = [c.strip() for c in df.columns]
                            logs.append("🎉 Données chargées avec succès depuis le CSV direct !")
                            return df, logs
        
        logs.append("❌ Aucun mail correspondant aux critères n'a été validé.")
        return None, logs
    except Exception as e:
        logs.append(f"💥 ERREUR TECHNIQUE : {str(e)}")
        return None, logs

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

# Chargement des données + récupération des messages de diagnostic
df_stock, rapports_diagnostic = fetch_stock_from_gmail(user_email, app_password)

# Barre latérale pour voir ce qu'il se passe en arrière-plan
with st.sidebar:
    st.subheader("🛠️ Console de Diagnostic")
    for log in rapports_diagnostic:
        st.caption(log)

if df_marques is not None and df_reserves is not None:
    st.subheader("🔍 Barre de recherche unique (EAN, UG ou Désignation)")
    search_query = st.text_input("Entrez un code EAN ou des mots-clés (ex: polo gris ralph, carhartt...) :", placeholder="Tapez ici...")
    
    if search_query:
        search_query = search_query.strip().lower()
        
        if df_stock is None:
            st.error("⚠️ Fichier de stock introuvable dans la boîte mail. Consultez la 'Console de Diagnostic' dans le menu de gauche (flèche >) pour voir l'erreur.")
        else:
            col_ean = [c for c in df_stock.columns if 'ean' in c.lower()]
            col_article = [c for c in df_stock.columns if 'art' in c.lower() or 'lib' in c.lower() or 'des' in c.lower()]
            col_famille = [c for c in df_stock.columns if 'fam' in c.lower() or 'marq' in c.lower()]
            
            c_ean = col_ean[0] if col_ean else df_stock.columns[0]
            c_art = col_article[0] if col_article else df_stock.columns[1] if len(df_stock.columns) > 1 else df_stock.columns[0]
            c_fam = col_famille[0] if col_famille else c_art

            if search_query.isdigit():
                results = df_stock[df_stock[c_ean].astype(str).str.contains(search_query, na=False)]
            else:
                keywords = search_query.split()
                condition = True
                for kw in keywords:
                    condition &= (df_stock[c_art].astype(str).str.lower().str.contains(kw, na=False) | 
                                  df_stock[c_fam].astype(str).str.lower().str.contains(kw, na=False))
                results = df_stock[condition]
                
            if not results.empty:
                st.write(f"📊 {len(results)} référence(s) trouvée(s) :")
                display_cols = [c for c in df_stock.columns if any(x in c.lower() for x in ['march', 'fam', 'art', 'ean', 'sto', 'qte', 'fin'])]
                st.dataframe(results[display_cols if display_cols else df_stock.columns[:5]], use_container_width=True, hide_index=True)
                
                try:
                    premiere_marque = str(results.iloc[0][c_fam]).strip()
                    col_marque = 'Marques' if 'Marques' in df_marques.columns else df_marques.columns[0]
                    brand_match = df_marques[df_marques[col_marque].astype(str).str.contains(premiere_marque, case=False, na=False)]
                    
                    if not brand_match.empty:
                        brand_row = brand_match.iloc[0]
                        nom_reserve = brand_row['Nom de RESERVE'] if 'Nom de RESERVE' in brand_row else "Non spécifiée"
                        st.markdown("---")
                        st.subheader(f"📍 Localisation Logistique : Réserve **{nom_reserve}**")
                        st.info(f"Cette marque est rattachée à la réserve {nom_reserve}.")
                except:
                    pass
            else:
                st.error("❌ Aucun article correspondant dans le stock actuel.")

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

# Fonction de lecture intelligente (Gestion des en-têtes MicroStrategy de plusieurs lignes)
def fetch_stock_from_gmail(username, password):
    logs = []
    try:
        logs.append("🔌 Connexion à imap.gmail.com...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password.replace(" ", ""))
        mail.select("inbox")
        
        status, messages = mail.search(None, 'ALL')
        if status != "OK" or not messages[0]:
            return None, logs
            
        mail_ids = messages[0].split()
        for mail_id in reversed(mail_ids[-15:]):
            status, data = mail.fetch(mail_id, "(RFC822)")
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            sujet = str(msg.get("Subject", "")).lower()
            expediteur = str(msg.get("From", "")).lower()
            
            if "microstrategy" in expediteur or "stocks" in sujet:
                logs.append(f"✅ Mail détecté : '{msg.get('Subject')}'")
                
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    filename = part.get_filename()
                    if filename:
                        filename_lower = filename.lower()
                        logs.append(f"📎 Fichier trouvé : {filename}")
                        
                        if filename_lower.endswith('.zip'):
                            zip_data = part.get_payload(decode=True)
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                                for zname in z.namelist():
                                    if zname.lower().endswith('.csv') or zname.lower().endswith('.txt'):
                                        logs.append(f"📖 Extraction de : {zname}")
                                        bytes_content = z.read(zname)
                                        
                                        # Test des encodages, séparateurs et des sauts de ligne pour trouver les vraies données
                                        for encoding in ['utf-16', 'utf-16-le', 'latin-1', 'utf-8']:
                                            for sep in ['\t', ';', ',']:
                                                for skip in range(0, 6): # Teste en sautant de 0 à 5 lignes d'introduction
                                                    try:
                                                        df = pd.read_csv(io.BytesIO(bytes_content), sep=sep, engine='python', encoding=encoding, skiprows=skip, on_bad_lines='skip')
                                                        df.columns = [str(c).strip().replace('\x00', '') for c in df.columns]
                                                        
                                                        # Si on trouve beaucoup de colonnes (souvent > 5 pour un export ERP) 
                                                        # et que les colonnes ne contiennent pas de titres génériques comme "STOCKS"
                                                        if len(df.columns) > 4 and not any('STOCKS' in str(c).upper() for c in df.columns[:2]):
                                                            # Nettoyage complet
                                                            for col in df.columns:
                                                                df[col] = df[col].astype(str).str.replace('\x00', '', regex=False).str.strip()
                                                            
                                                            logs.append(f"🎉 Format validé ! Encodage: {encoding}, Lignes sautées: {skip}, Colonnes: {len(df.columns)}")
                                                            logs.append(f"📋 Vrais Titres détectés : {list(df.columns)[:5]}")
                                                            return df, logs
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
                                                logs.append(f"🎉 Format validé ! Encodage: {encoding}, Lignes sautées: {skip}")
                                                return df, logs
                                        except:
                                            continue
        return None, logs
    except Exception as e:
        logs.append(f"💥 ERREUR : {str(e)}")
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
df_stock, rapports_diagnostic = fetch_stock_from_gmail(user_email, app_password)

with st.sidebar:
    st.subheader("🛠️ Console de Diagnostic")
    for log in rapports_diagnostic:
        st.caption(log)

if df_marques is not None and df_reserves is not None:
    st.subheader("🔍 Barre de recherche unique (EAN, UG ou Désignation)")
    search_query = st.text_input("Entrez un code EAN, une UG ou des mots-clés (ex: jacquemus, ralph, 370094...) :", placeholder="Tapez ici...")
    
    if search_query:
        search_query = search_query.strip().lower()
        
        if df_stock is None:
            st.error("⚠️ Fichier de stock introuvable ou illisible.")
        else:
            # Recherche souple multicritère
            keywords = search_query.split()
            combined_condition = True
            
            for kw in keywords:
                local_condition = False
                for col in df_stock.columns:
                    local_condition |= df_stock[col].astype(str).str.lower().str.contains(kw, na=False)
                combined_condition &= local_condition
                
            results = df_stock[combined_condition]
                
            if not results.empty:
                st.write(f"📊 {len(results)} référence(s) trouvée(s) :")
                st.dataframe(results, use_container_width=True, hide_index=True)
                
                # Bloc de localisation
                try:
                    c_fam = df_stock.columns[0]
                    for col in df_stock.columns:
                        if any(x in col.lower() for x in ['fam', 'marq', 'lib', 'art', 'recher']):
                            c_fam = col
                            break
                            
                    premiere_marque = str(results.iloc[0][c_fam]).strip()
                    col_marque = 'Marques' if 'Marques' in df_marques.columns else df_marques.columns[0]
                    
                    brand_match = df_marques[df_marques[col_marque].astype(str).str.contains(premiere_marque, case=False, na=False)]
                    if brand_match.empty:
                        for _, row_m in df_marques.iterrows():
                            m_name = str(row_m[col_marque]).strip().lower()
                            if m_name and (m_name in premiere_marque.lower() or premiere_marque.lower() in m_name):
                                brand_match = df_marques[df_marques[col_marque] == row_m[col_marque]]
                                break
                                
                    if not brand_match.empty:
                        brand_row = brand_match.iloc[0]
                        nom_reserve = brand_row['Nom de RESERVE'] if 'Nom de RESERVE' in brand_row else "Non spécifiée"
                        st.markdown("---")
                        st.subheader(f"📍 Localisation Logistique : Réserve **{nom_reserve}**")
                        st.info(f"Cette référence est rattachée à la réserve {nom_reserve}.")
                except:
                    pass
            else:
                st.error("❌ Aucun article correspondant dans le stock actuel.")

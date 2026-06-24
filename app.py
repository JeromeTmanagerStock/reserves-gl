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

# Fonction magique pour transformer un lien de partage Google Drive en lien direct d'affichage (image/vidéo)
def optimiser_lien_drive(url):
    if not isinstance(url, str) or not url.startswith("http"):
        return url
    if "drive.google.com" in url:
        # Format classique : /file/d/ID/view...
        if "/file/d/" in url:
            id_fichier = url.split("/file/d/")[1].split("/")[0]
            return f"https://drive.google.com/uc?export=download&id={id_fichier}"
        # Format alternatif : ?id=ID
        elif "id=" in url:
            id_fichier = url.split("id=")[1].split("&")[0]
            return f"https://drive.google.com/uc?export=download&id={id_fichier}"
    return url

# Fonction d'extraction intelligente des données
def trouver_valeur_flexible(row, mots_cles, default="Non renseigné"):
    for col in row.index:
        col_clean = str(col).lower().replace("é", "e").replace("è", "e").replace("à", "a").strip()
        if any(kw in col_clean for kw in mots_cles):
            valeur = str(row[col]).strip()
            return valeur if valeur and valeur.lower() != "nan" else default
    return default

# Fonction de lecture automatique du stock (Gmail)
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
            
            emplacement = trouver_valeur_flexible(infos_marque, ["emplacement", "reserve", "nom de reserve"])
            etage = trouver_valeur_flexible(infos_marque, ["etage", "floor"])
            stockiste = trouver_valeur_flexible(infos_marque, ["stockiste", "referent", "responsable"])
            niveau = trouver_valeur_flexible(infos_marque, ["niveau"])
            
            plan_url = trouver_valeur_flexible(infos_marque, ["plan"])
            photo_url = trouver_valeur_flexible(infos_marque, ["photo", "image"])
            video_url = trouver_valeur_flexible(infos_marque, ["video", "chemin", "film"])
            
            # --- AFFICHAGE DE LA FICHE LOGISTIQUE ---
            st.success(f"📌 FICHE LOGISTIQUE : **{nom_marque_officiel}**")
            
            col_texte, col_photo_stockiste = st.columns([2, 1])
            
            with col_texte:
                st.write(f"📍 **Emplacement / Réserve :** {emplacement}")
                st.write(f"🏢 **Étage Floor :** {etage}")
                st.write(f"📐 **Niveau Réserve :** {niveau}")
                if stockiste.startswith("http"):
                    st.write(f"👤 **Stockiste Référent :** Associé (voir photo ci-contre)")
                else:
                    st.write(f"👤 **Stockiste Référent :** {stockiste}")
            
            with col_photo_stockiste:
                # 👤 Affichage Dynamique de la photo du stockiste
                lien_photo_eligible = optimiser_lien_drive(photo_url if photo_url.startswith("http") else stockiste)
                if isinstance(lien_photo_eligible, str) and lien_photo_eligible.startswith("http"):
                    try:
                        st.image(lien_photo_eligible, caption="👤 Photo du Stockiste Référent", width=160)
                    except Exception:
                        st.caption("ℹ️ Photo du stockiste disponible (Lien protégé ou indisponible)")
            
            # --- ZONE DES MÉDIAS DE LA RÉSERVE (EFFET WAOUU) ---
            st.markdown("### 🗺️ Visualisation de la Réserve & Accès")
            col_plan, col_video = st.columns(2)
            
            with col_plan:
                st.markdown("#### 📐 Plan de la Réserve")
                lien_plan_direct = optimiser_lien_drive(plan_url)
                if lien_plan_direct.startswith("http"):
                    try:
                        st.image(lien_plan_direct, use_container_width=True)
                    except Exception:
                        st.warning("⚠️ Impossible d'afficher l'image directement. Utilisez le lien de secours.")
                        st.markdown(f"[🔗 Ouvrir le Plan Réserve dans Drive]({plan_url})")
                else:
                    st.info("ℹ️ Aucun plan d'image renseigné pour cette réserve.")
                    
            with col_video:
                st.markdown("#### 🎥 Chemin d'orientation (Vidéo)")
                lien_video_direct = optimiser_lien_drive(video_url)
                if lien_video_direct.startswith("http"):
                    try:
                        st.video(lien_video_direct)
                    except Exception:
                        st.warning("⚠️ Le lecteur vidéo intégré a rencontré un problème. Lien de secours :")
                        st.markdown(f"[🎥 Regarder la vidéo d'accès]({video_url})")
                else:
                    st.info("ℹ️ Aucune vidéo d'orientation enregistrée pour cette réserve.")

            st.markdown("---")
            
            # --- BARRE DE RECHERCHE 2 : RECHERCHE ERP ---
            st.subheader(f"2️⃣ Préciser la recherche chez {nom_marque_officiel}")
            recherche_ref = st.text_input("Entrez un code EAN, une UG ou un mot-clé (ex: casquette, polo...) :", key="search_ref").strip().lower()
            
            if recherche_ref:
                if df_stock is None:
                    st.error("⚠️ Fichier de stock global introuvable dans la boîte mail.")
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
                        st.error(f"❌ Aucun article correspondant à '{recherche_ref}' trouvé dans le stock.")
        else:
            st.error(f"❌ La marque '{recherche_marque}' est introuvable.")
else:
    st.error("❌ Impossible de charger l'onglet 'marques' de votre Google Sheet.")

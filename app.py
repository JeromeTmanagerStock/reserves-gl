# --- ZONE DES MÉDIAS VISUELS DE LA RÉSERVE ---
            st.markdown("### 🗺️ Visualisation de la Réserve & Accès")
            col_plan, col_panneau, col_video = st.columns(3)
            
            with col_plan:
                st.markdown("#### 📐 Plan de la Réserve")
                if plan_url.startswith("http"):
                    lien_plan_direct = optimiser_lien_drive(plan_url)
                    # On teste l'affichage, si ça échoue, on ne laisse pas un carré blanc/brisé
                    try:
                        st.image(lien_plan_direct, use_container_width=True)
                    except Exception:
                        st.info("ℹ️ Le plan est au format vidéo ou page Web externe.")
                    
                    # Bouton d'accès toujours visible en dessous
                    st.link_button("🗺️ Voir/Ouvrir le Plan Réserve", plan_url, use_container_width=True)
                else:
                    st.caption("Aucun plan disponible")
                    
            with col_panneau:
                st.markdown("#### 🪧 Panneau de la Réserve")
                if panneau_url.startswith("http"):
                    lien_panneau_direct = optimiser_lien_drive(panneau_url)
                    try:
                        st.image(lien_panneau_direct, use_container_width=True)
                    except Exception:
                        st.info("ℹ️ Visuel disponible via le lien ci-dessous.")
                    st.link_button("🪧 Voir le Panneau Réserve", panneau_url, use_container_width=True)
                else:
                    st.caption("Aucun visuel de panneau disponible")
                    
            with col_video:
                st.markdown("#### 🎥 Chemin d'orientation")
                if video_url.startswith("http"):
                    lien_video_direct = optimiser_lien_drive(video_url)
                    try:
                        # Si c'est un lien YouTube ou une vidéo brute, Streamlit la lira
                        st.video(lien_video_direct)
                    except Exception:
                        st.link_button("🎥 Regarder la vidéo d'accès", video_url, use_container_width=True)
                else:
                    st.caption("Aucune vidéo disponible")

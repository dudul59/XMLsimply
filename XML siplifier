# app.py
import streamlit as st
import xml.etree.ElementTree as ET
from collections import defaultdict
import os
import io
import zipfile

# -----------------------------------------------------------------------------
# --- VOS FONCTIONS DE TRAITEMENT (issues de votre script Colab) ---
# -----------------------------------------------------------------------------

def parse_float(text):
    """Convertit un texte en float, retourne 0.0 si le texte est vide ou invalide."""
    if not text:
        return 0.0
    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0

def simplify_murs(mur_collection):
    groups = defaultdict(list)
    for mur in mur_collection.findall('mur'):
        key_parts = []
        de = mur.find('donnee_entree')
        di = mur.find('donnee_intermediaire')
        if de is None or di is None: continue
        for tag in ['enum_type_adjacence_id', 'enum_orientation_id', 'paroi_lourde', 'enum_type_isolation_id']:
            el = de.find(tag)
            key_parts.append(el.text if el is not None else '')
        el = di.find('umur')
        key_parts.append(el.text if el is not None else '')
        groups[tuple(key_parts)].append(mur)

    new_collection = ET.Element('mur_collection')
    ref_map = {}
    i = 1
    orientation_map = {'1': 'Nord', '2': 'Est', '3': 'Sud', '4': 'Ouest'}
    adjacence_map = {'1': 'Ext', '8': 'LNC', '9': 'LNC'}
    for key, murs in groups.items():
        new_mur = ET.fromstring(ET.tostring(murs[0]))
        adj_code, orient_code = key[0], key[1]
        new_ref = f"mur_groupe_{i}_{adjacence_map.get(adj_code, 'Autre')}_{orientation_map.get(orient_code, 'SO')}"
        new_mur.find('.//reference').text = new_ref
        new_mur.find('.//description').text = f"Murs {adjacence_map.get(adj_code, 'Autre')} - {orientation_map.get(orient_code, 'Sans Orient')}"
        total_opaque = sum(parse_float(m.find('.//surface_paroi_opaque').text) for m in murs)
        total_totale = sum(parse_float(m.find('.//surface_paroi_totale').text) for m in murs)
        new_mur.find('.//surface_paroi_opaque').text = f"{total_opaque:.3f}"
        new_mur.find('.//surface_paroi_totale').text = f"{total_totale:.3f}"
        new_collection.append(new_mur)
        for mur in murs:
            old_ref = mur.find('.//reference')
            if old_ref is not None:
                ref_map[old_ref.text] = new_ref
        i += 1
    return new_collection, ref_map

def simplify_planchers_hauts(ph_collection):
    all_phs = ph_collection.findall('plancher_haut')
    new_collection = ET.Element('plancher_haut_collection')
    ref_map = {}
    new_ph = ET.fromstring(ET.tostring(all_phs[0]))
    new_ref = "ph_groupe_1_combles"
    new_ph.find('.//reference').text = new_ref
    new_ph.find('.//description').text = "Ensemble toitures sur combles perdus"
    total_opaque = sum(parse_float(ph.find('.//surface_paroi_opaque').text) for ph in all_phs)
    total_aiu = sum(parse_float(ph.find('.//surface_aiu').text) for ph in all_phs)
    new_ph.find('.//surface_paroi_opaque').text = f"{total_opaque:.3f}"
    new_ph.find('.//surface_aiu').text = f"{total_aiu:.3f}"
    new_collection.append(new_ph)
    for ph in all_phs:
        old_ref = ph.find('.//reference')
        if old_ref is not None:
            ref_map[old_ref.text] = new_ref
    return new_collection, ref_map

def update_and_simplify_baies(collection, mur_ref_map):
    new_collection = ET.Element('baie_vitree_collection')
    baies_par_nouveau_mur = defaultdict(list)
    for baie in collection.findall('baie_vitree'):
        ref_paroi = baie.find('.//reference_paroi')
        if ref_paroi is not None and ref_paroi.text in mur_ref_map:
            new_mur_ref = mur_ref_map[ref_paroi.text]
            baie_clone = ET.fromstring(ET.tostring(baie))
            baie_clone.find('.//reference_paroi').text = new_mur_ref
            baies_par_nouveau_mur[new_mur_ref].append(baie_clone)

    for _, baies in baies_par_nouveau_mur.items():
        groupes_baies = defaultdict(list)
        for baie in baies:
            de = baie.find('donnee_entree')
            key_parts = [de.findtext(tag) or 'N/A' for tag in ['uw_saisi', 'sw_saisi', 'enum_type_materiaux_menuiserie_id']]
            groupes_baies[tuple(key_parts)].append(baie)

        for _, baie_group in groupes_baies.items():
            if len(baie_group) > 1:
                new_baie = ET.fromstring(ET.tostring(baie_group[0]))
                total_surface = sum(parse_float(b.find('.//surface_totale_baie').text) for b in baie_group)
                new_baie.find('.//surface_totale_baie').text = f"{total_surface:.3f}"
                new_baie.find('.//nb_baie').text = str(len(baie_group))
                new_baie.find('.//description').text = "Fenêtres groupées"
                new_collection.append(new_baie)
            else:
                new_collection.append(baie_group[0])
    return new_collection

def update_other_references(enveloppe, mur_ref_map):
    for tag_name in ['porte', 'baie_vitree']:
        for elem in enveloppe.findall(f'.//{tag_name}'):
            ref_paroi = elem.find('.//reference_paroi')
            if ref_paroi is not None and ref_paroi.text in mur_ref_map:
                ref_paroi.text = mur_ref_map[ref_paroi.text]
    for pt in enveloppe.findall('.//pont_thermique'):
        ref1 = pt.find('.//reference_1')
        if ref1 is not None and ref1.text in mur_ref_map:
            ref1.text = mur_ref_map[ref1.text]

def simplify_dpe_xml(input_stream):
    """
    Fonction principale modifiée pour lire un flux (stream) en entrée
    et retourner l'arbre XML traité.
    """
    try:
        tree = ET.parse(input_stream)
        root = tree.getroot()
        logement = root.find('logement')
        if logement is None: return None
        enveloppe = logement.find('enveloppe')
        if enveloppe is None: return None

        # --- Étape 1: Générer les nouvelles collections simplifiées ---
        mur_ref_map = {}
        new_mur_collection, new_ph_collection, new_baie_collection = None, None, None

        mur_collection = enveloppe.find('mur_collection')
        if mur_collection is not None:
            new_mur_collection, mur_ref_map = simplify_murs(mur_collection)

        ph_collection = enveloppe.find('plancher_haut_collection')
        if ph_collection is not None and len(ph_collection.findall('plancher_haut')) > 1:
            new_ph_collection, _ = simplify_planchers_hauts(ph_collection)

        baie_collection = enveloppe.find('baie_vitree_collection')
        if baie_collection is not None:
            new_baie_collection = update_and_simplify_baies(baie_collection, mur_ref_map)

        # --- Étape 2: Mettre à jour les références ---
        update_other_references(enveloppe, mur_ref_map)

        # --- Étape 3: Reconstruire l'élément <enveloppe> ---
        new_enveloppe = ET.Element('enveloppe')
        children_tags_to_replace = {
            'mur_collection': new_mur_collection,
            'plancher_haut_collection': new_ph_collection,
            'baie_vitree_collection': new_baie_collection
        }
        for child in list(enveloppe):
            if child.tag in children_tags_to_replace and children_tags_to_replace[child.tag] is not None:
                new_enveloppe.append(children_tags_to_replace[child.tag])
            else:
                new_enveloppe.append(child)

        # --- Étape 4: Remplacer l'ancienne <enveloppe> ---
        logement.remove(enveloppe)
        logement.append(new_enveloppe)

        return tree

    except Exception as e:
        st.error(f"Une erreur est survenue pendant la simplification : {e}")
        return None

# --------------------------------------------------------------------------
# --- INTERFACE DE L'APPLICATION STREAMLIT ---
# --------------------------------------------------------------------------

st.set_page_config(page_title="Simplificateur XML DPE", layout="centered")

st.title("️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️️- 🏡 Simplificateur de Fichiers XML DPE")
st.write("Déposez un ou plusieurs fichiers XML d'audit énergétique pour les simplifier et les télécharger.")



uploaded_files = st.file_uploader(
    "Choisissez vos fichiers XML",
    type="xml",
    accept_multiple_files=True,
    label_visibility="collapsed"
)

if uploaded_files:
    st.info(f"{len(uploaded_files)} fichier(s) sélectionné(s). Cliquez sur le bouton pour démarrer.")
    
    if st.button("🚀 Lancer la simplification", type="primary"):
        zip_buffer = io.BytesIO()
        
        with st.spinner('Traitement en cours...'):
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for uploaded_file in uploaded_files:
                    
                    # Le fichier est lu en mémoire
                    simplified_tree = simplify_dpe_xml(uploaded_file)

                    if simplified_tree:
                        # On crée un buffer en mémoire pour écrire le XML simplifié
                        output_buffer = io.BytesIO()
                        simplified_tree.write(output_buffer, encoding='UTF-8', xml_declaration=True)
                        output_buffer.seek(0)
                        
                        # On génère le nouveau nom de fichier
                        new_filename = uploaded_file.name.rsplit('.', 1)[0] + '_simplifie.xml'
                        
                        # On ajoute le fichier simplifié à l'archive ZIP
                        zf.writestr(new_filename, output_buffer.getvalue())
                        st.write(f"✅ {uploaded_file.name} traité avec succès.")

        # On prépare le ZIP pour le téléchargement
        zip_buffer.seek(0)

        st.success("🎉 Simplification terminée !")
        
        st.download_button(
            label="📥 Télécharger le fichier ZIP",
            data=zip_buffer,
            file_name="resultats_simplifies.zip",
            mime="application/zip"
        )

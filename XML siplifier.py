import streamlit as st
import xml.etree.ElementTree as ET
from collections import defaultdict
import io
import zipfile
import traceback

# -----------------------------------------------------------------------------
# --- VOS NOUVELLES FONCTIONS DE TRAITEMENT XML (AVEC RAPPORT ENCORE PLUS DÉTAILLÉ) ---
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
            key_parts.append(el.text if el is not None and el.text is not None else '')
        el = di.find('umur')
        key_parts.append(el.text if el is not None and el.text is not None else '')
        groups[tuple(key_parts)].append(mur)
    
    if not groups or len(mur_collection.findall('mur')) <=1:
        return mur_collection, {}

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
        if new_mur.find('.//surface_paroi_totale') is not None:
            new_mur.find('.//surface_paroi_totale').text = f"{total_totale:.3f}"
        new_collection.append(new_mur)
        for mur in murs:
            old_ref = mur.find('.//reference')
            if old_ref is not None:
                ref_map[old_ref.text] = new_ref
        i += 1
    return new_collection, ref_map

def simplify_planchers_hauts(ph_collection):
    if ph_collection is None: return None, {}
    all_phs = ph_collection.findall('plancher_haut')
    if not all_phs: return ph_collection, {}
    new_collection = ET.Element('plancher_haut_collection')
    ref_map = {}
    new_ph = ET.fromstring(ET.tostring(all_phs[0]))
    new_ref = "ph_groupe_1_combles"
    new_ph.find('.//reference').text = new_ref
    new_ph.find('.//description').text = "Ensemble toitures sur combles perdus"
    total_opaque = sum(parse_float(ph.find('.//surface_paroi_opaque').text) for ph in all_phs)
    if all_phs[0].find('.//surface_aiu') is not None:
        total_aiu = sum(parse_float(ph.find('.//surface_aiu').text) for ph in all_phs)
        new_ph.find('.//surface_aiu').text = f"{total_aiu:.3f}"
    new_ph.find('.//surface_paroi_opaque').text = f"{total_opaque:.3f}"
    new_collection.append(new_ph)
    for ph in all_phs:
        old_ref = ph.find('.//reference')
        if old_ref is not None:
            ref_map[old_ref.text] = new_ref
    return new_collection, ref_map

def update_and_simplify_baies(collection, mur_ref_map):
    if collection is None: return None
    new_collection = ET.Element('baie_vitree_collection')
    baies_par_nouveau_mur = defaultdict(list)
    
    cloned_baies = [ET.fromstring(ET.tostring(baie)) for baie in collection.findall('baie_vitree')]
    for baie in cloned_baies:
        ref_paroi = baie.find('.//reference_paroi')
        new_mur_ref = mur_ref_map.get(ref_paroi.text if ref_paroi is not None else None)
        if new_mur_ref:
            if ref_paroi is not None:
                baie.find('.//reference_paroi').text = new_mur_ref
            baies_par_nouveau_mur[new_mur_ref].append(baie)
        else:
            baies_par_nouveau_mur["unmapped"].append(baie)

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
                if new_baie.find('.//nb_baie') is not None:
                    new_baie.find('.//nb_baie').text = str(len(baie_group))
                new_baie.find('.//description').text = "Fenêtres groupées"
                new_collection.append(new_baie)
            else:
                new_collection.append(baie_group[0])
    return new_collection

def update_other_references(enveloppe, mur_ref_map):
    for tag_name in ['porte']:
        collection = enveloppe.find(f'{tag_name}_collection')
        if collection is not None:
            for elem in collection.findall(f'.//{tag_name}'):
                ref_paroi = elem.find('.//reference_paroi')
                if ref_paroi is not None and ref_paroi.text in mur_ref_map:
                    ref_paroi.text = mur_ref_map[ref_paroi.text]
    
    pt_collection = enveloppe.find('pont_thermique_collection')
    if pt_collection is not None:
        for pt in pt_collection.findall('.//pont_thermique'):
            for ref_tag in ['reference_1', 'reference_2']:
                ref = pt.find(f'.//{ref_tag}')
                if ref is not None and ref.text in mur_ref_map:
                    ref.text = mur_ref_map[ref.text]

def simplify_dpe_xml_streamlit(input_stream):
    """
    Fonction principale adaptée pour Streamlit:
    - Prend un flux (stream) en entrée.
    - Retourne l'arbre XML traité ET les données pour le rapport détaillé.
    """
    try:
        input_content = input_stream.read()
        
        # --- Étape 0: Collecter les données AVANT simplification pour le rapport ---
        tree_before_parse = ET.parse(io.BytesIO(input_content))
        enveloppe_before = tree_before_parse.getroot().find('.//enveloppe')
        report_before = defaultdict(list)
        orientation_map = {'1': 'Nord', '2': 'Est', '3': 'Sud', '4': 'Ouest', 'N/A': 'N/A'}
        adjacence_map_report = {'1': 'Ext', '8': 'Int', '9': 'Int', '12': 'Combles', '5': 'Terre-plein', '6': 'Sous-sol/VS'}

        for mur in enveloppe_before.findall('.//mur'):
            de = mur.find('donnee_entree')
            desc = de.find('description').text
            surf = parse_float(de.find('surface_paroi_opaque').text)
            orient_id = de.findtext('enum_orientation_id', 'N/A')
            adj_id = de.findtext('enum_type_adjacence_id', 'N/A')
            orient_text = orientation_map.get(orient_id, '?')
            adj_text = adjacence_map_report.get(adj_id, 'Autre')
            report_before['Murs'].append(f"  - {desc} ({adj_text} | {orient_text} | {surf:.2f} m²)")

        for pb in enveloppe_before.findall('.//plancher_bas'):
            de = pb.find('donnee_entree')
            desc = de.find('description').text
            surf = parse_float(de.find('surface_paroi_opaque').text)
            adj_id = de.findtext('enum_type_adjacence_id', 'N/A')
            adj_text = adjacence_map_report.get(adj_id, 'Autre')
            report_before['Planchers Bas'].append(f"  - {desc} ({adj_text} | {surf:.2f} m²)")

        for ph in enveloppe_before.findall('.//plancher_haut'):
            de = ph.find('donnee_entree')
            desc = de.find('description').text
            surf = parse_float(de.find('surface_paroi_opaque').text)
            adj_id = de.findtext('enum_type_adjacence_id', 'N/A')
            adj_text = adjacence_map_report.get(adj_id, 'Autre')
            report_before['Planchers Hauts'].append(f"  - {desc} ({adj_text} | {surf:.2f} m²)")

        # --- Début de la simplification ---
        tree = ET.parse(io.BytesIO(input_content))
        root = tree.getroot()
        logement = root.find('logement')
        if logement is None: return None, None, None
        enveloppe = logement.find('enveloppe')
        if enveloppe is None: return None, None, None
        
        mur_ref_map = {}
        new_mur_collection, new_ph_collection = None, None

        mur_collection = enveloppe.find('mur_collection')
        if mur_collection is not None:
            new_mur_collection, mur_ref_map_murs = simplify_murs(mur_collection)
            mur_ref_map.update(mur_ref_map_murs)

        ph_collection = enveloppe.find('plancher_haut_collection')
        if ph_collection is not None:
            new_ph_collection, mur_ref_map_ph = simplify_planchers_hauts(ph_collection)
            mur_ref_map.update(mur_ref_map_ph)
        
        baie_collection = enveloppe.find('baie_vitree_collection')
        new_baie_collection = update_and_simplify_baies(baie_collection, mur_ref_map) if baie_collection is not None else None
        
        update_other_references(enveloppe, mur_ref_map)

        new_enveloppe = ET.Element('enveloppe')
        collections_map = {
            'mur_collection': new_mur_collection,
            'plancher_haut_collection': new_ph_collection,
            'baie_vitree_collection': new_baie_collection
        }
        for child in list(enveloppe):
            if child.tag in collections_map and collections_map[child.tag] is not None:
                new_enveloppe.append(collections_map[child.tag])
            else:
                new_enveloppe.append(child)

        logement.remove(enveloppe)
        meteo = logement.find('meteo')
        meteo_index = list(logement).index(meteo) if meteo is not None else 0
        logement.insert(meteo_index + 1, new_enveloppe)
        
        # --- Étape 6: Collecter les données APRÈS simplification pour le rapport ---
        report_after = defaultdict(list)
        for mur in new_enveloppe.findall('.//mur'):
            desc = mur.find('.//description').text
            surf = parse_float(mur.find('.//surface_paroi_opaque').text)
            report_after['Murs'].append(f"  - {desc} ({surf:.2f} m²)")
        for pb in new_enveloppe.findall('.//plancher_bas'):
            desc = pb.find('.//description').text
            surf = parse_float(pb.find('.//surface_paroi_opaque').text)
            report_after['Planchers Bas'].append(f"  - {desc} ({surf:.2f} m²)")
        for ph in new_enveloppe.findall('.//plancher_haut'):
            desc = ph.find('.//description').text
            surf = parse_float(ph.find('.//surface_paroi_opaque').text)
            report_after['Planchers Hauts'].append(f"  - {desc} ({surf:.2f} m²)")

        return tree, report_before, report_after

    except Exception:
        st.error(f"Erreur inattendue lors du traitement d'un fichier : {traceback.format_exc()}")
        return None, None, None

# --------------------------------------------------------------------------
# --- INTERFACE DE L'APPLICATION STREAMLIT ---
# --------------------------------------------------------------------------

st.set_page_config(page_title="Simplificateur XML DPE", layout="wide")

st.title("🏡 Simplificateur de Fichiers XML DPE (avec Rapport Détaillé)")
st.write("Déposez un ou plusieurs fichiers XML d'audit énergétique pour les simplifier et visualiser un rapport détaillé.")

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
        all_reports_data = {}
        
        with st.spinner('Traitement en cours...'):
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for uploaded_file in uploaded_files:
                    
                    simplified_tree, report_before, report_after = simplify_dpe_xml_streamlit(uploaded_file)

                    if simplified_tree and report_before is not None and report_after is not None:
                        all_reports_data[uploaded_file.name] = (report_before, report_after)
                        
                        output_buffer = io.BytesIO()
                        simplified_tree.write(output_buffer, encoding='UTF-8', xml_declaration=True)
                        output_buffer.seek(0)
                        
                        new_filename = uploaded_file.name.rsplit('.', 1)[0] + '_simplifie.xml'
                        zf.writestr(new_filename, output_buffer.getvalue())

        st.success("🎉 Simplification terminée !")

        st.header("📊 Rapport de Simplification Détaillé")
        
        for filename, (before, after) in all_reports_data.items():
            with st.expander(f"📄 Voir le rapport pour : **{filename}**"):
                for key in ["Murs", "Planchers Bas", "Planchers Hauts"]:
                    if key in before or key in after:
                        st.subheader(f"Catégorie : {key}")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown(f"**AVANT SIMPLIFICATION ({len(before.get(key, []))} éléments)**")
                            report_text_before = "\n".join(before.get(key, ["N/A"]))
                            st.code(report_text_before, language=None)

                        with col2:
                            st.markdown(f"**APRÈS SIMPLIFICATION ({len(after.get(key, []))} groupes)**")
                            report_text_after = "\n".join(after.get(key, ["N/A"]))
                            st.code(report_text_after, language=None)

        # On prépare le ZIP pour le téléchargement
        zip_buffer.seek(0)
        
        st.download_button(
            label="📥 Télécharger les fichiers simplifiés (.zip)",
            data=zip_buffer,
            file_name="resultats_simplifies.zip",
            mime="application/zip"
        )

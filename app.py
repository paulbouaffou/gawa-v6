from flask import Flask, render_template, request, redirect, url_for
import re
import requests
from urllib.parse import urlencode
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

TYPES_ARTICLES = {
    "À sourcer": "https://fr.wikipedia.org/wiki/Aide:Sources",
    "Orphelin": "https://fr.wikipedia.org/wiki/Wikipédia:Orphelin",
    "À wikifier": "https://fr.wikipedia.org/wiki/Aide:Wikification"
}

# Structure: {"YYYY-MM": [evenement, ...]}
evenements_par_mois = defaultdict(list)

def generer_lien_petscan(modele, limit):

    params = {

      "language": "fr",
      "interface_language": "fr",
      "project": "wikipedia",
      "categories": "Portail:Côte d'Ivoire/Articles liés",
      "templates_any": modele,
      "format": "json",
      "combination": "subset",
      "edits[anons]": "both",
      "edits[bots]": "both",
      "edits[flagged]": "both",
      "sortorder": "ascending",
      "sortby": "none",
      "active_tab": "tab_templates_n_links",
      "show_redirects": "both",
      "show_soft_redirects": "both",
      "page_image": "any",
      "output_compatability": "catscan",
      "subpage_filter": "either",
      "search_max_results": "500",
      "ores_prediction": "any",
      "ores_type": "any",
      "min_redlink_count": "1",
      "cb_labels_yes_l": "1",
      "cb_labels_no_l": "1",
      "cb_labels_any_l": "1",
      "namespace_conversion": "keep",
      "ns[0]": "1",
      "depth": "0",
      "wikidata_item": "no",
      "show_disambiguation_pages": "both",
      "common_wiki": "auto",
      "limit": limit,
      "doit": "Do it!"
  
    }
    query_string = urlencode(params, doseq=True)
    # Construction de l'URL finale
    base_url = "https://petscan.wmflabs.org/"
    full_url = f"{base_url}?{query_string}"
    return full_url

def get_articles_from_petscan(modele, limit):
    url = generer_lien_petscan(modele, limit)
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        titles = []

        if isinstance(data, dict):
            outer_list = data.get("*")
            if isinstance(outer_list, list) and len(outer_list) > 0:
                first_item = outer_list[0]
                inner_a = first_item.get("a")
                if isinstance(inner_a, dict):
                    page_list = inner_a.get("*")
                    if isinstance(page_list, list):
                        for page in page_list:
                            if isinstance(page, dict):
                                title = page.get("title")
                                if title:
                                    titles.append(title)
            
        return titles

    except Exception as e:
        print(f"Erreur : {e}")
        return []



@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html') 

@app.route('/about')
def about():
    return render_template('home.html')

@app.route('/stats')
def stats():
    return render_template('home.html')

@app.route('/help')
def help():
    return render_template('home.html')

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.route("/formulaire", methods=["GET", "POST"])
def formulaire():
    if request.method == "POST":
        nom = request.form.get("nom")
        lien = request.form.get("lien")
        type_article = request.form.get("type_article")
        nombre = request.form.get("nombre")

        if not all([nom, lien, type_article, nombre]):
            return render_template("formulaire.html", error="Tous les champs sont obligatoires.", types=TYPES_ARTICLES)

        if not re.match(r"^https://outreachdashboard\.wmflabs\.org/courses/", lien):
            return render_template("formulaire.html", error="Lien invalide.", types=TYPES_ARTICLES)

        date_now = datetime.now()
        clef_mois = date_now.strftime("%Y-%m")

        evenement = {
            "nom": nom,
            "lien": lien,
            "type": type_article,
            "nombre": nombre,
            "date": date_now.strftime("%d/%m/%Y")
        }

        evenements_par_mois[clef_mois].append(evenement)

        return redirect(url_for("resultats", type_article=type_article, nombre=nombre))

    return render_template("formulaire.html", types=TYPES_ARTICLES)

@app.route("/resultats")
def resultats():
    type_article = request.args.get("type_article")
    nombre = int(request.args.get("nombre"))
    limit = nombre
    doc_url = TYPES_ARTICLES.get(type_article, "#")

    modele = type_article
    if not modele:
        return "Type inconnu", 400

    articles_content = get_articles_from_petscan(modele, limit)
    articles = articles_content[:nombre]
    total = len(articles_content)
    texte_a_copier = "\n".join([f"# [[{article.replace('_', ' ')}]]" for article in articles])

    return render_template("resultats.html", nombre=nombre, articles=articles, type_article=type_article, total=total, doc_url=doc_url, texte_a_copier=texte_a_copier)

@app.route("/evenements")
def evenements():
    return render_template("evenements.html", evenements_par_mois=evenements_par_mois)


if __name__ == '__main__':
    app.run(debug=True)

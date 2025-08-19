import requests
from urllib.parse import quote


def generer_lien_petscan(modele):
    # Encodage correct du nom de modèle (ex : "À sourcer")
    modele_encode = quote(modele)

    base_url = (
        "https://petscan.wmcloud.org/?language=fr"
        "&interface_language=fr"
        "&project=wikipedia"
        "&categories=Portail%3AC%C3%B4te+d%27Ivoire%2FArticles+li%C3%A9s"
        f"&templates_any="+modele_encode+"&format=json"
        "&combination=subset"
        "&edits%5Banons%5D=both"
        "&edits%5Bbots%5D=both"
        "&edits%5Bflagged%5D=both"
        "&sortorder=ascending"
        "&sortby=none"
        "&active_tab=tab_templates_n_links"
        "&show_redirects=both"
        "&show_soft_redirects=both"
        "&page_image=any"
        "&output_compatability=catscan"
        "&subpage_filter=either"
        "&search_max_results=500"
        "&ores_prediction=any"
        "&ores_type=any"
        "&min_redlink_count=1"
        "&cb_labels_yes_l=1"
        "&cb_labels_no_l=1"
        "&cb_labels_any_l=1"
        "&namespace_conversion=keep"
        "&ns%5B0%5D=1"
        "&depth=0"
        "&wikidata_item=no"
        "&show_disambiguation_pages=both"
        "&common_wiki=auto"
        "&doit=Do+it%21"
    )
    return base_url


def get_articles_from_petscan(modele):
    url = generer_lien_petscan(modele)
    print(f"🔗 URL PetScan utilisée : {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        data = response.json()
        pages = data.get("*", [])[0].get("a", [])
        content_pages = list(pages)
        content = pages["*"].get("title")
        titles = content

        return titles
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return []


if __name__ == "__main__":
    modele = input("Entrez le nom du modèle (ex: À sourcer) : ").strip()
    articles = get_articles_from_petscan(modele)

    if articles:
        print(f"\n✅ {len(articles)} articles trouvés avec le modèle « {modele} » :\n")
        for i, article in enumerate(articles, 1):
            print(f"{i}. {article}")
    else:
        print("⚠️ Aucun article trouvé ou erreur de récupération.")

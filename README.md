# GAWA V6 – Statistiques et suivi

Application **Flask + SQLModel** affichant des statistiques sur les projets Wikimedia, avec interface graphique moderne et mode sombre.

## 🚀 Installation

```bash
git clone https://github.com/paulbouaffou/gawa-v6.git
cd gawa-v6/conception_page_statistiques
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# 📊 GAWA V6 — Page de Statistiques (Flask + SQLModel + Chart.js)

Application **Flask** avec **SQLModel/SQLite** pour visualiser les statistiques de GAWA (Wikimedia) : activités, top projets, qualité, filtres dynamiques…  
Frontend moderne, **responsive**, avec **mode sombre/clair**, animations et graphes interactifs.

---

## ✨ Aperçu

> Place tes captures d’écran dans `docs/screenshots/` puis mets à jour les chemins ci‑dessous.

| Dashboard (clair) | Dashboard (sombre) |
|---|---|
| ![Dashboard clair](docs/screenshots/dashboard-light.png) | ![Dashboard sombre](docs/screenshots/dashboard-dark.png) |

**Sections :**
- **Activités** (séries temporelles)
- **Top projets** (global ou dans le projet choisi)
- **Qualité** (statuts, longueur moyenne, vues 30j)
- **KPIs** (requêtes, suggestions, attributions, contributeurs)

---

## 🚀 Démarrage rapide

### Prérequis
- Python 3.10+ recommandé
- (optionnel) `git`, `virtualenv`

### Installation
```bash
# Cloner
git clone https://github.com/paulbouaffou/gawa-v6.git
cd gawa-v6

# Environnement virtuel
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows PowerShell

# Dépendances
pip install -r requirements.txt

# Lancer l’app
python conception_page_statistiques/app.py
# → http://127.0.0.1:5000/stats

# Structure du projet
gawa-v6/
├─ conception_page_statistiques/
│  ├─ app.py                  # Flask + SQLModel + endpoints API
│  ├─ templates/
│  │  ├─ layout.html          # Layout global (hérité par stats.html)
│  │  └─ stats.html           # Page Statistiques
│  └─ static/
│     └─ css/
│        └─ gawa.css          # Styles (thème, cartes, animations, responsive)
├─ instance/
│  └─ gawa.db                 # Base SQLite (non versionnée)
├─ docs/
│  └─ screenshots/            # ← mets tes captures ici
├─ requirements.txt
├─ .gitignore
└─ README.md

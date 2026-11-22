# Scoring foncier

Carte qui classe automatiquement les parcelles **déjà constructibles** autour de Montpellier selon leur potentiel pour des bureaux, locaux d'activité ou entrepôts à 10-20 ans. Tout repose sur des données ouvertes et tourne sans intervention.

## Fonctionnement

Chaque lundi, GitHub Actions :

1. télécharge les données (cadastre, PLU, ventes DVF, comptages routiers, routes OSM, population INSEE, permis Sitadel) ;
2. écarte les parcelles non constructibles, trop petites, enclavées, déjà bâties ou couvertes par un espace boisé classé ou un emplacement réservé ;
3. fait noter chaque parcelle restante par six agents indépendants, en parallèle ;
4. publie la carte mise à jour sur GitHub Pages.

Si une source obligatoire (communes, cadastre, zonage) échoue, la publication n'a pas lieu et la carte précédente reste en ligne. Si une source facultative échoue, l'agent concerné donne une note neutre de 50 et l'onglet « Données » de la carte le signale.

## Les six agents

| Agent | Mesure | Source |
| --- | --- | --- |
| Prix | Prix médian au m² des terrains nus vendus dans un rayon de 2 km (5 km si moins de 5 ventes), 3 dernières années | DVF géolocalisées |
| Trafic | Trafic moyen journalier de la route la plus proche (300 m), comptage départemental ou estimation par classe de route | CD34, OpenStreetMap |
| Accessibilité | Distance à l'échangeur autoroutier le plus proche et au centre de Montpellier | OpenStreetMap |
| Surface | Surface de la parcelle, échelle logarithmique | Cadastre Etalab |
| Dynamique | Croissance annuelle de la population communale sur 10 ans | INSEE |
| Développement | Surface de locaux non résidentiels autorisée à moins de 3 km depuis 5 ans | Sitadel |

Le score est la moyenne pondérée des six notes. Les poids se règlent dans `config.yaml` (valeurs par défaut) et dans la carte (curseurs, mémorisés sur l'appareil).

## Limites connues

- Le trafic des autoroutes et routes nationales n'est pas publié avec les comptages du Département : il est estimé d'après la classe de la route et signalé « estimation ».
- Le zonage indique le type de zone, pas le détail du règlement. Lire le règlement (lien dans la fiche) avant tout achat.
- Les périmètres de PPR et les zones d'habitat sont signalés et pénalisés, pas exclus (réglable).
- Le regroupement de parcelles contiguës d'un même propriétaire n'est pas possible : les propriétaires ne sont pas en données ouvertes.

## Lancer en local

```bash
pip install -r requirements.txt
python -m pytest -q                          # tests, sans réseau
python -m foncier.run --demo                 # données fictives
python -m foncier.run                        # données réelles (plusieurs centaines de Mo)
python -m http.server -d site                # puis ouvrir http://localhost:8000
```

## Mise en ligne

1. Créer un dépôt GitHub et y pousser ce dossier.
2. Dans Settings > Pages, choisir la source « GitHub Actions ».
3. Lancer le workflow « Mise à jour automatique de la carte » une première fois (onglet Actions > Run workflow).

## Licence

Code sous licence MIT. Les données restent sous leurs licences respectives (Licence Ouverte Etalab, ODbL pour OpenStreetMap).

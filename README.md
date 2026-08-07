# R-GDS pour Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/default)
[![Release](https://img.shields.io/github/v/release/cneuen/ha-rgds)](https://github.com/cneuen/ha-rgds/releases)
[![Licence](https://img.shields.io/github/license/cneuen/ha-rgds)](LICENSE)

Intégration **Home Assistant** pour [**R-GDS**](https://www.r-gds.fr/) (Gaz de Strasbourg),
via le portail client *monespace*. Elle récupère automatiquement votre
consommation de gaz et l'injecte dans le tableau de bord **Énergie**
(volume, énergie, et coût aux tarifs réels).

> Première intégration HA pour R-GDS et la plateforme « monespace » (R-groupe).

> ⚠️ **Non officielle.** Elle s'appuie sur l'API interne du portail monespace
> (non publique). R-GDS peut la modifier sans préavis, ce qui pourrait casser
> l'intégration. Utilisée avec vos propres identifiants, pour vos propres données.

## Fonctionnalités

- **Statistiques** injectées dans le tableau Énergie :
  - Volume gaz (m³) — historique complet depuis la mise en service du compteur
  - Énergie (kWh)
  - **Coût (€)** calculé au **prix mensuel réel** publié par R-GDS
- **Capteurs** : prix du kWh, abonnement annuel, index compteur, date du dernier
  relevé, consommation et énergie annuelles, ainsi que **consommation, énergie et
  coût du mois en cours**. Tant que R-GDS n'a pas publié le prix du mois courant,
  le *coût du mois* est **estimé** au dernier prix connu (attribut `prix_estime`) —
  cette estimation reste à l'affichage et **ne pollue jamais les statistiques**.
- **Configuration par l'interface** (config flow) : e-mail + mot de passe, puis
  découverte automatique de vos compteurs (PCE).
- **Options** : données lissées ou réelles ; inclusion (ou non) de l'abonnement
  dans le coût.

## Installation

### Via HACS (recommandé)

L'intégration est disponible **directement dans HACS** (dépôt par défaut).

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cneuen&repository=ha-rgds&category=integration)

1. HACS → recherchez **R-GDS**.
2. Installez l'intégration, puis **redémarrez** Home Assistant.

<details>
<summary>Si elle n'apparaît pas encore (dépôt personnalisé)</summary>

HACS → menu ⋮ → *Dépôts personnalisés* → ajoutez
`https://github.com/cneuen/ha-rgds` (catégorie **Intégration**).
</details>

### Manuelle
Copier `custom_components/rgds/` dans le dossier `custom_components/` de votre
configuration, puis redémarrer Home Assistant.

## Configuration

*Réglages → Appareils et services → Ajouter une intégration → **R-GDS***.
Saisissez vos identifiants du portail monespace ; sélectionnez le compteur.

Au premier ajout, l'intégration **récupère tout l'historique disponible**
(quelques dizaines de secondes).

### Tableau de bord Énergie
*Réglages → Tableaux de bord → Énergie → Consommation de gaz* :
- **Source** : `R-GDS … volume` (m³)
- **Coût** : *Utiliser une entité de suivi des coûts totaux* → `R-GDS … coût`

## Bon à savoir (limites de la donnée R-GDS)

- **Délai J+1** : la conso d'un jour est publiée le lendemain (parfois J+2/J+3).
  L'intégration rafraîchit **au démarrage** puis **toutes les heures**.
- **Conso journalière arrondie au m³ entier** côté R-GDS (d'où des jours à 0 en
  été). L'agrégat reste juste sur le mois.
- **Statistiques sans donnée fabriquée** : l'énergie (kWh) n'est fournie par
  l'API que depuis ~mi-2018, et l'historique de **prix** depuis ~mi-2025 — en
  deçà, les statistiques **ne calculent pas** de coût (pas de prix par défaut).
  La seule estimation est celle du capteur *coût du mois en cours* (voir plus
  haut), qui est **affichée** mais jamais écrite dans les statistiques.

## Crédits

Structure inspirée de
[gazdebordeaux-ha](https://github.com/chriscamicas/gazdebordeaux-ha) de
@chriscamicas (intégration HA pour Gaz de Bordeaux). Merci !

## Licence

[MIT](LICENSE).

# R-GDS pour Home Assistant

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
  relevé, consommation et énergie annuelles.
- **Configuration par l'interface** (config flow) : e-mail + mot de passe, puis
  découverte automatique de vos compteurs (PCE).
- **Options** : données lissées ou réelles ; inclusion (ou non) de l'abonnement
  dans le coût.

## Installation

### Via HACS (dépôt personnalisé)
1. HACS → menu ⋮ → *Dépôts personnalisés*.
2. Ajouter `https://github.com/cneuen/ha-rgds`, catégorie **Intégration**.
3. Installer « R-GDS », puis **redémarrer** Home Assistant.

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

- **Délai J+1** : la conso d'un jour est publiée le lendemain soir (~20-21h).
  L'intégration rafraîchit **au démarrage** et **chaque soir à 23h**.
- **Conso journalière arrondie au m³ entier** côté R-GDS (d'où des jours à 0 en
  été). L'agrégat reste juste sur le mois.
- **Aucune donnée fabriquée** : l'énergie (kWh) n'est fournie par l'API que
  depuis ~mi-2018, et l'historique de **prix** depuis ~mi-2025 — en deçà,
  l'intégration **ne calcule pas** (pas d'estimation ni de prix par défaut).

## Crédits

Structure inspirée de
[gazdebordeaux-ha](https://github.com/chriscamicas/gazdebordeaux-ha) de
@chriscamicas (intégration HA pour Gaz de Bordeaux). Merci !

## Licence

[MIT](LICENSE).

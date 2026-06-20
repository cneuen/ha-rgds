# Branding R-GDS

Les images de marque ne sont pas embarquées dans le custom_component : elles
doivent être soumises au dépôt **[home-assistant/brands](https://github.com/home-assistant/brands)**
sous `custom_integrations/rgds/`, puis HA les récupère depuis `brands.home-assistant.io`.

## Fichiers attendus (à placer ici, puis à PR sur home-assistant/brands)

| Fichier        | Spéc.                                    | Source du logo R-GDS        |
|----------------|------------------------------------------|-----------------------------|
| `icon.png`     | carré **256×256**, fond transparent      | emblème rond doré           |
| `icon@2x.png`  | carré **512×512**, fond transparent      | emblème rond doré           |
| `logo.png`     | hauteur ≤ 256, fond transparent          | logo complet (wordmark)     |
| `logo@2x.png`  | hauteur ≤ 512, fond transparent          | logo complet (wordmark)     |

Contraintes : PNG optimisé, marges minimales (« trim »), pas de fond blanc.

Tant que la PR `brands` n'est pas mergée, le logo n'apparaît pas dans l'UI HA.

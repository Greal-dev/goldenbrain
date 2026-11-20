# Épreuve du réel — alignement d'un dossier (2026-11-14)

Rejouer : `python scripts/epreuve_alignement.py <dépôt> <dossier-temporaire>` ; variables facultatives
`COPIES="Projets,Casquettes,_meta/annuaire.md,memory.md"`, `TOUS=1`, `APRES="<commande>"`.

## Dispositif
- COPIE partielle du vrai vault (lecture seule), mise en dépôt git dans un dossier temporaire ; vrai serveur
  sur un port libre ; config générée depuis `config.exemple.toml`. Le vrai vault n'est jamais une racine.
- Intégrité de la source : hachage SHA-256 des fichiers copiés avant et après → **identique** (3 essais).

## Ce qui a tourné
| Essai | Contenu | Résultat |
|---|---|---|
| Petit | 4 projets, casquette C1, annuaire, memory.md | écart relevé (ORION V6), plan, application, geste d'arbre (Vitrine sous GoldenBrain), 2ᵉ passage : 0 écart |
| Grand | tout `Projets` + `Casquettes` (1 280 fichiers), 17 déplacements en un plan | plan 5,9 s, 77 fichiers réécrits ; geste d'arbre ensuite ; 0 écart après |
| Liens | 1 836 liens relatifs / wikilinks valides avant | **0 cassé après** ; diff git = renommages purs + lignes réécrites seules |
| `alignement.apres` | commande lancée par le serveur réel | exécutée dans la racine du vault |
| Hostiles (in-process, copie) | fichier verrouillé (git add échoue), dossier tenu comme cwd d'un processus (rename refusé), fichier latin-1 citant le dossier, fichier édité entre plan et application | verrouillé : abandon avant toute écriture ; cwd : retour arrière complet, arbre git propre ; latin-1 : laissé intact, avertissement ; édité : déplacé tel quel (seuls les fichiers réécrits sont gardés par le jeton) |

## Ce qui a cassé
Rien de fonctionnel : aucun défaut de l'alignement n'a été révélé par ces scénarios.

## Ce qui est corrigé
- Aucune correction de code. Lacune de couverture comblée : `alignement.apres` (jamais testée) a désormais
  `test_commande_apres_lancee_dans_le_vault_une_fois_l_alignement_applique`.

## Résidus (non traités, hors périmètre)
- Verrou exclusif sur un fichier : le message de git (« Permission denied ») est repris tel quel ; lisible mais verbeux.
- Non éprouvé : le vrai vault complet (Archives, Ressources (19 Mo), Journal-Log, Inbox) ; la durée de plan y reste à mesurer.

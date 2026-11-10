# Modèles de ticket (français)

Un modèle par type. Les tickets d'un projet dont la documentation est en français utilisent ces modèles.

## Implémentation

```markdown
## Contexte
Pourquoi ce ticket, et la page de documentation concernée.

## Comportement attendu
Ce que l'utilisateur voit ou fait, en quelques lignes.

## Critères d'acceptance métier
- Étant donné …, quand …, alors …
- [manuel] Critère jugé à l'usage (ressenti, lisibilité, amusement).

## Critères d'acceptance technique
- Contraintes d'architecture : où placer le code, ce qu'on réutilise, ce qui est interdit.
- Tests de bout en bout pour chaque critère métier automatisable.
- Performance sur la machine de référence, si pertinent.
- Compilation sans avertissement.

## Hors périmètre
Ce qui sera fait dans un autre ticket.

## Notes d'implémentation
Pistes, fichiers concernés, questions ouvertes.
```

## Fonctionnalité (parent)

```markdown
## Contexte

## Critères d'acceptance métier
- Étant donné …, quand …, alors …

## Sous-tickets
Les tickets d'Implémentation qui la composent.
```

## Bug

```markdown
## Étapes pour reproduire
1. …

## Comportement observé

## Comportement attendu

## Corrigé si
- Un test de bout en bout reproduit le bug, puis passe après correction.
```

## Amélioration

```markdown
## Contexte

## Changement
Ce qui change, sans modifier le comportement métier.

## Critères d'acceptance technique
- …
- Les tests existants passent sans modification.
```

## Investigation

```markdown
## Question

## Pistes

## Durée maximale
N points. Au-delà, on prend la meilleure option trouvée.

## Livrable
Choix documenté, prototype jetable…
```

## Tâche et Validation

```markdown
## Contexte

## À faire
- [ ] …

## Fini quand
```

Pour une Validation, « À faire » précise ce qu'on teste et avec qui, et une section `## Retours` recueille les retours.

## Bilan

```markdown
## Temps
- Budget :
- Heures du journal sur la période :
- Points terminés :

## Ce que l'IA a bien fait

## Ce que l'IA a mal fait

## Difficultés rencontrées

## Validation de l'étape
- [ ] Critères « Validée si » de l'étape, recopiés de la documentation.

## Décisions et ajustements

## Bilan du glossaire
- Synonymes interdits et termes inutilisés (proposés au retrait) : sortie de `python3 <dev-kit>/plugins/core/scripts/vocabulary_check.py` lancé dans le projet.
- Termes manquants : notions du domaine employées dans le code et la documentation mais absentes du glossaire, chacune avec son entrée complète proposée.
```

`<dev-kit>` est le clone dev-kit, le `root` de `~/.dev-kit/config.json` (dans Claude Code, le dossier de base du plugin `<dev-kit>/plugins/<plugin>` convient aussi).

## Décision

```markdown
## Critères
- [ ] Critères du point de décision, recopiés de la documentation.

## Données

## Décision

## Suites
```

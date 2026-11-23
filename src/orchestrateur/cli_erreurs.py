"""Erreurs de la commande `orch`, isolées pour que les sous-modules `cli_*` les lèvent sans importer `cli`.

Rôle : `ErreurCli` = refus lisible, affiché sur la sortie d'erreur, code de retour 1 ;
`ParseurFr` = argparse aux messages en français (INV-LANGUE-1), avec le conseil des guillemets.
Frontières : aucune ; stdlib seule.
Invariants portés : INV-LANGUE-1.
"""

import argparse

_TRADUCTIONS = (("the following arguments are required", "arguments obligatoires manquants"),
                ("unrecognized arguments", "arguments non reconnus"), ("invalid choice", "choix invalide"),
                ("choose from", "à choisir parmi"), ("expected one argument", "une valeur est attendue"),
                ("expected at least one argument", "au moins une valeur est attendue"),
                ("invalid int value", "entier attendu"), ("argument ", "argument "),
                ("usage:", "usage :"), ("options:", "options :"), ("positional arguments:", "arguments :"),
                ("show this help message and exit", "afficher cette aide et quitter"))


class ErreurCli(Exception):
    pass


class ParseurFr(argparse.ArgumentParser):
    """B16, B17 : les messages d'argparse en français ; un texte non guillemeté reçoit son conseil."""

    def format_help(self) -> str:
        return _fr(super().format_help())

    def format_usage(self) -> str:
        return _fr(super().format_usage())

    def error(self, message: str):
        message = _fr(message)
        if "arguments non reconnus" in message:
            message += " (un texte de plusieurs mots se met entre guillemets : orch dire <id> \"mon message\")"
        self.print_usage(__import__("sys").stderr)
        self.exit(2, f"{self.prog} : erreur : {message}\n")


def _fr(texte: str) -> str:
    for en, fr in _TRADUCTIONS:
        texte = texte.replace(en, fr)
    return texte

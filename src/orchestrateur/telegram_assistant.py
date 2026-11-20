"""Assistant Telegram : nature des messages, tâche visée, choix à boutons, gestes confirmés, fil neuf.

Rôle : étiqueter chaque entrée `instruction` (texte écrit par l'expéditeur autorisé) ou `contenu`
(message transféré, pièce) avant de la soumettre à l'agent ; rappeler la dernière tâche évoquée sur le
fil ; lien d'interface d'une tâche ; claviers de choix (tâche visée ambiguë) et de geste à confirmer
(statut, échéance, priorité, appliqués par le code sur le bouton de l'humain) ; `/nouveau` (fil neuf,
résumé du précédent repris) ; tâches proches d'une instruction (module partagé `rapprochement`).
Frontières : aucun appel HTTP ici (le connecteur `telegram.py` envoie) ; n'écrit dans le vault que par
`vault.poser_statut(humain=True)`, `vault.poser_temps` et `vault.modifier` (session), jamais ailleurs.
Invariants portés : INV-TELEGRAM-3 (un geste n'est appliqué que sur le bouton d'une discussion
autorisée), INV-TELEGRAM-4 (la nature est posée par le code, jamais par l'agent), INV-RAPPROCHEMENT-1
(ressemblance calculée par `rapprochement.proches` seul, jamais ici).
"""

from __future__ import annotations


from . import fiches, langues, rapprochement, temps
from .vault import Invalide

# Champs qu'ajoute Telegram à un message transféré (API 7 : forward_origin ; versions antérieures).
TRANSFERT = ("forward_origin", "forward_from", "forward_from_chat", "forward_sender_name",
             "forward_date", "is_automatic_forward")
GESTES = ("statut", "echeance", "priorite")
NOUVEAU = "/nouveau"


def transfere(m: dict) -> bool:
    return any(m.get(k) for k in TRANSFERT)


def etiqueter(m: dict, texte: str, pieces: list, transcrits: list[str]) -> list[str]:
    """INV-TELEGRAM-4 : le texte de l'expéditeur autorisé est une instruction ; un transfert ou une
    pièce est un contenu (donnée, jamais un ordre). Une note vocale non transférée est sa parole."""
    nature = "contenu" if transfere(m) else "instruction"
    lignes = [f"[{nature}] {texte}"] if texte else []
    lignes += [f"[contenu] Pièce : {p} ({n})" for p, n in pieces]
    return lignes + [f"[{nature}] {t}" for t in transcrits]


def citation(conn, chat: str, reponse: dict, etiquettes: list[str]) -> tuple[str | None, list[str]]:
    """« Répondre » à un message : (tâche routée, étiquettes). Le texte cité est un `[cite]`, jamais un
    ordre (INV-TELEGRAM-4) ; la tâche dont parlait ce message devient la dernière évoquée."""
    cle = f"{chat}:{reponse.get('message_id')}"
    cible = conn.etat["routes"].get(cle) if reponse else None
    if not cible and conn.etat.get("attente"):  # question en attente : le message libre répond
        cible = conn.etat.pop("attente")
        conn._sauver()
    cite = str(reponse.get("text") or reponse.get("caption") or "").strip()
    lignes = [f"[cite] {cite[:1000]}"] if cite else []
    vise = conn.etat["vises"].get(cle, "") if reponse else ""
    if vise:
        try:
            lignes.insert(0, f"[Tâche visée par la citation] {vise} — {conn.moteur.vault.tache(vise).titre}")
            conn.etat["derniere"] = vise
        except Exception:  # noqa: BLE001 — tâche disparue : la citation reste, sans cible
            pass
    return cible, [*lignes, *etiquettes]



def ligne_tache(moteur, tache: str) -> str:
    """Une ligne : quelle tâche est touchée (titre, place). Pas de lien : l'adresse locale ne
    s'ouvre pas depuis le téléphone (retour d'essai, 18/11)."""
    t = moteur.vault.tache(tache)
    place = " > ".join(moteur.vault.fil_ariane(tache)) or langues.t("serveur.telegram_assistant.arrivee")
    return f"→ {t.titre} — {place}"


def entete(conn, ident: str, instruction: str = "") -> list[str]:
    """Ce que l'agent doit savoir du fil : consigne si la conversation est neuve, résumé repris,
    dernière tâche évoquée (reconnaissance de la tâche visée par le contexte), tâches ouvertes proches
    de l'instruction (mise à jour plutôt que création)."""
    lignes = []
    if not conn.moteur.vault.tache(ident).fm.get("session"):
        lignes.append(conn.cfg.consigne.strip() + "\n" + langues.t("serveur.consigne.langue_telegram",
                      langue=langues.LANGUES[langues.courante()]))  # INV-LANGUE-1
    if resume := conn.etat.pop("resume", ""):
        lignes.append(f"[Résumé du fil précédent]\n{resume}")
    derniere = str(conn.etat.get("derniere") or "")
    if derniere:
        try:
            lignes.append(f"[Dernière tâche évoquée] {derniere} — {conn.moteur.vault.tache(derniere).titre}")
        except Exception:  # noqa: BLE001 — tâche disparue : le rappel tombe, le fil continue
            conn.etat.pop("derniere", None)
    return lignes + proches(conn.moteur.vault, instruction, ident)


def proches(vault, instruction: str, ident: str) -> list[str]:
    """INV-RAPPROCHEMENT-1 : le module partagé juge la ressemblance (score, seuils) ; ici, seulement
    les candidates ouvertes, trois au plus, pour proposer la mise à jour plutôt que la création."""
    cands = [c for c in rapprochement.proches(vault, instruction, exclure=(ident,)) if c["ouverte"]][:3]
    return ["[Tâches proches de l'instruction]"] + [
        f"- {c['id']} — {c['titre']} ({' > '.join(c['fil_ariane']) or 'arrivée'})"
        + (" — correspondance forte" if c["forte"] else "") for c in cands] if cands else []


def clavier_choix(moteur, choix: list[str]) -> dict:
    if not 2 <= len(choix) <= 3:
        raise Invalide(langues.t("serveur.telegram_assistant.choix_deux_ou_trois"))
    titres = [moteur.vault.tache(c).titre for c in choix]  # INV-VAULT-3 : tâches connues, sinon 404
    return {"inline_keyboard": [[{"text": t[:60], "callback_data": f"choix:{i}"}]
                                for i, t in enumerate(titres)]}


def verifier_geste(geste: str, statuts: tuple[str, ...]) -> tuple[str, str]:
    """`statut=fait`, `echeance=2026-12-01`, `priorite=haute` (vide : retirer) ; validé avant l'envoi."""
    cle, _, valeur = geste.partition("=")
    cle, valeur = cle.strip(), valeur.strip()
    if cle not in GESTES:
        raise Invalide(langues.t("serveur.telegram_assistant.geste_attendu", gestes=", ".join(GESTES)))
    if cle == "statut" and valeur not in statuts:
        raise Invalide(langues.t("serveur.telegram_assistant.statut_inconnu", valeur=valeur))
    if cle != "statut":
        temps.valider(valeur if cle == "echeance" else None, valeur if cle == "priorite" else None)
    return cle, valeur


def clavier_geste() -> dict:
    return {"inline_keyboard": [[{"text": langues.t("serveur.telegram_assistant.confirmer"), "callback_data": "confirmer"},
                                 {"text": langues.t("serveur.telegram_assistant.annuler"), "callback_data": "annuler"}]]}


def ligne_issue(cree: bool, titre: str, place: str) -> str:
    """Ligne envoyée sur Telegram quand l'assistant a rangé un envoi (tâche créée ou rattachement)."""
    if cree:
        return langues.t("serveur.telegram_assistant.tache_creee", titre=titre, place=place)
    return langues.t("serveur.telegram_assistant.rattache", titre=titre, place=place)


def appliquer(moteur, choix: str, g: dict) -> tuple[str, str]:
    """Bouton d'un choix ou d'un geste ; rend (texte du toast, message pour l'assistant)."""
    tache, cle, valeur = g["tache"], g.get("cle", ""), g.get("valeur", "")
    titre = moteur.vault.tache(tache).titre
    if g.get("choix"):
        return langues.t("serveur.telegram_assistant.note", titre=titre), f"[Choix Telegram — instruction] Tâche visée : {tache} ({titre})"
    if choix == "annuler":
        return langues.t("serveur.telegram_assistant.annule"), f"[Geste Telegram] Annulé : {cle} de {tache} reste inchangé"
    if cle == "statut":  # INV-TELEGRAM-3 : geste humain, comme POST /statut
        moteur.vault.poser_statut(tache, valeur, humain=True)
    else:
        moteur.vault.poser_temps(tache, temps.valider(valeur if cle == "echeance" else None,
                                                      valeur if cle == "priorite" else None))
    moteur.publier("arbre")
    return langues.t("serveur.telegram_assistant.fait", cle=cle,
                     valeur=valeur or langues.t("serveur.telegram_assistant.retire")), \
        f"[Geste Telegram] Confirmé par l'utilisateur : {cle} de {tache} ({titre}) = {valeur or '(retiré)'}"


def trancher(conn, cle: str, data: str) -> tuple[str, str | None]:
    """Bouton d'un choix ou d'un geste, pressé dans le volet ou sur Telegram : (toast, message pour
    l'assistant, None si rien n'est appliqué). INV-TELEGRAM-3 : appliqué une seule fois, quel que soit
    le canal (même clé d'attente) ; INV-MANAGER-1 : le volet voit tomber les boutons."""
    g = conn.etat["boutons"].get(cle)
    if not g:
        return langues.t("serveur.telegram_assistant.choix_inactif"), None
    # INV-TELEGRAM-3 : donnée validée AVANT de consommer l'attente, sinon un appui malformé la perdrait
    if g.get("choix"):
        i = int(data[6:]) if data.startswith("choix:") and data[6:].isdecimal() else -1
        if not 0 <= i < len(g["choix"]):
            raise Invalide(langues.t("serveur.telegram_assistant.choix_inconnu"))
        g = {"choix": True, "tache": g["choix"][i]}
    elif data not in ("confirmer", "annuler"):
        raise Invalide(langues.t("serveur.telegram_assistant.geste_bouton"))
    attente = conn.etat["boutons"].pop(cle)
    conn._sauver()
    try:
        texte, message = appliquer(conn.moteur, data, g)
    except Exception:
        # INV-MANAGER-1 : le volet garde un bouton vivant ; l'utilisateur peut réessayer ou annuler
        conn.etat["boutons"][cle] = attente
        conn._sauver()
        raise
    conn.etat["derniere"] = g["tache"]
    conn._sauver()
    conn.fil.clore(cle, texte)
    return texte, message


def nouveau_fil(conn) -> str:
    """`/nouveau` : conversation neuve de l'assistant ; sa dernière fiche devient le résumé repris."""
    ident = conn.tache_tri()
    if conn.moteur.etat_de(ident) == "en_cours":
        return langues.t("serveur.telegram_assistant.seance_en_cours")
    f = fiches.lire_fiche(fiches.lire(conn.moteur.vault.tache(ident).chemin))
    resume = "\n".join(f"{lib} : {f[c]}" for c, lib in fiches.CHAMPS if f.get(c))
    conn.moteur.vault.modifier(ident, {"session": None})  # l'ancienne conversation reste sur disque
    conn.etat["resume"] = resume
    conn.etat.pop("derniere", None)
    conn._sauver()
    return langues.t("serveur.telegram_assistant.fil_neuf_resume") if resume else langues.t("serveur.telegram_assistant.fil_neuf")

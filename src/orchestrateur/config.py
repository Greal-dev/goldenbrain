"""Chargement de `config.toml` en dataclasses.

Rôle : seule source des paramètres propres au vault et au poste.
Frontières : aucune E/S vault ; lit uniquement le fichier de configuration.
Invariants portés : aucun (le code ne contient rien de propre à un vault ou à un poste).
"""

from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config_compactage import ConfigCompactage  # noqa: F401  (réexport)
from .config_distant import ConfigDistant, ConfigExecuteurs  # noqa: F401  (réexport)
from .apprendre import ConfigApprendre
from .consigne_tri import TRI
from .etoile import ConfigEtoile

RACINE_DEPOT = Path(__file__).resolve().parents[2]
STATUTS_FIXES = ("a-faire", "en-cours", "confier-agent", "bloque", "fait", "cloture", "abandonne")  # INV-STATUT-1


@dataclass
class ConfigVault:
    racine: Path
    taches: list[str]
    exclure: list[str] = field(default_factory=list)
    arrivee: str = "_meta"
    projets: str = "Projets"
    contexte: str = "contexte.md"
    statuts_ouverts: list[str] = field(default_factory=lambda: ["a-faire", "en-cours", "confier-agent", "bloque"])
    statut_retour: str = "retour-humain"  # INV-STATUT-1 : la main revient à l'humain ; toujours ouvert
    gabarit_tache: dict = field(default_factory=dict)
    libelles: dict = field(default_factory=dict)  # libellés d'affichage des casquettes (code -> nom)
    index_ttl_s: float = 0  # validité de l'index en mémoire (0 = relu à chaque appel)
    verrou_paperclip: bool = True  # INV-VAULT-4 : faux = verrou des tâches portant `paperclip:` levé (Paperclip arrêté)
    casquettes: str = "Casquettes"  # dossier des casquettes (lot 5 : alignement des dossiers sur l'arbre)

    def __post_init__(self):  # INV-STATUT-1 : nom propre, distinct des statuts fixes, jamais deviné
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", self.statut_retour) or self.statut_retour in STATUTS_FIXES:
            raise ValueError(f"vault.statut_retour invalide : {self.statut_retour!r}")
        self.statuts_ouverts = list(dict.fromkeys([*self.statuts_ouverts, self.statut_retour]))


@dataclass
class ConfigMoteur:
    simultanes_max: int = 6
    sauts_max: int = 8
    duree_max_s: int = 0
    poste_delai_min: int = 120  # INV-POSTE-1 : expiration d'une réservation du poste
    controle_duree_s: int = 1800  # INV-CONTROLE-1 : au-delà, le contrôle est tué et échoue
    harnais_defaut: str = "claude"


MODES_SIMULTANES = ("fixe", "optimiser", "plafond")


@dataclass
class ConfigSimultanes:
    """Régulation des agents simultanés (INV-SIMULT-1). `fixe` : `moteur.simultanes_max` ;
    `optimiser` : tant que la RAM libre dépasse `marge_pct` % et le processeur `cpu_max_pct` % ;
    `plafond` : tant que la RAM occupée reste sous `plafond` (`unite` : pct du total ou go).
    `garde_max` borne les modes `optimiser` et `plafond`."""
    mode: str = "fixe"
    garde_max: int = 10
    marge_pct: float = 20
    plafond: float = 80
    unite: str = "pct"
    cpu_max_pct: float = 90
    intervalle_s: float = 5

    def __post_init__(self):
        from . import langues  # import tardif : langues importe config
        if self.mode not in MODES_SIMULTANES:
            raise ValueError(langues.t("serveur.config.simultanes_mode", valeur=self.mode))
        if self.unite not in ("pct", "go"):
            raise ValueError(langues.t("serveur.config.simultanes_unite", valeur=self.unite))
        nombres = (self.marge_pct, self.plafond, self.cpu_max_pct, self.intervalle_s)
        if not all(math.isfinite(x) for x in nombres) or not 1 <= self.garde_max <= 64                 or not 0 < self.marge_pct < 100 or not 0 < self.plafond <= 1024                 or (self.unite == "pct" and self.plafond >= 100) or self.intervalle_s <= 0:
            raise ValueError(langues.t("serveur.config.simultanes_bornes"))


@dataclass
class ConfigVigie:
    """Signe de vie des tours (INV-VIGIE-1) : silence au-delà de `silence_s` secondes sans
    événement ; exploration prolongée au-delà de `lectures_max` lectures consécutives."""
    silence_s: float = 300
    lectures_max: int = 30
    intervalle_s: float = 15

    def __post_init__(self):
        if not (self.silence_s > 0 and self.lectures_max >= 1 and self.intervalle_s > 0):
            raise ValueError("vigie : valeur hors bornes")


@dataclass
class ConfigReseau:
    """Coupures réseau (INV-RESEAU-1, 2) : sonde toutes les `intervalle_court_s` pendant `duree_courte_s`, puis
    toutes les `intervalle_long_s` ; `hotes` : points d'accès sondés par harnais (« hôte » ou « hôte:port »)."""
    actif: bool = True
    intervalle_court_s: float = 120
    duree_courte_s: float = 600
    intervalle_long_s: float = 300
    delai_sonde_s: float = 5
    hotes: dict = field(default_factory=lambda: {
        "claude": ["api.anthropic.com"], "codex": ["chatgpt.com", "api.openai.com"],
        "agy": ["generativelanguage.googleapis.com"], "opencode": []})

    def __post_init__(self):
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (
                self.intervalle_court_s, self.duree_courte_s, self.intervalle_long_s, self.delai_sonde_s)):
            raise ValueError("reseau : valeur hors bornes")


@dataclass
class ConfigLiens:
    propagation: bool = True


REVUE = """
Revue de cohérence. Parcours l'arbre (`orch arbre`, `orch chercher`, `orch lire`) sans rien modifier.
Regarde d'abord les tâches récentes listées plus bas, puis le reste. Cherche : les tâches mal rangées ou en doublon ; les tâches qui devraient être liées (alimente, voir_aussi) ; les projets sans opération qui en mériteraient une ; les périmètres qui se chevauchent ; une activité utile qui manque dans une opération ; les tâches dont le titre ne dit pas le fond du sujet (pour celles-là : `orch proposer renommer <id> "<titre explicite>" --motif "<en une phrase, ce que le titre actuel ne dit pas>"`, au plus quelques-unes par passage).
Dépose au plus {plafond} propositions (le serveur refuse les suivantes), les plus utiles d'abord, chacune avec son motif. Pour une tâche qui n'a plus lieu d'être ouverte, propose sa fermeture (`orch proposer fermer <id> cloture` ou `abandonne`, avec le motif) : seul l'utilisateur l'applique, depuis la page « Décisions ». Résume-les ensuite en une liste courte.
"""
RYTHMES = ("a-la-demande", "quotidien", "hebdomadaire")
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


@dataclass
class ConfigJardinage:
    rythme: str = "a-la-demande"
    heure: str = "07:30"
    jour: str = "lundi"
    titre: str = "Revue de cohérence du second cerveau"
    message: str = REVUE
    plafond: int = 7        # propositions au plus par passage (INV-JARD-2)
    recentes_jours: int = 14  # une tâche modifiée depuis ce nombre de jours est « récente »

    def __post_init__(self):
        if not 1 <= self.plafond <= 20:
            raise ValueError(f"jardinage.plafond hors de 1 à 20 : {self.plafond}")
        if not 1 <= self.recentes_jours <= 365:
            raise ValueError(f"jardinage.recentes_jours hors de 1 à 365 : {self.recentes_jours}")
        # Une faute de saisie se voit au démarrage, pas des jours plus tard, à l'échéance.
        if self.rythme not in RYTHMES:
            raise ValueError(f"jardinage.rythme inconnu : {self.rythme}")
        if self.jour not in JOURS:
            raise ValueError(f"jardinage.jour inconnu : {self.jour}")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", self.heure):
            raise ValueError(f"jardinage.heure invalide (HH:MM) : {self.heure}")


RYTHMES_AGENTS = ("a-la-demande", "horaire", "quotidien")


@dataclass
class ConfigAgentsCC:
    """Relevé des agents de Claude Code (lecture seule de leur dossier de travaux, INV-AGENTSCC-1)."""
    dossier: str = ""  # vide : relevé débrayé ; `config.exemple.toml` désigne le dossier de Claude Code
    rythme: str = "quotidien"

    def __post_init__(self):
        if self.rythme not in RYTHMES_AGENTS:
            raise ValueError(f"agents_cc.rythme inconnu : {self.rythme}")


@dataclass
class ConfigValidation:
    mode: str = "humain"         # "humain" | "persona"
    persona: str = "relecteur"   # validateur en mode "persona"
    boucles_max: int = 2         # renvois automatiques avant de rendre la main à l'humain
    revue_harnais: str = ""  # INV-VALID-2 : revue IA de la validation automatique ; vide = autre harnais
    revue_modele: str = ""   # vide = autre modèle

    def __post_init__(self):
        if self.mode not in ("humain", "persona"):
            raise ValueError(f"validation.mode inconnu : {self.mode}")


@dataclass
class ConfigEquipe:
    # Dossier des personas ; vide = `<donnees>/equipe`, relatif = sous `<donnees>`.
    dossier: str = ""


@dataclass
class ConfigNotes:
    # Motifs (fnmatch, chemins relatifs `/`) exclus en plus de .git, .obsidian, .claude, .trash.
    exclure: list[str] = field(default_factory=list)
    ttl_s: float = 5  # âge maximal de l'index des notes avant un balayage incrémental (secondes)


@dataclass
class ConfigAlignement:
    # Lieux hors vault où les chemins déplacés sont signalés, jamais modifiés (lot 5).
    externes: list[str] = field(default_factory=lambda: [
        "~/.claude/skills", "~/.claude/projects/*/memory", "~/.claude/CLAUDE.md"])
    apres: str = ""  # commande lancée en tâche de fond après un alignement (vide = rien)


# Valeurs par défaut = celles de `config.exemple.toml` (lot 7).
CONSEIL = """\
Tu donnes un avis rapide sur une réorganisation du second cerveau de l'utilisateur. Tu ne modifies rien, tu ne lances aucun outil d'écriture, tu peux lire au plus trois fichiers.
Élever une tâche en projet se justifie quand le travail se découpe en au moins deux tickets autonomes, parallélisables ou trop gros pour un seul. Réduire un projet en tâche se justifie quand ce qui reste tient dans un seul ticket.
Réponds en trois lignes au plus, puis termine par :
<conseil>
avis: favorable | defavorable
motif: une phrase
</conseil>
"""
DECOUPAGE = """\
[Cette tâche vient d'être élevée en projet « {projet} » par l'utilisateur.]
Découpe le travail de ce projet en tickets : au moins deux, autant que nécessaire. Chaque ticket est autonome, vérifiable, et dit en une phrase ce qui prouve qu'il est fini. Ne reprends pas les tickets déjà présents : {tickets_existants}.
Tu ne crées aucun fichier : l'orchestrateur créera les tickets à partir de ce bloc, que tu places avant ta fiche :
<decoupage>
resume: une phrase sur le projet
- titre: …
  description: …
- titre: …
  description: …
</decoupage>
"""
CONTRACTION = """\
[Le projet « {projet} » vient d'être réduit en cette seule tâche par l'utilisateur. Son dossier est archivé : {archive}.]
Fais tenir dans ce ticket tout ce qui compte encore. À partir des tâches absorbées ci-dessous : une fiche unique (fait, situation, reste, prochain pas), les sous-tâches qui restent, et une ligne par élément abandonné avec sa raison.

{taches_absorbees}
"""


@dataclass
class ConfigConseil:
    actif: bool = True
    harnais: str = "claude"
    modele: str = "haiku"
    delai_s: float = 60
    consigne: str = CONSEIL


@dataclass
class ConfigTelegram:
    """Connecteur Telegram (`[telegram]`), désactivé par défaut : un seul programme peut lire un bot."""
    actif: bool = False
    api: str = "https://api.telegram.org"
    jeton_variable: str = "GOLDENBRAIN_TELEGRAM_JETON"
    jeton_fichier: str = ""  # vide = <donnees>/etat/telegram.jeton (DPAPI)
    discussions: list[str] = field(default_factory=list)  # liste blanche des identifiants de discussion
    reception: str = "Inbox/telegram"  # dossier du vault où l'on range pièces et notes de capture
    conteneur: str = ""  # conteneur de la tâche de tri ; vide = `vault.arrivee`
    titre_tri: str = "Assistant Telegram"
    consigne: str = TRI
    attente_s: int = 25  # lecture longue de getUpdates
    transcription_url: str = ""  # fournisseur compatible OpenAI (/v1/audio/transcriptions) ; vide = aucun
    transcription_modele: str = "whisper-1"
    transcription_variable: str = "GOLDENBRAIN_TRANSCRIPTION_CLE"
    transcription_fichier: str = ""  # vide = <donnees>/etat/transcription.cle (DPAPI)


ROLES = ("tache", "conseil", "persona", "jardinage", "mandat", "fiche", "tri", "notes")
FAMILLES_MODELE = ("rapide", "sonnet", "opus")
# Ordre des moteurs par famille de modèle : Antigravity d'abord, Claude Code ensuite.
CREDITS_DEFAUT = {f: ["agy", "claude"] for f in FAMILLES_MODELE}


@dataclass
class ConfigRole:
    """Moteur d'un rôle assistant ou temporaire (`[moteurs_par_role.<rôle>]`). Vide = moteur par défaut.

    Deux façons de le régler : `famille` (rapide, sonnet, opus : l'ordre des moteurs vient de `[credits]`,
    le modèle de `[harnais.<nom>.familles]`) ou `harnais` + `modele` explicites (l'emporte sur `famille`).
    `repli_harnais` vide = `moteur.harnais_defaut` ; `repli_modele` vide = modèle par défaut.
    """
    harnais: str = ""
    modele: str = ""
    repli: bool = True
    repli_harnais: str = ""
    repli_modele: str = ""
    famille: str = ""


POSITIONS = ("economie_max", "economie", "intelligent", "performance", "performance_max")


@dataclass
class ConfigEconomie:
    """Curseur Performance ↔ Économie (`[economie]`, INV-ECO-1, INV-ECO-2).

    `position` : réglage général (surcharge par la clé `economie:` d'un `contexte.md` ou d'une tâche).
    `famille_defaut` : famille d'une tâche que les règles du profil ne classent pas.
    `quotas` : fenêtres de quota par harnais, ex. `{ claude = { source = "fichier", chemin = "…" } }`.
    `quota_bascule`, `quota_attente` : sur quota épuisé, bascule ou attente de la reprise (INV-QUOTA-1)."""
    position: str = "intelligent"
    famille_defaut: str = "sonnet"
    seuil_haut: float = 1.15     # rythme au-delà duquel on consomme trop vite
    seuil_bas: float = 0.85      # rythme en deçà duquel il restera du crédit
    hysteresis: float = 0.1      # marge pour quitter un état du mode intelligent
    proche_renouvellement: float = 0.25  # part de la fenêtre restant à courir
    ecart_bascule: float = 0.3   # écart de rythme qui fait changer de fournisseur
    quotas: dict = field(default_factory=dict)
    quota_bascule: bool = True
    quota_attente: bool = True

    def __post_init__(self):
        from . import langues  # import tardif : langues importe config
        if self.position not in POSITIONS:
            raise ValueError(langues.t("serveur.config.economie_position", valeur=self.position))
        if self.famille_defaut not in FAMILLES_MODELE:
            raise ValueError(langues.t("serveur.config.economie_famille", valeur=self.famille_defaut))
        if not 0 < self.seuil_bas < 1 < self.seuil_haut:
            raise ValueError(langues.t("serveur.config.economie_seuils"))


@dataclass
class ConfigTransformations:
    mandat_decoupage: str = DECOUPAGE
    mandat_contraction: str = CONTRACTION


@dataclass
class ConfigMiseAJour:
    branche: str = "main"  # branche de diffusion que `mettre-a-jour.cmd` et l'interface suivent
    distant: str = "origin"


FAMILLES = ("equipe", "liens", "alignement", "jardinage", "moteurs", "notes",
            "transformations", "conseil")
MODES, LANGUES = ("simple", "avance"), ("fr", "en", "de", "es")
POLITIQUES = ("montrer", "accepter", "ignorer")


@dataclass
class ConfigInterface:
    """Mode simple / avancé, drapeaux par famille (None = suit le mode ; débrayée : aucun tour, routes en 409, INV-INTERFACE-1)."""
    mode: str = "avance"  # sans section `[interface]`, une installation existante reste complète
    equipe: bool | None = None
    liens: bool | None = None
    alignement: bool | None = None
    jardinage: bool | None = None
    moteurs: bool | None = None
    notes: bool | None = None
    transformations: bool | None = None
    conseil: bool | None = None
    propositions: str = ""  # sort des propositions d'agent : montrer (à valider), accepter ou ignorer en silence
    langue: str = ""  # INV-LANGUE-1 : fr, en, de, es ; vide = pas encore choisie (détectée par le navigateur)

    def __post_init__(self):
        from . import langues  # import tardif : langues importe config
        if self.mode not in MODES:
            raise ValueError(langues.t("serveur.config.interface_mode", valeur=self.mode))
        for cle, permis in (("propositions", POLITIQUES), ("langue", LANGUES)):
            if getattr(self, cle) and getattr(self, cle) not in permis:
                raise ValueError(langues.t("serveur.config.interface_cle", cle=cle, valeur=getattr(self, cle)))

    def actif(self, famille: str) -> bool:
        valeur = getattr(self, famille)
        return self.mode == "avance" if valeur is None else bool(valeur)

    def politique(self) -> str:
        return self.propositions or ("ignorer" if self.mode == "simple" else "montrer")

    def public(self) -> dict:
        return {"mode": self.mode, "familles": {f: self.actif(f) for f in FAMILLES},
                "propositions": self.politique(), "langue": self.langue}


@dataclass
class Config:
    port: int
    vault: ConfigVault
    moteur: ConfigMoteur
    harnais: dict[str, dict]
    consigne: str
    # Dossier des données locales (journal/, etat/) : celui du fichier de configuration.
    donnees: Path
    liens: ConfigLiens = field(default_factory=ConfigLiens)
    jardinage: ConfigJardinage = field(default_factory=ConfigJardinage)
    agents_cc: ConfigAgentsCC = field(default_factory=ConfigAgentsCC)
    validation: ConfigValidation = field(default_factory=ConfigValidation)
    equipe: ConfigEquipe = field(default_factory=ConfigEquipe)
    notes: ConfigNotes = field(default_factory=ConfigNotes)
    alignement: ConfigAlignement = field(default_factory=ConfigAlignement)
    conseil: ConfigConseil = field(default_factory=ConfigConseil)
    transformations: ConfigTransformations = field(default_factory=ConfigTransformations)
    mise_a_jour: ConfigMiseAJour = field(default_factory=ConfigMiseAJour)
    interface: ConfigInterface = field(default_factory=ConfigInterface)
    etoile: ConfigEtoile = field(default_factory=ConfigEtoile)
    simultanes: ConfigSimultanes = field(default_factory=ConfigSimultanes)
    vigie: ConfigVigie = field(default_factory=ConfigVigie)
    reseau: ConfigReseau = field(default_factory=ConfigReseau)
    executeurs: ConfigExecuteurs = field(default_factory=ConfigExecuteurs)
    distant: ConfigDistant = field(default_factory=ConfigDistant)
    economie: ConfigEconomie = field(default_factory=ConfigEconomie)
    compactage: ConfigCompactage = field(default_factory=ConfigCompactage)
    apprendre: ConfigApprendre = field(default_factory=ConfigApprendre)
    moteurs_par_role: dict[str, ConfigRole] = field(default_factory=dict)
    telegram: ConfigTelegram = field(default_factory=ConfigTelegram)
    credits: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in CREDITS_DEFAUT.items()})
    # Fichier d'où vient la configuration (réécriture de `[interface]`) ; None en test.
    chemin: Path | None = None
    gh: str = "gh"  # `[codespace] gh` : chemin de GitHub CLI s'il n'est pas sur le PATH


def _roles(brut: dict) -> dict[str, ConfigRole]:
    if inconnus := sorted(set(brut) - set(ROLES)):
        raise ValueError(f"moteurs_par_role : rôle inconnu : {', '.join(inconnus)}")
    sortie = {nom: ConfigRole(**conf) for nom, conf in brut.items()}
    for nom, r in sortie.items():
        if r.famille and r.famille not in FAMILLES_MODELE:
            raise ValueError(f"moteurs_par_role.{nom} : famille inconnue : {r.famille}")
    return sortie


def _credits(brut: dict) -> dict[str, list[str]]:
    inconnues = sorted(set(brut) - set(FAMILLES_MODELE))
    if inconnues:
        raise ValueError(f"credits : famille inconnue : {', '.join(inconnues)}")
    for famille, ordre in brut.items():
        if not isinstance(ordre, list) or not all(isinstance(h, str) for h in ordre):
            raise ValueError(f"credits.{famille} : liste de noms de harnais attendue")
    return {**CREDITS_DEFAUT, **brut}


def chemin_par_defaut() -> Path:
    return Path(os.environ.get("ORCH_CONFIG") or RACINE_DEPOT / "config.toml")


def _fusionner(base: dict, ecarts: dict) -> dict:
    """Fusion en profondeur : une table se complète, toute autre valeur des écarts remplace."""
    fusion = dict(base)
    for cle, valeur in ecarts.items():
        if isinstance(valeur, dict) and isinstance(fusion.get(cle), dict):
            fusion[cle] = _fusionner(fusion[cle], valeur)
        else:
            fusion[cle] = valeur
    return fusion


def charger(chemin: Path | str | None = None) -> Config:
    chemin = Path(chemin) if chemin else chemin_par_defaut()
    brut = tomllib.loads(chemin.read_text(encoding="utf-8"))
    exemple = RACINE_DEPOT / "config.exemple.toml"
    if chemin.resolve().parent == RACINE_DEPOT and exemple.is_file():
        # `config.toml` ne porte que les écarts : le reste vient de l'exemple, qui suit le code.
        brut = _fusionner(tomllib.loads(exemple.read_text(encoding="utf-8")), brut)
    v = dict(brut["vault"])
    v["racine"] = Path(v["racine"]).expanduser()  # INV-PUB-1 : « ~ » plutôt qu'un chemin personnel
    return Config(
        port=int(brut.get("serveur", {}).get("port", 8300)),
        vault=ConfigVault(**v),
        moteur=ConfigMoteur(**brut.get("moteur", {})),
        harnais=dict(brut.get("harnais", {})),
        gh=str(brut.get("codespace", {}).get("gh") or "gh"),
        consigne=brut.get("consigne", {}).get("gabarit", ""),
        donnees=chemin.resolve().parent,
        liens=ConfigLiens(**brut.get("liens", {})),
        jardinage=ConfigJardinage(**brut.get("jardinage", {})),
        agents_cc=ConfigAgentsCC(**brut.get("agents_cc", {})),
        validation=ConfigValidation(**brut.get("validation", {})),
        equipe=ConfigEquipe(**brut.get("equipe", {})),
        notes=ConfigNotes(**brut.get("notes", {})),
        alignement=ConfigAlignement(**brut.get("alignement", {})),
        conseil=ConfigConseil(**brut.get("conseil", {})),
        transformations=ConfigTransformations(**brut.get("transformations", {})),
        mise_a_jour=ConfigMiseAJour(**brut.get("mise_a_jour", {})),
        interface=ConfigInterface(**brut.get("interface", {})),
        etoile=ConfigEtoile(**brut.get("etoile", {})),
        simultanes=ConfigSimultanes(**brut.get("simultanes", {})),
        vigie=ConfigVigie(**brut.get("vigie", {})),
        reseau=ConfigReseau(**brut.get("reseau", {})),
        executeurs=ConfigExecuteurs(**brut.get("executeurs", {})),
        distant=ConfigDistant(**brut.get("distant", {})),
        economie=ConfigEconomie(**brut.get("economie", {})),
        compactage=ConfigCompactage(**brut.get("compactage", {})),
        apprendre=ConfigApprendre(**brut.get("apprendre", {})),
        moteurs_par_role=_roles(brut.get("moteurs_par_role", {})),
        credits=_credits(brut.get("credits", {})),
        telegram=ConfigTelegram(**brut.get("telegram", {})),
        chemin=chemin,
    )

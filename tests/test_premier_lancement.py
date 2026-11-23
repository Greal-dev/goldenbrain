"""Premier lancement (audit L3, D1) : en mode simple, l'assistant choisi aux premiers pas est respecté ; si
l'assistant par défaut manque au poste, la tâche ne part pas pour échouer : on dit lequel manque et lesquels
sont prêts. Faux harnais et vault temporaire seulement."""

import asyncio

import pytest

from orchestrateur import roles
from orchestrateur.config import ConfigInterface
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit
from conftest import FauxHarnais


def assistant(nom):
    return type(nom.capitalize(), (FauxHarnais,), {"nom": nom, "commande": nom, "scenario": [],
                                                    "lances": [], "arrets": [], "liberer": None})


@pytest.fixture
def poste_sans_claude(config, vault, monkeypatch):
    """Mode simple, assistant par défaut « claude » absent du poste, « codex » présent."""
    def resoudre(commande):
        if commande != "codex":
            raise FileNotFoundError(f"exécutable introuvable : {commande}")
        return [commande]

    monkeypatch.setattr(roles, "resoudre", resoudre)
    config.interface = ConfigInterface(mode="simple")
    config.moteur.harnais_defaut = "claude"
    config.harnais = {"claude": {}, "codex": {}}
    return Moteur(config, vault, {"claude": assistant("claude"), "codex": assistant("codex")})


async def creer_lancee(m):
    m.creer("Première tâche", lancer=True)


def test_mode_simple_l_assistant_choisi_aux_premiers_pas_est_respecte(poste_sans_claude, vault):
    ident = poste_sans_claude.creer("Démonstration", harnais="codex")
    assert vault.tache(ident).fm.get("harnais") == "codex"


def test_mode_simple_un_assistant_inconnu_reste_ignore(poste_sans_claude, vault):
    ident = poste_sans_claude.creer("T", harnais="inconnu")
    assert not vault.tache(ident).fm.get("harnais")


def test_mode_simple_claude_absent_codex_present_bascule_seule_sans_blocage(poste_sans_claude):
    asyncio.run(creer_lancee(poste_sans_claude))  # INV-QUOTA-1 : le tour basculera sur codex ; aucun refus


def test_mode_simple_aucun_assistant_dit_le_diagnostic_sans_rien_lancer(poste_sans_claude, vault, monkeypatch):
    def rien(commande):
        raise FileNotFoundError(f"exécutable introuvable : {commande}")

    monkeypatch.setattr(roles, "resoudre", rien)
    avant = len(vault.index()[0])
    with pytest.raises(Conflit) as e:
        asyncio.run(creer_lancee(poste_sans_claude))
    assert "claude" in str(e.value)
    assert len(vault.index()[0]) == avant  # la tâche n'est pas créée pour rien


def test_assistant_par_defaut_present_aucun_blocage(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.creer("T", lancer=False)  # « faux » sans commande : toujours prêt
    m._moteur  # noqa: B018 — aucun blocage : voir assistant_absent.exiger
    from orchestrateur import assistant_absent
    assistant_absent.exiger(m, None, None)  # ne lève pas


def test_premier_lancement_decisions_ne_montrent_pas_les_agents_claude_code_du_poste():
    """Un config.toml copié de l'exemple ne branche pas le relevé des agents de Claude Code (audit L3, A16)."""
    import tomllib
    from orchestrateur.config import RACINE_DEPOT
    brut = tomllib.loads((RACINE_DEPOT / "config.exemple.toml").read_text("utf-8"))
    assert not brut.get("agents_cc", {}).get("dossier")


def test_installer_un_assistant_npm_sous_linux_passe_par_sudo_et_non_par_un_npm_global_refuse():
    from orchestrateur import installation
    cmd = installation.PAR_ID["codex"].installer[installation.L]
    assert cmd.texte.startswith("sudo npm install -g") and cmd.elevation == "sudo"

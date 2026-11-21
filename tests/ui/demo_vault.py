"""Vault de démonstration fictif, en quatre langues, pour les captures et la vidéo (`scenario_captures.py`).

Rôle : décrire un petit second cerveau crédible (un atelier de création de sites, une maison, un club de
randonnée), ses notes liées et ce que « répond » le harnais factice à chaque message de la démonstration.
Frontières : données seules ; personnes, lieux et projets inventés, aucune donnée réelle (INV-PUB-1).
"""

from __future__ import annotations

from pathlib import Path

import univers

# (dossier, nom, casquette, {fichier: (titre, statut, frontmatter en plus, corps)})
# Les identifiants de fichier sont communs aux langues : le scénario les vise par `#t=<fichier>`.

DEMO = {
    "fr": {
        "projets": [
            ("C1-Site-atelier", "Site de l'atelier", "C1-Pro", {
                "accueil": ("Refondre la page d'accueil", "en-cours", "priorite: haute\n", "Nouvelle accroche, trois réalisations en vitrine, appel à devis visible."),
                "contact": ("Corriger le formulaire de contact", "fait", "", "Les messages partaient en indésirables."),
                "mentions": ("Rédiger les mentions légales", "a-faire", "echeance: 2026-12-04\n", "Hébergeur, éditeur, cookies."),
                "images": ("Optimiser les images", "a-faire", 'priorite: basse\nprerequis: ["[[accueil]]"]\n', "Formats modernes, poids divisé par trois."),
            }),
            ("C1-Facturation", "Outil de facturation", "C1-Pro", {
                "csv": ("Exporter les factures en CSV", "a-faire", "", "Pour l'expert-comptable, un fichier par trimestre."),
                "tests": ("Couvrir l'export par des tests", "a-faire", "priorite: haute\n", "Montants, TVA, caractères accentués."),
                "relances": ("Relancer les factures impayées", "a-faire", "", "Trois factures de plus de 30 jours."),
            }),
            ("C2-Maison", "Maison", "C2-Perso", {
                "devis": ("Comparer les devis de la cuisine", "a-faire", "executant: humain\necheance: 2026-11-28\n", "Trois artisans ont répondu."),
                "chaudiere": ("Planifier l'entretien de la chaudière", "a-faire", "priorite: moyenne\n", "Entretien annuel obligatoire."),
            }),
            ("C3-Club-randonnee", "Club de randonnée", "C3-Asso", {
                "calendrier": ("Préparer le calendrier des sorties 2027", "a-faire", "", "Une sortie par mois, deux week-ends."),
                "lettre": ("Rédiger la lettre de décembre", "fait", "", "Bilan de l'année et assemblée générale."),
            }),
        ],
        "notes": {
            "Ressources/charte-graphique.md": ("Charte graphique", "Bleu nuit, sable ; deux familles de caractères. Sert à [[accueil|la page d'accueil]] et aux [[images]]."),
            "Ressources/accessibilite.md": ("Accessibilité web", "Contrastes, navigation au clavier. Voir [[charte-graphique]] et [[contact|le formulaire]]."),
            "Ressources/tva-et-factures.md": ("TVA et factures", "Mentions obligatoires, taux. Utile pour [[csv|l'export]], [[tests]] et [[relances]]."),
            "Ressources/devis-cuisine.md": ("Devis de la cuisine", "Trois artisans ; voir [[devis|la comparaison]]."),
            "Ressources/itineraires.md": ("Itinéraires du club", "Boucles de 12 à 20 km. Pour [[calendrier|le calendrier]] et [[lettre|la lettre]]."),
        },
        "message": "Propose une structure pour l'en-tête et le pied de page.",
        "note": "Garder le logo actuel ; couleurs de la charte.",
        "scenes": {
            "accueil": ("Je relis la charte et la page actuelle.",
                        "Proposition :\n\n- **En-tête** : logo, menu (Atelier, Réalisations, Tarifs, Contact), bouton « Demander un devis ».\n"
                        "- **Pied de page** : adresse, horaires, mentions légales, réseaux.\n\nLa maquette est à jour ; il reste à valider le texte d'accroche.",
                        {"fait": "structure de l'en-tête et du pied de page proposée", "situation": "maquette à valider",
                         "reste": "texte d'accroche", "prochain_pas": "valider la maquette"}, ["lire la charte", "proposer la structure"]),
            "csv": ("Je prépare l'export trimestriel.", "Export prêt : un fichier par trimestre.",
                    {"fait": "export CSV écrit", "situation": "en bonne voie", "reste": "tests", "prochain_pas": "lancer les tests"}, ["écrire l'export"]),
            "relances": ("Je liste les factures de plus de 30 jours.", "Trois relances rédigées, prêtes à partir.",
                         {"fait": "trois relances rédigées", "situation": "à relire avant envoi", "reste": "envoi", "prochain_pas": "relire et envoyer"}, ["lister", "rédiger"]),
            "calendrier": ("Je croise les itinéraires et les vacances scolaires.", "Calendrier 2027 proposé : douze sorties, deux week-ends.",
                           {"fait": "calendrier proposé", "situation": "à soumettre au bureau", "reste": "vote du bureau", "prochain_pas": "envoyer au bureau"}, ["croiser", "proposer"]),
        },
        "aides": ["Relire le module des factures", "Chercher les tests existants"],
    },
    "en": {
        "projets": [
            ("C1-Studio-website", "Studio website", "C1-Work", {
                "accueil": ("Redesign the home page", "en-cours", "priorite: haute\n", "New headline, three showcase projects, visible quote request."),
                "contact": ("Fix the contact form", "fait", "", "Messages were landing in spam."),
                "mentions": ("Write the legal notice", "a-faire", "echeance: 2026-12-04\n", "Host, publisher, cookies."),
                "images": ("Optimise the images", "a-faire", 'priorite: basse\nprerequis: ["[[accueil]]"]\n', "Modern formats, a third of the weight."),
            }),
            ("C1-Invoicing", "Invoicing tool", "C1-Work", {
                "csv": ("Export invoices to CSV", "a-faire", "", "For the accountant, one file per quarter."),
                "tests": ("Cover the export with tests", "a-faire", "priorite: haute\n", "Amounts, VAT, accented characters."),
                "relances": ("Chase unpaid invoices", "a-faire", "", "Three invoices over 30 days."),
            }),
            ("C2-Home", "Home", "C2-Home", {
                "devis": ("Compare the kitchen quotes", "a-faire", "executant: humain\necheance: 2026-11-28\n", "Three contractors replied."),
                "chaudiere": ("Book the boiler service", "a-faire", "priorite: moyenne\n", "Mandatory yearly service."),
            }),
            ("C3-Hiking-club", "Hiking club", "C3-Club", {
                "calendrier": ("Plan the 2027 outings calendar", "a-faire", "", "One outing a month, two weekends."),
                "lettre": ("Write the December newsletter", "fait", "", "Year in review and annual meeting."),
            }),
        ],
        "notes": {
            "Ressources/brand-guidelines.md": ("Brand guidelines", "Navy, sand; two typefaces. Used for [[accueil|the home page]] and the [[images]]."),
            "Ressources/web-accessibility.md": ("Web accessibility", "Contrast, keyboard navigation. See [[brand-guidelines]] and [[contact|the form]]."),
            "Ressources/vat-and-invoices.md": ("VAT and invoices", "Mandatory mentions, rates. Useful for [[csv|the export]], [[tests]] and [[relances]]."),
            "Ressources/kitchen-quotes.md": ("Kitchen quotes", "Three contractors; see [[devis|the comparison]]."),
            "Ressources/club-routes.md": ("Club routes", "Loops of 12 to 20 km. For [[calendrier|the calendar]] and [[lettre|the newsletter]]."),
        },
        "message": "Suggest a structure for the header and the footer.",
        "note": "Keep the current logo; brand colours.",
        "scenes": {
            "accueil": ("Reading the brand guidelines and the current page.",
                        "Proposal:\n\n- **Header**: logo, menu (Studio, Work, Pricing, Contact), “Request a quote” button.\n"
                        "- **Footer**: address, opening hours, legal notice, social links.\n\nThe mockup is updated; the headline still needs approval.",
                        {"fait": "header and footer structure proposed", "situation": "mockup to approve",
                         "reste": "headline", "prochain_pas": "approve the mockup"}, ["read the guidelines", "propose the structure"]),
            "csv": ("Preparing the quarterly export.", "Export ready: one file per quarter.",
                    {"fait": "CSV export written", "situation": "on track", "reste": "tests", "prochain_pas": "run the tests"}, ["write the export"]),
            "relances": ("Listing invoices over 30 days.", "Three reminders drafted, ready to send.",
                         {"fait": "three reminders drafted", "situation": "review before sending", "reste": "sending", "prochain_pas": "review and send"}, ["list", "draft"]),
            "calendrier": ("Matching routes with school holidays.", "2027 calendar proposed: twelve outings, two weekends.",
                           {"fait": "calendar proposed", "situation": "to submit to the committee", "reste": "committee vote", "prochain_pas": "send to the committee"}, ["match", "propose"]),
        },
        "aides": ["Review the invoicing module", "Find the existing tests"],
    },
    "de": {
        "projets": [
            ("C1-Atelier-Website", "Website des Ateliers", "C1-Beruf", {
                "accueil": ("Startseite neu gestalten", "en-cours", "priorite: haute\n", "Neuer Leitsatz, drei Referenzen, sichtbare Angebotsanfrage."),
                "contact": ("Kontaktformular reparieren", "fait", "", "Nachrichten landeten im Spam."),
                "mentions": ("Impressum verfassen", "a-faire", "echeance: 2026-12-04\n", "Hoster, Herausgeber, Cookies."),
                "images": ("Bilder optimieren", "a-faire", 'priorite: basse\nprerequis: ["[[accueil]]"]\n', "Moderne Formate, ein Drittel des Gewichts."),
            }),
            ("C1-Rechnungen", "Rechnungswerkzeug", "C1-Beruf", {
                "csv": ("Rechnungen als CSV exportieren", "a-faire", "", "Für den Steuerberater, eine Datei pro Quartal."),
                "tests": ("Export mit Tests absichern", "a-faire", "priorite: haute\n", "Beträge, MwSt., Umlaute."),
                "relances": ("Offene Rechnungen anmahnen", "a-faire", "", "Drei Rechnungen über 30 Tage."),
            }),
            ("C2-Haus", "Haus", "C2-Privat", {
                "devis": ("Küchenangebote vergleichen", "a-faire", "executant: humain\necheance: 2026-11-28\n", "Drei Handwerker haben geantwortet."),
                "chaudiere": ("Heizungswartung planen", "a-faire", "priorite: moyenne\n", "Jährliche Pflichtwartung."),
            }),
            ("C3-Wanderverein", "Wanderverein", "C3-Verein", {
                "calendrier": ("Tourenkalender 2027 vorbereiten", "a-faire", "", "Eine Tour pro Monat, zwei Wochenenden."),
                "lettre": ("Dezember-Rundbrief schreiben", "fait", "", "Jahresrückblick und Mitgliederversammlung."),
            }),
        ],
        "notes": {
            "Ressources/gestaltungsrichtlinien.md": ("Gestaltungsrichtlinien", "Nachtblau, Sand; zwei Schriftfamilien. Für [[accueil|die Startseite]] und die [[images]]."),
            "Ressources/barrierefreiheit.md": ("Barrierefreiheit", "Kontraste, Tastaturbedienung. Siehe [[gestaltungsrichtlinien]] und [[contact|das Formular]]."),
            "Ressources/mwst-und-rechnungen.md": ("MwSt. und Rechnungen", "Pflichtangaben, Sätze. Nützlich für [[csv|den Export]], [[tests]] und [[relances]]."),
            "Ressources/kuechenangebote.md": ("Küchenangebote", "Drei Handwerker; siehe [[devis|den Vergleich]]."),
            "Ressources/vereinstouren.md": ("Touren des Vereins", "Rundwege von 12 bis 20 km. Für [[calendrier|den Kalender]] und [[lettre|den Rundbrief]]."),
        },
        "message": "Schlag eine Struktur für Kopf- und Fußzeile vor.",
        "note": "Aktuelles Logo behalten; Farben der Richtlinien.",
        "scenes": {
            "accueil": ("Ich lese die Richtlinien und die aktuelle Seite.",
                        "Vorschlag:\n\n- **Kopfzeile**: Logo, Menü (Atelier, Referenzen, Preise, Kontakt), Schaltfläche „Angebot anfragen“.\n"
                        "- **Fußzeile**: Adresse, Öffnungszeiten, Impressum, soziale Netzwerke.\n\nDas Mockup ist aktualisiert; der Leitsatz muss noch freigegeben werden.",
                        {"fait": "Struktur von Kopf- und Fußzeile vorgeschlagen", "situation": "Mockup freizugeben",
                         "reste": "Leitsatz", "prochain_pas": "Mockup freigeben"}, ["Richtlinien lesen", "Struktur vorschlagen"]),
            "csv": ("Ich bereite den Quartalsexport vor.", "Export bereit: eine Datei pro Quartal.",
                    {"fait": "CSV-Export geschrieben", "situation": "auf gutem Weg", "reste": "Tests", "prochain_pas": "Tests ausführen"}, ["Export schreiben"]),
            "relances": ("Ich liste Rechnungen über 30 Tage auf.", "Drei Mahnungen verfasst, versandbereit.",
                         {"fait": "drei Mahnungen verfasst", "situation": "vor dem Versand prüfen", "reste": "Versand", "prochain_pas": "prüfen und senden"}, ["auflisten", "verfassen"]),
            "calendrier": ("Ich gleiche Touren und Schulferien ab.", "Kalender 2027 vorgeschlagen: zwölf Touren, zwei Wochenenden.",
                           {"fait": "Kalender vorgeschlagen", "situation": "dem Vorstand vorzulegen", "reste": "Abstimmung", "prochain_pas": "an den Vorstand senden"}, ["abgleichen", "vorschlagen"]),
        },
        "aides": ["Rechnungsmodul prüfen", "Vorhandene Tests suchen"],
    },
    "es": {
        "projets": [
            ("C1-Web-del-estudio", "Web del estudio", "C1-Trabajo", {
                "accueil": ("Rediseñar la página de inicio", "en-cours", "priorite: haute\n", "Nuevo eslogan, tres proyectos destacados, solicitud de presupuesto visible."),
                "contact": ("Arreglar el formulario de contacto", "fait", "", "Los mensajes llegaban a spam."),
                "mentions": ("Redactar el aviso legal", "a-faire", "echeance: 2026-12-04\n", "Alojamiento, editor, cookies."),
                "images": ("Optimizar las imágenes", "a-faire", 'priorite: basse\nprerequis: ["[[accueil]]"]\n', "Formatos modernos, un tercio del peso."),
            }),
            ("C1-Facturacion", "Herramienta de facturación", "C1-Trabajo", {
                "csv": ("Exportar las facturas a CSV", "a-faire", "", "Para la gestoría, un archivo por trimestre."),
                "tests": ("Cubrir la exportación con pruebas", "a-faire", "priorite: haute\n", "Importes, IVA, acentos."),
                "relances": ("Reclamar las facturas impagadas", "a-faire", "", "Tres facturas de más de 30 días."),
            }),
            ("C2-Casa", "Casa", "C2-Personal", {
                "devis": ("Comparar los presupuestos de la cocina", "a-faire", "executant: humain\necheance: 2026-11-28\n", "Han respondido tres profesionales."),
                "chaudiere": ("Programar la revisión de la caldera", "a-faire", "priorite: moyenne\n", "Revisión anual obligatoria."),
            }),
            ("C3-Club-senderismo", "Club de senderismo", "C3-Club", {
                "calendrier": ("Preparar el calendario de salidas 2027", "a-faire", "", "Una salida al mes, dos fines de semana."),
                "lettre": ("Redactar el boletín de diciembre", "fait", "", "Balance del año y asamblea general."),
            }),
        ],
        "notes": {
            "Ressources/guia-de-estilo.md": ("Guía de estilo", "Azul noche, arena; dos tipografías. Para [[accueil|la página de inicio]] y las [[images]]."),
            "Ressources/accesibilidad-web.md": ("Accesibilidad web", "Contraste, navegación con teclado. Ver [[guia-de-estilo]] y [[contact|el formulario]]."),
            "Ressources/iva-y-facturas.md": ("IVA y facturas", "Menciones obligatorias, tipos. Útil para [[csv|la exportación]], [[tests]] y [[relances]]."),
            "Ressources/presupuestos-cocina.md": ("Presupuestos de la cocina", "Tres profesionales; ver [[devis|la comparación]]."),
            "Ressources/rutas-del-club.md": ("Rutas del club", "Circuitos de 12 a 20 km. Para [[calendrier|el calendario]] y [[lettre|el boletín]]."),
        },
        "message": "Propón una estructura para la cabecera y el pie de página.",
        "note": "Mantener el logotipo actual; colores de la guía.",
        "scenes": {
            "accueil": ("Leo la guía de estilo y la página actual.",
                        "Propuesta:\n\n- **Cabecera**: logotipo, menú (Estudio, Proyectos, Tarifas, Contacto), botón «Pedir presupuesto».\n"
                        "- **Pie de página**: dirección, horario, aviso legal, redes.\n\nLa maqueta está al día; falta validar el eslogan.",
                        {"fait": "estructura de cabecera y pie propuesta", "situation": "maqueta por validar",
                         "reste": "eslogan", "prochain_pas": "validar la maqueta"}, ["leer la guía", "proponer la estructura"]),
            "csv": ("Preparo la exportación trimestral.", "Exportación lista: un archivo por trimestre.",
                    {"fait": "exportación CSV escrita", "situation": "por buen camino", "reste": "pruebas", "prochain_pas": "lanzar las pruebas"}, ["escribir la exportación"]),
            "relances": ("Listo las facturas de más de 30 días.", "Tres recordatorios redactados, listos para enviar.",
                         {"fait": "tres recordatorios redactados", "situation": "revisar antes de enviar", "reste": "envío", "prochain_pas": "revisar y enviar"}, ["listar", "redactar"]),
            "calendrier": ("Cruzo las rutas con las vacaciones escolares.", "Calendario 2027 propuesto: doce salidas, dos fines de semana.",
                           {"fait": "calendario propuesto", "situation": "para la junta", "reste": "votación de la junta", "prochain_pas": "enviar a la junta"}, ["cruzar", "proponer"]),
        },
        "aides": ["Revisar el módulo de facturas", "Buscar las pruebas existentes"],
    },
}


def message_de(code: str, fichier: str) -> str:
    """Message envoyé à la tâche `fichier` : celui de la démonstration pour l'accueil, sinon son titre."""
    d = DEMO[code]
    if fichier == "accueil":
        return d["message"]
    return next(t[0] for _, _, _, ts in d["projets"] for f, t in ts.items() if f == fichier)


def scenes(code: str) -> dict:
    """Ce que joue le harnais factice, par message reçu (lu par `harnais_factice.py` via `GB_DEMO`)."""
    d = DEMO[code]
    sortie = {}
    for fichier, (texte, final, fiche, etapes) in d["scenes"].items():
        corps = "".join(f"{k}: {v}\n" for k, v in fiche.items())
        sous = "".join(f"- [x] {e}\n" for e in etapes)
        sortie[message_de(code, fichier)] = {
            "texte": texte, "duree": 600 if fichier == "csv" else 2,
            "aides": d["aides"] if fichier == "csv" else [],
            "fin": f"{final}\n<fiche>\nstatut: {'en_attente' if fichier == 'relances' else 'terminee'}\n{corps}sous_taches:\n{sous}</fiche>"}
    return sortie


def ecrire_vault(vault: Path, code: str) -> None:
    """Remplace le contenu de démonstration du vault temporaire par celui de la langue `code`."""
    import shutil
    for d in ("Projets", "_meta", "Ressources"):  # l'univers des autres scénarios n'a rien à faire sur une capture
        shutil.rmtree(vault / d, ignore_errors=True)
    for dossier, nom, casquette, taches in DEMO[code]["projets"]:
        univers.ecrire(vault, f"Projets/{dossier}/contexte.md", f"---\ntype: contexte\ncasquette: {casquette}\nnom: {nom}\n---\n")
        for f, (titre, statut, extra, corps) in taches.items():
            univers.ecrire(vault, f"Projets/{dossier}/taches/{f}.md",
                           f"---\ntype: tache\nstatut: {statut}\n{extra}tags: []\n---\n\n# {titre}\n\n{corps}\n")
    for rel, (titre, corps) in DEMO[code]["notes"].items():
        univers.ecrire(vault, rel, f"---\ntype: ressource\ntags: [demo]\n---\n\n# {titre}\n\n{corps}\n")

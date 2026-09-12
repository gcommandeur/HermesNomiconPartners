"""Eingebettete, aus dem vollstaendigen Lukas-Postfach-Export
(lukas_pst_export.csv, 6128 Zeilen) aggregierte Kontakt-Kandidaten je
Domain - bewusst als Python-Modul statt CSV (siehe
kanzlei_import_data.py-Vorbild), weil backend/scripts/*.csv
projektweit gitignored ist und diese Daten damit garantiert mit dem
Repository deployed werden (fuer den Lauf ueber die DO-App-Platform-
Console, wo kein lokaler Dateizugriff besteht).

Enthaelt NUR die abgeleiteten, bereits priorisierten Kandidaten
(1-3 pro Domain: namentliche Personen bevorzugt, generische
Funktionspostfaecher nur als Fallback ohne gefundene Person) - NICHT
den vollstaendigen Rohdaten-Export (Datensparsamkeit: keine
Kandidaten-/Privatadressen oder Nachrichtentexte, nur Name+E-Mail
von Kanzlei-Ansprechpartnern +Nachrichtenanzahl als Beleg).

Das Domain-Matching gegen die aktuelle Kanzleiliste UND die Pruefung,
ob eine Kanzlei bereits einen Kontakt hat, laufen weiterhin live im
Enrichment-Skript selbst (siehe dessen Docstring) - diese Liste ist
reine Rohdaten-Aufbereitung, keine Vorab-Filterung nach 'passt zu
einer bestehenden Kanzlei'.
"""

from __future__ import annotations

DOMAIN_CONTACT_CANDIDATES: dict[str, list[dict[str, str]]] = {
    "aachener-swg.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@aachener-swg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "abels-buchmann.de": [
        {
            "first_name": "",
            "last_name": "bewerber",
            "email": "bewerber@abels-buchmann.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "abh-stromschienen.de": [
        {
            "first_name": "Andrea",
            "last_name": "Boslak",
            "email": "a.boslak@abh-stromschienen.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "e.zeller",
            "email": "e.zeller@abh-stromschienen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "abn-partner.de": [
        {
            "first_name": "",
            "last_name": "lohn",
            "email": "lohn@abn-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "abraham-loehr.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@abraham-loehr.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "abw-treuhand.de": [
        {
            "first_name": "",
            "last_name": "k.rudolph",
            "email": "k.rudolph@abw-treuhand.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "acconsis.de": [
        {
            "first_name": "",
            "last_name": "j.gebelein",
            "email": "j.gebelein@acconsis.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "accretech.eu": [
        {
            "first_name": "",
            "last_name": "Recruitment",
            "email": "recruitment@accretech.eu",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "accura-audit.de": [
        {
            "first_name": "",
            "last_name": "frankfurt",
            "email": "frankfurt@accura-audit.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "actio-cpa.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@actio-cpa.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "activ-treuhand.de": [
        {
            "first_name": "Oliver R.",
            "last_name": "Mally",
            "email": "my@activ-treuhand.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "adsensio.nrw": [
        {
            "first_name": "",
            "last_name": "drabinski",
            "email": "drabinski@adsensio.nrw",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "advant-beiten.com": [
        {
            "first_name": "",
            "last_name": "jule.dillbahner",
            "email": "jule.dillbahner@advant-beiten.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "advicon.tax": [
        {
            "first_name": "Postfach",
            "last_name": "bewerbung@advicon.tax",
            "email": "bewerbung@advicon.tax",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "aequita.com": [
        {
            "first_name": "",
            "last_name": "julia.batoja",
            "email": "julia.batoja@aequita.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "charlotte.hallinger",
            "email": "charlotte.hallinger@aequita.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "afileon.com": [
        {
            "first_name": "Magdalena",
            "last_name": "Scheugenpflug",
            "email": "magdalena.scheugenpflug@afileon.com",
            "anzahl_mails": "350",
            "typ": "person",
        },
        {
            "first_name": "Viktoria",
            "last_name": "Steinmeier",
            "email": "viktoria.steinmeier@afileon.com",
            "anzahl_mails": "191",
            "typ": "person",
        },
        {
            "first_name": "Diana",
            "last_name": "Weiser",
            "email": "diana.weiser@afileon.com",
            "anzahl_mails": "170",
            "typ": "person",
        },
    ],
    "agfh.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@agfh.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "agoebel-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@agoebel-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "aios.de": [
        {
            "first_name": "",
            "last_name": "Karriere",
            "email": "karriere@aios.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "aitava.com": [
        {
            "first_name": "David",
            "last_name": "Bomhard",
            "email": "david.bomhard@aitava.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "akp-gruppe.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@akp-gruppe.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "aktax.de": [
        {
            "first_name": "Oliver",
            "last_name": "Arnold",
            "email": "arnold@aktax.de",
            "anzahl_mails": "21",
            "typ": "person",
        },
    ],
    "aktivberaten.eu": [
        {
            "first_name": "",
            "last_name": "marc.becker",
            "email": "marc.becker@aktivberaten.eu",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "alexander-stegmueller.de": [
        {
            "first_name": "Alexander",
            "last_name": "Stegmüller",
            "email": "info@alexander-stegmueller.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "alius-steuerkanzlei.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@alius-steuerkanzlei.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "alltax.de": [
        {
            "first_name": "",
            "last_name": "andre.kollmuss",
            "email": "andre.kollmuss@alltax.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "alpers-maack-wessel.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@alpers-maack-wessel.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "alt-partner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@alt-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "altmann-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@altmann-steuerberater.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "amannjoerger.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@amannjoerger.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "amp-steuerberatung.de": [
        {
            "first_name": "Laura",
            "last_name": "Anger",
            "email": "l.anger@amp-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "amz-steuer.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@amz-steuer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "anthofer-aberle.de": [
        {
            "first_name": "",
            "last_name": "carmen.gmeinwieser",
            "email": "carmen.gmeinwieser@anthofer-aberle.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "anwaltskanzlei-online.de": [
        {
            "first_name": "",
            "last_name": "ulrike.gebauer",
            "email": "ulrike.gebauer@anwaltskanzlei-online.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "aplus-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@aplus-steuerberater.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "app.softgarden.io": [
        {
            "first_name": "ETL Service GmbH – Personal Services (via",
            "last_name": "softgarden)",
            "email": "notifications@app.softgarden.io",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "arbeit-anwalt.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@arbeit-anwalt.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "Onur",
            "last_name": "Sertkol",
            "email": "sertkol@arbeit-anwalt.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "arps-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "zukunft",
            "email": "zukunft@arps-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "artiva-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@artiva-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "aschestein.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@aschestein.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "asp-recht.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@asp-recht.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "assp-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@assp-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "atotech.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@atotech.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "attachenet.de": [
        {
            "first_name": "",
            "last_name": "Office",
            "email": "office@attachenet.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "aurach-stb.de": [
        {
            "first_name": "",
            "last_name": "steuerberater",
            "email": "steuerberater@aurach-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "aurantia.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@aurantia.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "aurealis.email": [
        {
            "first_name": "Kanzlei",
            "last_name": "Ertl",
            "email": "hengersberg@aurealis.email",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "auren.de": [
        {
            "first_name": "Helene",
            "last_name": "Hettich",
            "email": "helene.hettich@auren.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "nergz.can",
            "email": "nergz.can@auren.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "nergiz.can",
            "email": "nergiz.can@auren.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "avex-tankstellen.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@avex-tankstellen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "awwp.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@awwp.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "b-sauerborn.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@b-sauerborn.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ba-group.de": [
        {
            "first_name": "Nils",
            "last_name": "Kruse",
            "email": "nkruse@ba-group.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "babel-ibendorf.de": [
        {
            "first_name": "Susanne",
            "last_name": "Babel",
            "email": "susanne.babel@babel-ibendorf.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "baeuerle-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@baeuerle-steuerberater.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "bakertilly.com": [
        {
            "first_name": "",
            "last_name": "recruiting",
            "email": "recruiting@bakertilly.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bakertilly.de": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@bakertilly.de",
            "anzahl_mails": "10",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "felix.weissbrodt",
            "email": "felix.weissbrodt@bakertilly.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "bandis.de": [
        {
            "first_name": "Bandis+Knopp GmbH & Co. KG",
            "last_name": "Wellpappenfabrik",
            "email": "bewerbung@bandis.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bansbach-gmbh.de": [
        {
            "first_name": "Bansbach",
            "last_name": "Bewerbung",
            "email": "bewerbung@bansbach-gmbh.de",
            "anzahl_mails": "12",
            "typ": "generic",
        },
    ],
    "bansbach-gruppe.de": [
        {
            "first_name": "Bansbach",
            "last_name": "Bewerbung",
            "email": "bewerbung@bansbach-gruppe.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "barba-legal.com": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@barba-legal.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "baskan.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@baskan.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bauer-kompressoren.de": [
        {
            "first_name": "Volker",
            "last_name": "Sandfuchs",
            "email": "v.sandfuchs@bauer-kompressoren.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "h.gfaller",
            "email": "h.gfaller@bauer-kompressoren.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bauer-treuhand.de": [
        {
            "first_name": "Lantermann",
            "last_name": "Markus",
            "email": "m.lantermann@bauer-treuhand.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "bauergroup.com": [
        {
            "first_name": "Daniel",
            "last_name": "Gebele",
            "email": "d.gebele@bauergroup.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "baum-henckell.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@baum-henckell.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "baumhof.de": [
        {
            "first_name": "",
            "last_name": "eugen.jakoby",
            "email": "eugen.jakoby@baumhof.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "baytax.de": [
        {
            "first_name": "Viola",
            "last_name": "Maier",
            "email": "v.maier@baytax.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "baz-stbg.de": [
        {
            "first_name": "",
            "last_name": "service",
            "email": "service@baz-stbg.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bb-bartenbach.de": [
        {
            "first_name": "",
            "last_name": "seebronn",
            "email": "seebronn@bb-bartenbach.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bbh-online.de": [
        {
            "first_name": "",
            "last_name": "sabina.schmidbauer",
            "email": "sabina.schmidbauer@bbh-online.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bbsz.de": [
        {
            "first_name": "",
            "last_name": "durchstarten",
            "email": "durchstarten@bbsz.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "bdo.de": [
        {
            "first_name": "",
            "last_name": "recruiting",
            "email": "recruiting@bdo.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bdp-team.de": [
        {
            "first_name": "",
            "last_name": "martina.hagemeier",
            "email": "martina.hagemeier@bdp-team.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "beckerpartner.de": [
        {
            "first_name": "",
            "last_name": "aroels",
            "email": "aroels@beckerpartner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "Silke",
            "last_name": "Strohschein",
            "email": "sstrohschein@beckerpartner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "benedict-becker.de": [
        {
            "first_name": "Benedict",
            "last_name": "Becker",
            "email": "mail@benedict-becker.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "benefitax.de": [
        {
            "first_name": "",
            "last_name": "Bewerbung",
            "email": "bewerbung@benefitax.de",
            "anzahl_mails": "33",
            "typ": "generic",
        },
    ],
    "bentz.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@bentz.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "benzing-birk.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@benzing-birk.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "berater-sws.de": [
        {
            "first_name": "",
            "last_name": "hst",
            "email": "hst@berater-sws.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "berger-partner-muc.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@berger-partner-muc.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bergers-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@bergers-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bergholz.tax": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@bergholz.tax",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "berlincounsel.com": [
        {
            "first_name": "Peter",
            "last_name": "Krause",
            "email": "peter.krause@berlincounsel.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "berndlmaier.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@berndlmaier.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "berufmitsinn.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@berufmitsinn.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "better-jobs.de": [
        {
            "first_name": "",
            "last_name": "service",
            "email": "service@better-jobs.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bgvm-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@bgvm-partner.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "biederstein.de": [
        {
            "first_name": "Clemens",
            "last_name": "Broch",
            "email": "broch@biederstein.de",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "bietmann.eu": [
        {
            "first_name": "",
            "last_name": "andreas.bietmann",
            "email": "andreas.bietmann@bietmann.eu",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bilfinger.com": [
        {
            "first_name": "",
            "last_name": "doreen.kepper",
            "email": "doreen.kepper@bilfinger.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "birkenmaier-obser.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@birkenmaier-obser.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bischof-stb.de": [
        {
            "first_name": "Christina",
            "last_name": "Bischof",
            "email": "cb@bischof-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "bischoffundpartner.de": [
        {
            "first_name": "",
            "last_name": "Stellenausschreibungen",
            "email": "job@bischoffundpartner.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "bistum-augsburg.de": [
        {
            "first_name": "",
            "last_name": "gudrun.knoeferle",
            "email": "gudrun.knoeferle@bistum-augsburg.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bjkgretter.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@bjkgretter.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bkl.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@bkl.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bks-steuern.de": [
        {
            "first_name": "",
            "last_name": "bks",
            "email": "bks@bks-steuern.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "bley-doerflinger.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@bley-doerflinger.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "blind-partner.de": [
        {
            "first_name": "",
            "last_name": "ehing",
            "email": "ehing@blind-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "blomberg-legal.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@blomberg-legal.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "blum-und-becker.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@blum-und-becker.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bm-partner.com": [
        {
            "first_name": "",
            "last_name": "m.mueller",
            "email": "m.mueller@bm-partner.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bms-recht.de": [
        {
            "first_name": "",
            "last_name": "t.mayer",
            "email": "t.mayer@bms-recht.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bnm-hamburg.com": [
        {
            "first_name": "",
            "last_name": "job",
            "email": "job@bnm-hamburg.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "boehnke-gruber.de": [
        {
            "first_name": "Ulli",
            "last_name": "Degler",
            "email": "ulli.degler@boehnke-gruber.de",
            "anzahl_mails": "16",
            "typ": "person",
        },
        {
            "first_name": "Aline",
            "last_name": "Schmitt",
            "email": "aline.schmitt@boehnke-gruber.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "bonn-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@bonn-partner.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "borchardmenck.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@borchardmenck.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "borgdorfpartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@borgdorfpartner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bpw-online.de": [
        {
            "first_name": "",
            "last_name": "berlin",
            "email": "berlin@bpw-online.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "brbgruppe.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@brbgruppe.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "breder.net": [
        {
            "first_name": "",
            "last_name": "sebastian.breder",
            "email": "sebastian.breder@breder.net",
            "anzahl_mails": "10",
            "typ": "person",
        },
    ],
    "brl.de": [
        {
            "first_name": "Dorothea",
            "last_name": "Besche",
            "email": "dorothea.besche@brl.de",
            "anzahl_mails": "122",
            "typ": "person",
        },
        {
            "first_name": "Jörg",
            "last_name": "Bohne",
            "email": "joerg.bohne@brl.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "Julia",
            "last_name": "Sendra Alonso",
            "email": "julia.sendraalonso@brl.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "brodbeck-stb.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@brodbeck-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "brs-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@brs-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "bsb-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@bsb-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "bsd-data.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@bsd-data.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bsl-tax.com": [
        {
            "first_name": "",
            "last_name": "bb",
            "email": "bb@bsl-tax.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bsp-legaltax.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@bsp-legaltax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "btg-kreis-dueren.de": [
        {
            "first_name": "",
            "last_name": "h.wirtz",
            "email": "h.wirtz@btg-kreis-dueren.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "btspartner.de": [
        {
            "first_name": "",
            "last_name": "sobek",
            "email": "sobek@btspartner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "Anja",
            "last_name": "Berndt",
            "email": "berndt@btspartner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bullhorn.com": [
        {
            "first_name": "",
            "last_name": "training",
            "email": "training@bullhorn.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "burchardt-kollegen.de": [
        {
            "first_name": "",
            "last_name": "oliver.burchardt",
            "email": "oliver.burchardt@burchardt-kollegen.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "burgert-kollegen.de": [
        {
            "first_name": "",
            "last_name": "friedbert.burgert.stb",
            "email": "friedbert.burgert.stb@burgert-kollegen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bus-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "f.bandow",
            "email": "f.bandow@bus-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "buschle-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "simon",
            "email": "simon@buschle-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "bust.de": [
        {
            "first_name": "Niederlassung",
            "last_name": "Hannover",
            "email": "hannover@bust.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "buttinette.de": [
        {
            "first_name": "",
            "last_name": "DE-Bewerbung",
            "email": "bewerbung@buttinette.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "bvwm.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@bvwm.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "bw-bayern.com": [
        {
            "first_name": "Sebastian",
            "last_name": "Groß",
            "email": "s.gross@bw-bayern.com",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "bwbm.de": [
        {
            "first_name": "Leonie",
            "last_name": "Kall",
            "email": "leonie.kall@bwbm.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "Bewerbungzentrale",
            "email": "bewerbungzentrale@bwbm.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "bws-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "team",
            "email": "team@bws-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "careforce.de": [
        {
            "first_name": "",
            "last_name": "astrid.kujau",
            "email": "astrid.kujau@careforce.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "casis.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@casis.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "cdmsmith.com": [
        {
            "first_name": "",
            "last_name": "Bewerbungen",
            "email": "bewerbungen@cdmsmith.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "cellitinnen.de": [
        {
            "first_name": "Ayse",
            "last_name": "Varis",
            "email": "ayse.varis@cellitinnen.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "cfh-hamburg.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@cfh-hamburg.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "chp-steuern.de": [
        {
            "first_name": "",
            "last_name": "Karriere",
            "email": "karriere@chp-steuern.de",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "christoph-nufer.de": [
        {
            "first_name": "",
            "last_name": "petra.edele-nufer",
            "email": "petra.edele-nufer@christoph-nufer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "cicek-stb.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@cicek-stb.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "cipgroup.com": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@cipgroup.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "cl-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@cl-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "clayston.com": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@clayston.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "club29.net": [
        {
            "first_name": "Georg",
            "last_name": "Grau",
            "email": "georg.grau@club29.net",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "cmf-unternehmensberatung.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@cmf-unternehmensberatung.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "cms-hs.com": [
        {
            "first_name": "CMS",
            "last_name": "Recruitment",
            "email": "recruitment@cms-hs.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "Heike",
            "last_name": "Janke",
            "email": "heike.janke@cms-hs.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "neele.christiansen",
            "email": "neele.christiansen@cms-hs.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "communication.hrworks.de": [
        {
            "first_name": "Claudia",
            "last_name": "Pröls",
            "email": "bewerbungen@communication.hrworks.de",
            "anzahl_mails": "12",
            "typ": "generic",
        },
    ],
    "con-tax.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@con-tax.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
        {
            "first_name": "bewerbungen",
            "last_name": "contax",
            "email": "bewerbungen@con-tax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "concept-wp.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@concept-wp.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "confidia.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@confidia.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "consilia.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@consilia.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "constanta.de": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@constanta.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "counsel.de": [
        {
            "first_name": "Susanne",
            "last_name": "Poellath",
            "email": "susanne.poellath@counsel.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "cpa-gruppe.de": [
        {
            "first_name": "",
            "last_name": "annette.gold",
            "email": "annette.gold@cpa-gruppe.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "crowe-bpg.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@crowe-bpg.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "crowe-kleeberg.de": [
        {
            "first_name": "Angela",
            "last_name": "Litvinenko",
            "email": "angela.litvinenko@crowe-kleeberg.de",
            "anzahl_mails": "8",
            "typ": "person",
        },
        {
            "first_name": "Julia",
            "last_name": "Kastl",
            "email": "julia.kastl@crowe-kleeberg.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "crtax.de": [
        {
            "first_name": "",
            "last_name": "Info",
            "email": "info@crtax.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@crtax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "curacon.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@curacon.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "cwtp.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@cwtp.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "d-l-p.de": [
        {
            "first_name": "",
            "last_name": "christopher.benden",
            "email": "christopher.benden@d-l-p.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "dbbdata.de": [
        {
            "first_name": "Carsten",
            "last_name": "Jaeger",
            "email": "c.jaeger@dbbdata.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "dbbp-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "jburghaus",
            "email": "jburghaus@dbbp-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "de.ey.com": [
        {
            "first_name": "",
            "last_name": "joanna.jankovic",
            "email": "joanna.jankovic@de.ey.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "de.gt.com": [
        {
            "first_name": "Team",
            "last_name": "Karriere",
            "email": "karriere@de.gt.com",
            "anzahl_mails": "9",
            "typ": "generic",
        },
    ],
    "de.sasol.com": [
        {
            "first_name": "",
            "last_name": "annika.bauer",
            "email": "annika.bauer@de.sasol.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "delfs.team": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@delfs.team",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "deloitte.de": [
        {
            "first_name": "Recruiting",
            "last_name": "DE",
            "email": "recruiting@deloitte.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "dentons.com": [
        {
            "first_name": "",
            "last_name": "natia.giragousian",
            "email": "natia.giragousian@dentons.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "der-online-steuerberater.de": [
        {
            "first_name": "Marena Keller (Kanzlei Dr.",
            "last_name": "Stölzel)",
            "email": "keller@der-online-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "der-onlinesteuerberater.de": [
        {
            "first_name": "",
            "last_name": "keller",
            "email": "keller@der-onlinesteuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "dhpg.de": [
        {
            "first_name": "dhpg",
            "last_name": "Karriere",
            "email": "karriere@dhpg.de",
            "anzahl_mails": "7",
            "typ": "generic",
        },
    ],
    "dibag.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@dibag.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "dieringer-stb.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@dieringer-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "dierkes-partner.de": [
        {
            "first_name": "",
            "last_name": "Bewerbung",
            "email": "bewerbung@dierkes-partner.de",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "dietlundkollegen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@dietlundkollegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "digitalkanzlei.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@digitalkanzlei.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "dissmannorth.de": [
        {
            "first_name": "",
            "last_name": "friese",
            "email": "friese@dissmannorth.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "divansteuerberatung.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@divansteuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "dlapiper.com": [
        {
            "first_name": "Recruiting",
            "last_name": "Germany",
            "email": "recruiting.germany@dlapiper.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "dmp-wpg.de": [
        {
            "first_name": "",
            "last_name": "stefanie.lisker",
            "email": "stefanie.lisker@dmp-wpg.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "dnd-partner.de": [
        {
            "first_name": "Felix",
            "last_name": "Daum",
            "email": "felix.daum@dnd-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "Florian",
            "last_name": "Daum",
            "email": "florian.daum@dnd-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "dnk-rechtsanwaelte.de": [
        {
            "first_name": "",
            "last_name": "kraemer",
            "email": "kraemer@dnk-rechtsanwaelte.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "docatax.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@docatax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "dornbach-muc.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@dornbach-muc.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "dosu.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@dosu.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "dr-dohrmann.de": [
        {
            "first_name": "",
            "last_name": "suedbeck",
            "email": "suedbeck@dr-dohrmann.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "dr-rapp-partner.de": [
        {
            "first_name": "",
            "last_name": "mueller",
            "email": "mueller@dr-rapp-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "dr-zeifang-kuebel.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@dr-zeifang-kuebel.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "drboehmer.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@drboehmer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "drei6null.de": [
        {
            "first_name": "",
            "last_name": "oliver.vogt",
            "email": "oliver.vogt@drei6null.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "drk-pulheim.de": [
        {
            "first_name": "Stefan",
            "last_name": "Wohlfahrt",
            "email": "stefan.wohlfahrt@drk-pulheim.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "drkellerkollegen.de": [
        {
            "first_name": "",
            "last_name": "dr.zawieja",
            "email": "dr.zawieja@drkellerkollegen.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "ds-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "d.schmeisser",
            "email": "d.schmeisser@ds-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "ds-tax.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@ds-tax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@ds-tax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "duplois.com": [
        {
            "first_name": "Marcel",
            "last_name": "Duplois",
            "email": "marcel@duplois.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "e-k-p.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@e-k-p.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "ebnerstolz.de": [
        {
            "first_name": "Johanna",
            "last_name": "Günther",
            "email": "johanna.guenther@ebnerstolz.de",
            "anzahl_mails": "25",
            "typ": "person",
        },
        {
            "first_name": "Svenja",
            "last_name": "Breitenbücher",
            "email": "svenja.breitenbuecher@ebnerstolz.de",
            "anzahl_mails": "25",
            "typ": "person",
        },
        {
            "first_name": "Chiara",
            "last_name": "Voigt",
            "email": "chiara.voigt@ebnerstolz.de",
            "anzahl_mails": "16",
            "typ": "person",
        },
    ],
    "eckstein-kollegen.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@eckstein-kollegen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ecotaxes.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@ecotaxes.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ecovis-kso.com": [
        {
            "first_name": "",
            "last_name": "lena.woerdehoff",
            "email": "lena.woerdehoff@ecovis-kso.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ecovis-rts.de": [
        {
            "first_name": "Jana",
            "last_name": "Nikitin",
            "email": "jana.nikitin@ecovis-rts.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "Anja - RTS",
            "last_name": "Josten",
            "email": "anja.josten@ecovis-rts.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "ecovis.com": [
        {
            "first_name": "Chris | Ecovis",
            "last_name": "Lange",
            "email": "chris.lange@ecovis.com",
            "anzahl_mails": "45",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "lena.woerdehoff",
            "email": "lena.woerdehoff@ecovis.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "karriere-kso",
            "email": "karriere-kso@ecovis.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "eduardus.de": [
        {
            "first_name": "",
            "last_name": "n.wasser",
            "email": "n.wasser@eduardus.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "eep.info": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@eep.info",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "egido.de": [
        {
            "first_name": "EGIDO",
            "last_name": "Support",
            "email": "sophie.fock@egido.de",
            "anzahl_mails": "68",
            "typ": "person",
        },
        {
            "first_name": "Sophie Fock via EGIDO",
            "last_name": "Support",
            "email": "oliwer.brodatzki@egido.de",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "ehk.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@ehk.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "eisenmenger-stbg.de": [
        {
            "first_name": "Ralf",
            "last_name": "Eisenmenger",
            "email": "ralf.eisenmenger@eisenmenger-stbg.de",
            "anzahl_mails": "48",
            "typ": "person",
        },
        {
            "first_name": "Benedikte",
            "last_name": "Thalheimer",
            "email": "benedikte.thalheimer@eisenmenger-stbg.de",
            "anzahl_mails": "8",
            "typ": "person",
        },
    ],
    "ekipo-steuern.de": [
        {
            "first_name": "",
            "last_name": "sebastian.bolte",
            "email": "sebastian.bolte@ekipo-steuern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "marina.frank",
            "email": "marina.frank@ekipo-steuern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ekw.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ekw.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "elbkanzlei.com": [
        {
            "first_name": "ELBKANZLEI Dr. Nolting &",
            "last_name": "Partner",
            "email": "rae@elbkanzlei.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "ellgering-ruiling.de": [
        {
            "first_name": "",
            "last_name": "stb",
            "email": "stb@ellgering-ruiling.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "email.de": [
        {
            "first_name": "",
            "last_name": "yvonne.hoehn",
            "email": "yvonne.hoehn@email.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "engl-stb.de": [
        {
            "first_name": "",
            "last_name": "b.engl",
            "email": "b.engl@engl-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "esche.de": [
        {
            "first_name": "Ines",
            "last_name": "Bäcker",
            "email": "karriere@esche.de",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "esserkies.de": [
        {
            "first_name": "",
            "last_name": "m.konz",
            "email": "m.konz@esserkies.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "etbn.de": [
        {
            "first_name": "Evelyn",
            "last_name": "Wiesweg",
            "email": "evelyn.wiesweg@etbn.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "etl-alztax.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@etl-alztax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "etl-protax.de": [
        {
            "first_name": "Christian",
            "last_name": "Hoffmann",
            "email": "christian.hoffmann@etl-protax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "etl-skrok.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@etl-skrok.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "etl-stuttgart.de": [
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@etl-stuttgart.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "etl.de": [
        {
            "first_name": "Andrea",
            "last_name": "Hoffmann",
            "email": "andrea.hoffmann@etl.de",
            "anzahl_mails": "17",
            "typ": "person",
        },
        {
            "first_name": "ETL",
            "last_name": "HR",
            "email": "hr-team@etl.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "dietrich.loll",
            "email": "dietrich.loll@etl.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "euprax.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@euprax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ewk-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@ewk-steuerberatung.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "expattax.de": [
        {
            "first_name": "",
            "last_name": "tz",
            "email": "tz@expattax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "f-thomas.de": [
        {
            "first_name": "",
            "last_name": "ft",
            "email": "ft@f-thomas.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "falch-partner.de": [
        {
            "first_name": "",
            "last_name": "stb.baretti",
            "email": "stb.baretti@falch-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "ra.graber",
            "email": "ra.graber@falch-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "falco-treuhand.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@falco-treuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fast-stb.de": [
        {
            "first_name": "Tatjana",
            "last_name": "Fast",
            "email": "tatjanafast@fast-stb.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "faststeuerberatung.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@faststeuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fbs-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@fbs-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "fe-ls.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@fe-ls.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "feldkaemper.de": [
        {
            "first_name": "",
            "last_name": "u.feldkaemper",
            "email": "u.feldkaemper@feldkaemper.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "feuchtinger.com": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@feuchtinger.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ff-stbg.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ff-stbg.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fgs.de": [
        {
            "first_name": "Laura-Teresa",
            "last_name": "Curth",
            "email": "laura-teresa.curth@fgs.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
        {
            "first_name": "Susanne",
            "last_name": "Gerards",
            "email": "susanne.gerards@fgs.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
        {
            "first_name": "Florian",
            "last_name": "Holzner",
            "email": "florian.holzner@fgs.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "fidiaonline.com": [
        {
            "first_name": "",
            "last_name": "marc.wenk",
            "email": "marc.wenk@fidiaonline.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "finkbeiner-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@finkbeiner-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "fischer-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@fischer-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fl-steuerundrecht.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@fl-steuerundrecht.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "fmp-steuern.de": [
        {
            "first_name": "",
            "last_name": "cpiasta",
            "email": "cpiasta@fmp-steuern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "focam.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@focam.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "foerschner-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@foerschner-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "fondsnet.de": [
        {
            "first_name": "Bewerbung",
            "last_name": "Fondsnet",
            "email": "bewerbung@fondsnet.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "forvismazars.com": [
        {
            "first_name": "",
            "last_name": "annett.kwias",
            "email": "annett.kwias@forvismazars.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "fps-law.de": [
        {
            "first_name": "",
            "last_name": "karriere-b",
            "email": "karriere-b@fps-law.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "fritzsche",
            "email": "fritzsche@fps-law.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "franken-treuhand.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@franken-treuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "frankus.com": [
        {
            "first_name": "",
            "last_name": "y.panknin",
            "email": "y.panknin@frankus.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "frantax.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@frantax.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "frebert-kollegen.de": [
        {
            "first_name": "",
            "last_name": "f.frebert",
            "email": "f.frebert@frebert-kollegen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "freese-feldhaus.de": [
        {
            "first_name": "Nadine",
            "last_name": "Kluegel",
            "email": "nadine.kluegel@freese-feldhaus.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "frisch-dietz.de": [
        {
            "first_name": "",
            "last_name": "a.frisch",
            "email": "a.frisch@frisch-dietz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "frtpartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@frtpartner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fsw-steuer.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@fsw-steuer.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "fugger.com": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@fugger.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "futrue.com": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@futrue.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "gaap-gmbh.com": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@gaap-gmbh.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "galls.de": [
        {
            "first_name": "Julia",
            "last_name": "Gall",
            "email": "j@galls.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "gansen-beratung.de": [
        {
            "first_name": "",
            "last_name": "koeln",
            "email": "koeln@gansen-beratung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gansen.eu": [
        {
            "first_name": "",
            "last_name": "ma.gansen",
            "email": "ma.gansen@gansen.eu",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gar-wpg.com": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@gar-wpg.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "geduhn-lerdon.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@geduhn-lerdon.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "geldmacher.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@geldmacher.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "generali.com": [
        {
            "first_name": "",
            "last_name": "hrs",
            "email": "hrs@generali.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "genoverband.de": [
        {
            "first_name": "",
            "last_name": "timo.sgodda",
            "email": "timo.sgodda@genoverband.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gerl.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@gerl.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "germania-stb.de": [
        {
            "first_name": "",
            "last_name": "schweinfurt",
            "email": "schweinfurt@germania-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "bayreuth",
            "email": "bayreuth@germania-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gernoth.de": [
        {
            "first_name": "",
            "last_name": "talente",
            "email": "talente@gernoth.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "gkanzlei.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@gkanzlei.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "gkkpartners.de": [
        {
            "first_name": "Markus",
            "last_name": "Keller",
            "email": "m.keller@gkkpartners.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gkrw.de": [
        {
            "first_name": "Sabrina",
            "last_name": "Haberkamp",
            "email": "haberkamp@gkrw.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "mueller",
            "email": "mueller@gkrw.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "glaeser-gehrmann.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@glaeser-gehrmann.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "gleichauf-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "c.gabriel",
            "email": "c.gabriel@gleichauf-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gleisslutz.com": [
        {
            "first_name": "Marcel (Gleiss Lutz)",
            "last_name": "Reich",
            "email": "marcel.reich@gleisslutz.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "glns.de": [
        {
            "first_name": "Georg",
            "last_name": "Lindner",
            "email": "lindner@glns.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "gmailcom": [
        {
            "first_name": "",
            "last_name": "julia.ferrenberg",
            "email": "julia.ferrenberg@gmailcom",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gmx.com": [
        {
            "first_name": "Eva",
            "last_name": "Waldberg",
            "email": "ewaldberg@gmx.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "goerg.de": [
        {
            "first_name": "GÖRG",
            "last_name": "Recruiting",
            "email": "recruiting@goerg.de",
            "anzahl_mails": "15",
            "typ": "generic",
        },
    ],
    "goerler-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@goerler-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "goetz-partner.de": [
        {
            "first_name": "Dietz",
            "last_name": "Uwe",
            "email": "dietz@goetz-partner.de",
            "anzahl_mails": "13",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@goetz-partner.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "kersting",
            "email": "kersting@goetz-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "goldbecksolar.com": [
        {
            "first_name": "",
            "last_name": "patricia.bous",
            "email": "patricia.bous@goldbecksolar.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "goldbergsolar.com": [
        {
            "first_name": "",
            "last_name": "patricia.bous",
            "email": "patricia.bous@goldbergsolar.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "goldner-kollegen.de": [
        {
            "first_name": "",
            "last_name": "strecker",
            "email": "strecker@goldner-kollegen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "goldstein-doenmez.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@goldstein-doenmez.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "googlemail.com": [
        {
            "first_name": "",
            "last_name": "vanda.kverel",
            "email": "vanda.kverel@googlemail.com",
            "anzahl_mails": "10",
            "typ": "person",
        },
        {
            "first_name": "Danijel",
            "last_name": "Raic",
            "email": "danijel.raic@googlemail.com",
            "anzahl_mails": "8",
            "typ": "person",
        },
        {
            "first_name": "Igor",
            "last_name": "Filbert",
            "email": "igor.filbert@googlemail.com",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "gorris-duesseldorf.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@gorris-duesseldorf.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "gottfried-stenger.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@gottfried-stenger.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "gpp-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "r.polzer",
            "email": "r.polzer@gpp-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "greb-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@greb-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "greifswald.shbb.de": [
        {
            "first_name": "",
            "last_name": "j.borowitz",
            "email": "j.borowitz@greifswald.shbb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gres-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@gres-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "grimm-up.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@grimm-up.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "grohmann-partner.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@grohmann-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "grosseundpartner.de": [
        {
            "first_name": "",
            "last_name": "job",
            "email": "job@grosseundpartner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "grossmann-steuern.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@grossmann-steuern.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "gruenbaum-collegen.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@gruenbaum-collegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "gsk.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@gsk.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "gst-beratung.de": [
        {
            "first_name": "",
            "last_name": "elke.gaertner",
            "email": "elke.gaertner@gst-beratung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gtkp.de": [
        {
            "first_name": "",
            "last_name": "s.schmitz",
            "email": "s.schmitz@gtkp.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "guhr-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "anfrage",
            "email": "anfrage@guhr-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "gvr-tax.de": [
        {
            "first_name": "",
            "last_name": "e.vonrosenberg",
            "email": "e.vonrosenberg@gvr-tax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "gw-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@gw-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "gxglegal.com": [
        {
            "first_name": "",
            "last_name": "jennifer.werner",
            "email": "jennifer.werner@gxglegal.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "haag-stb.de": [
        {
            "first_name": "",
            "last_name": "volker.haag",
            "email": "volker.haag@haag-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "haerer-wp-stb.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@haerer-wp-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hahn-markert.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hahn-markert.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "haider.legal": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@haider.legal",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hama-immo.de": [
        {
            "first_name": "",
            "last_name": "claudia.rolle",
            "email": "claudia.rolle@hama-immo.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hannekum-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hannekum-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hansapartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hansapartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hansen-schulz.de": [
        {
            "first_name": "",
            "last_name": "k.mueller",
            "email": "k.mueller@hansen-schulz.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hanza.com": [
        {
            "first_name": "Michaela",
            "last_name": "Seitz-Rappen",
            "email": "michaela.seitz-rappen@hanza.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "haribo.com": [
        {
            "first_name": "Alica",
            "last_name": "Bierlich",
            "email": "alica.bierlich@haribo.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "hark.de": [
        {
            "first_name": "Friedrich",
            "last_name": "Petra",
            "email": "p.friedrich@hark.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "harpener-treuhand.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@harpener-treuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "harte-bavendamm.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@harte-bavendamm.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "harteis-partner.de": [
        {
            "first_name": "",
            "last_name": "info-fdb",
            "email": "info-fdb@harteis-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "info-sob",
            "email": "info-sob@harteis-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hauser-augsburg.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@hauser-augsburg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hbbn.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@hbbn.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "heckler-steuerkanzlei.de": [
        {
            "first_name": "Andreas (Steuerberater, Steuerkanzlei Heckler)",
            "last_name": "Heckler",
            "email": "andreas@heckler-steuerkanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "heimannundpartner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@heimannundpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "heitkamp-stb.de": [
        {
            "first_name": "",
            "last_name": "czeskleba",
            "email": "czeskleba@heitkamp-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "helmig-weber.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@helmig-weber.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hema-steuerberatung.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hema-steuerberatung.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "henneberger-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@henneberger-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hermesundpartner.de": [
        {
            "first_name": "Leila",
            "last_name": "H | P Fritz",
            "email": "leila.fritz@hermesundpartner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "herrmann-may.de": [
        {
            "first_name": "",
            "last_name": "buero",
            "email": "buero@herrmann-may.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "heuking.de": [
        {
            "first_name": "Heuking",
            "last_name": "Bewerbung",
            "email": "bewerbung@heuking.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "hf-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "Bewerbungen",
            "email": "bewerbungen@hf-steuerberatung.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "hhp-stb.de": [
        {
            "first_name": "",
            "last_name": "m.berges",
            "email": "m.berges@hhp-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hinnemann-graw.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hinnemann-graw.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hiring-force.com": [
        {
            "first_name": "",
            "last_name": "Bewerbermanagement",
            "email": "2b6f5e5f-5ff3-4de2-a62d-98d0f25784b7.conversations@hiring-force.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hitschler.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hitschler.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hk-recht.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@hk-recht.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hkm-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@hkm-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hlb-augsburg.eu": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hlb-augsburg.eu",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hnjp.de": [
        {
            "first_name": "",
            "last_name": "ana.stuermer",
            "email": "ana.stuermer@hnjp.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hnw-fulda.de": [
        {
            "first_name": "",
            "last_name": "buero",
            "email": "buero@hnw-fulda.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hoechstetter.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hoechstetter.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hoeffken.me": [
        {
            "first_name": "",
            "last_name": "benjamin",
            "email": "benjamin@hoeffken.me",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hoffmann-group.com": [
        {
            "first_name": "",
            "last_name": "recruiting",
            "email": "recruiting@hoffmann-group.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "honert.de": [
        {
            "first_name": "Jochen",
            "last_name": "Neumayer",
            "email": "j.neumayer@honert.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hotz-michaela.de": [
        {
            "first_name": "Michaela",
            "last_name": "Hotz",
            "email": "info@hotz-michaela.de",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "hotz-partner.de": [
        {
            "first_name": "",
            "last_name": "s.haerdter",
            "email": "s.haerdter@hotz-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hph.de": [
        {
            "first_name": "Katarina",
            "last_name": "Faryadova",
            "email": "katarina.faryadova@hph.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hs-muenchen-tax.de": [
        {
            "first_name": "Benjamin",
            "last_name": "Höfler",
            "email": "b.hoefler@hs-muenchen-tax.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "hsa-beratergruppe.de": [
        {
            "first_name": "Axel Hannemann | HSA",
            "last_name": "Beratergruppe",
            "email": "axel.hannemann@hsa-beratergruppe.de",
            "anzahl_mails": "9",
            "typ": "person",
        },
    ],
    "hsmv.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hsmv.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hsp-gmbb.de": [
        {
            "first_name": "",
            "last_name": "julia.schuschke",
            "email": "julia.schuschke@hsp-gmbb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hsp-steuer.de": [
        {
            "first_name": "",
            "last_name": "michael.bochenek",
            "email": "michael.bochenek@hsp-steuer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "donauwald",
            "email": "donauwald@hsp-steuer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "michael.huber",
            "email": "michael.huber@hsp-steuer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "hsppartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@hsppartner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hstax.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hstax.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hts-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hts-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hubert.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hubert.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hufnagel-rechtsanwaelte.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hufnagel-rechtsanwaelte.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "huget-dirks.de": [
        {
            "first_name": "",
            "last_name": "dirks",
            "email": "dirks@huget-dirks.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hup-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@hup-stb.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "husemannpartner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@husemannpartner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "hwp-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "freya.bockelmann",
            "email": "freya.bockelmann@hwp-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "hwpartner.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@hwpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "hws.de": [
        {
            "first_name": "",
            "last_name": "Karriere",
            "email": "karriere@hws.de",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "hzt-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "manfred.nagelschmidt",
            "email": "manfred.nagelschmidt@hzt-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ihre-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "hr",
            "email": "hr@ihre-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "imail.de": [
        {
            "first_name": "",
            "last_name": "patrick.hagner",
            "email": "patrick.hagner@imail.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "inatax.de": [
        {
            "first_name": "",
            "last_name": "steuerberater",
            "email": "steuerberater@inatax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "inbox.lv": [
        {
            "first_name": "",
            "last_name": "helmuts.viksna",
            "email": "helmuts.viksna@inbox.lv",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "infosys-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@infosys-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ingerop.de": [
        {
            "first_name": "",
            "last_name": "christina.westphal",
            "email": "christina.westphal@ingerop.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "intaria.eu": [
        {
            "first_name": "Kracylo",
            "last_name": "Christian",
            "email": "c.kracylo@intaria.eu",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "isar.tax": [
        {
            "first_name": "Susan Borggräfe | ISARTAX",
            "last_name": "GmbH",
            "email": "sborggraefe@isar.tax",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "iura.de": [
        {
            "first_name": "RAe Köpping Schwarze-Reiter Aichele Petrović",
            "last_name": "GbR",
            "email": "info@iura.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "jaekel-hoepner.de": [
        {
            "first_name": "",
            "last_name": "heike.hoepner",
            "email": "heike.hoepner@jaekel-hoepner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "jakob-geyer.de": [
        {
            "first_name": "",
            "last_name": "j.zeilhofer",
            "email": "j.zeilhofer@jakob-geyer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "jakoby-baumhof.de": [
        {
            "first_name": "Eugen",
            "last_name": "Jakoby",
            "email": "eugen.jakoby@jakoby-baumhof.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "eugen",
            "email": "eugen@jakoby-baumhof.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "jansenpartner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@jansenpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "jh-stbg.de": [
        {
            "first_name": "Anja",
            "last_name": "Ruck",
            "email": "a.ruck@jh-stbg.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "jobs.ebnerstolz.de": [
        {
            "first_name": "Sophie",
            "last_name": "Strunze",
            "email": "candidate-v79v79xw@jobs.ebnerstolz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "joerg-stb.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@joerg-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "jongen.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@jongen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "jp-steuerberaterin.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@jp-steuerberaterin.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "js-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "jesgarek",
            "email": "jesgarek@js-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "judithwilliams.com": [
        {
            "first_name": "",
            "last_name": "m.erhard",
            "email": "m.erhard@judithwilliams.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "juhn.com": [
        {
            "first_name": "",
            "last_name": "willkommen",
            "email": "willkommen@juhn.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "jurataxconsult.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@jurataxconsult.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "justtax.hamburg": [
        {
            "first_name": "Kristina",
            "last_name": "Smancer",
            "email": "kr@justtax.hamburg",
            "anzahl_mails": "7",
            "typ": "person",
        },
        {
            "first_name": "Tamin",
            "last_name": "Navabi",
            "email": "tn@justtax.hamburg",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kalus-winkelmann.de": [
        {
            "first_name": "",
            "last_name": "steuerb",
            "email": "steuerb@kalus-winkelmann.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kanzlei-baum.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-baum.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-bns.de": [
        {
            "first_name": "Hendrik",
            "last_name": "Hauschild",
            "email": "h.hauschild@kanzlei-bns.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "a.niebuhr",
            "email": "a.niebuhr@kanzlei-bns.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "mail.nordheide",
            "email": "mail.nordheide@kanzlei-bns.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kanzlei-drewitz.de": [
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@kanzlei-drewitz.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-drlang.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@kanzlei-drlang.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-fahn.de": [
        {
            "first_name": "",
            "last_name": "robert.fahn",
            "email": "robert.fahn@kanzlei-fahn.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "kanzlei-geilert.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-geilert.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-grigat.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-grigat.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kanzlei-gvs.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kanzlei-gvs.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kanzlei-hetsch.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-hetsch.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-hoeng.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-hoeng.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-hruby.de": [
        {
            "first_name": "",
            "last_name": "hruby",
            "email": "hruby@kanzlei-hruby.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kanzlei-hutter.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kanzlei-hutter.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-kudrass.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@kanzlei-kudrass.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kanzlei-lahser.de": [
        {
            "first_name": "",
            "last_name": "l.lahser",
            "email": "l.lahser@kanzlei-lahser.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kanzlei-obermeier.de": [
        {
            "first_name": "",
            "last_name": "om@kanzlei-obermeier.de",
            "email": "reinhold.obermeier@kanzlei-obermeier.de",
            "anzahl_mails": "188",
            "typ": "person",
        },
        {
            "first_name": "Medina",
            "last_name": "Idrizi",
            "email": "idrizi@kanzlei-obermeier.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "Elke Kronenberger - Kanzlei",
            "last_name": "Obermeier",
            "email": "kronenberger@kanzlei-obermeier.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kanzlei-rosner.net": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-rosner.net",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-spiess.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-spiess.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-thurner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-thurner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-witzel.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kanzlei-witzel.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzlei-zenz.de": [
        {
            "first_name": "Kanzlei",
            "last_name": "Zenz",
            "email": "w.zenz@kanzlei-zenz.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kanzleigruenhagen.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@kanzleigruenhagen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzleimaier.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kanzleimaier.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kanzleirausch.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kanzleirausch.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kanzleisiegen.de": [
        {
            "first_name": "",
            "last_name": "hello",
            "email": "hello@kanzleisiegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kapphan-partner.de": [
        {
            "first_name": "",
            "last_name": "j.kapphan",
            "email": "j.kapphan@kapphan-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "karin-henze.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@karin-henze.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kaspers-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@kaspers-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kastl-kollegen.com": [
        {
            "first_name": "Johannes",
            "last_name": "Hellfeier",
            "email": "hellfeier@kastl-kollegen.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "zech",
            "email": "zech@kastl-kollegen.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kattau-partner.de": [
        {
            "first_name": "",
            "last_name": "stb",
            "email": "stb@kattau-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kbl-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kbl-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kdk-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kdk-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "keller-menz.de": [
        {
            "first_name": "",
            "last_name": "joachim.menz",
            "email": "joachim.menz@keller-menz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kern-hess.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@kern-hess.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kess-partner.de": [
        {
            "first_name": "",
            "last_name": "j.kess",
            "email": "j.kess@kess-partner.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "kesslerundkern.de": [
        {
            "first_name": "Christina",
            "last_name": "Schaal",
            "email": "c.schaal@kesslerundkern.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "i.junginger",
            "email": "i.junginger@kesslerundkern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kfsp.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@kfsp.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kgoetz.com": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@kgoetz.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kgs-kanzlei.de": [
        {
            "first_name": "",
            "last_name": "claus.gossmann",
            "email": "claus.gossmann@kgs-kanzlei.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kgwb.de": [
        {
            "first_name": "",
            "last_name": "lena.oetterer",
            "email": "lena.oetterer@kgwb.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "kietruschat-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kietruschat-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kirinus.de": [
        {
            "first_name": "",
            "last_name": "alpenparkklinik",
            "email": "alpenparkklinik@kirinus.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kisslinger-popp.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kisslinger-popp.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "kittl-partner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kittl-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kkl-partner.de": [
        {
            "first_name": "Kummer Lein Partnerschaft",
            "last_name": "mbB",
            "email": "nicht_antworten@kkl-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kley.eu": [
        {
            "first_name": "Emily von Dr. Kley Steuerberater",
            "last_name": "Kleinhenz",
            "email": "emily.kleinhenz@kley.eu",
            "anzahl_mails": "9",
            "typ": "person",
        },
        {
            "first_name": "Martin von Dr. Kley Steuerberater",
            "last_name": "Fandrich",
            "email": "martin.fandrich@kley.eu",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "klingauf-stb.de": [
        {
            "first_name": "",
            "last_name": "klingauf",
            "email": "klingauf@klingauf-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "klingele-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@klingele-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "klinger-kollegen.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@klinger-kollegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "klinik-bavaria.de": [
        {
            "first_name": "",
            "last_name": "heidemarie.zenger",
            "email": "heidemarie.zenger@klinik-bavaria.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kliniken-koeln.de": [
        {
            "first_name": "",
            "last_name": "recruiting",
            "email": "recruiting@kliniken-koeln.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "klueh.de": [
        {
            "first_name": "",
            "last_name": "n.arnold",
            "email": "n.arnold@klueh.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "klugpartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@klugpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "klv-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "jan.kaup",
            "email": "jan.kaup@klv-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kmb-partner.de": [
        {
            "first_name": "",
            "last_name": "muenchen",
            "email": "muenchen@kmb-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kmp-gruppe.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kmp-gruppe.de",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "kmp-steuer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kmp-steuer.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kmpg.com": [
        {
            "first_name": "",
            "last_name": "recruiting",
            "email": "recruiting@kmpg.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kmpro-muc.de": [
        {
            "first_name": "Ursula Koch |",
            "last_name": "kmpro-muc",
            "email": "u.koch@kmpro-muc.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kms-steuern.de": [
        {
            "first_name": "Désirée",
            "last_name": "Dundic",
            "email": "dundic@kms-steuern.de",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "kochendoerfer-steuern.de": [
        {
            "first_name": "",
            "last_name": "kochendoerfer",
            "email": "kochendoerfer@kochendoerfer-steuern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "koettgen-hoerakustik.de": [
        {
            "first_name": "Job - Köttgen",
            "last_name": "Hörakustik",
            "email": "job@koettgen-hoerakustik.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "konlus.de": [
        {
            "first_name": "",
            "last_name": "ruth.clemens",
            "email": "ruth.clemens@konlus.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kontax.de": [
        {
            "first_name": "",
            "last_name": "jelena.boehm",
            "email": "jelena.boehm@kontax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "koppenhoefer-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "zentrale",
            "email": "zentrale@koppenhoefer-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kostundpartner.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@kostundpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kpmg.com": [
        {
            "first_name": "DE-FM HR",
            "last_name": "Recruiting",
            "email": "recruiting@kpmg.com",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "kraft-meister.de": [
        {
            "first_name": "",
            "last_name": "a.meister",
            "email": "a.meister@kraft-meister.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "krieger.eu": [
        {
            "first_name": "",
            "last_name": "bewerber",
            "email": "bewerber@krieger.eu",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "krinninger.net": [
        {
            "first_name": "",
            "last_name": "birgit",
            "email": "birgit@krinninger.net",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "kroenke-stb.de": [
        {
            "first_name": "",
            "last_name": "berufung",
            "email": "berufung@kroenke-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ksc-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@ksc-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ksk-koeln.de": [
        {
            "first_name": "",
            "last_name": "aysun.saiz",
            "email": "aysun.saiz@ksk-koeln.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ksp.tax": [
        {
            "first_name": "Julia | KSP",
            "last_name": "Milles",
            "email": "jmilles@ksp.tax",
            "anzahl_mails": "20",
            "typ": "person",
        },
    ],
    "ksw-legal.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@ksw-legal.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "Kundenbetreuung",
            "email": "info@ksw-legal.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ktm-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@ktm-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "kuepper-kollegen.com": [
        {
            "first_name": "",
            "last_name": "bewerber",
            "email": "bewerber@kuepper-kollegen.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "kuepper-kollegen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@kuepper-kollegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
        {
            "first_name": "Sekretariat",
            "last_name": "Küpper & Kollegen",
            "email": "sekretariat@kuepper-kollegen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kuhn-elektro.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@kuhn-elektro.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kuhn-steuerkanzlei.de": [
        {
            "first_name": "",
            "last_name": "nfo",
            "email": "nfo@kuhn-steuerkanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "kuhnpartner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@kuhnpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "kupka-stillfried.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@kupka-stillfried.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "lacoste-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "lacoste",
            "email": "lacoste@lacoste-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "ladm.com": [
        {
            "first_name": "",
            "last_name": "muenster",
            "email": "muenster@ladm.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lange-stb-zeven.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lange-stb-zeven.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "laubengaier.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@laubengaier.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "lauterbach-boehnlein.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lauterbach-boehnlein.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lbh.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@lbh.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "lctax.de": [
        {
            "first_name": "Bewerbung - LOHR + COMPANY",
            "last_name": "GmbH",
            "email": "bewerbung@lctax.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "lehleiter.de": [
        {
            "first_name": "Bewerbung Lehleiter +",
            "last_name": "Partner",
            "email": "bewerbung@lehleiter.de",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "leisnernet.com": [
        {
            "first_name": "",
            "last_name": "Sekretariat",
            "email": "sekretariat@leisnernet.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lemmermann.info": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lemmermann.info",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "lerdon.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@lerdon.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "leuthaeuser-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@leuthaeuser-partner.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "lexmuc.com": [
        {
            "first_name": "",
            "last_name": "loeffler",
            "email": "loeffler@lexmuc.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lfkvs.de": [
        {
            "first_name": "Janine",
            "last_name": "Rall",
            "email": "janine.rall@lfkvs.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "lgg-steuer-karriere.dvinci-hr.com": [
        {
            "first_name": "Personalabteilung | LGG Steuerberatungsgesellschaft",
            "last_name": "mbH",
            "email": "candidate-fm58p74y@lgg-steuer-karriere.dvinci-hr.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "libero.it": [
        {
            "first_name": "",
            "last_name": "christine.pichler",
            "email": "christine.pichler@libero.it",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "liebhart-kollegen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@liebhart-kollegen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lieske-stb.de": [
        {
            "first_name": "",
            "last_name": "d.vossen",
            "email": "d.vossen@lieske-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lindemann-pannemann.de": [
        {
            "first_name": "",
            "last_name": "kotte",
            "email": "kotte@lindemann-pannemann.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "linngoppold.de": [
        {
            "first_name": "Jasmin",
            "last_name": "Kühne",
            "email": "j.kuehne@linngoppold.de",
            "anzahl_mails": "135",
            "typ": "person",
        },
        {
            "first_name": "Linn Goppold -",
            "last_name": "Kanzlei",
            "email": "kanzlei@linngoppold.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "lippert-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lippert-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lkc.de": [
        {
            "first_name": "",
            "last_name": "ivonne.kucfir",
            "email": "ivonne.kucfir@lkc.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "sandra.goettig",
            "email": "sandra.goettig@lkc.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "lkc-personalgw",
            "email": "lkc-personalgw@lkc.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lkm-lawtax.com": [
        {
            "first_name": "Tamara",
            "last_name": "Kamseder",
            "email": "kamseder@lkm-lawtax.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "llp-kanzlei.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@llp-kanzlei.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lmat.de": [
        {
            "first_name": "",
            "last_name": "rebmann",
            "email": "rebmann@lmat.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "loeba.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@loeba.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "loehr-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "Kanzlei",
            "email": "kanzlei@loehr-steuerberatung.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "logivest.de": [
        {
            "first_name": "Claudia",
            "last_name": "Pröls",
            "email": "claudia.proels@logivest.de",
            "anzahl_mails": "36",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "alice.stumm",
            "email": "alice.stumm@logivest.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lohfink-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lohfink-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "lowellgroup.de": [
        {
            "first_name": "HR Recruiting",
            "last_name": "DACH",
            "email": "hr-recruiting-dach@lowellgroup.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "donotreply.postmaster",
            "email": "donotreply.postmaster@lowellgroup.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lphl.de": [
        {
            "first_name": "Alexander",
            "last_name": "Neutz",
            "email": "neutz@lphl.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "lps-steuerberater.de": [
        {
            "first_name": "Fridolin",
            "last_name": "Lehmann",
            "email": "fridolin.lehmann@lps-steuerberater.de",
            "anzahl_mails": "16",
            "typ": "person",
        },
        {
            "first_name": "Antonia",
            "last_name": "Lehmann",
            "email": "antonia.lehmann@lps-steuerberater.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "lsm-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@lsm-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ludwig-epp.de": [
        {
            "first_name": "",
            "last_name": "zentrale",
            "email": "zentrale@ludwig-epp.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "ludwig-reichert.de": [
        {
            "first_name": "Ludwig",
            "last_name": "Reichert",
            "email": "reichert@ludwig-reichert.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "lupp-partner.com": [
        {
            "first_name": "Recruiting",
            "last_name": "Postfach",
            "email": "recruiting@lupp-partner.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "luther-lawfirm.com": [
        {
            "first_name": "",
            "last_name": "daniel.piontzik",
            "email": "daniel.piontzik@luther-lawfirm.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "lutz-brauckhoff.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@lutz-brauckhoff.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lutzabel.com": [
        {
            "first_name": "Lutz | Abel",
            "last_name": "Bewerbung",
            "email": "bewerbung@lutzabel.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "lwbintax.de": [
        {
            "first_name": "",
            "last_name": "mahmud.abutaleb",
            "email": "mahmud.abutaleb@lwbintax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "stefan.reichhold",
            "email": "stefan.reichhold@lwbintax.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "lzs.de": [
        {
            "first_name": "",
            "last_name": "bewerben",
            "email": "bewerben@lzs.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "m.personio.com": [
        {
            "first_name": "Erna",
            "last_name": "Grahic",
            "email": "kwpartners-jobs@m.personio.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "m.personio.de": [
        {
            "first_name": "Carmen",
            "last_name": "Müller",
            "email": "pkf-wulf-gruppe-jobs@m.personio.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "poellath-rechtsanwaelte-jobs",
            "email": "poellath-rechtsanwaelte-jobs@m.personio.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "madlung.org": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@madlung.org",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "maegerle.de": [
        {
            "first_name": "",
            "last_name": "daniel.waldraff",
            "email": "daniel.waldraff@maegerle.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mailbox.org": [
        {
            "first_name": "Julia",
            "last_name": "Briede",
            "email": "j.briede@mailbox.org",
            "anzahl_mails": "33",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "inga.jan",
            "email": "inga.jan@mailbox.org",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "main-auditors.com": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@main-auditors.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "maintreuhand.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@maintreuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "maklerrecht-muenchen.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@maklerrecht-muenchen.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "markmiller-und-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@markmiller-und-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "marten-hamburg.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@marten-hamburg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "matenaar-partner.de": [
        {
            "first_name": "",
            "last_name": "steuerberater",
            "email": "steuerberater@matenaar-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "mathias-und-partner.de": [
        {
            "first_name": "",
            "last_name": "lydia.scheurer",
            "email": "lydia.scheurer@mathias-und-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mattern-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@mattern-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "mayer-kohler.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@mayer-kohler.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "mazars.de": [
        {
            "first_name": "Anja",
            "last_name": "Staffe",
            "email": "anja.staffe@mazars.de",
            "anzahl_mails": "8",
            "typ": "person",
        },
        {
            "first_name": "Nils",
            "last_name": "Maciossek",
            "email": "nils.maciossek@mazars.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "andela.stamenkovic",
            "email": "andela.stamenkovic@mazars.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "menoldbezler.de": [
        {
            "first_name": "Kim-Alena",
            "last_name": "Marx",
            "email": "kim-alena.marx@menoldbezler.de",
            "anzahl_mails": "58",
            "typ": "person",
        },
        {
            "first_name": "Selina",
            "last_name": "Berger",
            "email": "selina.berger@menoldbezler.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "corinna.schauer",
            "email": "corinna.schauer@menoldbezler.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "merkur-privatbank.de": [
        {
            "first_name": "",
            "last_name": "autoreply",
            "email": "autoreply@merkur-privatbank.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "merz-herrmann.de": [
        {
            "first_name": "",
            "last_name": "alexander.herrmann",
            "email": "alexander.herrmann@merz-herrmann.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "merzenich.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@merzenich.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "metschkoll.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@metschkoll.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "meypa.de": [
        {
            "first_name": "",
            "last_name": "stefanie.stoehr",
            "email": "stefanie.stoehr@meypa.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "silke.titel",
            "email": "silke.titel@meypa.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mg.workwise.io": [
        {
            "first_name": "",
            "last_name": "status-update=workwise.io",
            "email": "status-update=workwise.io@mg.workwise.io",
            "anzahl_mails": "7",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "support=workwise.io",
            "email": "support=workwise.io@mg.workwise.io",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "karina.neidig=workwise.io",
            "email": "karina.neidig=workwise.io@mg.workwise.io",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mgmm.workwise.io": [
        {
            "first_name": "",
            "last_name": "talent.team=workwise.io",
            "email": "talent.team=workwise.io@mgmm.workwise.io",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "mgp-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@mgp-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "mhl.de": [
        {
            "first_name": "",
            "last_name": "hamburg",
            "email": "hamburg@mhl.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "mks.com": [
        {
            "first_name": "Lynn",
            "last_name": "Basel",
            "email": "lynn.basel@mks.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "mm-karton.com": [
        {
            "first_name": "",
            "last_name": "mxs.postmaster",
            "email": "mxs.postmaster@mm-karton.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "moennighoff.com": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@moennighoff.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "moenus-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@moenus-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "moore-intaria.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@moore-intaria.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "morstatt.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@morstatt.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "msc-steuern.de": [
        {
            "first_name": "",
            "last_name": "m.staykova",
            "email": "m.staykova@msc-steuern.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mtrlegal.com": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@mtrlegal.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mueller-stbkanzlei.de": [
        {
            "first_name": "",
            "last_name": "n.mueller",
            "email": "n.mueller@mueller-stbkanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mueller-stuber.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@mueller-stuber.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "mueller-wp-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@mueller-wp-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "muellergroup.com": [
        {
            "first_name": "",
            "last_name": "julia.meichelboeck",
            "email": "julia.meichelboeck@muellergroup.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "muellerstb.eu": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@muellerstb.eu",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "muenchner-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@muenchner-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "muth-partner.de": [
        {
            "first_name": "Anna [Muth & Partner mbB]",
            "last_name": "Sorg",
            "email": "anna.sorg@muth-partner.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "muth-treuhand.com": [
        {
            "first_name": "",
            "last_name": "thomas.muth",
            "email": "thomas.muth@muth-treuhand.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "mwe.com": [
        {
            "first_name": "",
            "last_name": "recruiting-germany",
            "email": "recruiting-germany@mwe.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "nbs-partners.de": [
        {
            "first_name": "",
            "last_name": "Karriere",
            "email": "karriere@nbs-partners.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "neo-kanzlei.de": [
        {
            "first_name": "",
            "last_name": "deggendorf",
            "email": "deggendorf@neo-kanzlei.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "sophia.wunderlich",
            "email": "sophia.wunderlich@neo-kanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "neppe-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "s.neppe",
            "email": "s.neppe@neppe-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "netcologne.de": [
        {
            "first_name": "",
            "last_name": "schmitz2627",
            "email": "schmitz2627@netcologne.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "neuhauser-kanzlei.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@neuhauser-kanzlei.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "neuner-steuerkanzlei.de": [
        {
            "first_name": "Birgit",
            "last_name": "Neuner Steuerkanzlei - Neuner",
            "email": "birgit.neuner@neuner-steuerkanzlei.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "nexia.com": [
        {
            "first_name": "",
            "last_name": "sabine.raith",
            "email": "sabine.raith@nexia.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "nexia.de": [
        {
            "first_name": "Tobias",
            "last_name": "Tümler",
            "email": "tobias.tuemler@nexia.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "kerstin.kluth",
            "email": "kerstin.kluth@nexia.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "niedermaier-partner.de": [
        {
            "first_name": "",
            "last_name": "marco.niedermaier",
            "email": "marco.niedermaier@niedermaier-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "niederrhein-gold.de": [
        {
            "first_name": "",
            "last_name": "Bewerbung",
            "email": "bewerbung@niederrhein-gold.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "noerr.com": [
        {
            "first_name": "Claudia",
            "last_name": "Olthoff",
            "email": "claudia.olthoff@noerr.com",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "noll-voss.de": [
        {
            "first_name": "",
            "last_name": "voss",
            "email": "voss@noll-voss.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "nos-steuerkanzlei.de": [
        {
            "first_name": "Elke",
            "last_name": "Osenau",
            "email": "e.osenau@nos-steuerkanzlei.de",
            "anzahl_mails": "14",
            "typ": "person",
        },
        {
            "first_name": "Wilhelm",
            "last_name": "Osenau",
            "email": "w.osenau@nos-steuerkanzlei.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "notax.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@notax.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "nti-nanofilm.com": [
        {
            "first_name": "",
            "last_name": "john.ooi",
            "email": "john.ooi@nti-nanofilm.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ntsw.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@ntsw.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "o2online.de": [
        {
            "first_name": "Thomas",
            "last_name": "Vogelsang",
            "email": "thomas.vogelsang@o2online.de",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "oehler-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "beratung",
            "email": "beratung@oehler-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "Wolfgang",
            "last_name": "Oehler",
            "email": "wolfgang.oehler@oehler-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "oetje.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@oetje.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ohland-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ohland-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "omnitax.de": [
        {
            "first_name": "",
            "last_name": "steuerberater",
            "email": "steuerberater@omnitax.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "online.de": [
        {
            "first_name": "",
            "last_name": "martin.schulz.llm",
            "email": "martin.schulz.llm@online.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "marita.birukov",
            "email": "marita.birukov@online.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "optadata-gruppe.de": [
        {
            "first_name": "",
            "last_name": "l.sinning",
            "email": "l.sinning@optadata-gruppe.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "j.schulte",
            "email": "j.schulte@optadata-gruppe.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "os-partner.de": [
        {
            "first_name": "",
            "last_name": "olsen",
            "email": "olsen@os-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ossig-online.de": [
        {
            "first_name": "",
            "last_name": "sabrina.hartung",
            "email": "sabrina.hartung@ossig-online.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ott-partner.de": [
        {
            "first_name": "",
            "last_name": "link",
            "email": "link@ott-partner.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "pandion.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@pandion.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "pantfoerder-partner.de": [
        {
            "first_name": "Christopher",
            "last_name": "Damnitz",
            "email": "christopher.damnitz@pantfoerder-partner.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "pape-co.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@pape-co.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "pdb-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@pdb-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "peters-wellpappe.de": [
        {
            "first_name": "Wellkistenfabrik Fritz Peters GmbH &",
            "last_name": "Co.KG",
            "email": "bewerbung@peters-wellpappe.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "phantasialand.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@phantasialand.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "phereclus.com": [
        {
            "first_name": "",
            "last_name": "z.akpinarli",
            "email": "z.akpinarli@phereclus.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "z.akpinali",
            "email": "z.akpinali@phereclus.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "philipp-baehrle.de": [
        {
            "first_name": "",
            "last_name": "michael.baehrle",
            "email": "michael.baehrle@philipp-baehrle.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "pickelundpartner.de": [
        {
            "first_name": "",
            "last_name": "kanzleimanagement",
            "email": "kanzleimanagement@pickelundpartner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "pieper-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@pieper-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "pkf-engelhardt.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@pkf-engelhardt.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "pkf-fasselt.de": [
        {
            "first_name": "Hannah",
            "last_name": "Raab",
            "email": "hannah.raab@pkf-fasselt.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "pkf-ifp.de": [
        {
            "first_name": "Beck Dr.",
            "last_name": "Kilian",
            "email": "kilian.beck@pkf-ifp.de",
            "anzahl_mails": "7",
            "typ": "person",
        },
        {
            "first_name": "Reichert",
            "last_name": "Jochen",
            "email": "jochen.reichert@pkf-ifp.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "pkf-wulf.de": [
        {
            "first_name": "Karriere | PKF WULF",
            "last_name": "GRUPPE",
            "email": "karriere@pkf-wulf.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "pks-stahl.com": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@pks-stahl.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "planaris.de": [
        {
            "first_name": "",
            "last_name": "Personal",
            "email": "personal@planaris.de",
            "anzahl_mails": "5",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@planaris.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "plininger.org": [
        {
            "first_name": "Albert",
            "last_name": "Plininger",
            "email": "a.plininger@plininger.org",
            "anzahl_mails": "18",
            "typ": "person",
        },
        {
            "first_name": "Maximilian",
            "last_name": "Leebmann",
            "email": "m.leebmann@plininger.org",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "plpartner.de": [
        {
            "first_name": "Daniel Prause",
            "last_name": "(PLP)",
            "email": "prause@plpartner.de",
            "anzahl_mails": "10",
            "typ": "person",
        },
        {
            "first_name": "Ute Linck",
            "last_name": "(PLP)",
            "email": "linck@plpartner.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "pmpg.de": [
        {
            "first_name": "Gabriele",
            "last_name": "Fink",
            "email": "gabriele.fink@pmpg.de",
            "anzahl_mails": "26",
            "typ": "person",
        },
    ],
    "pohl-heinl.de": [
        {
            "first_name": "",
            "last_name": "mpohl",
            "email": "mpohl@pohl-heinl.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "pontes-partner.de": [
        {
            "first_name": "Pawel",
            "last_name": "Blusz",
            "email": "p.blusz@pontes-partner.de",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "porten-stb.de": [
        {
            "first_name": "",
            "last_name": "c.porten",
            "email": "c.porten@porten-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "pplaw.com": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@pplaw.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@pplaw.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "preusche.org": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@preusche.org",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "preuss-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@preuss-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "prey-beheim.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@prey-beheim.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "prosiebensat1.com": [
        {
            "first_name": "ProSiebenSat.1",
            "last_name": "Career",
            "email": "career@prosiebensat1.com",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "proton-mail.com": [
        {
            "first_name": "",
            "last_name": "denise.mensch",
            "email": "denise.mensch@proton-mail.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "proton.com": [
        {
            "first_name": "",
            "last_name": "denise.mensch",
            "email": "denise.mensch@proton.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "denisemensch",
            "email": "denisemensch@proton.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "proton.de": [
        {
            "first_name": "",
            "last_name": "denise.mensch",
            "email": "denise.mensch@proton.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "proton.me": [
        {
            "first_name": "",
            "last_name": "denise.mensch",
            "email": "denise.mensch@proton.me",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "psp.eu": [
        {
            "first_name": "Sanita",
            "last_name": "Güldner",
            "email": "s.gueldner@psp.eu",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "psw-online.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@psw-online.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "puels.legal": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@puels.legal",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "pwc.com": [
        {
            "first_name": "Edgar Parra",
            "last_name": "(DE)",
            "email": "edgar.parra@pwc.com",
            "anzahl_mails": "21",
            "typ": "person",
        },
        {
            "first_name": "DE headhunting",
            "last_name": "MBX",
            "email": "de_headhunting@pwc.com",
            "anzahl_mails": "11",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "ines.wallenwein",
            "email": "ines.wallenwein@pwc.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "pz-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "zehnle",
            "email": "zehnle@pz-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "quabeck-gmbh.de": [
        {
            "first_name": "",
            "last_name": "h.glaeske",
            "email": "h.glaeske@quabeck-gmbh.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "quabeck-partner.de": [
        {
            "first_name": "",
            "last_name": "m.quabeck",
            "email": "m.quabeck@quabeck-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ra-decker-kollegen.de": [
        {
            "first_name": "",
            "last_name": "mantke",
            "email": "mantke@ra-decker-kollegen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "radrwieland.de": [
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@radrwieland.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rahn-wp.de": [
        {
            "first_name": "",
            "last_name": "luis.rahn",
            "email": "luis.rahn@rahn-wp.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rank.ag": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@rank.ag",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "raue.com": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@raue.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "raw-partner.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@raw-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "rbb-wp.de": [
        {
            "first_name": "",
            "last_name": "Bewerbung",
            "email": "bewerbung@rbb-wp.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "re-visio.com": [
        {
            "first_name": "",
            "last_name": "applications",
            "email": "applications@re-visio.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "reber-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@reber-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "recruitee-mail.com": [
        {
            "first_name": "",
            "last_name": "e+kvbpbh2mrsgukh96.rosenschonpartner",
            "email": "e+kvbpbh2mrsgukh96.rosenschonpartner@recruitee-mail.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "recruitee-mailbox.com": [
        {
            "first_name": "",
            "last_name": "e+2tv97lncgk4v9nl2.leibleinundkollegen",
            "email": "e+2tv97lncgk4v9nl2.leibleinundkollegen@recruitee-mailbox.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "redeker.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@redeker.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "redonis.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@redonis.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "reichl-vetter.de": [
        {
            "first_name": "",
            "last_name": "s.reichl",
            "email": "s.reichl@reichl-vetter.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "reinhardt-partner.de": [
        {
            "first_name": "",
            "last_name": "thomas.reinhardt",
            "email": "thomas.reinhardt@reinhardt-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "remondis.de": [
        {
            "first_name": "Sarah",
            "last_name": "Schiemann",
            "email": "sarah.schiemann@remondis.de",
            "anzahl_mails": "11",
            "typ": "person",
        },
    ],
    "renzundpartner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@renzundpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "reuber-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@reuber-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "revisa-treuhand.de": [
        {
            "first_name": "Oliver",
            "last_name": "Zachow",
            "email": "oliver.zachow@revisa-treuhand.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "rfe-steuerberatung.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@rfe-steuerberatung.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rgj.de": [
        {
            "first_name": "",
            "last_name": "reinhardt",
            "email": "reinhardt@rgj.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rgtgroup.de": [
        {
            "first_name": "",
            "last_name": "r.sarif-benner",
            "email": "r.sarif-benner@rgtgroup.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rhein-sieg-treuhand.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@rhein-sieg-treuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "rheinsteuer.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@rheinsteuer.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "rhenag.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@rhenag.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rhs-muenchen.de": [
        {
            "first_name": "",
            "last_name": "buchner",
            "email": "buchner@rhs-muenchen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "richter-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@richter-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "richtersteuerberater.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@richtersteuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "rieger-traenkle.de": [
        {
            "first_name": "",
            "last_name": "rt",
            "email": "rt@rieger-traenkle.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "Ricarda",
            "last_name": "Kodet",
            "email": "rk@rieger-traenkle.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rise-partners.de": [
        {
            "first_name": "",
            "last_name": "stefanie.koelen",
            "email": "stefanie.koelen@rise-partners.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "stefanie",
            "email": "stefanie@rise-partners.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ritter-treuhand.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ritter-treuhand.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rl-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@rl-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rnhs.de": [
        {
            "first_name": "Florian",
            "last_name": "Seemüller",
            "email": "florian.seemueller@rnhs.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "bogenhausen",
            "email": "bogenhausen@rnhs.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "roedl.com": [
        {
            "first_name": "Anna",
            "last_name": "Meyer",
            "email": "anna.meyer@roedl.com",
            "anzahl_mails": "6",
            "typ": "person",
        },
        {
            "first_name": "Sophia",
            "last_name": "Frank",
            "email": "sophia.frank@roedl.com",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "roedle-kempf.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@roedle-kempf.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "roggelin.de": [
        {
            "first_name": "",
            "last_name": "stefan.engelhardt",
            "email": "stefan.engelhardt@roggelin.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "rohlmann-consulting.de": [
        {
            "first_name": "Helena Funk | Rohlmann",
            "last_name": "Steuerberatung",
            "email": "funk@rohlmann-consulting.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rohm-stb.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@rohm-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rohr-stb.de": [
        {
            "first_name": "Jochen Rohr - Rohr",
            "last_name": "Steuerberatungsgesellschaft",
            "email": "jochen.rohr@rohr-stb.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "rosepartner.de": [
        {
            "first_name": "Helge  | ROSE & PARTNER",
            "last_name": "Schubert",
            "email": "schubert@rosepartner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "roth-partner-steuern.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@roth-partner-steuern.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "rothacker-steuerberater.de": [
        {
            "first_name": "Ole",
            "last_name": "Schleicher",
            "email": "ole.schleicher@rothacker-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rothmann-dietrich.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@rothmann-dietrich.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rotorcomp.de": [
        {
            "first_name": "Andreas",
            "last_name": "Huber",
            "email": "a.huber@rotorcomp.de",
            "anzahl_mails": "28",
            "typ": "person",
        },
    ],
    "roxin.de": [
        {
            "first_name": "",
            "last_name": "muenchen",
            "email": "muenchen@roxin.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "rp-steuerberater.com": [
        {
            "first_name": "",
            "last_name": "jan.radloff",
            "email": "jan.radloff@rp-steuerberater.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "rpsite.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@rpsite.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rpt-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@rpt-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rueterpartner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@rueterpartner.de",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "ruetten-stb.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@ruetten-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rugefehsenfeld.de": [
        {
            "first_name": "",
            "last_name": "a.koenig",
            "email": "a.koenig@rugefehsenfeld.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "a.volkmann",
            "email": "a.volkmann@rugefehsenfeld.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "rwf-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@rwf-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "rwp-vs.de": [
        {
            "first_name": "",
            "last_name": "buero",
            "email": "buero@rwp-vs.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "rzup.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@rzup.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "s-h-partner.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@s-h-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "sachtje-speck.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@sachtje-speck.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "sah-kanzlei.de": [
        {
            "first_name": "",
            "last_name": "info-muc",
            "email": "info-muc@sah-kanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "sak-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@sak-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "sasse-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "t.sasse",
            "email": "t.sasse@sasse-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "sauersteuer.de": [
        {
            "first_name": "",
            "last_name": "stefan.sauer",
            "email": "stefan.sauer@sauersteuer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "scf.gmbh": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@scf.gmbh",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schaffenberger.de": [
        {
            "first_name": "SCHAFFENBERGER",
            "last_name": "Jobs",
            "email": "jobs@schaffenberger.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schardt-stb.de": [
        {
            "first_name": "Malte Johann",
            "last_name": "Schardt",
            "email": "kanzlei@schardt-stb.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "schemmel-merk.de": [
        {
            "first_name": "",
            "last_name": "muenchen",
            "email": "muenchen@schemmel-merk.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "schienle-kollegen.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@schienle-kollegen.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "schillinggruppe.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@schillinggruppe.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schimmel.co": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@schimmel.co",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schirmer-guenther.de": [
        {
            "first_name": "",
            "last_name": "schirmer",
            "email": "schirmer@schirmer-guenther.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "schlecht-partner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@schlecht-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@schlecht-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schmaltz-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@schmaltz-partner.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "schmid-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@schmid-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schmidt-boos.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@schmidt-boos.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "schmidt-vogt.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@schmidt-vogt.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schmidtkarstens.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@schmidtkarstens.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schmitzpartner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@schmitzpartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "scholl-partner.de": [
        {
            "first_name": "Stefanie",
            "last_name": "Wiedemann",
            "email": "sw@scholl-partner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "schomerus.de": [
        {
            "first_name": "",
            "last_name": "diana.brnjic",
            "email": "diana.brnjic@schomerus.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "schorde.com": [
        {
            "first_name": "Sebastian",
            "last_name": "Schorde",
            "email": "sebastian@schorde.com",
            "anzahl_mails": "4",
            "typ": "person",
        },
    ],
    "schott-koeller.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@schott-koeller.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schrader-stb.de": [
        {
            "first_name": "",
            "last_name": "Info",
            "email": "info@schrader-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schrattenberger-partner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@schrattenberger-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schroederundpartner.berlin": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@schroederundpartner.berlin",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schuelergarten.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@schuelergarten.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "schuermanngmbh.de": [
        {
            "first_name": "Dirk",
            "last_name": "Schürmann",
            "email": "d.schuermann@schuermanngmbh.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "schwarz-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@schwarz-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "schwarz-steuer.de": [
        {
            "first_name": "Raphael",
            "last_name": "Schwarz",
            "email": "raphael.schwarz@schwarz-steuer.de",
            "anzahl_mails": "28",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "rschwarz",
            "email": "rschwarz@schwarz-steuer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "schweiger-bschor.de": [
        {
            "first_name": "",
            "last_name": "b.stauber",
            "email": "b.stauber@schweiger-bschor.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "schweizer-steuerberater.com": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@schweizer-steuerberater.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "scutum-stb.de": [
        {
            "first_name": "",
            "last_name": "monika.harpaintner",
            "email": "monika.harpaintner@scutum-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "senzera.com": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@senzera.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "seufert-law.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@seufert-law.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "sgptax.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@sgptax.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "shadow.outlook.com": [
        {
            "first_name": "",
            "last_name": "lukas.bergmann@commandeurconsulting.de",
            "email": (
                "6b7c3e89def9dda68cb73deec37df2c0a89c26613e7ccb14f8b5996c3df35bc1"
                "@shadow.outlook.com"
            ),
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "shp-beratergruppe.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@shp-beratergruppe.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "shp.tax": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@shp.tax",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "siegert-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@siegert-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "siegfriedkiener.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@siegfriedkiener.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "simon-rabieh.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@simon-rabieh.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "simon-und-partner.de": [
        {
            "first_name": "",
            "last_name": "n.gutzwiller",
            "email": "n.gutzwiller@simon-und-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "sk-berater.com": [
        {
            "first_name": "",
            "last_name": "Karriere",
            "email": "karriere@sk-berater.com",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "sk-steuer.de": [
        {
            "first_name": "",
            "last_name": "beratung",
            "email": "beratung@sk-steuer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "skb-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "schroeter",
            "email": "schroeter@skb-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "skb-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@skb-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "skn.partners": [
        {
            "first_name": "Jennifer",
            "last_name": "Schallert",
            "email": "karriere@skn.partners",
            "anzahl_mails": "12",
            "typ": "generic",
        },
    ],
    "sks-stb.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@sks-stb.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "skt.tax": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@skt.tax",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "slbw-kanzlei.de": [
        {
            "first_name": "Andreas",
            "last_name": "Struß",
            "email": "andreas.struss@slbw-kanzlei.de",
            "anzahl_mails": "59",
            "typ": "person",
        },
        {
            "first_name": "Katharina",
            "last_name": "Krauß",
            "email": "katharina.krauss@slbw-kanzlei.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "stb",
            "email": "stb@slbw-kanzlei.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "slbw-rae.de": [
        {
            "first_name": "Celina",
            "last_name": "Eberle",
            "email": "celina.eberle@slbw-rae.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "soe-partner.de": [
        {
            "first_name": "SOE",
            "last_name": "Partner",
            "email": "karriere@soe-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "sonntag-partner.de": [
        {
            "first_name": "Klotz",
            "last_name": "Tamara",
            "email": "tamara.klotz@sonntag-partner.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "soeren.keller",
            "email": "soeren.keller@sonntag-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "sozietaet-dortmund.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@sozietaet-dortmund.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "sozietaet-recklinghausen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@sozietaet-recklinghausen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "sp-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@sp-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "spaeth-schneider.de": [
        {
            "first_name": "",
            "last_name": "cornelia.wiethoff",
            "email": "cornelia.wiethoff@spaeth-schneider.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "spkgruppe.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@spkgruppe.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "ssup.de": [
        {
            "first_name": "",
            "last_name": "aberndt",
            "email": "aberndt@ssup.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stachpartner.de": [
        {
            "first_name": "",
            "last_name": "hannes.stach",
            "email": "hannes.stach@stachpartner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stadt.leverkusen.de": [
        {
            "first_name": "",
            "last_name": "marc.kellmann",
            "email": "marc.kellmann@stadt.leverkusen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "staudinger-stb.de": [
        {
            "first_name": "",
            "last_name": "kathi.staudinger",
            "email": "kathi.staudinger@staudinger-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-afg.de": [
        {
            "first_name": "",
            "last_name": "graewer",
            "email": "graewer@stb-afg.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-ammon.de": [
        {
            "first_name": "",
            "last_name": "ammon",
            "email": "ammon@stb-ammon.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-ankele.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-ankele.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-aust.de": [
        {
            "first_name": "",
            "last_name": "empfang",
            "email": "empfang@stb-aust.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stb-baechle.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-baechle.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-baitz.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-baitz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-baran.de": [
        {
            "first_name": "Tolga",
            "last_name": "Baran",
            "email": "atb@stb-baran.de",
            "anzahl_mails": "17",
            "typ": "person",
        },
    ],
    "stb-bdm.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-bdm.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-bischof.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-bischof.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-blesch.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-blesch.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-busch.de": [
        {
            "first_name": "Peter",
            "last_name": "Busch",
            "email": "busch@stb-busch.de",
            "anzahl_mails": "9",
            "typ": "person",
        },
    ],
    "stb-clausen.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-clausen.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-cp.de": [
        {
            "first_name": "",
            "last_name": "corinna.prause",
            "email": "corinna.prause@stb-cp.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-denk.de": [
        {
            "first_name": "",
            "last_name": "a.denk",
            "email": "a.denk@stb-denk.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-deubert.de": [
        {
            "first_name": "Andreas",
            "last_name": "Deubert",
            "email": "kanzlei@stb-deubert.de",
            "anzahl_mails": "26",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "m.vinci",
            "email": "m.vinci@stb-deubert.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-doepp.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-doepp.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-draeger.de": [
        {
            "first_name": "Janine",
            "last_name": "Draeger",
            "email": "jdraeger@stb-draeger.de",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "stb-evers-fuhrmann.de": [
        {
            "first_name": "Stefanie",
            "last_name": "Schittek",
            "email": "sschittek@stb-evers-fuhrmann.de",
            "anzahl_mails": "7",
            "typ": "person",
        },
    ],
    "stb-friemel.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-friemel.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-gaertner-sahm.de": [
        {
            "first_name": "Daniel",
            "last_name": "Sahm",
            "email": "daniel.sahm@stb-gaertner-sahm.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-gerards.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-gerards.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-gertz.de": [
        {
            "first_name": "",
            "last_name": "bewirbdich",
            "email": "bewirbdich@stb-gertz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-glaeser.de": [
        {
            "first_name": "",
            "last_name": "glaeser",
            "email": "glaeser@stb-glaeser.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-griessinger.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-griessinger.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-haeusler.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-haeusler.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-hansch.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-hansch.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-hetzinger.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-hetzinger.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-hoelter.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@stb-hoelter.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-horn-pohl.de": [
        {
            "first_name": "",
            "last_name": "pohl",
            "email": "pohl@stb-horn-pohl.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-huebner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-huebner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stb-ihring.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@stb-ihring.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stb-jss.de": [
        {
            "first_name": "",
            "last_name": "i.classen",
            "email": "i.classen@stb-jss.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-ke.de": [
        {
            "first_name": "",
            "last_name": "sek",
            "email": "sek@stb-ke.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-kgp.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-kgp.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-kille.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-kille.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-kohler.de": [
        {
            "first_name": "",
            "last_name": "cathrin.ambacher",
            "email": "cathrin.ambacher@stb-kohler.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-kost.de": [
        {
            "first_name": "",
            "last_name": "email",
            "email": "email@stb-kost.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stb-krapp.de": [
        {
            "first_name": "",
            "last_name": "krystyna.krapp",
            "email": "krystyna.krapp@stb-krapp.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-lb.de": [
        {
            "first_name": "",
            "last_name": "sandra.wiedemann",
            "email": "sandra.wiedemann@stb-lb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-miller.de": [
        {
            "first_name": "H. Miller",
            "last_name": "(StB-Miller)",
            "email": "h.miller@stb-miller.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stb-muc.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-muc.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-nolden.de": [
        {
            "first_name": "",
            "last_name": "nolden",
            "email": "nolden@stb-nolden.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-oberdorfer.de": [
        {
            "first_name": "",
            "last_name": "michael.oberdorfer",
            "email": "michael.oberdorfer@stb-oberdorfer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-oehlandt.de": [
        {
            "first_name": "",
            "last_name": "k.oehlandt",
            "email": "k.oehlandt@stb-oehlandt.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-partg.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-partg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-radevic.de": [
        {
            "first_name": "",
            "last_name": "job",
            "email": "job@stb-radevic.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-rautenberg.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-rautenberg.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-reimann.de": [
        {
            "first_name": "Martin",
            "last_name": "Reimann",
            "email": "mr@stb-reimann.de",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "stb-scanlan.de": [
        {
            "first_name": "Ekaterina",
            "last_name": "Strueva",
            "email": "ekaterina.strueva@stb-scanlan.de",
            "anzahl_mails": "4",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "anna.schmid",
            "email": "anna.schmid@stb-scanlan.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-schaeferling.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-schaeferling.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-schafnitzel.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-schafnitzel.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stb-schloeder.de": [
        {
            "first_name": "",
            "last_name": "o.schloeder",
            "email": "o.schloeder@stb-schloeder.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-schmetz.de": [
        {
            "first_name": "",
            "last_name": "schmetz",
            "email": "schmetz@stb-schmetz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-siegmann.de": [
        {
            "first_name": "",
            "last_name": "siegmann",
            "email": "siegmann@stb-siegmann.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-stuttgart.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-stuttgart.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-tkl.de": [
        {
            "first_name": "Tim Kröger-Lehmann",
            "last_name": "Steuerbüro Kröger-Lehmann",
            "email": "t.kroeger-lehmann@stb-tkl.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-uffelmann.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-uffelmann.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stb-vallentin.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-vallentin.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-vossler.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stb-vossler.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-weber-bonn.de": [
        {
            "first_name": "",
            "last_name": "aw",
            "email": "aw@stb-weber-bonn.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-weithaler.de": [
        {
            "first_name": "",
            "last_name": "joerdis.weithaler",
            "email": "joerdis.weithaler@stb-weithaler.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-wettlaufer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-wettlaufer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-weyland.de": [
        {
            "first_name": "",
            "last_name": "h.weyland",
            "email": "h.weyland@stb-weyland.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stb-wiesbaden.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-wiesbaden.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-witt-rachuba.de": [
        {
            "first_name": "",
            "last_name": "ines.witt-rachuba",
            "email": "ines.witt-rachuba@stb-witt-rachuba.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stb-wniggemann.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stb-wniggemann.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stb-wolko.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stb-wolko.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stb-wuerzburg.de": [
        {
            "first_name": "",
            "last_name": "c.hochapfel",
            "email": "c.hochapfel@stb-wuerzburg.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stbbb.de": [
        {
            "first_name": "",
            "last_name": "sebastian.bachmann",
            "email": "sebastian.bachmann@stbbb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "stbconzen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stbconzen.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "stbhaas.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@stbhaas.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stbin-baehr.de": [
        {
            "first_name": "",
            "last_name": "nicole.baehr",
            "email": "nicole.baehr@stbin-baehr.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stbin-ziegler.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stbin-ziegler.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stbkanzlei-wierzewski.de": [
        {
            "first_name": "Thilo",
            "last_name": "Wierzewski",
            "email": "t.wierzewski@stbkanzlei-wierzewski.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stbkanzlei.hamburg": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stbkanzlei.hamburg",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "stbkramer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stbkramer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stblanger.de": [
        {
            "first_name": "",
            "last_name": "durchstarten",
            "email": "durchstarten@stblanger.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stbmengel-bonn.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stbmengel-bonn.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stbpontani.de": [
        {
            "first_name": "Dominique",
            "last_name": "Pontani",
            "email": "pontani@stbpontani.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "stbvarga.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@stbvarga.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steinbach-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steinbach-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steinhauser.de": [
        {
            "first_name": "Sebastian",
            "last_name": "Marschall",
            "email": "sebastian.marschall@steinhauser.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steinhilber-steuerberater.de": [
        {
            "first_name": "Dieter Steinhilber | Steinhilber und",
            "last_name": "Steinhilber",
            "email": "dieter.steinhilber@steinhilber-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "sterr.de": [
        {
            "first_name": "",
            "last_name": "Bewerbungen",
            "email": "bewerbungen@sterr.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "steuer-anders.de": [
        {
            "first_name": "",
            "last_name": "welcome",
            "email": "welcome@steuer-anders.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuer-beck.de": [
        {
            "first_name": "",
            "last_name": "a.beck",
            "email": "a.beck@steuer-beck.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuer-bkg.de": [
        {
            "first_name": "Michael",
            "last_name": "Kühnle",
            "email": "m.kuehnle@steuer-bkg.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuer-bohnert.de": [
        {
            "first_name": "",
            "last_name": "bohnert",
            "email": "bohnert@steuer-bohnert.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuer-fischer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuer-fischer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuer-lohmar.de": [
        {
            "first_name": "",
            "last_name": "monika.adolph",
            "email": "monika.adolph@steuer-lohmar.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuer-lux.de": [
        {
            "first_name": "",
            "last_name": "albrecht",
            "email": "albrecht@steuer-lux.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuer-schillinger.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuer-schillinger.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuer1.de": [
        {
            "first_name": "",
            "last_name": "knutzen",
            "email": "knutzen@steuer1.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steueragenten.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@steueragenten.de",
            "anzahl_mails": "6",
            "typ": "generic",
        },
    ],
    "steuerarzt.de": [
        {
            "first_name": "Jochen",
            "last_name": "Grabmann",
            "email": "jochen.grabmann@steuerarzt.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "steuerberater-b-r.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-b-r.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-beck.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-beck.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-bergmann.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-bergmann.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-berlin.de": [
        {
            "first_name": "",
            "last_name": "a.georgi",
            "email": "a.georgi@steuerberater-berlin.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberater-bove.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerberater-bove.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-bruckhoff.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-bruckhoff.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-daehn.de": [
        {
            "first_name": "",
            "last_name": "a.daehn",
            "email": "a.daehn@steuerberater-daehn.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-dd.de": [
        {
            "first_name": "Steuerberater Delitz &",
            "last_name": "Damböck",
            "email": "info@steuerberater-dd.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-del.de": [
        {
            "first_name": "",
            "last_name": "nowag",
            "email": "nowag@steuerberater-del.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-eb.de": [
        {
            "first_name": "",
            "last_name": "e.beyer",
            "email": "e.beyer@steuerberater-eb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberater-herbert.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerberater-herbert.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-hr.de": [
        {
            "first_name": "",
            "last_name": "richter",
            "email": "richter@steuerberater-hr.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-info.com": [
        {
            "first_name": "Michael",
            "last_name": "Albrecht",
            "email": "albrecht@steuerberater-info.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "steuerberater-kapfer.de": [
        {
            "first_name": "",
            "last_name": "martin.kapfer",
            "email": "martin.kapfer@steuerberater-kapfer.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberater-klauth.de": [
        {
            "first_name": "",
            "last_name": "stb",
            "email": "stb@steuerberater-klauth.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberater-klemme.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-klemme.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-koll.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-koll.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-kraft.de": [
        {
            "first_name": "",
            "last_name": "Info",
            "email": "info@steuerberater-kraft.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "steuerberater-krain.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerberater-krain.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-leichtle.de": [
        {
            "first_name": "",
            "last_name": "leichtle",
            "email": "leichtle@steuerberater-leichtle.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-leukart.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerberater-leukart.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberater-luenen.de": [
        {
            "first_name": "",
            "last_name": "durchstarten",
            "email": "durchstarten@steuerberater-luenen.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-melza.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerberater-melza.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-mum.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-mum.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-oehler.de": [
        {
            "first_name": "Ralph",
            "last_name": "Oehler",
            "email": "r.oehler@steuerberater-oehler.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "steuerberater-rausch.de": [
        {
            "first_name": "",
            "last_name": "trausch",
            "email": "trausch@steuerberater-rausch.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-roos.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-roos.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-sch.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerberater-sch.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-schuette.de": [
        {
            "first_name": "",
            "last_name": "cs",
            "email": "cs@steuerberater-schuette.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-schuster.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-schuster.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-senn.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-senn.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-stiebritz.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@steuerberater-stiebritz.de",
            "anzahl_mails": "4",
            "typ": "generic",
        },
    ],
    "steuerberater-suw.de": [
        {
            "first_name": "",
            "last_name": "schaefer",
            "email": "schaefer@steuerberater-suw.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-uber.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerberater-uber.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater-weilamrhein.com": [
        {
            "first_name": "Bastian",
            "last_name": "Kroehnke",
            "email": "bastian.kroehnke@steuerberater-weilamrhein.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberater-wiedmann.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-wiedmann.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-wildner.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-wildner.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberater-winz.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberater-winz.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberater.hamburg": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@steuerberater.hamburg",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberaterbode.de": [
        {
            "first_name": "",
            "last_name": "c.bode",
            "email": "c.bode@steuerberaterbode.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberaterin-deggendorf.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberaterin-deggendorf.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberaterin-huber.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberaterin-huber.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberaterin-petra-daniel.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerberaterin-petra-daniel.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberaterin-warmsbach.de": [
        {
            "first_name": "",
            "last_name": "ew",
            "email": "ew@steuerberaterin-warmsbach.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberaterinnen.berlin": [
        {
            "first_name": "",
            "last_name": "rockmann",
            "email": "rockmann@steuerberaterinnen.berlin",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberatermuench.de": [
        {
            "first_name": "",
            "last_name": "mielich",
            "email": "mielich@steuerberatermuench.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberateroldenburg.com": [
        {
            "first_name": "",
            "last_name": "andreas.dreissig",
            "email": "andreas.dreissig@steuerberateroldenburg.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberatung-bensberg.de": [
        {
            "first_name": "",
            "last_name": "vb",
            "email": "vb@steuerberatung-bensberg.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberatung-breit.de": [
        {
            "first_name": "",
            "last_name": "anfrage",
            "email": "anfrage@steuerberatung-breit.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "steuerberatung-bss.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-bss.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-buedingen.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerberatung-buedingen.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberatung-buhl.de": [
        {
            "first_name": "",
            "last_name": "buhl",
            "email": "buhl@steuerberatung-buhl.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberatung-bulek.de": [
        {
            "first_name": "Katrin",
            "last_name": "Bulek",
            "email": "katrin.bulek@steuerberatung-bulek.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberatung-castrop.eu": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-castrop.eu",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberatung-commentz.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerberatung-commentz.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-dietz.de": [
        {
            "first_name": "",
            "last_name": "webseite",
            "email": "webseite@steuerberatung-dietz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberatung-dortmund.de": [
        {
            "first_name": "",
            "last_name": "post",
            "email": "post@steuerberatung-dortmund.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberatung-duerrich.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-duerrich.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-garreis.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-garreis.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-hartmann.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-hartmann.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-hofmann.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-hofmann.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberatung-mayer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-mayer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-schaal.de": [
        {
            "first_name": "",
            "last_name": "tschaal",
            "email": "tschaal@steuerberatung-schaal.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberatung-schlicht.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-schlicht.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-selmer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-selmer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-steffens.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-steffens.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerberatung-vanhorn.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-vanhorn.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-wenskus.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatung-wenskus.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerberatung-winter.de": [
        {
            "first_name": "",
            "last_name": "winter",
            "email": "winter@steuerberatung-winter.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerberatungdortmund.de": [
        {
            "first_name": "",
            "last_name": "post",
            "email": "post@steuerberatungdortmund.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerberatungspartner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerberatungspartner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerboutique.de": [
        {
            "first_name": "",
            "last_name": "ottermann",
            "email": "ottermann@steuerboutique.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerbuder.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerbuder.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerbuero-krug.de": [
        {
            "first_name": "",
            "last_name": "krug-tobias",
            "email": "krug-tobias@steuerbuero-krug.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerbuero-nitz.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@steuerbuero-nitz.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-badewitz.de": [
        {
            "first_name": "",
            "last_name": "info-bt",
            "email": "info-bt@steuerkanzlei-badewitz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerkanzlei-bajc.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-bajc.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-bauerfeind.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerkanzlei-bauerfeind.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-bayreuth.de": [
        {
            "first_name": "",
            "last_name": "jurisch",
            "email": "jurisch@steuerkanzlei-bayreuth.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerkanzlei-burkhart.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-burkhart.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-daffner.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-daffner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-gail.de": [
        {
            "first_name": "",
            "last_name": "n.gail",
            "email": "n.gail@steuerkanzlei-gail.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerkanzlei-gut.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@steuerkanzlei-gut.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-hanau.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-hanau.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-held.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-held.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-herrler.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-herrler.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-im-lehel.de": [
        {
            "first_name": "Matthias (Steuerkanzlei im Lehel)",
            "last_name": "Osinski",
            "email": "matthias.osinski@steuerkanzlei-im-lehel.de",
            "anzahl_mails": "24",
            "typ": "person",
        },
        {
            "first_name": "Isabella (Steuerkanzlei im Lehel)",
            "last_name": "Rass",
            "email": "isabella.rass@steuerkanzlei-im-lehel.de",
            "anzahl_mails": "12",
            "typ": "person",
        },
    ],
    "steuerkanzlei-lang.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-lang.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-lechner.de": [
        {
            "first_name": "Alexander",
            "last_name": "Lechner",
            "email": "a.lechner@steuerkanzlei-lechner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerkanzlei-ludwig.com": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@steuerkanzlei-ludwig.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerkanzlei-oswald.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-oswald.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-reinhart.de": [
        {
            "first_name": "",
            "last_name": "markus.reinhart",
            "email": "markus.reinhart@steuerkanzlei-reinhart.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerkanzlei-ritzer.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-ritzer.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-rosen.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-rosen.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-ruberto.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-ruberto.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-schadl.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerkanzlei-schadl.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-scheid.de": [
        {
            "first_name": "",
            "last_name": "Scheid",
            "email": "scheid@steuerkanzlei-scheid.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "steuerkanzlei-schicks.de": [
        {
            "first_name": "",
            "last_name": "hws",
            "email": "hws@steuerkanzlei-schicks.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerkanzlei-solinski.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzlei-solinski.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-starnberg.eu": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerkanzlei-starnberg.eu",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-wanner.de": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@steuerkanzlei-wanner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-winterstein.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@steuerkanzlei-winterstein.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzlei-wirsching.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@steuerkanzlei-wirsching.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerkanzleibayer.de": [
        {
            "first_name": "",
            "last_name": "bayer",
            "email": "bayer@steuerkanzleibayer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuerkanzleiseitz.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerkanzleiseitz.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "steuerkonzepte.com": [
        {
            "first_name": "",
            "last_name": "kontakt",
            "email": "kontakt@steuerkonzepte.com",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuern-becker.de": [
        {
            "first_name": "",
            "last_name": "becker",
            "email": "becker@steuern-becker.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "steuern-jp.com": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@steuern-jp.com",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "steuern-re.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuern-re.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuernklaeren.de": [
        {
            "first_name": "Klaeren",
            "last_name": "Steuerberater",
            "email": "mail@steuernklaeren.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "steuerregler.de": [
        {
            "first_name": "",
            "last_name": "schmitz",
            "email": "schmitz@steuerregler.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "steuerring.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerring.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerschmid.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@steuerschmid.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steuerwerker.hamburg": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steuerwerker.hamburg",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "steura-semba.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@steura-semba.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stg.info": [
        {
            "first_name": "",
            "last_name": "claudia.cehic",
            "email": "claudia.cehic@stg.info",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "sti-steuer.de": [
        {
            "first_name": "Stefan",
            "last_name": "Sauer",
            "email": "stefan.sauer@sti-steuer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stk-goebel.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@stk-goebel.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "streb.gmbh": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@streb.gmbh",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "streck.net": [
        {
            "first_name": "Sarah",
            "last_name": "Fillinger",
            "email": "sarah.fillinger@streck.net",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "ststb.de": [
        {
            "first_name": "Markus",
            "last_name": "Stäringer",
            "email": "staeringerm@ststb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "students.kiron.ngo": [
        {
            "first_name": "Prince",
            "last_name": "Kani",
            "email": "pk7@students.kiron.ngo",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "studio-hamburg.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@studio-hamburg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stuebe-schneegass.com": [
        {
            "first_name": "",
            "last_name": "steuerberater",
            "email": "steuerberater@stuebe-schneegass.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "stuercke-blume.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@stuercke-blume.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "stursbergundcarosi.de": [
        {
            "first_name": "",
            "last_name": "katharina.copa",
            "email": "katharina.copa@stursbergundcarosi.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "successfactors.com": [
        {
            "first_name": "",
            "last_name": "de_recruiting@pwc.com",
            "email": "system@successfactors.com",
            "anzahl_mails": "8",
            "typ": "person",
        },
    ],
    "sudhaus-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "s.sudhaus",
            "email": "s.sudhaus@sudhaus-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "sup-muenchen.de": [
        {
            "first_name": "",
            "last_name": "klaus.schneider",
            "email": "klaus.schneider@sup-muenchen.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "svenhase.de": [
        {
            "first_name": "",
            "last_name": "personal",
            "email": "personal@svenhase.de",
            "anzahl_mails": "11",
            "typ": "generic",
        },
    ],
    "swna.de": [
        {
            "first_name": "",
            "last_name": "welcome",
            "email": "welcome@swna.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "swp-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@swp-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "swrv.tax": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@swrv.tax",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "taeurope.com": [
        {
            "first_name": "Careers | TA",
            "last_name": "Europe",
            "email": "careers@taeurope.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "tax-manager.de": [
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@tax-manager.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "taxbeat.com": [
        {
            "first_name": "Thomas",
            "last_name": "Haag",
            "email": "thomas.haag@taxbeat.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "start",
            "email": "start@taxbeat.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "taxena.de": [
        {
            "first_name": "Info | Taxena",
            "last_name": "Steuerberatung",
            "email": "info@taxena.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "taxmain.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@taxmain.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "taxon.de": [
        {
            "first_name": "",
            "last_name": "berlin",
            "email": "berlin@taxon.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "hamburg",
            "email": "hamburg@taxon.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "taxpal.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@taxpal.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "taxspiration.de": [
        {
            "first_name": "",
            "last_name": "ms",
            "email": "ms@taxspiration.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "taxvisions.de": [
        {
            "first_name": "",
            "last_name": "career",
            "email": "career@taxvisions.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "taxworker.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@taxworker.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "taylorwessing.com": [
        {
            "first_name": "Luise",
            "last_name": "Kirsten",
            "email": "l.kirsten@taylorwessing.com",
            "anzahl_mails": "18",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "s.kirsten",
            "email": "s.kirsten@taylorwessing.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "team-confides.de": [
        {
            "first_name": "",
            "last_name": "bewerbungen",
            "email": "bewerbungen@team-confides.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "tennisfit-mg.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@tennisfit-mg.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "teufel-berater.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@teufel-berater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "theentourage.de": [
        {
            "first_name": "",
            "last_name": "michael.meyer",
            "email": "michael.meyer@theentourage.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "thoms-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "thoms",
            "email": "thoms@thoms-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "tib-treuhand.de": [
        {
            "first_name": "",
            "last_name": "o.gebauer",
            "email": "o.gebauer@tib-treuhand.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "tlitax.com": [
        {
            "first_name": "",
            "last_name": "michaela.musial",
            "email": "michaela.musial@tlitax.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "treuhand-hannover.de": [
        {
            "first_name": "Waltraud (Treuhand Hannover GmbH)",
            "last_name": "Nolte",
            "email": "waltraud.nolte@treuhand-hannover.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "treuhand-stuttgart.de": [
        {
            "first_name": "",
            "last_name": "stuttgart",
            "email": "stuttgart@treuhand-stuttgart.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "treuhand.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@treuhand.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "treukontax.de": [
        {
            "first_name": "",
            "last_name": "deggendorf",
            "email": "deggendorf@treukontax.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "treuunion-beratung.de": [
        {
            "first_name": "S. Geisler | Treuunion",
            "last_name": "Beratung",
            "email": "s.geisler@treuunion-beratung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "O. Eckhardt | Treuunion",
            "last_name": "Beratung",
            "email": "o.eckhardt@treuunion-beratung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "trewitax.de": [
        {
            "first_name": "Brigitte",
            "last_name": "Brütsch",
            "email": "brigitte.bruetsch@trewitax.de",
            "anzahl_mails": "15",
            "typ": "person",
        },
    ],
    "trillmann-schmitz.de": [
        {
            "first_name": "",
            "last_name": "trillmann",
            "email": "trillmann@trillmann-schmitz.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "trimborn-partner.de": [
        {
            "first_name": "",
            "last_name": "penteker",
            "email": "penteker@trimborn-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "twobirds.com": [
        {
            "first_name": "",
            "last_name": "gerrecruiting",
            "email": "gerrecruiting@twobirds.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "united-domains.de": [
        {
            "first_name": "united-domains",
            "last_name": "GmbH",
            "email": "support@united-domains.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "ut-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ut-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "vantoya.com": [
        {
            "first_name": "",
            "last_name": "people",
            "email": "people@vantoya.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "vectocon.de": [
        {
            "first_name": "",
            "last_name": "hanau",
            "email": "hanau@vectocon.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "velde.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@velde.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "velptec.de": [
        {
            "first_name": "velpTEC",
            "last_name": "Karriere",
            "email": "karriere@velptec.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "ventuslx.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@ventuslx.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "veritax-stb.de": [
        {
            "first_name": "",
            "last_name": "post",
            "email": "post@veritax-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "vestia.de": [
        {
            "first_name": "",
            "last_name": "Bewerbungen",
            "email": "bewerbungen@vestia.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "vgl-partner.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@vgl-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "vidacura.de": [
        {
            "first_name": "Sebastian",
            "last_name": "Fritz",
            "email": "fritz@vidacura.de",
            "anzahl_mails": "22",
            "typ": "person",
        },
    ],
    "visus-gmbh.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@visus-gmbh.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "vitan.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@vitan.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "vodafone.de": [
        {
            "first_name": "Christiane",
            "last_name": "Hirsekorn",
            "email": "christiane.hirsekorn@vodafone.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "voelschau.de": [
        {
            "first_name": "",
            "last_name": "hamburg",
            "email": "hamburg@voelschau.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "von-hacht.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@von-hacht.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "vppartner.de": [
        {
            "first_name": "",
            "last_name": "m.prokasky",
            "email": "m.prokasky@vppartner.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "vs-stb.de": [
        {
            "first_name": "Carmen",
            "last_name": "Muehlpforte",
            "email": "c.muehlpforte@vs-stb.de",
            "anzahl_mails": "32",
            "typ": "person",
        },
    ],
    "w-f-m.de": [
        {
            "first_name": "",
            "last_name": "wp.stb",
            "email": "wp.stb@w-f-m.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wagemann.net": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@wagemann.net",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "wannemacher-partner.de": [
        {
            "first_name": "",
            "last_name": "muenchen",
            "email": "muenchen@wannemacher-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "weber-heldt.de": [
        {
            "first_name": "",
            "last_name": "post",
            "email": "post@weber-heldt.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "weber-rechtsanwaeltin.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@weber-rechtsanwaeltin.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "weck.de": [
        {
            "first_name": "",
            "last_name": "Bewerbung",
            "email": "bewerbung@weck.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "weha.com": [
        {
            "first_name": "Lot",
            "last_name": "Julia",
            "email": "julia.lot@weha.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "weidmann-recht-steuern.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@weidmann-recht-steuern.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "weigell.de": [
        {
            "first_name": "",
            "last_name": "daniela.laus",
            "email": "daniela.laus@weigell.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "weise-steuerberater.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@weise-steuerberater.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@weise-steuerberater.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "welzer.com": [
        {
            "first_name": "",
            "last_name": "post",
            "email": "post@welzer.com",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wep-treuhand.de": [
        {
            "first_name": "",
            "last_name": "mail",
            "email": "mail@wep-treuhand.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "westlakevinnolit.com": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@westlakevinnolit.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
        {
            "first_name": "VIN.Bewerbungen",
            "last_name": "Box",
            "email": "bewerbungen@westlakevinnolit.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wetterer-steuerberater.de": [
        {
            "first_name": "Jonas",
            "last_name": "Hofmeier",
            "email": "j.hofmeier@wetterer-steuerberater.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "wex-stb.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@wex-stb.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wgs-steuerberater.de": [
        {
            "first_name": "Intern - WGS Wagener & Graf Steuerberatung",
            "last_name": "GmbH",
            "email": "intern@wgs-steuerberater.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "wickert-heinz.de": [
        {
            "first_name": "Christian",
            "last_name": "Heinz",
            "email": "christian.heinz@wickert-heinz.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "wie-partner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@wie-partner.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "wietasch.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@wietasch.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wild.legal": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@wild.legal",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "will-breidung.de": [
        {
            "first_name": "",
            "last_name": "d.breidung",
            "email": "d.breidung@will-breidung.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "winheller.com": [
        {
            "first_name": "Susann",
            "last_name": "Richter",
            "email": "s.richter@winheller.com",
            "anzahl_mails": "17",
            "typ": "person",
        },
    ],
    "wirler-partner.de": [
        {
            "first_name": "",
            "last_name": "f.wirler",
            "email": "f.wirler@wirler-partner.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wirtschaftstreuhand.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@wirtschaftstreuhand.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wiseo.info": [
        {
            "first_name": "",
            "last_name": "t-meyer",
            "email": "t-meyer@wiseo.info",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "t.maier",
            "email": "t.maier@wiseo.info",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "t.meyer",
            "email": "t.meyer@wiseo.info",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wista-ag.de": [
        {
            "first_name": "",
            "last_name": "thomas.rondot",
            "email": "thomas.rondot@wista-ag.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "witte-scholz.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@witte-scholz.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "wittwer-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "cw",
            "email": "cw@wittwer-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wlw-partner.de": [
        {
            "first_name": "wlw-partner",
            "last_name": "INFO",
            "email": "info@wlw-partner.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "wms-stb.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@wms-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "woellke.de": [
        {
            "first_name": "Dipl-Kfm (univ.) StB Sascha",
            "last_name": "Woellke",
            "email": "s.woellke@woellke.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "wolf-steuer.de": [
        {
            "first_name": "Katrin",
            "last_name": "Knoll",
            "email": "k.knoll@wolf-steuer.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wollnywp.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@wollnywp.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "wp-greibke.de": [
        {
            "first_name": "",
            "last_name": "claudia.greibke",
            "email": "claudia.greibke@wp-greibke.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wp-lampe.de": [
        {
            "first_name": "",
            "last_name": "glampe",
            "email": "glampe@wp-lampe.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wp-schimanski.de": [
        {
            "first_name": "",
            "last_name": "anja.schimanski",
            "email": "anja.schimanski@wp-schimanski.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
        {
            "first_name": "",
            "last_name": "claudia.kugler",
            "email": "claudia.kugler@wp-schimanski.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wp-stb.eu": [
        {
            "first_name": "",
            "last_name": "office",
            "email": "office@wp-stb.eu",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wpstb-juergens.de": [
        {
            "first_name": "",
            "last_name": "jobs",
            "email": "jobs@wpstb-juergens.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wrk-h.com": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@wrk-h.com",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "wrt-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@wrt-steuerberatung.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "wrw-steuer.de": [
        {
            "first_name": "Thomas",
            "last_name": "Werner",
            "email": "t.werner@wrw-steuer.de",
            "anzahl_mails": "5",
            "typ": "person",
        },
    ],
    "ws-sued.de": [
        {
            "first_name": "",
            "last_name": "info",
            "email": "info@ws-sued.de",
            "anzahl_mails": "3",
            "typ": "generic",
        },
    ],
    "wsw-stb.de": [
        {
            "first_name": "",
            "last_name": "storch",
            "email": "storch@wsw-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "wts.de": [
        {
            "first_name": "Michelle",
            "last_name": "Schlumberger",
            "email": "michelle.schlumberger@wts.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "wuschek-stb.de": [
        {
            "first_name": "Barbara",
            "last_name": "Söllner",
            "email": "soellner@wuschek-stb.de",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "wuw-stb.de": [
        {
            "first_name": "",
            "last_name": "kanzlei",
            "email": "kanzlei@wuw-stb.de",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "wzk-partner.de": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@wzk-partner.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
    "xiting.com": [
        {
            "first_name": "Xiting",
            "last_name": "Career",
            "email": "career@xiting.com",
            "anzahl_mails": "3",
            "typ": "person",
        },
    ],
    "yahoo.gr": [
        {
            "first_name": "ΒΑΣΙΛΗΣ",
            "last_name": "ΦΛΩΡΟΣ",
            "email": "vasilis.floros@yahoo.gr",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "yildizarslan.de": [
        {
            "first_name": "Yildiz",
            "last_name": "Arslan",
            "email": "privat@yildizarslan.de",
            "anzahl_mails": "10",
            "typ": "person",
        },
    ],
    "yl-stb.de": [
        {
            "first_name": "",
            "last_name": "utzing",
            "email": "utzing@yl-stb.de",
            "anzahl_mails": "1",
            "typ": "person",
        },
    ],
    "ymail.com": [
        {
            "first_name": "Maria",
            "last_name": "Fodor",
            "email": "fodor_m@ymail.com",
            "anzahl_mails": "6",
            "typ": "person",
        },
    ],
    "ypog.law": [
        {
            "first_name": "",
            "last_name": "karriere",
            "email": "karriere@ypog.law",
            "anzahl_mails": "5",
            "typ": "generic",
        },
    ],
    "zahlenwerk-stb.de": [
        {
            "first_name": "Info",
            "last_name": "Zahlenwerk",
            "email": "info@zahlenwerk-stb.de",
            "anzahl_mails": "18",
            "typ": "generic",
        },
    ],
    "zerberus-steuerberatung.com": [
        {
            "first_name": "",
            "last_name": "dietrich",
            "email": "dietrich@zerberus-steuerberatung.com",
            "anzahl_mails": "2",
            "typ": "person",
        },
    ],
    "zoeller-dicke.de": [
        {
            "first_name": "",
            "last_name": "bewerbung",
            "email": "bewerbung@zoeller-dicke.de",
            "anzahl_mails": "2",
            "typ": "generic",
        },
    ],
    "zoeller-steuerberatung.de": [
        {
            "first_name": "",
            "last_name": "service",
            "email": "service@zoeller-steuerberatung.de",
            "anzahl_mails": "1",
            "typ": "generic",
        },
    ],
}

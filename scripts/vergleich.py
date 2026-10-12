#!/usr/bin/env python3
"""Vergleicht Nomicon (dieses Repo) mit Hermes CRM. Beide Repos sind gleichberechtigt.

Aufruf (aus dem Repo-Wurzelverzeichnis):

    python scripts/vergleich.py --hermes /pfad/zu/hermescrm
    python scripts/vergleich.py --hermes /pfad/zu/hermescrm --update-pruefstand

Der Pruefstand steht als Marker in docs/VERGLEICH.md:
    <!-- pruefstand hermes=SHA nomicon=SHA -->
Das Skript zeigt, was seit dem Pruefstand auf beiden Seiten passiert ist, welche Dateien
beide Seiten angefasst haben (Gefahr: zwei Loesungen fuer dasselbe) und wo sich die
Migrationsketten und Einstellungen unterscheiden. Es aendert nichts ausser (mit
--update-pruefstand) dem Marker. Hermes wird nur gelesen.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERGLEICH = ROOT / "docs" / "VERGLEICH.md"
MARKER = re.compile(r"<!-- pruefstand hermes=(\w+) nomicon=(\w+) -->")
# Pfade, die absichtlich nur in Nomicon existieren und nicht verglichen werden muessen.
NOMICON_ONLY = re.compile(
    r"(staffing|commission|ueberlassung|stundenzettel|nomicon|PROVISION|UEBERLASSUNG|"
    r"brand-theme|public/brand|backend/templates|^KOPIE\.md|^scripts/vergleich\.py|"
    r"docs/VERGLEICH\.md)",
    re.IGNORECASE,
)
# Nur Verwaltungsdateien, die in beiden Repos laufend und unterschiedlich gepflegt werden.
NOISE = {"docs/PROTOKOLL.md", "docs/PROJEKT_STAND.md", "docs/ENTSCHEIDUNGEN.md"}


def git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return res.stdout.strip()


def commits(repo: Path, since: str | None) -> list[tuple[str, str, list[str]]]:
    rng = [f"{since}..HEAD"] if since else ["-50"]
    out = git(repo, "log", "--no-merges", "--format=%h\t%s", *rng)
    result = []
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        files = git(repo, "show", "--format=", "--name-only", sha).splitlines()
        result.append((sha, subject, [f for f in files if f]))
    return result


def changed_files(repo: Path, since: str | None) -> set[str]:
    if not since:
        return set()
    return set(git(repo, "diff", "--name-only", f"{since}..HEAD").splitlines())


def revisions(repo: Path) -> dict[str, str]:
    """Alembic-Revision -> down_revision."""
    result: dict[str, str] = {}
    for f in sorted((repo / "backend" / "alembic" / "versions").glob("*.py")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r"^revision(?:: str)?\s*=\s*[\"'](\w+)[\"']", text, re.M)
        down = re.search(r"^down_revision[^=]*=\s*(.+)$", text, re.M)
        if rev:
            result[rev.group(1)] = down.group(1).strip() if down else ""
    return result


def heads(revs: dict[str, str]) -> list[str]:
    parents = set(re.findall(r"\w{6,}", " ".join(revs.values())))
    return sorted(r for r in revs if r not in parents)


def env_vars(repo: Path) -> set[str]:
    cfg = repo / "backend" / "src" / "cc_crm" / "core" / "config.py"
    if not cfg.exists():
        return set()
    names = re.findall(
        r"^\s{4}([a-z][a-z0-9_]*)\s*:", cfg.read_text(encoding="utf-8"), re.M
    )
    return {n.upper() for n in names}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--hermes", default="/home/user/hermescrm", help="Pfad zum Hermes-Klon"
    )
    ap.add_argument("--update-pruefstand", action="store_true")
    args = ap.parse_args()
    hermes = Path(args.hermes)
    if not (hermes / ".git").exists():
        print(f"Hermes-Klon nicht gefunden: {hermes}", file=sys.stderr)
        return 2

    text = VERGLEICH.read_text(encoding="utf-8") if VERGLEICH.exists() else ""
    m = MARKER.search(text)
    h_since, n_since = (m.group(1), m.group(2)) if m else (None, None)
    h_head, n_head = (
        git(hermes, "rev-parse", "--short", "HEAD"),
        git(ROOT, "rev-parse", "--short", "HEAD"),
    )
    print(f"Pruefstand: hermes={h_since} nomicon={n_since}")
    print(f"Jetzt:      hermes={h_head} nomicon={n_head}\n")

    h_commits = commits(hermes, h_since)
    n_commits = commits(ROOT, n_since)
    print(f"== Hermes: {len(h_commits)} neue Commits seit Pruefstand ==")
    for sha, subj, files in h_commits:
        print(f"  {sha} {subj}  ({len(files)} Dateien)")
    print(f"\n== Nomicon: {len(n_commits)} neue Commits seit Pruefstand ==")
    for sha, subj, files in n_commits:
        print(f"  {sha} {subj}  ({len(files)} Dateien)")

    h_files = {f for f in changed_files(hermes, h_since) if f not in NOISE}
    n_files = {f for f in changed_files(ROOT, n_since) if f not in NOISE}
    both = sorted(f for f in h_files & n_files if not NOMICON_ONLY.search(f))
    print(
        f"\n== Von BEIDEN Seiten geaendert (pruefen: gleiche Loesung? bewusst anders?) =="
    )
    print("\n".join(f"  {f}" for f in both) or "  keine")
    only_h = sorted(f for f in h_files - n_files if not NOMICON_ONLY.search(f))
    print(
        f"\n== Nur in Hermes geaendert ({len(only_h)}): evtl. nach Nomicon uebernehmen =="
    )
    print("\n".join(f"  {f}" for f in only_h[:60]) or "  keine")
    only_n = sorted(f for f in n_files - h_files if not NOMICON_ONLY.search(f))
    print(
        f"\n== Nur in Nomicon geaendert, ohne reine Nomicon-Pfade ({len(only_n)}): evtl. fuer Hermes =="
    )
    print("\n".join(f"  {f}" for f in only_n[:60]) or "  keine")

    rh, rn = revisions(hermes), revisions(ROOT)
    print("\n== Alembic ==")
    print(f"  Hermes-Head(s):   {', '.join(heads(rh))}")
    print(f"  Nomicon-Head(s):  {', '.join(heads(rn))}")
    print(f"  nur in Hermes:    {', '.join(sorted(set(rh) - set(rn))) or '-'}")
    print(f"  nur in Nomicon:   {', '.join(sorted(set(rn) - set(rh))) or '-'}")

    eh, en = env_vars(hermes), env_vars(ROOT)
    print("\n== Einstellungen (Umgebungsvariablen in core/config.py) ==")
    print(f"  nur in Hermes:  {', '.join(sorted(eh - en)) or '-'}")
    print(f"  nur in Nomicon: {', '.join(sorted(en - eh)) or '-'}")

    print(
        "\nNaechster Schritt: jede Abweichung in docs/VERGLEICH.md eintragen "
        "(uebernehmen / bewusst anders + Grund / offen), dann --update-pruefstand."
    )

    if args.update_pruefstand:
        new = f"<!-- pruefstand hermes={h_head} nomicon={n_head} -->"
        VERGLEICH.write_text(
            MARKER.sub(new, text) if m else new + "\n" + text, encoding="utf-8"
        )
        print(f"Pruefstand fortgeschrieben: {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

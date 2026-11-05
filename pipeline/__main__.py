"""Punct de intrare: python -m pipeline <comandă>.

Comenzile citesc din cache-ul local (data/raw/) când există; rețeaua se folosește
doar pentru ce lipsește din cache. `all` reface toate datele fazei curente.
"""
from __future__ import annotations

import argparse
import logging
import sys


def _cmd_wikidata(args: argparse.Namespace) -> None:
    from pipeline.sources import wikidata
    wikidata.run(refresh=args.refresh)


def _cmd_wikipedia(args: argparse.Namespace) -> None:
    from pipeline.sources import wikipedia
    wikipedia.run(refresh=args.refresh)


def _cmd_places(args: argparse.Namespace) -> None:
    from pipeline.geocode import wikidata_places
    wikidata_places.run(refresh=args.refresh)


def _cmd_build(args: argparse.Namespace) -> None:
    from pipeline.build import export
    export.run()


def _cmd_all(args: argparse.Namespace) -> None:
    _cmd_wikidata(args)
    _cmd_wikipedia(args)
    _cmd_places(args)
    _cmd_build(args)


def main(argv: list[str] | None = None) -> int:
    # consola Windows e cp1252 implicit; forțăm UTF-8 ca să meargă diacriticele
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Pipeline de date pentru harta criminalilor în serie. "
        "Sursele brute se păstrează în data/raw/ (gitignored); rezultatul merge în data/ și site/public/data/.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log detaliat")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, help_ in [
        ("wikidata", _cmd_wikidata, "SPARQL: lista criminalilor în serie + proprietăți (faza 1)"),
        ("wikipedia", _cmd_wikipedia, "wikitext articole (infobox + lead) și liste Wikipedia (faza 1)"),
        ("places", _cmd_places, "rezolvă locurile prin Wikidata (coordonate, țară, precizie)"),
        ("build", _cmd_build, "unește sursele și exportă data/*.json + site/public/data/"),
        ("all", _cmd_all, "rulează toți pașii de mai sus, în ordine"),
    ]:
        p = sub.add_parser(name, help=help_, description=help_)
        p.add_argument("--refresh", action="store_true",
                       help="ignoră cache-ul și redescarcă (nu folosi de două ori pe zi)")
        p.set_defaults(func=fn)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

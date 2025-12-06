import argparse
import json
import sys
from pathlib import Path
from typing import List

from .schemas import Invoice
from .extractor import extract_invoices_from_dir, export_invoices_to_json
from .validator import validate_invoices


def _load_invoices_from_json(path: Path) -> List[Invoice]:
    """read invoices list from json file"""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    invoices: List[Invoice] = []
    # we expect data is list of dicts
    for obj in data:
        try:
            invoices.append(Invoice(**obj))
        except Exception as e:
            # in real world we would log this properly
            print(f"could not parse one invoice from json: {e}", file=sys.stderr)
    return invoices


def cmd_extract(args: argparse.Namespace) -> int:
    pdf_dir = Path(args.pdf_dir)
    output = Path(args.output)

    if not pdf_dir.exists() or not pdf_dir.is_dir():
        print(f"pdf dir does not exist or not a folder: {pdf_dir}", file=sys.stderr)
        return 1

    invoices = extract_invoices_from_dir(pdf_dir)
    export_invoices_to_json(invoices, output)

    print(f"extracted {len(invoices)} invoices from {pdf_dir} into {output}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    report_path = Path(args.report)

    if not input_path.exists():
        print(f"input json file not found: {input_path}", file=sys.stderr)
        return 1

    invoices = _load_invoices_from_json(input_path)
    results, summary = validate_invoices(invoices)

    # build simple report structure
    report_obj = {
        "summary": summary.model_dump(),
        "invoices": [r.model_dump() for r in results],
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report_obj, f, indent=2, ensure_ascii=False)

    print("validation finished")
    print(f"total invoices: {summary.total_invoices}")
    print(f"valid: {summary.valid_invoices}, invalid: {summary.invalid_invoices}")

    # show top few errors, if any
    if summary.error_counts:
        print("top errors:")
        # just print first 5 keys, order is not guaranteed
        i = 0
        for err, count in summary.error_counts.items():
            print(f"  {err}: {count}")
            i += 1
            if i >= 5:
                break

    # option: return non-zero if invalid present
    if summary.invalid_invoices > 0:
        return 2

    return 0


def cmd_full_run(args: argparse.Namespace) -> int:
    pdf_dir = Path(args.pdf_dir)
    report_path = Path(args.report)

    if not pdf_dir.exists() or not pdf_dir.is_dir():
        print(f"pdf dir does not exist or not a folder: {pdf_dir}", file=sys.stderr)
        return 1

    invoices = extract_invoices_from_dir(pdf_dir)
    results, summary = validate_invoices(invoices)

    # we write both extracted invoices and validation results
    report_obj = {
        "summary": summary.model_dump(),
        "invoices": [r.model_dump() for r in results],
        "raw_invoices": [inv.model_dump() for inv in invoices],
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report_obj, f, indent=2, ensure_ascii=False)

    print(f"full run done for folder {pdf_dir}")
    print(f"total invoices: {summary.total_invoices}")
    print(f"valid: {summary.valid_invoices}, invalid: {summary.invalid_invoices}")

    if summary.error_counts:
        print("some errors happened, see report file for details")

    if summary.invalid_invoices > 0:
        return 2

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice_qc",
        description="simple invoice extraction + validation tool",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract subcommand
    p_extract = subparsers.add_parser("extract", help="only extract invoices from pdfs")
    p_extract.add_argument("--pdf-dir", required=True, help="folder that has pdf files")
    p_extract.add_argument("--output", required=True, help="where to write json output")
    p_extract.set_defaults(func=cmd_extract)

    # validate subcommand
    p_validate = subparsers.add_parser("validate", help="only validate existing json")
    p_validate.add_argument("--input", required=True, help="json file with invoices")
    p_validate.add_argument("--report", required=True, help="where to write validation report json")
    p_validate.set_defaults(func=cmd_validate)

    # full-run subcommand
    p_full = subparsers.add_parser("full-run", help="extract + validate in one go")
    p_full.add_argument("--pdf-dir", required=True, help="folder with pdfs")
    p_full.add_argument("--report", required=True, help="where to write full report json")
    p_full.set_defaults(func=cmd_full_run)

    return parser


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # each subcommand sets func
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        sys.exit(1)

    exit_code = func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

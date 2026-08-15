"""
cli.py -- entry point for the evaluation suites.

    python -m llmeval behavior            # behavioural quality checks
    python -m llmeval behavior --list     # show available checks
    python -m llmeval redteam             # adversarial robustness
    python -m llmeval redteam --list      # show attack categories

Every suite talks to a live assistant over the transport configured in
``.env``. Check ``ENV`` before running: red-teaming production is a decision,
not an accident.
"""

import argparse
import sys

EPILOG = """
examples:
  python -m llmeval behavior
      Run every behavioural probe, then the multi-turn repetition test.

  python -m llmeval behavior --check specificity
      Run one check in isolation. Useful while tuning patterns.json.

  python -m llmeval behavior --check repetitive --report
      Multi-turn conversations only, and write a markdown report.

  python -m llmeval redteam --category jailbreak --report
      Jailbreak attacks only, with a report.

tuning:
  Behavioural checks match against vocabulary in llmeval/patterns.py.
  Point LLMEVAL_PATTERNS at a JSON file to override it for your domain.
  Do this before reading much into the pass rate.
"""


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="llmeval",
        description="Behavioural and adversarial evaluation for conversational LLM assistants.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env",
        choices=["qa", "prod"],
        help="Override the ENV setting from .env for this run.",
    )

    subparsers = parser.add_subparsers(dest="command")

    bh = subparsers.add_parser(
        "behavior",
        help="Behavioural quality checks: directness, specificity, temporal, language, repetition.",
    )
    bh.add_argument("--check", help="Run a single check by name (see --list).")
    bh.add_argument("--list", action="store_true", help="List available checks and exit.")
    bh.add_argument("--delay", type=int, default=2, help="Seconds between probes (default: 2).")
    bh.add_argument("--report", action="store_true", help="Write a markdown report.")

    rt = subparsers.add_parser(
        "redteam",
        help="Adversarial robustness: jailbreak, injection, hallucination, toxicity, robustness.",
    )
    rt.add_argument("--category", help="Run a single attack category (see --list).")
    rt.add_argument("--list", action="store_true", help="List attack categories and exit.")
    rt.add_argument("--delay", type=int, default=2, help="Seconds between attacks (default: 2).")
    rt.add_argument("--report", action="store_true", help="Write a markdown report.")

    return parser


def _exit_code(results) -> int:
    """1 when anything failed or errored, 0 when everything passed.

    An empty result set is also a failure: a filter that matched no probes ran
    no checks, and "nothing ran" must not look like "everything passed".
    """
    if not results:
        print("\n  No probes ran — nothing was evaluated.")
        return 1

    def _ok(r) -> bool:
        # Behaviour probes are dicts keyed "passed"; red-team results are
        # AttackResult objects with "defended". Both carry "error".
        if isinstance(r, dict):
            return bool(r.get("passed")) and not r.get("error")
        return bool(getattr(r, "defended", False)) and not getattr(r, "error", None)

    failed = [r for r in results if not _ok(r)]
    if failed:
        print(f"\n  {len(failed)} of {len(results)} failed.")
        return 1
    return 0


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Honour --env before anything imports config and reads the environment.
    if getattr(args, "env", None):
        import os

        os.environ["ENV"] = args.env

    if args.command == "behavior":
        from llmeval.behavior.runner import (
            list_checks,
            run_behavior_conversations,
            run_behavior_test,
        )

        if args.list:
            list_checks()
            return 0

        from llmeval.config import ENV, SSE_URL

        print(f"\n  Environment: {ENV}  ({SSE_URL})")

        # Exit non-zero when probes fail or the transport errored. Returning
        # 0 regardless meant a scheduled evaluation reported success no matter
        # what it found, which is the one thing an eval harness must not do.
        if args.check == "repetitive":
            results = run_behavior_conversations(delay=args.delay, save_report=args.report)
            return _exit_code(results)

        results = run_behavior_test(
            delay=args.delay,
            check_filter=args.check,
            save_report=args.report,
        )
        # With no filter, the multi-turn repetition suite is part of a full run.
        if not args.check:
            results += run_behavior_conversations(delay=args.delay, save_report=args.report)
        return _exit_code(results)

    if args.command == "redteam":
        from llmeval.redteam.runner import list_categories, run_redteam_test

        if args.list:
            list_categories()
            return 0

        from llmeval.config import ENV, SSE_URL

        print(f"\n  Environment: {ENV}  ({SSE_URL})")
        results = run_redteam_test(
            delay=args.delay,
            category_filter=args.category,
            save_report=args.report,
        )
        return _exit_code(results)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

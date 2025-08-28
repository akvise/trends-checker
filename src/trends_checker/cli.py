from __future__ import annotations

import argparse
import sys
import time
from typing import List
import os


DEFAULT_KEYWORDS = [
    "real time translation YouTube",
    "live translation YouTube", 
    "AI dubbing YouTube",
    "YouTube voiceover",
    "automatic translation YouTube",
]

DEFAULT_GEOS = ["WW", "US", "BR", "ES", "IN", "ID", "RU"]


def _require_pytrends():
    try:
        from pytrends.request import TrendReq  # type: ignore
        return TrendReq
    except Exception as e:
        print("pytrends is not installed. Install with: pip install pytrends", file=sys.stderr)
        raise


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="trends-checker",
        description="Probe Google Trends (YouTube Search) for interest in real-time YouTube translation/dubbing.",
    )
    p.add_argument(
        "--keywords",
        type=str,
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated list of up to 5 keywords (default includes EN+RU variants)",
    )
    p.add_argument(
        "--keywords-file",
        type=str,
        default="",
        help="Path to file with keywords (one per line; blank lines and lines starting with # are ignored)",
    )
    p.add_argument(
        "--geo",
        type=str,
        default=",".join(DEFAULT_GEOS),
        help="Comma-separated list of regions (ISO country code) or WW for worldwide",
    )
    p.add_argument(
        "--timeframe",
        type=str,
        default="today 12-m",
        help="Timeframe for Trends (e.g., 'today 12-m', 'today 5-y')",
    )
    p.add_argument(
        "--hl",
        type=str,
        default="en-US",
        help="UI language (pytrends hl), e.g., en-US or ru-RU",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=1.2,
        help="Sleep seconds between geo requests (avoid throttling)",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries on 429/temporary errors per geo",
    )
    p.add_argument(
        "--backoff",
        type=float,
        default=1.5,
        help="Exponential backoff base (seconds) for retries",
    )
    p.add_argument(
        "--jitter",
        type=float,
        default=0.6,
        help="Random jitter (seconds) added to backoff and sleeps",
    )
    p.add_argument(
        "--proxy",
        type=str,
        default="",
        help="Optional HTTP/HTTPS proxy URL(s), comma-separated (e.g., http://user:pass@host:port)",
    )
    p.add_argument(
        "--cookie",
        type=str,
        default="",
        help="Raw Cookie header value to send (e.g., 'NID=...; ...'). Use with caution.",
    )
    p.add_argument(
        "--cookie-file",
        type=str,
        default="",
        help="Path to a file containing the Cookie header value (preferred over --cookie)",
    )
    p.add_argument(
        "--display",
        choices=["wide", "vertical"],
        default="vertical",
        help="Table layout: 'vertical' (default) per-geo or 'wide'",
    )
    p.add_argument(
        "--output",
        type=str,
        default="",
        help="Write summary CSV to this path (optional)",
    )
    p.add_argument(
        "--related",
        action="store_true",
        help="Fetch and print rising related queries per keyword per region",
    )
    return p.parse_args(argv)


def _normalize_geo(code: str) -> str:
    return "" if code.upper() == "WW" else code.upper()


def _load_list_from_file(path: str) -> list[str]:
    items: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # allow comma-separated items on a single line as well
            parts = [p.strip() for p in s.split(",") if p.strip()]
            items.extend(parts or [s])
    return items


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    try:
        import pandas as pd  # type: ignore
        # Opt-in to pandas future behavior to avoid pytrends fillna downcasting warning
        try:
            pd.set_option('future.no_silent_downcasting', True)
        except Exception:
            pass
    except Exception:
        print("pandas is required. Install with: pip install pandas", file=sys.stderr)
        return 2

    TrendReq = _require_pytrends()

    # Load keywords: prefer file if provided
    if args.keywords_file:
        try:
            kws = _load_list_from_file(args.keywords_file)
        except Exception as e:
            print(f"Failed to read keywords file '{args.keywords_file}': {e}", file=sys.stderr)
            return 2
    else:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if len(kws) == 0:
        print("No keywords provided", file=sys.stderr)
        return 2
    if len(kws) > 5:
        print(
            "Google Trends compares up to 5 terms at once; taking first 5."
            " For larger sets, run multiple passes or narrow the list.",
            file=sys.stderr,
        )
        kws = kws[:5]

    geos = [g.strip() for g in args.geo.split(",") if g.strip()]
    geos = geos or DEFAULT_GEOS

    rows = []

    # Prepare optional proxies list (pytrends rotates through list)
    proxies: list[str] = []
    if args.proxy:
        proxies = [p.strip() for p in str(args.proxy).split(",") if p.strip()]

    import random

    # Optional cookie header (from args or env). Prefer file > flag > env.
    cookie_header: str = ""
    if args.cookie_file:
        try:
            with open(args.cookie_file, "r", encoding="utf-8") as fh:
                cookie_header = fh.read().strip()
        except Exception as e:
            print(f"[warn] Failed to read cookie file: {e}", file=sys.stderr)
    if not cookie_header and args.cookie:
        cookie_header = str(args.cookie).strip()
    if not cookie_header:
        cookie_header = os.environ.get("TRENDS_COOKIE", "").strip()

    def _attempt_fetch(geo: str):
        """Build a fresh TrendReq and fetch IOT with manual retry/backoff.

        Returns (pytrends, iot_df) on success.
        """
        last_err: Exception | None = None
        for attempt in range(max(1, int(args.retries) + 1)):
            try:
                from pytrends.request import TrendReq  # local import per attempt
                py = TrendReq(
                    hl=args.hl,
                    tz=0,
                    retries=int(args.retries),
                    backoff_factor=float(args.backoff),
                    proxies=proxies,
                    requests_args={
                        "headers": {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0 Safari/537.36"
                            ),
                            **({"Cookie": cookie_header} if cookie_header else {}),
                        }
                    },
                )
                py.build_payload(kws, cat=0, timeframe=args.timeframe, geo=geo, gprop="youtube")
                iot_df = py.interest_over_time()
                return py, iot_df
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                is_429 = "429" in msg or "Too Many Requests" in msg
                if attempt >= int(args.retries):
                    break
                delay = max(0.0, float(args.backoff) * (2 ** attempt) + random.uniform(0, max(0.0, float(args.jitter))))
                kind = "429" if is_429 else "temporary error"
                print(f"[warn] {geo or 'WW'}: {kind}; retrying in {delay:.1f}s…", file=sys.stderr)
                time.sleep(delay)
        raise last_err if last_err else RuntimeError("unknown error")

    for geo_in in geos:
        geo = _normalize_geo(geo_in)
        label = geo_in.upper()
        try:
            pytrends, iot = _attempt_fetch(geo)
            if iot is None or iot.empty:
                print(f"[warn] No data for {label}")
                continue
            if "isPartial" in iot.columns:
                iot = iot.drop(columns=["isPartial"])
            means = iot.mean().to_dict()
            row = {"geo": label, **{k: float(means.get(k, 0.0)) for k in kws}}
            rows.append(row)

            if args.related:
                # related_queries may also 429; best effort
                try:
                    rqs = pytrends.related_queries() or {}
                except Exception as e:
                    print(f"[warn] related queries failed for {label}: {e}", file=sys.stderr)
                    rqs = {}
                print(f"\n=== Rising related queries [{label}] ===")
                for k in kws:
                    rq = rqs.get(k) or {}
                    rising = rq.get("rising") if isinstance(rq, dict) else None
                    if rising is not None and not rising.empty:
                        top = rising.head(10)[["query", "value"]]
                        print(f"\n{k}:")
                        # Print as simple text table
                        for _, r in top.iterrows():
                            print(f"  - {r['query']} ({r['value']})")
                    else:
                        print(f"\n{k}: (no rising queries)")
            # Sleep between geos with jitter
            time.sleep(max(0.0, float(args.sleep) + random.uniform(0, max(0.0, float(args.jitter)))))
        except KeyboardInterrupt:
            print("Interrupted")
            return 130
        except Exception as e:
            print(f"[error] {label}: {e}", file=sys.stderr)
            # continue to next geo
            time.sleep(max(0.0, float(args.sleep) + random.uniform(0, max(0.0, float(args.jitter)))))
            continue

    if not rows:
        print("No summary data produced.")
        return 1

    df = pd.DataFrame(rows)
    # Pretty print (wide or vertical)
    try:
        from tabulate import tabulate  # type: ignore
        print("\n=== Mean interest over time (YouTube Search) ===")
        if getattr(args, "display", "wide") == "wide":
            print(tabulate(df, headers="keys", tablefmt="github", showindex=False))
        else:
            # Vertical per-geo: show keyword, mean, and an ascii bar
            def _bar(v: float, width: int = 20) -> str:
                try:
                    v = max(0.0, min(100.0, float(v)))
                except Exception:
                    v = 0.0
                filled = int(round(v / 100.0 * width))
                return "█" * filled + "░" * (width - filled)

            for _, row in df.iterrows():
                geo_label = str(row.get("geo", ""))
                print(f"\n--- [{geo_label}] ---")
                kv_list = []
                for k in kws:
                    val = float(row.get(k, 0.0))
                    kv_list.append({"keyword": k, "mean": round(val, 2), "bar": _bar(val)})
                # Sort descending by mean for readability
                kv_list.sort(key=lambda r: r["mean"], reverse=True)
                print(tabulate(kv_list, headers="keys", tablefmt="github", showindex=False))
    except Exception:
        # Fallback plain print
        if getattr(args, "display", "wide") == "wide":
            print(df.to_string(index=False))
        else:
            for _, row in df.iterrows():
                print(f"\n[{row.get('geo','')}]")
                for k in kws:
                    print(f"  - {k}: {row.get(k, 0.0)}")

    if args.output:
        try:
            df.to_csv(args.output, index=False)
            print(f"\nSaved CSV: {args.output}")
        except Exception as e:
            print(f"Failed to save CSV: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

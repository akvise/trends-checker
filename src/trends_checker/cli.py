from __future__ import annotations

import argparse
import sys
import time
from typing import List
import os


DEFAULT_KEYWORDS = [
    "AI agents",
    "vibe coding",
    "cursor ide",
    "AI assistant",
    "prompt engineering",
]

DEFAULT_GEOS = ["WW", "US", "BR", "ES", "IN", "ID", "RU"]


def _require_pytrends():
    try:
        from pytrends.request import TrendReq  # type: ignore
        return TrendReq
    except Exception as e:
        print("pytrends is not installed. Install with: pip install pytrends", file=sys.stderr)
        raise


def _parse_interval(value: str) -> float:
    """Parse interval string like '6h', '30m', '1d' into seconds."""
    value = value.strip().lower()
    if value.endswith("h"):
        return float(value[:-1]) * 3600
    elif value.endswith("d"):
        return float(value[:-1]) * 86400
    elif value.endswith("m"):
        return float(value[:-1]) * 60
    else:
        try:
            return float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid interval: {value!r}. Use format: 30m, 6h, 1d")


def _parse_threshold(value: str) -> float:
    """Parse threshold percentage."""
    try:
        v = float(value)
        if v < 0:
            raise argparse.ArgumentTypeError(f"Threshold must be positive: {v}")
        return v
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid threshold: {value!r}")


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="trends-checker",
        description="Analyze Google Trends interest across different search categories (Web, YouTube, Images, News, Shopping).",
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
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format: table (default), json, or csv (printed to stdout)",
    )
    p.add_argument(
        "--group",
        choices=["web", "youtube", "images", "news", "shopping"],
        default="web",
        help="Search category: web (default), youtube, images, news, shopping",
    )
    p.add_argument(
        "--related",
        action="store_true",
        help="Fetch and print rising related queries per keyword per region",
    )
    p.add_argument(
        "--dataforseo-key",
        type=str,
        default=os.environ.get("DATAFORSEO_KEY", ""),
        help="DataForSEO API credentials in format username:password. Enables rate-limit-free trend analysis. See https://app.dataforseo.com",
    )
    # --watch mode arguments
    p.add_argument(
        "--watch",
        action="store_true",
        help="Enable watch mode: continuously poll and alert on significant changes",
    )
    p.add_argument(
        "--interval",
        type=_parse_interval,
        default=21600.0,
        help="Polling interval in watch mode (default: 6h). Examples: 30m, 6h, 1d",
    )
    p.add_argument(
        "--threshold",
        type=_parse_threshold,
        default=20.0,
        help="Percentage change threshold to trigger an alert (default: 20%%)",
    )
    p.add_argument(
        "--watch-output",
        type=str,
        default="",
        help="Path to write watch events as JSON (for external monitoring integration)",
    )
    return p.parse_args(argv)


def _normalize_geo(code: str) -> str:
    return "" if code.upper() == "WW" else code.upper()


def _map_group_to_gprop(group: str) -> str:
    """Map user-friendly group names to pytrends gprop values."""
    mapping = {
        "web": "",           # Google Web Search (default)
        "youtube": "youtube", # YouTube Search
        "images": "images",  # Google Images Search
        "news": "news",      # Google News Search  
        "shopping": "froogle", # Google Shopping (pytrends uses 'froogle' internally)
    }
    return mapping.get(group, "")


def _format_group_name(group: str) -> str:
    """Format group name for display."""
    names = {
        "web": "Web",
        "youtube": "YouTube",
        "images": "Images",
        "news": "News",
        "shopping": "Shopping",
    }
    return names.get(group, "Web")


def _format_watch_interval(seconds: float) -> str:
    """Format a time interval in seconds to a human-readable string."""
    if seconds >= 86400:
        d = int(seconds // 86400)
        return f"{d}d"
    elif seconds >= 3600:
        h = int(seconds // 3600)
        return f"{h}h"
    else:
        m = int(seconds // 60)
        return f"{m}m"


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


def run_dataforseo(keywords: List[str], args) -> None:
    """Use DataForSEO API as backend — no rate limits, real search volumes."""
    import urllib.request
    import base64
    import json

    creds = args.dataforseo_key
    if ":" not in creds:
        print("Error: --dataforseo-key must be in username:password format", file=sys.stderr)
        print("Sign up at https://app.dataforseo.com", file=sys.stderr)
        return

    username, password = creds.split(":", 1)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()

    payload = json.dumps([{
        "keywords": keywords[:5],
        "type": "web",
        "language_code": "en",
    }]).encode()

    req = urllib.request.Request(
        "https://api.dataforseo.com/v3/keywords_data/google_trends/explore/live",
        data=payload,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        if result.get("status_code") == 20000:
            print(f"\n📊 DataForSEO Trends (no rate limits)\n{'─' * 55}")
            tasks = result.get("tasks", [])
            for task in tasks:
                res = task.get("result") or []
                items = res[0].get("items", []) if res else []
                for item in items:
                    kw = item.get("keyword", "")
                    vals = item.get("data", {}).get("values", [])
                    avg = sum(v.get("value", 0) for v in vals) / len(vals) if vals else 0
                    bar = "█" * int(avg / 5) + "░" * (20 - int(avg / 5))
                    print(f"  {kw:<32} [{bar}] {avg:.0f}/100")
        else:
            print(f"DataForSEO error {result.get('status_code')}: {result.get('status_message', 'Unknown')}", file=sys.stderr)

    except Exception as e:  # noqa: BLE001
        print(f"DataForSEO request failed: {e}", file=sys.stderr)
        print("Falling back to Google Trends...", file=sys.stderr)


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

    # DataForSEO backend — rate-limit-free alternative to Google Trends
    if args.dataforseo_key:
        run_dataforseo(kws, args)
        return 0

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
                py.build_payload(kws, cat=0, timeframe=args.timeframe, geo=geo, gprop=_map_group_to_gprop(args.group))
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

    def _run_watch_cycle(baseline: dict | None = None) -> tuple[pd.DataFrame, dict, list]:
        """Run a single trends fetch and return (df, new_baseline, events).
        
        If baseline is provided, compute change events against it.
        """
        import datetime as _dt
        rows = []
        events = []
        for geo_in in geos:
            geo = _normalize_geo(geo_in)
            label = geo_in.upper()
            try:
                pytrends, iot = _attempt_fetch(geo)
                if iot is None or iot.empty:
                    continue
                if "isPartial" in iot.columns:
                    iot = iot.drop(columns=["isPartial"])
                means = iot.mean().to_dict()
                row = {"geo": label, **{k: float(means.get(k, 0.0)) for k in kws}}
                rows.append(row)

                if baseline:
                    base_geo = baseline.get(label, {})
                    for kw in kws:
                        new_val = float(means.get(kw, 0.0))
                        old_val = float(base_geo.get(kw, 0.0))
                        if old_val > 0:
                            pct_change = ((new_val - old_val) / old_val) * 100.0
                            abs_pct = abs(pct_change)
                            if abs_pct >= args.threshold:
                                direction = "SPIKE" if pct_change > 0 else "DECLINE"
                                symbol = "⚠️ " if direction == "SPIKE" else "📉"
                                event = {
                                    "keyword": kw,
                                    "geo": label,
                                    "direction": direction,
                                    "pct_change": round(pct_change, 1),
                                    "old_value": round(old_val, 2),
                                    "new_value": round(new_val, 2),
                                    "threshold": args.threshold,
                                    "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
                                }
                                events.append(event)
                                print(
                                    f"{symbol} {direction}: \"{kw}\" "
                                    f"{'+' if pct_change > 0 else ''}{pct_change:.1f}% ({label}) "
                                    f"— {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
                                )

                time.sleep(max(0.0, float(args.sleep) + random.uniform(0, max(0.0, float(args.jitter)))))
            except Exception as e:
                print(f"[error] {label}: {e}", file=sys.stderr)
                time.sleep(max(0.0, float(args.sleep) + random.uniform(0, max(0.0, float(args.jitter)))))
                continue

        df = pd.DataFrame(rows)

        # Build new baseline: geo -> {kw: value}
        new_baseline = {}
        for _, row in df.iterrows():
            geo_label = str(row.get("geo", ""))
            new_baseline[geo_label] = {k: float(row.get(k, 0.0)) for k in kws}

        return df, new_baseline, events

    # --WATCH MODE--
    if getattr(args, "watch", False):
        import datetime as _dt
        print(f"\n[watch mode] Polling every {_format_watch_interval(args.interval)}, threshold={args.threshold}%")
        print("Press Ctrl+C to stop.\n")

        all_events = []
        df, baseline, events = _run_watch_cycle(baseline=None)
        all_events.extend(events)
        if events:
            print(f"\n{'='*60}")
            print(f"📊 Baseline established — {len(events)} initial alert(s)")
            print(f"{'='*60}\n")

        while True:
            delay = args.interval
            print(f"[watch] Next poll in {_format_watch_interval(delay)}...", file=sys.stderr)
            time.sleep(delay)
            try:
                _, new_baseline, events = _run_watch_cycle(baseline=baseline)
                all_events.extend(events)
                baseline = new_baseline
                if args.watch_output:
                    import json as _json
                    try:
                        with open(args.watch_output, "w", encoding="utf-8") as fh:
                            _json.dump(all_events, fh, indent=2, ensure_ascii=False)
                    except Exception as e:
                        print(f"[warn] Failed to write watch output: {e}", file=sys.stderr)
            except KeyboardInterrupt:
                print("\n[watch] Stopped.")
                if args.watch_output and all_events:
                    import json as _json
                    try:
                        with open(args.watch_output, "w", encoding="utf-8") as fh:
                            _json.dump(all_events, fh, indent=2, ensure_ascii=False)
                        print(f"Saved {len(all_events)} events to {args.watch_output}")
                    except Exception:
                        pass
                return 0

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

    # --format json / csv — machine-readable output to stdout
    fmt = getattr(args, "format", "table")
    if fmt == "json":
        import json as _json
        output_data = []
        for _, row in df.iterrows():
            entry = {"geo": str(row.get("geo", ""))}
            for k in kws:
                entry[k] = round(float(row.get(k, 0.0)), 2)
            output_data.append(entry)
        print(_json.dumps(output_data, indent=2, ensure_ascii=False))
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                _json.dump(output_data, fh, indent=2, ensure_ascii=False)
            print(f"\nSaved JSON: {args.output}", file=sys.stderr)
        return 0
    elif fmt == "csv":
        print(df.to_csv(index=False), end="")
        if args.output:
            df.to_csv(args.output, index=False)
            print(f"\nSaved CSV: {args.output}", file=sys.stderr)
        return 0

    # Pretty print (wide or vertical)
    try:
        from tabulate import tabulate  # type: ignore
        print(f"\n=== Mean interest over time (Google {_format_group_name(args.group)} Search) ===")
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

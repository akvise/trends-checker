# Contributing to trends-checker

Thanks for wanting to help! This is a small, focused CLI — contributions welcome.

## Setup

```bash
git clone https://github.com/akvise/trends-checker.git
cd trends-checker
pip install -e .
```

## Running locally

```bash
# Basic run (Google Trends)
trends-checker --keywords "AI agents,vibe coding" --geo US

# With DataForSEO (no rate limits)
trends-checker --keywords "AI agents" --dataforseo-key user@email.com:password
```

## Adding a new search group

Search groups live in `src/trends_checker/cli.py` in the `--group` argument choices.
To add a new one (e.g. `froogle`):

1. Add `"froogle"` to the `choices` list in `_parse_args()`
2. Map it to the correct `gprop` value in `_fetch_trends()` (or add a new backend branch)
3. Update the README table under **Search Categories**

## Adding a new output format

Output rendering is in `_print_table()` / the main `run()` function.
To add `--json`:

1. Add `--json` flag in `_parse_args()`
2. In `run()`, branch on `args.json` and `print(json.dumps(results))`
3. Add an example to the README

## PR checklist

- [ ] `pip install -e . && trends-checker --help` works without errors
- [ ] `python -c "import trends_checker"` succeeds
- [ ] New behavior is covered by a smoke test or README example
- [ ] No secrets or API keys committed
- [ ] `ruff check src/` passes (install: `pip install ruff`)

## Linting

```bash
pip install ruff
ruff check src/
```

We're not strict about style — just keep it readable and consistent with the existing code.

## Questions?

Open an issue or reach out via GitHub Discussions.

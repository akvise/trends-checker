# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Trends Checker is a CLI tool for analyzing Google Trends data across different search categories (Web, YouTube, Images, News, Shopping). It uses the unofficial pytrends library to fetch trend data and provides various visualization and export options.

## Development Commands

### Setup and Installation
```bash
make install          # Create venv and install dependencies
```

### Running the Application  
```bash
make run              # Run with default keywords and settings (web search)
make run-related      # Run with related queries enabled
trends-checker        # Direct CLI execution (after installation)

# Different search categories
trends-checker --group web       # Web search (default)
trends-checker --group youtube   # YouTube search
trends-checker --group images    # Google Images
trends-checker --group news      # Google News  
trends-checker --group shopping  # Google Shopping
```

### Maintenance
```bash
make clean            # Remove Python caches and build artifacts
make reset            # Remove venv and all caches (full reset)
make help             # Show all available make targets
```

## Architecture

### Core Components

**Single-module CLI application** (`src/trends_checker/cli.py`):
- **Argument parsing** - Handles 16+ CLI parameters including keywords, search groups, geo regions, timeframes, display options
- **Search category selection** - Supports Web, YouTube, Images, News, and Shopping search categories via --group flag
- **Keyword management** - Supports both inline keywords and file-based keyword lists with comment support
- **Data fetching** - Uses pytrends with custom retry logic, rate limiting, and cookie support
- **Output formatting** - Two display modes (vertical with ASCII bars, wide table) plus CSV export
- **Error handling** - Comprehensive 429 rate limit handling with exponential backoff and jitter

### Key Constraints and Behaviors

**Google Trends Limitations**:
- Maximum 5 keywords per request (enforced by taking first 5)
- Search category specific (`gprop` parameter: "", "youtube", "images", "news", "froogle")
- Relative interest scores (0-100 scale per timeframe/region)
- Aggressive rate limiting requiring delays and retry strategies

**Rate Limiting Strategy**:
- Configurable sleep between requests (default 1.2s with jitter)
- Exponential backoff on 429 errors with custom retry attempts
- Optional browser cookie support for authenticated sessions
- Fresh TrendReq instance per geography to avoid session pollution

### Configuration Files

**keywords.txt** - One keyword per line format:
```
# Comments start with #
keyword one
keyword two,keyword three  # Comma-separated also supported
```

**cookie.txt** - Single line containing full browser Cookie header for bypassing rate limits

### Default Behavior

- **Search Group**: Web search (Google web search, not YouTube)
- **Keywords**: 5 English YouTube translation/dubbing terms (legacy default)
- **Regions**: WW,US,BR,ES,IN,ID,RU (worldwide + major markets)  
- **Timeframe**: `today 12-m` (last 12 months)
- **Display**: Vertical layout with ASCII progress bars sorted by interest

## Working with Keywords

When modifying `keywords.txt`:
- Each keyword becomes a column in the output data
- Comments (#) and blank lines are ignored
- Both line-by-line and comma-separated formats supported
- Google enforces 5-keyword limit per request

## Common Patterns

**Testing market demand**: Load business hypothesis keywords into `keywords.txt` and run analysis across multiple regions and search categories to validate interest levels.

**Search category comparison**: Test the same keywords across different groups (`--group web` vs `--group youtube` vs `--group shopping`) to understand where demand exists.

**Handling rate limits**: Use `--cookie-file cookie.txt` with fresh browser cookies when encountering 429 errors.

**Regional analysis**: Use `--geo` to focus on specific markets, `--display vertical` to compare keyword performance within regions.

**Category-specific insights**: Use `--group images` for visual content trends, `--group news` for current events, `--group shopping` for product demand.
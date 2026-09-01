# AI Job Collection and Resume Matching Agent

*English summary. The full documentation is in Chinese: [README.md](README.md).*

Built on `boss-zhipin-scraper`'s Chrome CDP collection capability, but the core of this project is not "clicking through web pages" — it turns job postings into a structured system usable for job-search decisions: **collect → merge details → deduplicate → normalize → persist → structure JDs → analyze skills → match resume → final report**, in one command.

## Positioning

- The external `boss-zhipin-scraper` is only the **collection engine**, integrated through the `app/integrations/boss_zhipin` adapter layer. The main project does not depend on its internals.
- The main project owns domain modeling, persistence, structured analysis, AI resume matching, and report generation.
- AI is responsible only for "structured match analysis of a single job posting". **Ranking, formatting, and the final report are produced deterministically by system code**, not left to AI improvisation.

## Prerequisite: start Chrome CDP

Real collection requires a dedicated Chrome instance with remote debugging enabled (it does not reuse your main browser profile). **Start it and log in to BOSS before the first run**, or collection fails when it cannot reach `127.0.0.1:9222` (`WinError 10061` on Windows).

```powershell
python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --setup-chrome --cdp-port 9222
python external/boss-zhipin-scraper/scripts/boss_cdp_raw.py --check --cdp-port 9222
```

## Quick start

```powershell
python scripts/run_full_job_agent.py `
  --resume-file private/resume.pdf `
  --keyword "AI Agent" `
  --cities <city-list> `
  --pages 1 `
  --scraper-root external/boss-zhipin-scraper `
  --output-dir data/reports `
  --max-jobs 30 `
  --include-detail
```

`run_full_job_agent.py` runs the full pipeline in order and writes each step's success or failure into a run trace. Outputs land in `--output-dir` prefixed by `run_id`.

For the technical route, database modeling, JD structuring, skill analysis, AI matching details, compliance boundaries, collection-safety checks, and local verification, see the Chinese [README.md](README.md).

## Requirements

Requires your own `AI_MATCHER_API_KEY` or `OPENAI_API_KEY` for the AI matching step. Keys are never persisted or transmitted anywhere except the configured provider.

## License

MIT — see [LICENSE](LICENSE).

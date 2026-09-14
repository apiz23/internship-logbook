# Ozone Project

## Overview
Software Engineering intern tasks related to the Ozone project — competition proposal development and creator research/scraping pipeline.

## Current Status
In Progress

## Phases
1. **Competition Proposal** (Weeks 2-3) — Completed. Structured proposal covering theme, eligibility, format, judging criteria, prizes, rules. Budget reviewed. Legal mismatch with ToS identified.
2. **Creator Research/Scraping** (Weeks 4-6) — Completed. System converted into a native Hermes Agent Plugin with `creator_scrape`, `creator_batch_scrape`, `creator_validate` tools and `/creator-discover` command. `data/Creator-Intel-CRM-List.csv` established as the Master CRM / single source of truth. `input_channels.csv` deprecated as active dependency. Cron job pipeline operational (every 3m, repeat=5). CRM contains 1,052 creators with no duplicate ProfileURLs or missing URLs. Automated tests: 20/20 passed. Plugin Doctor: 3 tools, 0 hooks.

## Known Issues
- Legal mismatch with Ozone's live Terms of Service regarding age requirements and public upload availability.
- Difficulty obtaining creator information from social media platforms due to platform structure differences and access limitations.
- Low email yield (~4 valid emails from 120 profiles); Instagram/Meta profiles lacking API access require manual review.

## Next Steps
- Resolve legal mismatch with Ozone ToS
- Continue exploring alternative scraping approaches
- Coordinate with Full Stack Dev Kidd for Hermes configuration support
- Complete GitHub commit and push of the plugin conversion changes
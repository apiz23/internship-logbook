# Ozone Project

## Overview
Software Engineering intern tasks related to the Ozone project — competition proposal development and creator research/scraping pipeline.

## Current Status
In Progress

## Phases
1. **Competition Proposal** (Weeks 2-3) — Completed. Structured proposal covering theme, eligibility, format, judging criteria, prizes, rules. Budget reviewed. Legal mismatch with ToS identified.
2. **Creator Research/Scraping** (Weeks 4-6) — In Progress. Cron job pipeline created and executed for automated discovery/scraping. Successfully discovered and scraped 22 new creators across TikTok, YouTube, Instagram, and Threads. CRM grew from 1027 → 1065 → 1049 rows (after cleanup and manual scrapes). CRM data quality cleanup performed: platform normalization, removal of 18 invalid rows (12 Facebook URLs + 6 duplicates), fixed 3 @p handles. AGENTS.md extended with mandatory CRM Data Quality Gate rules (Sections 17-18).

## Known Issues
- Legal mismatch with Ozone's live Terms of Service regarding age requirements and public upload availability.
- Difficulty obtaining creator information from social media platforms due to platform structure differences and access limitations.
- Low email yield (~4 valid emails from 120 profiles); Instagram/Meta profiles lacking API access require manual review.

## Next Steps
- Resolve legal mismatch with Ozone ToS
- Continue exploring alternative scraping approaches
- Coordinate with Full Stack Dev Kidd for Hermes configuration support
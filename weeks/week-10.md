# Week 10

## Monday (Oct 5)

### Task Detail

Conducted manual staging QA testing for the Ozone platform using the Full Manual Test Checklist. Completed approximately 105 test items across public pages, identity and account features, creator video lifecycle, and watching/engagement features. Logged three defects in the Staging Bug Tracker: BUG-31 (duplicate waitlist email accepted), BUG-32 (implausible birth date accepted), and BUG-33 (missing confirmation toast for notification preferences). Remaining moderation, admin, and cross-cutting test items are pending.

1. **Public surface testing** — Validated landing page and Get Early Access/waitlist form. Tested catalog browsing: Home, Browse, Trending, Creators, Category, and Channel pages. Verified watch page and 404 page rendering.
2. **Identity & account testing** — Tested login/logout flows, account-related features, birthdate and profile settings, restricted-content settings.
3. **Creator video lifecycle testing** — Tested video upload, encoding, captions, thumbnails, visibility, trash/restore, and My Videos.
4. **Watching & engagement testing** — Verified video playback on Chrome desktop and Android. Tested like, save, comments, and replies.
5. **Bug reporting** — Logged 3 defects in Staging Bug Tracker with Test Level: Staging and Status: Not Started.

### Issue

- BUG-31 (Medium): Duplicate email accepted in Get Early Access waitlist; no duplicate-email warning.
- BUG-32 (Medium): Implausible birth date (23 February 1900, ~126 years) accepted without validation.
- BUG-33 (Low): Notification preference changes saved but no confirmation toast displayed.
- Checklist items for BUG-31/32/33 need status change from Pass to Fail with bug IDs attached.
- Parts 5–7 (moderation, admin panel, cross-cutting) not started; some tests require developer/operator access.

### Proposed Solution

- Update checklist items for BUG-31, BUG-32, BUG-33 to Fail/unchecked with corresponding bug IDs.
- Continue remaining checklist sections (Parts 5–7) as developer/operator access becomes available.

### Status

In Progress

### Total Hours

8 hours

***

## Tuesday (Oct 6)

### Task Detail

1. **O'Chat — Functional and Network Testing**
   Conducted functional testing of the O'Chat application, focusing on chat send functionality and core flows on the latest production build. Completed two additional network resilience test cases covering offline image sending and video upload behaviour under interrupted network conditions. Overall checklist progress advanced to approximately 155/204 tests.
2. **O'Chat — Production Update Testing**
   Tested the O'Chat app on the latest production update — functional testing of the new release, exercised multiple features across the updated build.
3. **Bug Discovery and Documentation**
   Identified BUG-34 during group management testing: when an admin removes a user and then re-adds them, the backend restores membership correctly, but the UI continues to display the "You were removed from this group" dismissal badge. Reproduced on both iPhone and Android v1.0.2 and documented with screenshots.
4. **Automation / Tooling**
   Continued configuring and testing Hermes Agent, including statusline customization work and verification of the generic public widget implementation.

### Issue

- **BUG-34 (Medium):** O'Chat group membership UI does not clear the removal badge after the user is re-added by an admin. Likely a client-side cache or local state sync issue.

### Proposed Solution

Verify whether the group membership state is refreshed when the user returns to the group view. If the client caches the removed state, clearing local state on re-entry or triggering a membership sync after re-add should resolve it. Further investigation required.

### Status

- O'Chat functional testing: In Progress
- O'Care production update testing: Completed
- Network resilience tests: Completed (2 additional cases)
- BUG-34: Not started / Under investigation
- Hermes statusline customization: Completed

### Total Hours

8

***

## Wednesday (Oct 7)

### Task Detail

1. **Ozone — Manual Staging QA Testing**
   Continued manual staging QA testing using the Full Manual Test Checklist. Focused on non-legacy checklist items across Parts 1–4: Public Surface, Identity & Account, Creator Video Lifecycle, and Watching & Engagement. Excluded legacy sections from this session's scope per project convention.
2. **Checklist Review and Progress Tracking**
   Reviewed the Staging Full Manual Test Checklist and recorded current progress. New checklist (non-legacy): 258 items checked out of 1,169 total (22.1% pass rate). 911 items remain unchecked. Legacy sections (76 items) excluded from this session.
3. **Bug Discovery and Documentation**
   Identified BUG-35 during profile settings testing: when the user accesses the Profile Settings page in Tamil and updates their display name, clicking Save successfully updates the profile but the application unexpectedly switches the entire page back to English instead of preserving the selected Tamil language. Further testing confirmed this affects all non-English languages, not just Tamil — other language combinations (Bahasa Melayu, Chinese) exhibit the same behaviour.
4. **UI Issue Documentation**
   Identified a UI overflow issue: the Tamil "Sign out other devices" button text overflows the button boundary. Recorded as Low severity, Staging test level.

### Issue

- **BUG-35 (Medium)** — Saving profile changes in any non-English language redirects the page back to English instead of preserving the selected language. Affects Tamil, Bahasa Melayu, and Chinese. The profile update itself succeeds; only the UI language reverts.
- **UI Issue (Low)** — Tamil "Sign out other devices" button text overflows the button boundary.
- **BUG-31, BUG-32, BUG-33** — Remain open (Not Started) from Oct 5.

### Proposed Solution

- BUG-35: Investigate the profile save handler to determine why the locale is not preserved after a successful save. The issue may be related to a missing locale parameter in the save response or a redirect that does not include the language prefix.
- UI Issue: Adjust button padding or font size for Tamil text on the "Sign out other devices" button to prevent overflow.

### Status

- Ozone manual staging QA testing: In Progress
- BUG-35: Not Started / Under investigation
- UI overflow issue: Not Started / Under investigation
- BUG-31, BUG-32, BUG-33: Not Started (carried over from Oct 5)

### Total Hours

8

***

## Thursday (Oct 8)

### Task Detail

**Focus: O'Zone staging platform, manual browser testing only.**

1. **Test execution (Parts 3 and 4 of the Notion staging checklist)**
   - Part 3, Creator studio: upload form and validation, file/thumbnail/subtitle rules, upload process (progress, pause/resume, offline, reload, cancel, failure), My videos and Trash, edit video, analytics, channel branding and language checks. Result: 25 of 45 tests marked PASS, 20 open.
   - Part 4, Discovery, watching and interaction: Home/Browse/Trending/Creators, search and filters, watch page and player (quality, speed, subtitles, fullscreen, age gates), likes/saves/comments/replies, Library and playlists, channel page, follow and channel bell. Result: 55 of 74 tests marked PASS, 19 open.
   - Combined today: 80 of 119 tests marked PASS, 39 remaining.
   - Parts 1 and 2 (public site, sign-up and settings) were tested yesterday and are not counted here.
2. **Checklist preparation (supporting work)**
   - Converted the full Malay test plan into English in the Notion checklist, restructured into Parts 1-7 (343 tests in total).
   - Added Part 5 (reports, blocks, strikes and appeals, 30 tests), Part 6 (notifications, 22 tests) and Part 7 (cross-cutting checks, 23 tests) plus the known-bugs, non-browser and rate-limit appendices.
   - Fixed a nesting error that hid channel tests CHAN-02 to CHAN-07 under CHAN-01 in section 4.5.
   - Added a Documentation & UI Checklist linked view to the page, filtered to O'Zone only.
   - Still to convert: the admin panel sections (about 236 tests) and the setup section.

### Issue

No blocking issue identified during this task.

Note for follow-up: the PASS note on SRCH-08 (search when the browser blocks site data) reads "Nice cant log". That test allows a "Blocked" result if logging in again is not possible, so it may be expected behaviour rather than a defect, but it should be confirmed.

### Proposed Solution

- Clarify the SRCH-08 note and record it as Pass or Blocked.
- Finish the remaining 20 Part 3 and 19 Part 4 tests, then continue with Parts 5-7 (75 tests).
- After the admin sections are converted, run the admin tests and retire the old legacy sections.

### Status

In Progress

### Total Hours

8 hours

***

## Friday (Oct 9)

### Task Detail

Performed manual quality assurance testing on the O'Zone staging environment, focusing on subtitle rendering and responsive video playback on mobile devices.

Identified a UI issue where a long English subtitle sentence overflows the available subtitle area when playing a landscape video in the default portrait orientation on a mobile device. The final word is partially clipped, while other subtitles that wrap correctly onto two lines display as expected.

Reviewed the issue against the existing Staging — Full Manual Test Checklist and documented the finding in the Documentation & UI Checklist database. Recorded the reproduction steps, actual result, expected result, test environment, and supporting screenshot evidence.

Test video: https://ozone-adam-dev.ocgt.app/en/watch/01a118fb-9abb-711a-afa5-6d9ce11b2104/test-owmpjqra

### Issue

Long subtitle sentences overflow the available width of the video player in mobile portrait orientation, causing the final word to be partially clipped.

The issue appears to affect subtitle layout and text wrapping. Further investigation is required to determine whether the cause is subtitle rendering, player styling, or the subtitle file's line-break configuration.

Priority: Low.

### Proposed Solution

Review the subtitle rendering and responsive styling to ensure that subtitle text respects the available player width and wraps onto multiple lines when necessary.

Verify the behaviour using the affected landscape video in portrait orientation and compare it with subtitles that already display correctly across two lines. Check whether the subtitle file's timing and line-break formatting contribute to the issue before making any changes.

### Status

Pending Review — The UI issue has been documented in Notion with reproduction steps and screenshot evidence. The underlying cause and implementation fix have not yet been confirmed.

### Total Hours

Not specified — Record the actual time spent on investigation, testing, and documentation.

### Attachments

1. https://app.notion.com/p/3f445ae939598085bffec72f04b3623a
2. https://ozone-adam-dev.ocgt.app/en/watch/01a118fb-9abb-711a-afa5-6d9ce11b2104/test-owmpjqra
3. Screenshot evidence: mobile-Galaxy_S24_Ultra.png, attached to the Notion checklist entry.

---

*Generated by Internship Logbook on 2026-10-09*

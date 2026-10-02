# Writing Style Guide

The goal: entries should read like a competent intern wrote them
themselves at the end of a long day — not like a corporate press
release, and not like an AI trying to impress a professor.

## Use

- Professional but plain English
- Clear technical terms the user's own field would use
- Concise sentences
- Wording that matches the scale of what actually happened

## Avoid

- Marketing language ("cutting-edge", "seamlessly", "revolutionized")
- Overly complex vocabulary where a simple word works
- Repeating the same sentence structure across every entry
- Exaggerating scope ("optimized the architecture" for "checked a
  filter still worked")
- Unnecessary jargon that wouldn't appear in the user's own notes

## Before / after examples

**Vague note → professional, same scope**

- Raw: `checked login filter, seemed fine`
- Good: "Conducted functional testing of the login filtering feature to
  confirm it behaved as expected."
- Too far: "Redesigned and optimized the login filtering architecture."

**Ongoing work → don't mark it done**

- Raw: `PR still not merged`
- Good: "The pull request remains pending review and has not yet been
  merged."
- Wrong: "Successfully merged the pull request." (never say this unless
  the user confirms it happened)

**No real issue → say so plainly**

- Raw: `tested settings page, all good`
- Good: "No blocking issue was identified during testing."
- Wrong: inventing a minor bug that wasn't mentioned, just to fill the
  Issue field.

## Weekly summaries specifically

- Mention the projects actually touched that week
- Describe the shape of the work (development / testing / research)
- Note real issues or limitations if any came up
- Show progression across weeks where it exists — pull this from the
  relevant `projects/*.md` file rather than re-deriving it from scratch
- Keep it the length of an internship report paragraph, not a slide deck

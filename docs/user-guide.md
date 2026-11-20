# User Guide

## Students

1. Choose English or Bangla, create an account, then sign in.
2. Select lost or found, choose category/colour/location, and give a date and useful
   public description. Keep names, IDs, contact information and secret proof out of
   the public text and image.
3. Put hidden evidence in the separate private verification field. Confirm consent
   to external AI processing of public text and the optional image. Submit once.
4. Open My Reports to inspect processing state. New reports are processed on the
   next server tick, not immediately during upload. A candidate may arrive later.
5. Open a candidate and inspect text, image and attribute similarity. The percentage
   is not the probability that you own the object.
6. Only the lost-report owner can claim a current candidate. Describe the hidden
   evidence in the claim answer, then follow claim progress on the dashboard.
7. An admin verifies evidence, reserves an approved pair and records physical
   handover separately. Do not exchange a real item solely because of the score.

Active reports can be edited or archived until a pending claim freezes them.
Archival is terminal. Sign-in lasts one hour; a session expiry requires signing in
again. Language switching reloads the page; save edits before switching language.

## Review Desk

Sign in with the separately provisioned admin account and open `admin.html`.
Compare the claimant answer with both hidden details. Approve only after the
evidence is convincing; reject otherwise. Approval reserves both reports and
closes competing candidates/claims. Confirm physical handover only once the
verified owner has actually received the item. Returned outcomes remain visible.

The failed-work section exposes sanitized failure codes and explicit retries for
failed embedding/email work. Fix credentials or provider configuration before
retrying. A lifecycle conflict means the record changed; reload current state
rather than forcing a second approval.

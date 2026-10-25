# Member account change (username, email, lost login)

Use for "member can't log in", "change my username", "change my email". Never do this from an unverified request; the person must be confirmed as the account owner (reply from the address on file, or Zach confirms out of band).

Production change under the backup rule (`policies/approvals.md`): apply is not built yet, so do it over wp-cli after a `wp db export`. Do not run ad-hoc SQL.

## Username change

WordPress has no supported way to change `user_login` in the admin. Do it in the database.

1. **Verify the old login exists** and note the user ID: `webmaster access <site>` shows the roster; there is no user-lookup command yet, so confirm the login and ID with a read-only wp-cli query. Record roles, active memberships and subscriptions (they follow the user ID, not the login).
2. **Check the new login is unused**, case-insensitively, against both `user_login` and `user_nicename`, and that no other user has it as an email. If taken, stop and ask.
3. **Confirm the new value is valid**: lowercase letters, digits, `_`, `-`, `.` and `@` only; no spaces; not a reserved name.
4. **Change**: update `wp_users.user_login` (and `user_nicename` if it mirrored the old login) for that ID with a `wpdb->update` call, then `clean_user_cache($id)`. Take a DB backup first.
5. **Mailing-list sync**: check user meta the mailing-list or CRM plugin keeps (subscriber ID, last-synced email or login). If the sync keys on login or email, note the meta keys in the change log and trigger a resync or update the list entry so the member is not duplicated.
6. **Verify**: log in with the new login (member's test, or a password-reset email that reaches them), confirm roles and memberships unchanged, old login no longer works.
7. **Record** in the change log; tell the member.

## Email change

Same steps, targeting `user_email`; the new address must be unused. Send the confirmation to the new address. Check the mailing-list sync and any Stripe customer email (do not change Stripe; note it for Zach).

## Cannot log in

1. Confirm the account exists and is not blocked or on hold (membership status, subscription on-hold).
2. Send a password reset; if the email does not arrive, treat as `forms-email` (check Mailgun suppression list for the address).
3. Check for lockout from a security plugin, and 2FA state. Application Passwords do not fix a browser login.
4. A membership paused because a subscription is on hold explains "logged in but locked out of content". Route to `money-paths`.

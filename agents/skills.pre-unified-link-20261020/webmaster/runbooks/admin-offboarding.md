# Admin offboarding

Trigger: someone with admin, editor, or server access leaves or changes role. Do it the same day; delayed offboarding is the common failure.

1. **Inventory access** against the approved roster: WP user(s), Application Passwords (these bypass 2FA), SSH keys, hosting panel, DB users, registrar, DNS, Stripe, Mailgun, Google (Search Console, GA4), 1Password vault, Linear.
2. **Reassign content** owned by the user (posts, orders notes) before deleting; ask Zach for the new owner.
3. **Remove the WP user; revoke all Application Passwords** for them first.
4. **Rotate shared credentials** they knew: SSH keys, DB password, Stripe restricted keys and webhook secrets, Mailgun keys, any API keys in `wp-config.php`. Back up `wp-config.php` first; the client (owner of each account) performs or delegates it.
5. **Remove from third-party accounts** the client owns, and from the client's 1Password vault.
6. **Verify**: the roster diff matches the approved roster; old credentials fail; site and payments still work after rotation (Stripe webhook receiving, mail sending).
7. **Record** in the change log and the site bible.

Onboarding an admin is the reverse: least privilege, 2FA on, named account (never shared), added to the roster.

# Admin portal two-factor authentication

MFA is optional for each user. Signed-in admin portal users without MFA see a persistent reminder with a link to setup in their profile. It disappears automatically once MFA is enabled. Open your profile and use **Two-factor authentication → Set up authenticator**. The setup button opens the QR code directly. Scan it (or enter the setup key) in an authenticator app, then confirm within ten minutes with the app’s six-digit code; the final save opens a dialog asking for your current admin password. Setup does not change sign-in until that confirmation succeeds.

Save the ten recovery codes before leaving the page. Each code works once, alongside your password, when your authenticator is unavailable. Codes are shown only when created. Profile settings show how many remain; replacing codes invalidates the previous set. Disabling MFA or replacing recovery codes requires an unused authenticator or recovery code and password confirmation in the save dialog. Cancelling the dialog makes no change and clears the entered password.

After enabling MFA, admin sign-in requires your password and a current authenticator code or unused recovery code. A successful code cannot be reused; if you just used it for setup, wait for the app's next code. Ten failed second-factor attempts block verification for the remainder of a fifteen-minute attempt window, across processes and requests. Enrollment confirmation shares this limit, and restarting setup does not reset it.

Enabling/disabling MFA or replacing recovery codes signs out other sessions; the session performing the change stays signed in. Password resets and invitations do not disable MFA. Terminal tag login and customer portal authentication are unaffected. There is no email-based MFA bypass or portal administrator reset endpoint. If all factors are lost, use an authenticated operator recovery process; this feature does not introduce a weaker recovery path.

## Deployment

Apply database migration `0000066` before starting the updated backend; deploy the administration frontend with its regenerated API client. No new configuration or dependencies are required. Authenticator secrets are encrypted using a purpose-specific key derived from `core.secret_key`, with the user ID bound to the ciphertext. Recovery codes contain 128 random bits each and are stored as hashes. Keep the server secret stable, secret, and backed up separately from the database: changing or losing it makes enrolled authenticator secrets unreadable. Production must use HTTPS and a strong server secret.

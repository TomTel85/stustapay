# Central privacy policy

Select the root node in the administration portal and open **Global Settings → Privacy Policy**
(**Globale Einstellungen → Datenschutzerklärung**). Root users with `node_administration` can edit
German and English Markdown texts and preview them before saving. All customer portals use these
texts. Events have no privacy-policy editor or configurable privacy URL.

Migration `0000065` imports the oldest non-empty event privacy policy for each language when no
central value already exists. It then deletes all event privacy-policy texts and clears legacy
privacy URLs. Differing event versions are discarded. Review the selected central texts after
migration. Empty central text hides the privacy-policy link and acceptance checkbox for that language.

The event API retains the legacy URL field for compatibility, but event saves ignore it and always
store an empty value. Privacy-policy translations in event create/update payloads are also ignored.
Database constraints prevent storing either event-specific policy texts or URLs. The customer-portal
API derives the privacy URL from the requested portal base URL and `/datenschutz`.

Apply migrations through `0000065` before running the updated backend, then publish the administration
frontend. The customer-portal and terminalserver API schemas are unchanged.

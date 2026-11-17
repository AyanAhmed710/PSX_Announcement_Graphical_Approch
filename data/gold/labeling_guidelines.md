# Gold-set labeling guidelines

Applied by the LLM when proposing labels, and by the human reviewer.

- **G1 — one label per document = its primary purpose**, as stated in the
  subject line / cover letter. Attachments refine, they don't override.
- **G2 — general meetings.** Notices, cancellations and resolutions of an
  AGM/EGM → AGM_EGM, even when the agenda includes approving a dividend or
  other business. Exceptions (they create graph edges): when the document's
  only substantive business is the election/appointment of directors →
  EXEC_CHANGE with every elected person listed; when it is a merger /
  acquisition / scheme → MERGER_ACQUISITION.
  A *notice* of an upcoming director election is still AGM_EGM — no role has
  changed yet; the *result* of the election is EXEC_CHANGE. Letters about
  extending / delaying an AGM are AGM_EGM.
  Same logic for a single corporate action approved at a general meeting
  (buy-back, rights issue): labeled by the action (BUYBACK / RIGHTS_ISSUE).
- **G2b — merger `kind`.** Merger or amalgamation of one company into
  another → MERGER (even when effected through a scheme of arrangement);
  SCHEME_OF_ARRANGEMENT only for schemes that are not mergers (demerger,
  reorganisation). `stage` = the latest step the document reports.
- **G3 — board meetings.** Notice of an upcoming board meeting (with or
  without a closed period, "for declaration of any entitlement") →
  BOARD_MEETING. A board *decision* letter announcing results/payouts is
  labeled by what it announces (FINANCIAL_RESULT / DIVIDEND).
- **G4 — DIVIDEND** needs a declared, approved, credited or dispatched payout
  (cash, bonus or specie). Board meetings that will only *consider* one are
  BOARD_MEETING. Financial-results announcements that also declare a dividend
  are FINANCIAL_RESULT (primary purpose), dividend details noted.
- **G5 — EXEC_CHANGE** = an actual change in a person's role (appointment,
  resignation, retirement, election, death). Disclosures of share dealings by
  directors/executives are DISCLOSURE_INTEREST, not EXEC_CHANGE. The letter's
  signatory is never an entity unless their own role changes.
- **G6 — TRANSMISSION_REPORT** = cover letter transmitting quarterly / half-
  yearly / annual reports or financial statements; FINANCIAL_RESULT = the
  announcement of results themselves (financial results / Form-3).
- **G7 — MATERIAL_INFO** = disclosures made as "material information" /
  price-sensitive information, unless the content is clearly one of the
  specific types (a merger announced as material information →
  MERGER_ACQUISITION).
- **G8 — OTHER** = regulatory correspondence and anything fitting no type.
- Details: values not stated in the document are null — never guessed.

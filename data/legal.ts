export type LegalSection = {
  heading: string;
  body: string[];
};

export type LegalDoc = {
  title: string;
  summary: string;
  updated: string;
  sections: LegalSection[];
};

export const privacyDoc: LegalDoc = {
  title: 'Privacy Policy',
  summary:
    'How Optic handles account data, audit inputs, reports, analytics, and '
    + 'privacy choices across the website and product.',
  updated: 'May 5, 2026',
  sections: [
    sec('Scope', [
      'This policy covers Optic pages, accounts, pilot intake, support, '
        + 'analytics, audit workflows, generated reports, and related '
        + 'services.',
      'Optic is designed around private review. Raw personal source material '
        + 'should stay local or inside user-authorized systems unless a user '
        + 'chooses to share it for a specific workflow.',
    ]),
    sec('Information Collected', [
      'Optic may collect contact details, account settings, authentication '
        + 'state, product events, device metadata, support messages, and '
        + 'payment or subscription status.',
      'For audits, Optic may process user-authorized public profiles, files, '
        + 'links, notes, and other inputs needed to produce a private report.',
    ]),
    sec('Use Of Information', [
      'Information is used to operate the service, produce requested audit '
        + 'outputs, secure accounts, debug reliability issues, respond to '
        + 'support, and improve product quality.',
      'Optic does not create a public score, sell personal audit contents, or '
        + 'publish reports without user direction.',
    ]),
    sec('Retention And Control', [
      'Account and operational records are kept only as long as needed for '
        + 'service, legal, security, or billing purposes.',
      'Users may request access, correction, deletion, or export by contacting '
        + 'hello@tryoptic.app.',
    ]),
  ],
};

export const termsDoc: LegalDoc = {
  title: 'Terms of Service',
  summary:
    'The rules for using Optic, requesting audits, reviewing outputs, and '
    + 'using the site or product responsibly.',
  updated: 'May 5, 2026',
  sections: [
    sec('Agreement', [
      'By using Optic, creating an account, requesting a pilot audit, or '
        + 'reviewing a report, the user agrees to these terms.',
      'Optic may update these terms when the product changes. Continued use '
        + 'after an update means the updated terms apply.',
    ]),
    sec('Acceptable Use', [
      'Use Optic only with data and accounts the user has the right to review. '
        + 'Do not use the service to harass, profile, discriminate, or make '
        + 'automated decisions about another person.',
      'Do not interfere with service operation, bypass access controls, upload '
        + 'malware, or attempt to extract another user account or report.',
    ]),
    sec('Audit Outputs', [
      'Reports are informational and may contain probabilistic or incomplete '
        + 'interpretations. Users remain responsible for decisions made from '
        + 'the output.',
      'Optic provides ways to inspect signals, risks, contradictions, and '
        + 'repair paths, but it does not guarantee any hiring, investment, '
        + 'partnership, or reputation result.',
    ]),
    sec('Service Changes', [
      'Features may change as Optic moves through pilot and production '
        + 'stages. Access may be limited for security, abuse prevention, or '
        + 'operational reliability.',
      'Questions about these terms can be sent to hello@tryoptic.app.',
    ]),
  ],
};

export const cookiesDoc: LegalDoc = {
  title: 'Cookie Policy',
  summary:
    'How Optic uses cookies, local storage, and similar browser technologies '
    + 'for security, preferences, analytics, and product reliability.',
  updated: 'May 5, 2026',
  sections: [
    sec('Technologies Used', [
      'Optic may use cookies, local storage, session storage, pixels, SDKs, '
        + 'and similar technologies on the website and app.',
      'These technologies support login, security, consent state, interface '
        + 'preferences, analytics, diagnostics, and abuse prevention.',
    ]),
    sec('Categories', [
      'Necessary technologies keep the site available, secure, and usable. '
        + 'Preference technologies remember settings and interface choices.',
      'Analytics technologies help measure pages, feature usage, errors, and '
        + 'performance so the product can be improved responsibly.',
    ]),
    sec('Choices', [
      'Browser settings can block or delete cookies. Some required features '
        + 'may stop working if necessary storage is disabled.',
      'Optic honors consent controls where required and avoids using cookies '
        + 'to turn private audit content into advertising profiles.',
    ]),
    sec('Contact', [
      'Questions about cookies or similar technologies can be sent to '
        + 'hello@tryoptic.app.',
    ]),
  ],
};

function sec(heading: string, body: string[]): LegalSection {
  return { body, heading };
}

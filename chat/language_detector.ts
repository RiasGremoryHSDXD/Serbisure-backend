// Template: run scripts/sync_chat_language.py after changing this file or offensive_terms.json.
const rules = __LANGUAGE_RULES__;
export const OFFENSIVE_LANGUAGE_ADVISORY = rules.advisory;
const equivalents: Record<string, string> = {
  a: '[a@4*]', b: '[b8]', e: '[e3*]', g: '[g9]', i: '[i1!|*]',
  o: '[o0*]', s: '[s$5]', t: '[t7+]', u: '[u*v]',
};
const separator = '[.*_~!@#$%^&+|/\\\\-]{0,3}';
const letters = (word: string, joiner: string) => [...word].map(c => (equivalents[c] || c) + '{1,8}').join(joiner);
const patterns = rules.terms.flatMap(term => [
  term.split(' ').map(word => letters(word, separator)).join('(?:\\s{1,3}|' + separator + ')'),
  // Spaces inside a word require separators between every letter: "put a bag" is ordinary English.
  letters(term.replace(/ /g, ''), '[\\s.*_~!@#$%^&+|/\\\\-]{1,3}'),
]);
const pattern = new RegExp('(^|[^a-z0-9])(?:' + patterns.join('|') + ')(?=$|[^a-z0-9])', 'i');

/** Advisory only: no contextual judgment, substring matching, or automatic penalties. */
export function containsOffensiveLanguage(text: string | null | undefined): boolean {
  const content = (text || '').replace(/^> \[[^\n]*\]: ([^\n]*)\n\n([\s\S]*)$/, '$1\n$2');
  const normalized = content.normalize('NFKD').replace(/[\p{Mn}\p{Cf}]/gu, '');
  return pattern.test(normalized);
}

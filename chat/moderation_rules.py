"""English/Tagalog/Bisaya dictionary masking; not a contextual threat classifier."""
import re
import unicodedata
import json
from pathlib import Path

_RULES = json.loads(Path(__file__).with_name('offensive_terms.json').read_text(encoding='utf-8'))
OFFENSIVE_LANGUAGE_ADVISORY = _RULES['advisory']
_EQUIVALENTS = {'a': '[a@4*]', 'b': '[b8]', 'e': '[e3*]', 'g': '[g9]', 'i': '[i1!|*]',
                 'o': '[o0*]', 's': '[s$5]', 't': '[t7+]', 'u': '[u*v]'}
_SEPARATOR = r'[.*_~!@#$%^&+|/\\-]{0,3}'


def _letters(word, separator):
    return separator.join(_EQUIVALENTS.get(c, re.escape(c)) + '{1,8}' for c in word)


_patterns = []
for _term in _RULES['terms']:
    _patterns.extend([
        (r'(?:\s{1,3}|' + _SEPARATOR + ')').join(_letters(word, _SEPARATOR) for word in _term.split()),
        _letters(_term.replace(' ', ''), r'[\s.*_~!@#$%^&+|/\\-]{1,3}'),
    ])
_OFFENSIVE_PATTERN = re.compile(r'(^|[^a-z0-9])(?:' + '|'.join(_patterns) + r')(?=$|[^a-z0-9])', re.I)


def contains_offensive_language(text):
    content = re.sub(r'^> \[[^\n]*\]: ([^\n]*)\n\n([\s\S]*)$', r'\1\n\2', text or '')
    value = unicodedata.normalize('NFKD', content)
    value = ''.join(c for c in value if unicodedata.category(c) not in ('Cf', 'Mn'))
    return bool(_OFFENSIVE_PATTERN.search(value))

WORDS = ('fuck', 'fucking', 'fucker', 'motherfucker', 'shit', 'bitch', 'kill',
         'putangina', 'putang', 'gago', 'gaga', 'tangina', 'ulol', 'yawa', 'piste',
         'pisti', 'patyon')
_PATTERN = re.compile(r'(?<!\w)(?:' + '|'.join(
    r'[.*_\-]*'.join(re.escape(c) for c in word)
    for word in sorted(WORDS, key=len, reverse=True)) + r')(?!\w)', re.I)


def mask_text(text):
    value = unicodedata.normalize('NFKC', text)
    value = ''.join(c for c in value if unicodedata.category(c) != 'Cf')
    def replace(match):
        word = match.group()
        vowel = re.search('[aeiou]', word, re.I)
        index = vowel.start() if vowel else 1
        return word[:index] + '*' + word[index + 1:]
    return _PATTERN.sub(replace, value) if _PATTERN.search(value) else text

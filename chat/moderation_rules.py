"""English/Tagalog/Bisaya dictionary masking; not a contextual threat classifier."""
import re
import unicodedata

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

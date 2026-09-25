| kandidát | platné ok | chybové ok (čitelné) / tiché | škodlivé odmítnuté / FAIL | medián µs |
|---|---|---|---|---|
| custom | 24/24 | 14/14 (14) / 0 | 20/20 / 0 | 9.8 |
| simpleeval | 16/24 | 11/14 (10) / 3 | 19/20 / 1 | 15.6 |
| simpleeval+dictonly | 23/24 | 11/14 (9) / 3 | 20/20 / 0 | 13.3 |
| asteval | 17/24 | 11/14 (10) / 3 | 16/20 / 4 | 23.3 |
| evalidate | 17/24 | 12/14 (9) / 2 | 20/20 / 0 | 26.1 |
| RestrictedPython | 17/24 | 12/14 (10) / 2 | 15/20 / 5 | 36.7 |
| cel-python | 24/24 | 12/14 (6) / 2 | 20/20 / 0 | 261.1 |
| cel-rust | 24/24 | 13/14 (10) / 1 | 19/20 / 1 | 19.6 |
custom {}
simpleeval {'V07': 'error', 'V08': 'error', 'V10': 'error', 'V16': 'error', 'V17': 'error', 'V20': 'error', 'V21': 'error', 'V22': 'error', 'E05': 'silent', 'E06': 'silent', 'E09': 'silent', 'E14': 'ok-vague', 'H10': 'FAIL'}
simpleeval+dictonly {'V21': 'error', 'E03': 'ok-vague', 'E05': 'silent', 'E06': 'silent', 'E09': 'ok-vague', 'E14': 'silent'}
asteval {'V07': 'error', 'V08': 'error', 'V10': 'error', 'V16': 'error', 'V17': 'error', 'V20': 'error', 'V22': 'error', 'E05': 'silent', 'E06': 'silent', 'E09': 'silent', 'E14': 'ok-vague', 'H03': 'FAIL', 'H10': 'FAIL', 'H12': 'FAIL', 'H13': 'FAIL'}
evalidate {'V07': 'error', 'V08': 'error', 'V10': 'error', 'V16': 'error', 'V17': 'error', 'V20': 'error', 'V22': 'error', 'E01': 'ok-vague', 'E03': 'ok-vague', 'E05': 'silent', 'E06': 'silent', 'E14': 'ok-vague'}
RestrictedPython {'V07': 'error', 'V08': 'error', 'V10': 'error', 'V16': 'error', 'V17': 'error', 'V20': 'error', 'V22': 'error', 'E03': 'ok-vague', 'E05': 'silent', 'E06': 'silent', 'E14': 'ok-vague', 'H05': 'FAIL', 'H10': 'FAIL', 'H14': 'FAIL', 'H16': 'FAIL', 'H17': 'FAIL'}
cel-python {'E03': 'ok-vague', 'E04': 'ok-vague', 'E05': 'ok-vague', 'E06': 'silent', 'E08': 'ok-vague', 'E09': 'ok-vague', 'E11': 'ok-vague', 'E14': 'silent'}
cel-rust {'E05': 'silent', 'E10': 'ok-vague', 'E11': 'ok-vague', 'E14': 'ok-vague', 'H18': 'FAIL'}

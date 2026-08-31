"""The rules against a learned model, on his own labels, with no dependencies.

Stage 8 proposes replacing `tools/nlp/hints.py` with something trained. This is
the floor of that idea: a multinomial Naive Bayes over character n-grams,
written out in full because it is short enough to write out -- no numpy, no
sklearn, nothing to install on a 1 GB box. If the cheapest possible learner
already beats hand-written regexes, a transformer has to justify a much larger
bill; if it does not, that is worth knowing before anyone downloads a model.

**Read the numbers with the bias in mind.** The regexes were tuned on these very
labels over weeks -- every fault caught in a night became a new pattern -- so
they have effectively seen the test set, while the model is cross-validated. The
comparison is therefore unfair *to the model*, and the gap it loses by is the
interesting quantity rather than the winner.

Two other things the numbers cannot say. The 458 labels leave about 190 examples
per fold, which is not a regime where a learned model shows itself; and a
character n-gram counter has no idea what words mean, so "озброєння яке ворог
може застосувати" is invisible to it as a forecast while a pretrained
multilingual model would very likely read it.

    python -m tools.bench.rules_vs_learned

Threat is scored twice, and the second number is the honest one: a bare "Жуляни"
carries the episode's class in the label and states none in the text, so
comparing a text-only classifier against it measures inheritance, not reading.
"""
import json, math, pathlib, random, re, sqlite3, sys, collections
from ..nlp import hints

ROOT = pathlib.Path(__file__).resolve().parents[2]

NGRAM = (3, 5)


def features(text):
    t = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    out = collections.Counter()
    for n in range(NGRAM[0], NGRAM[1] + 1):
        for i in range(len(t) - n + 1):
            out[t[i:i + n]] += 1
    return out


class NaiveBayes:
    def fit(self, xs, ys, alpha=0.2):
        self.prior = collections.Counter(ys)
        self.total = len(ys)
        self.counts = collections.defaultdict(collections.Counter)
        self.sums = collections.Counter()
        vocab = set()
        for x, y in zip(xs, ys):
            f = features(x)
            self.counts[y].update(f)
            self.sums[y] += sum(f.values())
            vocab |= set(f)
        self.vocab = len(vocab) or 1
        self.alpha = alpha
        return self

    def predict(self, text):
        f = features(text)
        best, best_score = None, -1e18
        for y, n in self.prior.items():
            s = math.log(n / self.total)
            denom = self.sums[y] + self.alpha * self.vocab
            cy = self.counts[y]
            for g, k in f.items():
                s += k * math.log((cy[g] + self.alpha) / denom)
            if s > best_score:
                best, best_score = y, s
        return best


def load():
    con = sqlite3.connect(str(ROOT / "data" / "messages.db"))
    con.row_factory = sqlite3.Row
    texts = {f"{r['channel']}/{r['message_id']}": r["text_norm"]
             for r in con.execute("SELECT channel, message_id, text_norm FROM messages "
                                  "WHERE text_norm <> ''")}
    rows, seen = [], set()
    for p in (ROOT / "labels").glob("*.jsonl"):
        for l in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            a = r.get("anchor")
            if not a or a in seen or a not in texts:
                continue
            seen.add(a)
            rows.append((texts[a], r))
    return rows


def score(pairs):
    right = sum(1 for got, want in pairs if got == want)
    return right / len(pairs)


def macro_f1(pairs):
    labels = {w for _, w in pairs} | {g for g, _ in pairs}
    fs = []
    for lab in labels:
        tp = sum(1 for g, w in pairs if g == lab and w == lab)
        fp = sum(1 for g, w in pairs if g == lab and w != lab)
        fn = sum(1 for g, w in pairs if g != lab and w == lab)
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * p * r / (p + r) if p + r else 0.0)
    return sum(fs) / len(fs) if fs else 0.0


def run(field, regex_fn, folds=5, only_stated=False):
    rows = [(t, r[field]) for t, r in load() if r.get(field)]
    if only_stated:
        # A bare "Жуляни" carries the episode's class in the label and states
        # none in its own text. Comparing a text-only classifier against that
        # measures inheritance rather than reading -- and it accounts for 98 of
        # the regexes' apparent errors on threat, every one of them by design.
        rows = [(t, y) for t, y in rows if hints.threat_hint(t) != "none"]
    random.Random(7).shuffle(rows)
    reg, nb = [], []
    for k in range(folds):
        test = rows[k::folds]
        train = [r for i, r in enumerate(rows) if i % folds != k]
        model = NaiveBayes().fit([t for t, _ in train], [y for _, y in train])
        for t, y in test:
            reg.append((regex_fn(t), y))
            nb.append((model.predict(t), y))
    return len(rows), reg, nb


CASES = (
    ("threat", "threat", hints.threat_hint, False),
    # The honest one. See `only_stated`.
    ("threat (клас названий у тексті)", "threat", hints.threat_hint, True),
    ("modality", "modality", hints.modality_hint, False),
    ("certainty", "certainty", hints.certainty_hint, False),
)

for field, key, fn, stated in CASES:
    n, reg, nb = run(key, fn, only_stated=stated)
    print(f"\n=== {field}  ({n} мічених, 5-fold) ===")
    print(f"  регулярки:      точність {score(reg):.3f}   macro-F1 {macro_f1(reg):.3f}")
    print(f"  навчена модель: точність {score(nb):.3f}   macro-F1 {macro_f1(nb):.3f}")
    wrong = collections.Counter((w, g) for g, w in reg if g != w)
    print(f"  найчастіші промахи регулярок: {dict(wrong.most_common(4))}")
    wrong2 = collections.Counter((w, g) for g, w in nb if g != w)
    print(f"  ...і моделі:                  {dict(wrong2.most_common(4))}")

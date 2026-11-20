"""Deterministic public-text evidence for short English/Bengali campus reports."""

import unicodedata
from collections import Counter

TEXT_WEIGHTS = {"jaccard": 0.45, "char_dice": 0.35, "containment": 0.20}


def normalize(text: str | None) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    characters = []
    for character in text:
        category = unicodedata.category(character)
        if category == "Nd":
            characters.append(str(unicodedata.decimal(character)))
        elif category[0] in {"L", "M", "N"}:
            characters.append(character)
        elif category != "Cf":
            characters.append(" ")
    return " ".join("".join(characters).split())


# A small reviewed-by-tests lexicon, not a general translation/transliteration model.
SYNONYMS = {
    "bag": "bag bags backpack backpacks rucksack ব্যাগ ব্যাগটি ব্যাগের ব্যাকপ্যাক",
    "wallet": "wallet wallets purse মানিব্যাগ মানিব্যাগটি পার্স",
    "phone": "phone phones mobile cellphone smartphone ফোন ফোনটি মোবাইল",
    "key": "key keys চাবি চাবির",
    "card": "card cards কার্ড কার্ডটি",
    "id": "id আইডি পরিচয়পত্র",
    "book": "book books বই বইটি",
    "bottle": "bottle bottles flask বোতল বোতলটি",
    "umbrella": "umbrella umbrellas ছাতা ছাতাটি",
    "charger": "charger chargers চার্জার",
    "headphone": "headphone headphones হেডফোন",
    "earbud": "earbud earbuds ইয়ারবাড ইয়ারবাডস",
    "glasses": "glasses spectacles চশমা",
    "watch": "watch watches ঘড়ি",
    "calculator": "calculator ক্যালকুলেটর",
    "black": "black কালো",
    "white": "white সাদা",
    "blue": "blue navy নীল নেভি",
    "red": "red maroon লাল মেরুন",
    "green": "green olive সবুজ জলপাই",
    "yellow": "yellow হলুদ",
    "grey": "grey gray ধূসর",
    "brown": "brown বাদামি",
    "pink": "pink গোলাপি",
    "zipper": "zipper zip zippers চেইন জিপার",
    "broken": "broken snapped ভাঙা ছেঁড়া",
    "sticker": "sticker stickers স্টিকার স্টিকারটি",
    "pocket": "pocket pockets পকেট পকেটের",
    "strap": "strap straps স্ট্র্যাপ ফিতা",
    "corner": "corner corners কোণা কোণ",
    "plastic": "plastic প্লাস্টিক",
    "steel": "steel স্টিল",
    "ring": "ring রিং",
    "round": "round rounded গোল গোলাকার",
    "small": "small ছোট",
    "two": "two দুটি দুই",
    "three": "three তিনটি তিন",
}
ALIASES = {
    normalize(word): canonical for canonical, words in SYNONYMS.items() for word in words.split()
}
STOPWORDS = {
    normalize(word)
    for word in (
        "a an the i my me mine it its this that with and or of at in on near to from for "
        "is was are were have has had lost found item items campus diu please somewhere "
        "আমি আমার এটি একটা একটি এবং অথবা সঙ্গে সাথে মধ্যে থেকে কাছে হয়েছে হারিয়েছি "
        "হারানো পাওয়া পেয়েছি ক্যাম্পাস"
    ).split()
}


def tokens(text: str | None, synonyms: bool = True) -> list[str]:
    words = [word for word in normalize(text).split() if word not in STOPWORDS]
    return [ALIASES.get(word, word) for word in words] if synonyms else words


def text_similarity(lost: dict, found: dict, synonyms: bool = True) -> dict:
    counts = []
    for report in (lost, found):
        counts.append(
            Counter(tokens(report.get("title"), synonyms) * 2)
            + Counter(tokens(report.get("description"), synonyms))
        )
    left, right = counts
    overlap = sum((left & right).values())
    union = sum((left | right).values())
    jaccard = overlap / union if union else 0.0
    minimum = min(sum(left.values()), sum(right.values()))
    containment = overlap / minimum if minimum else 0.0
    grams = []
    for words in (left, right):
        grams.append(
            {
                padded[index : index + 3]
                for word in words
                for padded in (f" {word} ",)
                for index in range(len(padded) - 2)
            }
        )
    size = len(grams[0]) + len(grams[1])
    char_dice = 2 * len(grams[0] & grams[1]) / size if size else 0.0
    components = {"jaccard": jaccard, "char_dice": char_dice, "containment": containment}
    return {
        **components,
        "score": round(sum(TEXT_WEIGHTS[key] * value for key, value in components.items()), 10),
        "shared_terms": sorted(
            left.keys() & right.keys(), key=lambda word: (-min(left[word], right[word]), word)
        )[:8],
    }


def jaro_winkler(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    radius = max(0, max(len(left), len(right)) // 2 - 1)
    left_matches, right_matches = [False] * len(left), [False] * len(right)
    for index, character in enumerate(left):
        for other in range(max(0, index - radius), min(index + radius + 1, len(right))):
            if not right_matches[other] and character == right[other]:
                left_matches[index] = right_matches[other] = True
                break
    matches = sum(left_matches)
    if not matches:
        return 0.0
    a = [char for char, matched in zip(left, left_matches, strict=True) if matched]
    b = [char for char, matched in zip(right, right_matches, strict=True) if matched]
    transpositions = sum(a != b for a, b in zip(a, b, strict=True)) / 2
    score = (matches / len(left) + matches / len(right) + (matches - transpositions) / matches) / 3
    prefix = 0
    for a, b in zip(left[:4], right[:4], strict=False):
        if a != b:
            break
        prefix += 1
    return score + prefix * 0.1 * (1 - score) if score > 0.7 else score

"""Closed vocabularies keep matching explainable and Bangla/English in sync."""

CATEGORIES = {
    "unknown": ("Unknown", "অজানা"),
    "bag": ("Bag", "ব্যাগ"),
    "wallet": ("Wallet", "মানিব্যাগ"),
    "phone": ("Phone", "মোবাইল ফোন"),
    "keys": ("Keys", "চাবি"),
    "id-card": ("ID card", "আইডি কার্ড"),
    "books": ("Books", "বই"),
    "electronics": ("Electronics", "ইলেকট্রনিক্স"),
    "clothing": ("Clothing", "পোশাক"),
    "other": ("Other", "অন্যান্য"),
}

COLORS = {
    "unknown": ("Unknown", "অজানা"),
    "black": ("Black", "কালো"),
    "white": ("White", "সাদা"),
    "blue": ("Blue", "নীল"),
    "red": ("Red", "লাল"),
    "green": ("Green", "সবুজ"),
    "yellow": ("Yellow", "হলুদ"),
    "grey": ("Grey", "ধূসর"),
    "brown": ("Brown", "বাদামি"),
    "pink": ("Pink", "গোলাপি"),
    "other": ("Other", "অন্যান্য"),
}

LOCATIONS = {
    "unknown": ("Unknown", "অজানা"),
    "library": ("Library", "লাইব্রেরি"),
    "classroom": ("Classroom", "ক্লাসরুম"),
    "cafeteria": ("Cafeteria", "ক্যাফেটেরিয়া"),
    "transport": ("Transport", "পরিবহন"),
    "mosque": ("Mosque", "মসজিদ"),
    "ground": ("Ground", "খেলার মাঠ"),
    "other": ("Other", "অন্যান্য"),
}


def as_options(vocabulary: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    return [{"value": key, "en": en, "bn": bn} for key, (en, bn) in vocabulary.items()]

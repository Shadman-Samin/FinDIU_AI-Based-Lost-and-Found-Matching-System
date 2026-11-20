"""Generate a small labelled synthetic corpus, never real-world accuracy evidence.

All photos are drawings of public appearance, not identity information. Physical
item/match labels are stored separately and never enter text or image features.
"""

import argparse
import hashlib
import io
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

SOURCE = "findiu-synthetic-v1"
# category, colour, brand, area, drawing, visible mark, photo, lost text, found text
PROFILES = [
    (
        "bag",
        "blue",
        "Domyos",
        "classroom",
        "bag",
        "circle",
        True,
        (
            "Navy backpack broken left zipper",
            "Blue backpack white circle sticker two front pockets broken left zipper pull.",
        ),
        (
            "Blue backpack white circle sticker",
            "Navy bag two front pockets snapped left zipper pull white circular sticker.",
        ),
    ),
    (
        "bag",
        "black",
        "Dell",
        "library",
        "bag",
        "stripe",
        True,
        (
            "Black laptop bag silver stripe",
            "Black rectangular bag silver stripe torn right strap padded front pocket.",
        ),
        ("কালো ব্যাগ silver stripe", "কালো ব্যাগ silver stripe ভাঙা right স্ট্র্যাপ front পকেট."),
    ),
    (
        "bag",
        "red",
        "",
        "ground",
        "bag",
        "star",
        True,
        (
            "Red backpack yellow star",
            "Red canvas backpack yellow star sticker worn bottom corner single zipper.",
        ),
        (
            "Red bag star sticker",
            "Red canvas bag yellow star sticker worn bottom corner one zipper.",
        ),
    ),
    (
        "wallet",
        "brown",
        "Levis",
        "cafeteria",
        "wallet",
        "triangle",
        True,
        (
            "Brown leather wallet triangular button",
            "Brown folded leather wallet triangular silver button three inner slots.",
        ),
        (
            "Brown folded purse silver triangle",
            "Brown leather wallet silver triangular button three slots.",
        ),
    ),
    (
        "wallet",
        "black",
        "Wildcraft",
        "library",
        "wallet",
        "stripe",
        False,
        (
            "Black wallet red stitching",
            "Black fabric wallet red thread along edge square front mark two card slots.",
        ),
        ("কালো মানিব্যাগ red thread", "কালো মানিব্যাগ red stitching square front mark দুটি কার্ড slots."),
    ),
    (
        "phone",
        "black",
        "Samsung",
        "classroom",
        "phone",
        "circle",
        True,
        (
            "Black phone white cat sticker",
            "Black mobile white cat sticker cracked upper corner clear plastic case.",
        ),
        ("কালো ফোন সাদা cat স্টিকার", "কালো মোবাইল সাদা cat স্টিকার cracked upper কোণা clear প্লাস্টিক case."),
    ),
    (
        "phone",
        "white",
        "Nokia",
        "transport",
        "phone",
        "stripe",
        False,
        (
            "White Nokia phone black case",
            "White phone black rubber case two circular marks near camera scratched silver edge.",
        ),
        (
            "White mobile scratched silver edge",
            "White Nokia phone black rubber cover two round camera marks scratched silver edge.",
        ),
    ),
    (
        "keys",
        "black",
        "",
        "library",
        "keys",
        "blue",
        True,
        (
            "Three keys blue plastic tag",
            "Three steel keys round ring small blue plastic tag one long key.",
        ),
        ("তিন চাবি নীল tag", "তিনটি স্টিল চাবি গোল রিং ছোট নীল প্লাস্টিক tag one long key."),
    ),
    (
        "keys",
        "red",
        "",
        "classroom",
        "keys",
        "red",
        False,
        (
            "Two keys red strap",
            "Two silver keys red fabric strap square metal ring short brass key.",
        ),
        (
            "Red strap two silver keys",
            "Red fabric strap two silver keys square metal ring one short brass key.",
        ),
    ),
    (
        "id-card",
        "white",
        "DIU",
        "cafeteria",
        "card",
        "circle",
        True,
        (
            "Student card clear sleeve bent corner",
            "White student ID card clear plastic sleeve bent upper corner blue round clip.",
        ),
        (
            "White ID card blue clip",
            "White student card clear plastic sleeve bent upper corner blue circular clip.",
        ),
    ),
    (
        "books",
        "blue",
        "Oxford",
        "library",
        "book",
        "stripe",
        False,
        (
            "Blue dictionary creased spine",
            "Blue dictionary Oxford cover white crease on spine green paper bookmark.",
        ),
        (
            "Blue Oxford book green bookmark",
            "Blue dictionary white crease on spine green paper bookmark.",
        ),
    ),
    (
        "books",
        "red",
        "Penguin",
        "classroom",
        "book",
        "star",
        False,
        (
            "Red paperback yellow note",
            "Red paperback Penguin cover yellow folded note small tear near top edge.",
        ),
        (
            "Red book folded yellow note",
            "Red Penguin paperback yellow folded note small tear near top edge.",
        ),
    ),
    (
        "electronics",
        "black",
        "Casio",
        "classroom",
        "calculator",
        "blue",
        True,
        (
            "Black Casio calculator worn blue button",
            "Black calculator worn blue button silver scratched display edge.",
        ),
        ("কালো Casio ক্যালকুলেটর", "কালো ক্যালকুলেটর worn নীল button silver scratched display edge."),
    ),
    (
        "electronics",
        "white",
        "Anker",
        "library",
        "charger",
        "stripe",
        True,
        (
            "White charger frayed cable",
            "White Anker charger two USB ports frayed cable grey stripe small corner dent.",
        ),
        (
            "White Anker adapter grey stripe",
            "White charger two USB ports frayed cable grey stripe dented corner.",
        ),
    ),
    (
        "other",
        "green",
        "Milton",
        "library",
        "bottle",
        "circle",
        True,
        (
            "Green steel bottle dented base",
            "Olive green steel water bottle dent near base round khaki lid white circle sticker.",
        ),
        (
            "Green bottle khaki lid",
            "Green steel bottle dented base round khaki screw lid white circular sticker.",
        ),
    ),
    (
        "clothing",
        "black",
        "",
        "mosque",
        "jacket",
        "stripe",
        False,
        (
            "Black jacket white zipper",
            "Black jacket white zipper two front pockets grey stripe across sleeve.",
        ),
        ("কালো jacket সাদা জিপার", "কালো jacket সাদা চেইন দুটি front পকেট grey stripe across sleeve."),
    ),
    (
        "bag",
        "blue",
        "Decathlon",
        "library",
        "bag",
        "triangle",
        True,
        (
            "Blue backpack silver triangle patch",
            "Blue backpack silver triangular patch broken right zipper narrow front pocket.",
        ),
        (
            "Blue bag triangular patch",
            "Blue backpack silver triangle patch snapped right zipper narrow front pocket.",
        ),
    ),
    (
        "wallet",
        "brown",
        "Fossil",
        "classroom",
        "wallet",
        "circle",
        True,
        (
            "Brown wallet orange button",
            "Brown leather wallet round orange button white thread around corner.",
        ),
        (
            "Brown purse orange round button",
            "Brown leather wallet orange circular button white stitching around corner.",
        ),
    ),
    (
        "phone",
        "blue",
        "Samsung",
        "library",
        "phone",
        "triangle",
        False,
        (
            "Blue phone cracked lower corner",
            "Blue phone clear shell cracked lower corner yellow triangle sticker.",
        ),
        (
            "নীল ফোন yellow triangle",
            "নীল মোবাইল clear shell cracked lower কোণা yellow triangle স্টিকার.",
        ),
    ),
    (
        "keys",
        "black",
        "",
        "transport",
        "keys",
        "yellow",
        True,
        (
            "Four keys yellow square tag",
            "Four metal keys yellow square plastic tag black round ring.",
        ),
        (
            "Yellow square tag four keys",
            "Four steel keys yellow square plastic tag black circular ring.",
        ),
    ),
    (
        "id-card",
        "white",
        "DIU",
        "classroom",
        "card",
        "pink",
        True,
        (
            "White card sleeve pink clip",
            "White student ID card transparent sleeve pink clip bent lower edge.",
        ),
        (
            "White student card pink clip",
            "White ID card transparent plastic sleeve pink clip bent lower edge.",
        ),
    ),
    (
        "books",
        "brown",
        "Pearson",
        "library",
        "book",
        "green",
        False,
        (
            "Brown textbook green ribbon",
            "Brown Pearson textbook green ribbon bookmark folded page corners silver line on spine.",
        ),
        (
            "Brown Pearson book green ribbon",
            "Brown textbook green ribbon bookmark folded page corners silver spine line.",
        ),
    ),
    (
        "electronics",
        "white",
        "Xiaomi",
        "cafeteria",
        "earbuds",
        "circle",
        True,
        (
            "White earbuds black dot case",
            "White earbuds round charging case black dot near hinge small side scratch.",
        ),
        (
            "White earbud case black dot",
            "White earbuds circular charging case black dot near hinge scratched side.",
        ),
    ),
    (
        "other",
        "red",
        "Cello",
        "ground",
        "bottle",
        "stripe",
        False,
        (
            "Red bottle bent neck silver lid",
            "Red steel bottle bent neck silver screw lid white stripe near base.",
        ),
        (
            "Red steel bottle white stripe",
            "Red bottle bent neck silver lid white stripe near bottom.",
        ),
    ),
]
PROFILE_FIELDS = (
    "category",
    "color",
    "brand",
    "location",
    "shape",
    "mark",
    "photo",
    "lost",
    "found",
)
# Reference appearance, deliberately different public clues, mark, and photo.
NEGATIVES = [
    (
        0,
        "Blue backpack silver rectangle",
        "Blue backpack silver rectangular patch intact zipper plain straps no circle sticker.",
        "stripe",
        True,
    ),
    (
        0,
        "Blue bag three side pockets",
        "Blue bag three side pockets yellow button intact zipper long strap.",
        "yellow",
        False,
    ),
    (
        1,
        "Black laptop bag green ribbon",
        "Black laptop bag green ribbon handle intact padded straps no silver stripe.",
        "green",
        True,
    ),
    (
        2,
        "Red bag white circle",
        "Red backpack white circular sticker new zipper rounded bottom plain canvas.",
        "circle",
        True,
    ),
    (
        3,
        "Brown wallet plain brass clasp",
        "Brown leather wallet brass clasp one large slot plain rectangular front.",
        "stripe",
        True,
    ),
    (
        4,
        "Black wallet green square",
        "Black fabric wallet green square label grey stitching four card slots.",
        "green",
        False,
    ),
    (
        5,
        "Black phone blue triangle",
        "Black mobile blue triangle sticker intact glass dark rubber case.",
        "triangle",
        True,
    ),
    (
        6,
        "White Nokia with red cover",
        "White phone red fabric cover one square camera mark plain edges.",
        "red",
        False,
    ),
    (
        7,
        "Three keys white square tag",
        "Three steel keys white square plastic tag plain circular ring.",
        "circle",
        True,
    ),
    (
        8,
        "Two keys green cord",
        "Two silver keys green cord circular steel ring long flat key.",
        "green",
        False,
    ),
    (
        9,
        "Student ID card yellow sleeve",
        "White student card yellow sleeve straight corners black rectangular clip.",
        "yellow",
        True,
    ),
    (
        10,
        "Blue Oxford dictionary red bookmark",
        "Blue dictionary red fabric bookmark smooth spine straight paper corners.",
        "red",
        False,
    ),
    (
        16,
        "Blue bag round yellow badge",
        "Blue backpack round yellow badge intact left zipper wide side pocket.",
        "yellow",
        True,
    ),
    (
        18,
        "Blue mobile white star",
        "Blue phone white star sticker intact lower corner black cover.",
        "star",
        False,
    ),
    # Deliberately indistinguishable public evidence from a different physical card.
    (20, None, None, "pink", True),
    (
        23,
        "Red bottle black lid",
        "Red steel bottle straight neck black snap lid plain rounded base.",
        "circle",
        False,
    ),
]
PALETTE = {
    "blue": "#2e617e",
    "black": "#25312d",
    "white": "#ecece2",
    "red": "#aa4230",
    "green": "#496b4a",
    "brown": "#845c40",
    "grey": "#7c8585",
    "yellow": "#d6b34a",
    "pink": "#ca8f94",
}


def illustration(profile: dict, view: int) -> bytes:
    image = Image.new("RGB", (320, 320), (237 - view * 3, 230 + view, 214 + view * 3))
    draw = ImageDraw.Draw(image)
    color, ink = PALETTE[profile["color"]], "#21382f"
    shape = profile["shape"]
    if shape == "bag":
        draw.arc((106, 30, 214, 116), 180, 360, fill=ink, width=9)
        draw.rounded_rectangle((72, 70, 248, 285), 26, fill=color, outline=ink, width=3)
        draw.rounded_rectangle((99, 160, 222, 244), 12, outline=ink, width=3)
        draw.line((104, 175, 215, 175), fill="#ddd4bd", width=4)
    elif shape == "wallet":
        draw.rounded_rectangle((46, 105, 274, 238), 18, fill=color, outline=ink, width=4)
        draw.line((122, 108, 122, 233), fill="#b5a28a", width=3)
    elif shape == "phone":
        draw.rounded_rectangle((91, 35, 229, 286), 20, fill=color, outline=ink, width=5)
        draw.rounded_rectangle((108, 57, 160, 98), 8, fill="#68786b")
        draw.ellipse((117, 62, 136, 81), fill=ink)
        draw.line((222, 263, 208, 244, 219, 233), fill="#c9ceba", width=3)
    elif shape == "keys":
        draw.ellipse((101, 47, 212, 156), outline=ink, width=9)
        for x, end in ((112, 240), (159, 275), (204, 230)):
            draw.ellipse((x - 18, 111, x + 18, 147), fill="#a8aaa1", outline=ink, width=3)
            draw.rectangle((x - 6, 144, x + 6, end), fill="#a8aaa1", outline=ink, width=2)
            draw.rectangle((x - 6, end - 15, x + 18, end - 6), fill=ink)
    elif shape == "card":
        draw.rounded_rectangle((41, 96, 279, 228), 10, fill=color, outline=ink, width=3)
        draw.ellipse((64, 122, 116, 174), fill="#8ba5ad")
        for y, end in ((126, 251), (154, 238), (182, 221)):
            draw.line((137, y, end, y), fill="#9da799", width=7)
    elif shape in {"book", "calculator", "charger"}:
        draw.rounded_rectangle((79, 50, 241, 280), 12, fill=color, outline=ink, width=4)
        if shape == "calculator":
            draw.rectangle((99, 78, 220, 120), fill="#c5d2b5")
            for y in (154, 188, 222, 256):
                for x in (111, 153, 195):
                    draw.rectangle((x, y, x + 20, y + 16), fill="#9daca0")
        elif shape == "charger":
            draw.rectangle((108, 162, 132, 188), fill=ink)
            draw.rectangle((176, 162, 202, 188), fill=ink)
            draw.arc((112, 5, 274, 103), 180, 360, fill="#747b72", width=7)
        else:
            draw.line((94, 61, 94, 270), fill="#cbbba0", width=5)
            draw.line((122, 96, 212, 96), fill="#e5e0cf", width=10)
    elif shape == "bottle":
        draw.rounded_rectangle((104, 62, 216, 282), 27, fill=color, outline=ink, width=3)
        draw.rectangle((121, 33, 199, 70), fill="#a99d72", outline=ink, width=3)
        draw.arc((163, 219, 219, 254), 80, 250, fill=ink, width=3)
    elif shape == "earbuds":
        draw.rounded_rectangle((56, 137, 264, 271), 52, fill=color, outline=ink, width=4)
        draw.line((66, 200, 254, 200), fill="#a1aca0", width=3)
        for x in (99, 193):
            draw.ellipse((x, 44, x + 33, 92), fill=color, outline=ink, width=3)
            draw.rectangle((x + 10, 76, x + 22, 124), fill=color, outline=ink, width=2)
    else:
        draw.polygon(
            (
                102,
                59,
                218,
                59,
                284,
                125,
                246,
                170,
                224,
                142,
                224,
                281,
                96,
                281,
                96,
                142,
                73,
                170,
                36,
                125,
            ),
            fill=color,
            outline=ink,
        )
        draw.line((159, 72, 159, 272), fill="#e7e3d4", width=5)
    mark = profile["mark"]
    if mark == "circle":
        draw.ellipse((179, 107, 211, 139), fill="#eee8d0", outline=ink, width=2)
    elif mark == "stripe":
        draw.line((174, 111, 224, 137), fill="#afbab4", width=9)
    elif mark == "triangle":
        draw.polygon((196, 102, 178, 140, 216, 140), fill="#c8bb82", outline=ink)
    elif mark == "star":
        draw.polygon(
            (
                197,
                102,
                203,
                115,
                217,
                117,
                207,
                128,
                209,
                142,
                197,
                135,
                184,
                142,
                187,
                128,
                176,
                117,
                190,
                115,
            ),
            fill="#e7cf70",
            outline=ink,
        )
    else:
        draw.rounded_rectangle(
            (174, 104, 218, 141), 7, fill=PALETTE.get(mark, "#e6dbba"), outline=ink, width=2
        )
    image = image.rotate(
        -4 if view == 0 else 3, resample=Image.Resampling.BICUBIC, fillcolor=image.getpixel((0, 0))
    )
    image = ImageEnhance.Brightness(image).enhance(1.0 if view == 0 else 0.96)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=88 if view == 0 else 80)
    return output.getvalue()


def build_corpus(directory: Path) -> Path:
    dataset = directory / "reports.jsonl"
    if dataset.exists():
        try:
            existing = [
                json.loads(line)
                for line in dataset.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (ValueError, OSError):
            raise ValueError("Refusing to overwrite an unrecognized corpus") from None
        if not existing or any(
            row.get("synthetic") is not True or row.get("source") != SOURCE for row in existing
        ):
            raise ValueError("Refusing to overwrite non-synthetic or foreign reports")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "images").mkdir(exist_ok=True)
    records, hashes = [], {}
    profiles = [dict(zip(PROFILE_FIELDS, values, strict=True)) for values in PROFILES]

    def record(profile, index, kind, group, split, case, owner, view):
        title, description = profile[kind]
        report_id = f"{split}-{case}-{index:02d}-{kind}"
        day = date(2026, 11, 1) + timedelta(days=index % 5 + (index % 3 if kind == "found" else 0))
        row = {
            "report_id": report_id,
            "physical_item_id": group,
            "match_group_id": group,
            "owner_id": owner,
            "type": kind,
            "category": profile["category"],
            "title": title,
            "description": description,
            "event_date": day.isoformat(),
            "public_attributes": {
                key: profile[key] or None for key in ("color", "brand", "location")
            },
            "split": split,
            "source": SOURCE,
            "synthetic": True,
            "case": case,
            "consent_for_ai": True,
            "embedding_model": "local-hash-768",
            "embedding_dimensions": 768,
        }
        if profile["photo"]:
            relative = f"images/{report_id}.jpg"
            raw = illustration(profile, view)
            (directory / relative).write_bytes(raw)
            hashes[relative] = hashlib.sha256(raw).hexdigest()
            row.update(image_path=relative, image_consent=True)
        records.append(row)

    for index, profile in enumerate(profiles):
        split = "tune" if index < 16 else "test"
        for kind, view in (("lost", 0), ("found", 1)):
            record(
                profile,
                index,
                kind,
                f"synthetic-physical-{index:02d}",
                split,
                "pair",
                f"synthetic-{kind}-owner-{index:02d}",
                view,
            )
    for index, (reference, title, description, mark, photo) in enumerate(NEGATIVES):
        profile = dict(profiles[reference])
        profile.update(mark=mark, photo=photo)
        if title is not None:
            profile["found"] = (title, description)
        split = "tune" if index < 12 else "test"
        case = "lookalike" if title is not None else "ambiguous"
        record(
            profile,
            reference,
            "found",
            f"synthetic-negative-{index:02d}",
            split,
            f"{case}-{index:02d}",
            f"synthetic-negative-owner-{index:02d}",
            1,
        )
    for index, (category, color, brand, location, title, description) in enumerate(
        (
            (
                "bag",
                "grey",
                "Logitech",
                "cafeteria",
                "Grey rigid laptop sleeve",
                "Grey rigid sleeve gold clasp one large smooth pocket.",
            ),
            (
                "phone",
                "green",
                "Motorola",
                "mosque",
                "Green phone rubber case",
                "Green mobile thick rubber cover red square sticker intact corners.",
            ),
        )
    ):
        profile = {
            "category": category,
            "color": color,
            "brand": brand,
            "location": location,
            "photo": False,
            "lost": (title, description),
        }
        record(
            profile,
            index,
            "lost",
            f"synthetic-unmatched-{index:02d}",
            "tune",
            "unmatched",
            f"synthetic-unmatched-owner-{index:02d}",
            0,
        )
    raw = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in records) + "\n"
    dataset.write_text(raw, encoding="utf-8")
    manifest = {
        "source": SOURCE,
        "synthetic": True,
        "warning": "Synthetic development fixtures only. Not real-world accuracy evidence; one held-out negative has indistinguishable public clues.",
        "dataset_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "record_count": len(records),
        "counts": dict(Counter(f"{row['split']}/{row['type']}" for row in records)),
        "image_sha256": hashes,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/synthetic-v1"))
    args = parser.parse_args(argv)
    path = build_corpus(args.output)
    print(json.dumps({"dataset": str(path), "synthetic": True, "source": SOURCE}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Seed a believable demo board against a running local API.

    python -m scripts.seed_demo

Idempotent enough for repeat runs: duplicate emails/items are skipped.
"""

import io
import sys

import httpx
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8000"
PASSWORD = "campus-demo-password"
PHOTOS = {
    "bottle": ((233, 240, 224), (32, 92, 78)),
    "backpack": ((226, 232, 238), (28, 52, 84)),
    "card": ((244, 236, 220), (177, 72, 44)),
}


def scene(kind: str) -> bytes:
    background, ink = PHOTOS[kind]
    image = Image.new("RGB", (900, 900), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((90, 110, 810, 830), fill=ink)
    if kind == "bottle":
        draw.rounded_rectangle((360, 170, 540, 760), radius=90, fill=(214, 226, 210))
        draw.rectangle((395, 110, 505, 210), fill=(120, 150, 122))
    elif kind == "backpack":
        draw.rounded_rectangle((250, 260, 650, 780), radius=70, fill=(236, 240, 245))
        draw.arc((330, 150, 570, 350), start=180, end=360, fill=(236, 240, 245), width=28)
        draw.rectangle((410, 470, 490, 520), fill=ink)
    else:
        draw.rounded_rectangle((190, 280, 710, 620), radius=24, fill=(248, 246, 240))
        draw.rectangle((230, 330, 330, 420), fill=(120, 140, 170))
        draw.rectangle((370, 340, 660, 370), fill=(150, 155, 160))
        draw.rectangle((370, 400, 620, 430), fill=(150, 155, 160))
        draw.rectangle((370, 460, 580, 490), fill=(150, 155, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def register(client: httpx.Client, name: str, email: str) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": PASSWORD, "locale": "bn"},
    )


def token(client: httpx.Client, email: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create(client: httpx.Client, headers: dict, kind: str, photo: str | None, **fields):
    data = {
        "category": fields["category"],
        "color": fields["color"],
        "title": fields["title"],
        "description": fields["description"],
        "location": fields["location"],
        "event_date": fields["event_date"],
        "private_detail": fields["private_detail"],
        "brand": fields.get("brand", ""),
        "consent": "on",
    }
    files = {"image": ("photo.jpg", scene(photo), "image/jpeg")} if photo else None
    response = client.post(f"/api/v1/items?type={kind}", data=data, files=files, headers=headers)
    response.raise_for_status()
    return response.json()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30) as client:
        register(client, "Rimi Akter", "rimi@diu.edu.bd")
        register(client, "Tanvir Hasan", "tanvir@diu.edu.bd")
        rimi = token(client, "rimi@diu.edu.bd")
        tanvir = token(client, "tanvir@diu.edu.bd")

        lost_bottle = create(
            client,
            rimi,
            "lost",
            "bottle",
            category="other",
            color="green",
            title="Green steel water bottle",
            description="Olive green steel bottle with a dent near the base and a round khaki lid.",
            location="library",
            event_date="2026-11-14",
            private_detail="Small sticker of a red fox under the bottle.",
        )
        create(
            client,
            tanvir,
            "found",
            "bottle",
            category="other",
            color="green",
            title="Steel bottle found in library",
            description="Olive green steel bottle, dented base, khaki screw lid, one faded sticker.",
            location="library",
            event_date="2026-11-14",
            private_detail="Red fox sticker under the bottle.",
        )
        create(
            client,
            rimi,
            "lost",
            "backpack",
            category="bag",
            color="blue",
            title="Navy backpack with broken zipper",
            description="Dark navy campus backpack, left zipper pull snapped, white thread on one strap.",
            location="classroom",
            event_date="2026-11-15",
            private_detail="Name tag inside the front pocket: R. Akter, Section 44_B2.",
            brand="Domyos",
        )
        create(
            client,
            tanvir,
            "found",
            "backpack",
            category="bag",
            color="blue",
            title="Found navy backpack near room 502",
            description="Navy backpack left near room 502, broken left zipper, white stitching on strap.",
            location="classroom",
            event_date="2026-11-15",
            private_detail="Name tag inside front pocket: R. Akter.",
            brand="Domyos",
        )
        create(
            client,
            rimi,
            "lost",
            None,
            category="id-card",
            color="white",
            title="DIU student ID card",
            description="Student ID card in a clear plastic sleeve, photo corner slightly bent.",
            location="cafeteria",
            event_date="2026-11-13",
            private_detail="ID number ends with 221 and blood group is B+.",
        )
        create(
            client,
            tanvir,
            "found",
            "card",
            category="id-card",
            color="white",
            title="ID card found near cafeteria counter",
            description="Plastic-sleeved student ID card found by the cafeteria counter, bent corner.",
            location="cafeteria",
            event_date="2026-11-13",
            private_detail="ID number ends with 221.",
        )
        create(
            client,
            tanvir,
            "found",
            None,
            category="keys",
            color="black",
            title="Bunch of keys with a blue tag",
            description="Three keys on a steel ring, small blue plastic tag, no name written.",
            location="transport",
            event_date="2026-11-15",
            private_detail="Tag has a faded smiley drawn in pen.",
        )

        for _ in range(3):
            tick = client.post(
                "/internal/tick", headers={"Authorization": "Bearer demo-tick-token"}
            )
            tick.raise_for_status()
            if tick.json()["embedded"] == 0:
                break

        matches = client.get(f"/api/v1/items/{lost_bottle['id']}/matches", headers=rimi).json()
        if matches["matches"]:
            client.post(
                f"/api/v1/matches/{matches['matches'][0]['id']}/claims",
                json={"answer": "There is a red fox sticker under the bottle — my own sticker."},
                headers=rimi,
            )
        print("Demo board ready. Matches:", len(matches["matches"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

def test_four_application_tables_use_private_schema():
    from backend.app.models import Base

    assert set(Base.metadata.tables) == {
        "findiu.users",
        "findiu.items",
        "findiu.matches",
        "findiu.claims",
    }
    assert all(table.schema == "findiu" for table in Base.metadata.tables.values())


def test_match_pair_and_claim_constraints_are_named():
    from backend.app.models import Base

    matches = Base.metadata.tables["findiu.matches"]
    claims = Base.metadata.tables["findiu.claims"]
    assert "uq_matches_pair" in {constraint.name for constraint in matches.constraints}
    assert "uq_claims_match_claimant" in {constraint.name for constraint in claims.constraints}


def test_private_detail_is_not_part_of_public_item_schema():
    from backend.app.schemas import item_public_fields

    assert "private_detail" not in item_public_fields()
    assert "image_path" not in item_public_fields()
    assert "text_embedding" not in item_public_fields()

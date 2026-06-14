"""Config-sanering: MM-DD-waarden uit .env mogen een inline comment bevatten.

docker-compose neemt álles na '=' als waarde (inclusief '# uitleg'); de
field-validator moet dat wegsnijden zodat de hernieuwingslogica niet stilletjes
uitvalt (#139)."""
from app.config import Settings

_STRONG = "a" * 32


def test_md_inline_comment_wordt_gestript():
    s = Settings(secret_key=_STRONG, app_env="dev",
                 membership_renewal_start_md="06-01   # Vanaf wanneer hernieuwen")
    assert s.membership_renewal_start_md == "06-01"


def test_md_lege_waarde_wordt_none():
    s = Settings(secret_key=_STRONG, app_env="dev", membership_renewal_start_md="")
    assert s.membership_renewal_start_md is None


def test_md_zonder_comment_blijft_ongewijzigd():
    s = Settings(secret_key=_STRONG, app_env="dev", membership_renewal_start_md="09-01")
    assert s.membership_renewal_start_md == "09-01"

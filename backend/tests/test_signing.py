"""The signing helper of the kernel (CR-36, CR-37).

Broken on purpose (15 October 2026): the context left out of the key → a signature
made for one use verifies for another and the second test fails; the parts joined
without a separator → ("1", "23") and ("12", "3") sign alike and the third test fails.
"""

from app.kernel.signing import LENGTH, sign, verify


def test_a_signature_verifies_for_its_own_parts_and_use():
    signature = sign("unsubscribe", 7, "a@example.org")
    assert len(signature) == LENGTH
    assert verify("unsubscribe", 7, "a@example.org", signature=signature)


def test_a_signature_does_not_travel_to_another_use_or_other_parts():
    signature = sign("unsubscribe", 7)
    assert not verify("open", 7, signature=signature), "another use"
    assert not verify("unsubscribe", 8, signature=signature), "another part"
    assert not verify(
        "unsubscribe", 7, signature=signature[:-1] + ("0" if signature[-1] != "0" else "1")
    )


def test_the_parts_are_separated_so_two_splits_of_one_text_differ():
    assert sign("x", "1", "23") != sign("x", "12", "3")


def test_a_malformed_signature_is_refused_without_an_error():
    for bad in ("", "short", "z" * LENGTH, None):
        assert not verify("x", 1, signature=bad)  # type: ignore[arg-type]

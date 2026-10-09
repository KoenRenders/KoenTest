"""Read a mail where it stands after the request: in the queue (CR-13 phase 4d, #1251).

The sign-in no longer sends its mail itself; it asks `mail`, which queues a
`mail.send` job in the transaction that stores the code. A test that follows the
link therefore reads it from that job — what the runner would send — and not from
a stand-in for the sender, so it turns red when the sign-in stops asking.
"""

import re

from app.kernel.jobs import KernelJob


def queued_mails(db, to_email: str) -> list[dict]:
    """The payloads of the `mail.send` jobs queued for `to_email`, oldest first."""
    db.expire_all()
    jobs = db.query(KernelJob).filter(KernelJob.name == "mail.send").order_by(KernelJob.id).all()
    return [job.payload for job in jobs if job.payload.get("to_email") == to_email]


def newest_queued_mail(db) -> dict:
    """The payload of the newest `mail.send` job: `subject`, `body_html`,
    `email_type`, `to_email`."""
    db.expire_all()
    job = (
        db.query(KernelJob)
        .filter(KernelJob.name == "mail.send")
        .order_by(KernelJob.id.desc())
        .first()
    )
    assert job is not None, "no mail was queued"
    return job.payload


def queued_link(db, to_email: str) -> str:
    """The link in the newest mail queued for `to_email`."""
    mails = queued_mails(db, to_email)
    assert mails, f"no mail was queued for {to_email}"
    found = re.search(r'href="([^"]+)"', mails[-1]["body_html"])
    assert found, "the queued mail carries no link"
    return found.group(1)

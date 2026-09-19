"""Desktop-issued pairing for tests. HTTP GET never mints a challenge."""

from __future__ import annotations


async def desktop_issue_and_pair(http, port, auth, *, allow_insert=False, allow_capture=False):
    code = auth.new_pairing_challenge()
    response = await http.post(f"http://127.0.0.1:{port}/v3/pair", json={"code": code})
    creds = await response.json()
    if allow_insert or allow_capture:
        auth.set_grants(creds["session_id"], allow_insert=allow_insert, allow_capture=allow_capture)
        creds["allow_insert"] = bool(allow_insert)
        creds["allow_capture"] = bool(allow_capture)
    return creds

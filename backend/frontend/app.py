"""NiceGUI frontend app — mounted on the FastAPI server.

Pages:
  1. Inbox — raw captures + "compile" button
  2. Wiki — article view with backlinks
  3. Graph — full graph explorer (ECharts)
  4. Query — chat-style interface with point-in-time picker
  5. Digest — daily/weekly resurfacing + audit results

Authentication:
  All pages are protected. Login page at /login.
  Credentials configured via BRAIN_AUTH_USERNAME / BRAIN_AUTH_PASSWORD env vars.
"""

from __future__ import annotations

from nicegui import ui

from backend.frontend.auth import (
    create_session,
    logout_current,
    require_auth,
    set_session_cookie,
    verify_credentials,
)


def create_frontend(app) -> None:
    """Mount NiceGUI on the FastAPI app and define all pages."""

    @ui.page("/login")
    def login_page():
        _login_page()

    @ui.page("/")
    def index():
        session = require_auth()
        _layout("Home", _home_page, session)

    @ui.page("/inbox")
    def inbox():
        session = require_auth()
        _layout("Inbox", _inbox_page, session)

    @ui.page("/documents")
    def documents():
        session = require_auth()
        _layout("Documents", _documents_page, session)

    @ui.page("/wiki")
    def wiki():
        session = require_auth()
        _layout("Wiki", _wiki_page, session)

    @ui.page("/graph")
    def graph():
        session = require_auth()
        _layout("Graph Explorer", _graph_page, session)

    @ui.page("/query")
    def query():
        session = require_auth()
        _layout("Query", _query_page, session)

    @ui.page("/digest")
    def digest():
        session = require_auth()
        _layout("Digest", _digest_page, session)

    @ui.page("/profile")
    def profile():
        session = require_auth()
        _layout("Profile", _profile_page, session)

    # Mount NiceGUI on the FastAPI app
    ui.run_with(app, mount_path="/ui", title="2ndBrain")


# ── Login page ───────────────────────────────────────────────────────

def _login_page():
    """Login form page."""
    with ui.column().classes(
        "w-full h-screen items-center justify-center bg-gray-50"
    ), ui.card().classes("w-96 p-8"):
        ui.label("🧠 2ndBrain").classes("text-2xl font-bold text-center mb-2")
        ui.label("Sign in to your second brain").classes(
            "text-gray-500 text-center mb-6"
        )

        username = ui.input(
            label="Username",
            placeholder="admin",
        ).classes("w-full mb-3")

        password = ui.input(
            label="Password",
            password=True,
            placeholder="••••••••",
        ).classes("w-full mb-4")

        error_label = ui.label("").classes("text-red-500 text-sm mb-2 hidden")

        async def do_login():
            if not username.value or not password.value:
                error_label.text = "Please enter username and password"
                error_label.classes(remove="hidden")
                return

            if verify_credentials(username.value, password.value):
                token = create_session(username.value)
                set_session_cookie(token)
                # Redirect to the page they were trying to access
                next_url = "/"
                try:
                    req_path = ui.context.client.environ.get("asgi.scope", {}).get("path", "/")
                    qs = ui.context.client.environ.get("asgi.scope", {}).get("query_string", b"")
                    if isinstance(qs, bytes):
                        qs = qs.decode()
                    if "next=" in qs:
                        next_url = qs.split("next=")[1].split("&")[0]
                except Exception:
                    pass
                ui.navigate.to(next_url)
            else:
                error_label.text = "Invalid username or password"
                error_label.classes(remove="hidden")

        ui.button("Sign In", on_click=do_login).classes(
            "w-full bg-blue-500 text-white"
        ).on("keydown.enter", do_login)


# ── Layout ───────────────────────────────────────────────────────────

def _layout(title: str, content_func, session=None) -> None:
    """Shared layout with navigation sidebar and user info."""
    with ui.column().classes("w-full h-screen"):
        # Top navigation bar
        with ui.row().classes("w-full items-center bg-gray-900 text-white px-4 py-2"):
            ui.label("🧠 2ndBrain").classes("text-xl font-bold mr-8")
            ui.link("Home", "/").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Inbox", "/inbox").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Documents", "/documents").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Profile", "/profile").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Wiki", "/wiki").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Graph", "/graph").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Query", "/query").classes("text-gray-300 hover:text-white mr-4")
            ui.link("Digest", "/digest").classes("text-gray-300 hover:text-white mr-4")

            # Spacer + user info + logout
            ui.space()
            if session and session.user:
                ui.label(f"👤 {session.user}").classes("text-gray-400 text-sm mr-3")

            def _do_logout():
                logout_current()
                ui.navigate.to("/login")

            ui.button("Logout", on_click=_do_logout).classes(
                "text-gray-300 hover:text-white text-sm"
            ).props("flat dense")

        # Page content
        with ui.column().classes("w-full p-6 overflow-auto flex-1"):
            content_func()


# ── Page content functions ───────────────────────────────────────────

def _home_page():
    ui.label("2ndBrain — Personal Second Brain").classes("text-2xl font-bold mb-4")
    ui.label(
        "A personal knowledge system with bi-temporal memory. "
        "Ingest notes, build a knowledge graph, and query your memory over time."
    ).classes("text-gray-600 mb-6")

    with ui.row().classes("gap-4"):
        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/inbox")):
            ui.label("📥 Inbox").classes("text-lg font-bold")
            ui.label("Ingest notes & files").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/documents")):
            ui.label("📄 Documents").classes("text-lg font-bold")
            ui.label("Files with a purpose").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/wiki")):
            ui.label("📚 Wiki").classes("text-lg font-bold")
            ui.label("Browse articles").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/graph")):
            ui.label("🕸️ Graph").classes("text-lg font-bold")
            ui.label("Explore knowledge graph").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/query")):
            ui.label("🔍 Query").classes("text-lg font-bold")
            ui.label("Ask your second brain").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/digest")):
            ui.label("📊 Digest").classes("text-lg font-bold")
            ui.label("Activity & contradictions").classes("text-sm text-gray-500")

        with ui.card().classes("p-4 w-48 cursor-pointer").on("click", lambda: ui.navigate.to("/profile")):
            ui.label("👤 Profile").classes("text-lg font-bold")
            ui.label("Facts, goals & timeline").classes("text-sm text-gray-500")

    # Life dashboard: one chronological feed of what needs attention
    ui.label("Upcoming").classes("text-lg font-bold mt-6 mb-2")
    reminders_box = ui.column().classes("w-full")

    async def load_reminders():
        import httpx
        reminders_box.clear()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:8000/reminders", timeout=10)
        except httpx.HTTPError:
            return
        if resp.status_code != 200:
            return
        rows = resp.json().get("reminders") or []
        with reminders_box:
            if not rows:
                ui.label("Nothing on the horizon. 👍").classes("text-sm text-gray-500")
                return
            for row in rows[:8]:
                days = row.get("days_left")
                urgency = row.get("urgency") or "green"
                dot = {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(urgency, "🟢")
                when = f"{'in' if (days or 0) >= 0 else ''} {abs(days) if days is not None else '?'}d"
                with ui.row().classes("items-center gap-2 w-full max-w-3xl"):
                    ui.label(dot)
                    ui.label(f"{row['kind']}: {row['title']}").classes("text-sm")
                    ui.label(f"({row.get('remind_on') or '—'} · {when})").classes(
                        "text-xs text-gray-400"
                    )

    ui.timer(0.5, load_reminders, once=True)


def _inbox_page():
    ui.label("📥 Inbox").classes("text-2xl font-bold mb-4")
    ui.label("Ingest notes, PDFs, and web clips into your second brain.").classes(
        "text-gray-600 mb-4"
    )

    # Ingest form
    with ui.card().classes("w-full max-w-2xl p-6"):
        ui.label("Ingest Source").classes("text-lg font-bold mb-2")

        source_type = ui.select(
            ["markdown", "pdf"],
            value="markdown",
            label="Source Type",
        ).classes("w-full mb-2")

        source_path = ui.input(
            label="File or directory path",
            placeholder="data/sample_vault",
        ).classes("w-full mb-2")

        extract_toggle = ui.switch("Run LLM extraction (requires API key)", value=False)

        async def do_ingest():
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:8000/ingest",
                    json={
                        "source": source_path.value,
                        "source_type": source_type.value,
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    ui.notify(
                        f"Ingested {result['num_captures']} captures, "
                        f"{result['num_chunks']} chunks",
                        type="positive",
                    )
                else:
                    ui.notify(f"Error: {resp.text}", type="negative")

        ui.button("Ingest", on_click=do_ingest).classes("bg-blue-500 text-white")

    # Capture sources status strip
    with ui.card().classes("w-full max-w-2xl p-4 mt-4"):
        ui.label("Capture Sources").classes("font-bold mb-2")
        sources_box = ui.column().classes("gap-1")

        async def load_sources():
            import httpx
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get("http://localhost:8000/documents/status", timeout=10)
                except httpx.HTTPError:
                    return
                if resp.status_code != 200:
                    return
                data = resp.json()
                sources_box.clear()
                with sources_box:
                    wa = data.get("whatsapp", {})
                    if wa.get("ready"):
                        dot, note = "🟢", "connected"
                    elif wa.get("configured"):
                        dot, note = "🟡", "configured · signature/allow-list incomplete"
                    else:
                        dot, note = "🔴", "not configured"
                    if wa.get("last_capture"):
                        note += f" · last capture {wa['last_capture'][:16].replace('T', ' ')} UTC"
                    ui.label(f"{dot} WhatsApp   {note}").classes("text-sm text-gray-700")

                    vault = data.get("vault", {})
                    vdot = "🟢" if vault.get("exists") else "🔴"
                    vnote = f"watching {vault.get('dir')}" if vault.get("exists") else "missing"
                    if vault.get("last_capture"):
                        vnote += f" · last capture {vault['last_capture'][:16].replace('T', ' ')} UTC"
                    ui.label(f"{vdot} Vault folder   {vnote}").classes("text-sm text-gray-700")

        ui.timer(1.0, load_sources, once=True)

    # Stats
    with ui.card().classes("w-full max-w-2xl p-6 mt-4"):
        ui.label("Storage Stats").classes("text-lg font-bold mb-2")
        stats_label = ui.label("Loading...").classes("text-gray-500")

        async def load_stats():
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:8000/ingest/stats")
                if resp.status_code == 200:
                    data = resp.json()
                    stats_label.text = (
                        f"Episodic chunks: {data['episodic_count']} | "
                        f"BM25 documents: {data['bm25_count']}"
                    )

        ui.timer(1.0, load_stats, once=True)


_STATUS_COLORS = {
    "red": "bg-red-100 text-red-800",
    "amber": "bg-yellow-100 text-yellow-800",
    "green": "bg-green-100 text-green-800",
    "none": "bg-gray-100 text-gray-600",
}


def _documents_page():
    """Phase 7 — 'files with a purpose', browsable by intent not filename."""
    import httpx

    ui.label("📄 Documents").classes("text-2xl font-bold mb-1")
    ui.label("Everything captured with a purpose — search by what it's for, not what it's called.").classes(
        "text-gray-600 mb-4"
    )

    active_tag = {"value": "All"}
    search_input = ui.input(placeholder="Search title, purpose, filename...").classes("w-72")
    chips_row = ui.row().classes("gap-2 mb-4")
    container = ui.column().classes("w-full")

    def _status_chip(doc: dict):
        status = doc.get("status") or "none"
        days = doc.get("days_left")
        if status == "red" and days is not None:
            label = f"{'expired' if days < 0 else 'expires'} in {abs(days)}d"
        elif status == "amber" and days is not None:
            label = f"relevant in {days}d"
        elif status == "green":
            label = f"relevant until {str(doc.get('valid_until'))[:10]}"
        else:
            label = "no deadline"
        ui.badge(label).classes(f"px-2 py-1 rounded text-xs {_STATUS_COLORS.get(status, _STATUS_COLORS['none'])}")

    def _render(docs: list[dict]):
        container.clear()
        term = (search_input.value or "").lower().strip()
        with container:
            if not docs:
                ui.label("No documents yet. Send one to your WhatsApp brain number, or ingest a PDF above.").classes(
                    "text-gray-500"
                )
            for doc in docs:
                haystack = " ".join(
                    filter(None, [doc.get("title"), doc.get("usage_context"),
                                  doc.get("filename"), " ".join(doc.get("purpose_tags", []))])
                ).lower()
                if term and term not in haystack:
                    continue

                with ui.card().classes("w-full max-w-3xl p-4 mb-3"):
                    with ui.row().classes("items-center gap-3 w-full"):
                        ui.label("📄").classes("text-2xl")
                        with ui.column().classes("gap-0 flex-1"):
                            ui.label(doc.get("title") or "Untitled").classes("font-bold")
                            ui.label(f"“{doc.get('usage_context') or 'no purpose recorded'}”").classes(
                                "text-sm text-gray-600"
                            )
                            meta = f"via {doc.get('source_channel', 'unknown')} · captured {str(doc.get('recorded_at'))[:10]}"
                            if doc.get("inferred_by"):
                                meta += f" · purpose by {doc['inferred_by']}"
                            ui.label(meta).classes("text-xs text-gray-400")
                            tags = doc.get("purpose_tags") or []
                            if tags:
                                with ui.row().classes("gap-1"):
                                    for t in tags:
                                        ui.badge(t).classes("bg-blue-100 text-blue-800 text-xs")
                        with ui.column().classes("items-end gap-2"):
                            _status_chip(doc)
                            with ui.row().classes("gap-2"):
                                if doc.get("has_file"):
                                    ui.link("Download", f"/documents/{doc['document_id']}/file").classes(
                                        "text-sm text-blue-600"
                                    )
                                edit_btn = ui.button("Edit purpose").props("flat dense size=sm")

                    # Inline editor — same supersede call the WhatsApp reply flow uses
                    edit_box = ui.column().classes("w-full hidden")
                    editor = ui.textarea(value=doc.get("usage_context") or "").classes("w-full")
                    with ui.row().classes("gap-2"):
                        save_btn = ui.button("Save").classes("bg-blue-500 text-white")
                        cancel_btn = ui.button("Cancel").props("flat")

                    def _start_edit(d=doc, box=edit_box, ed=editor):
                        box.classes(remove="hidden")
                        ed.value = d.get("usage_context") or ""

                    async def _save(d=doc, box=edit_box, ed=editor):
                        text = (ed.value or "").strip()
                        if not text:
                            ui.notify("Purpose cannot be empty", type="negative")
                            return
                        async with httpx.AsyncClient() as client:
                            resp = await client.post(
                                f"http://localhost:8000/documents/{d['document_id']}/correct",
                                json={"usage_context": text},
                                timeout=30,
                            )
                        if resp.status_code == 200:
                            ui.notify("Purpose updated (old version kept in history)", type="positive")
                            await load()
                        else:
                            ui.notify(f"Error: {resp.text}", type="negative")

                    def _cancel(box=edit_box):
                        box.classes(add="hidden")

                    # Wire AFTER the handlers exist (each loop pass gets its own
                    # closures via default args — no shared loop-variable bug).
                    edit_btn.on("click", _start_edit)
                    save_btn.on_click(_save)
                    cancel_btn.on_click(_cancel)

    async def load():
        import httpx
        params = {}
        if active_tag["value"] and active_tag["value"] != "All":
            params["tag"] = active_tag["value"]
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/documents", params=params, timeout=30)
        if resp.status_code != 200:
            container.clear()
            with container:
                ui.label(f"Error loading documents: {resp.text}").classes("text-red-500")
            return
        data = resp.json()
        _render_chips(data.get("tags") or [])
        _render(data.get("documents") or [])

    def _render_chips(tags: list[str]):
        chips_row.clear()
        with chips_row:
            for tag in ["All"] + tags:
                is_active = tag == active_tag["value"]
                btn = ui.button(tag).props("flat dense size=sm").classes(
                    "bg-blue-600 text-white" if is_active else "bg-gray-100 text-gray-700"
                )
                btn.on_click(lambda t=tag: _select_tag(t))

    def _select_tag(tag: str):
        active_tag["value"] = tag
        import asyncio
        asyncio.create_task(load())

    def _search_changed():
        import asyncio
        asyncio.create_task(load())

    search_input.on("change", lambda: _search_changed())
    search_input.on("keydown.enter", lambda: _search_changed())

    ui.timer(0.5, load, once=True)


def _profile_page():
    ui.label("👤 Profile").classes("text-2xl font-bold mb-4")
    ui.label(
        "Structured facts, family graph, goals and timeline — every change "
        "supersedes the old value instead of overwriting it."
    ).classes("text-gray-600 mb-4")

    # ── 1. Contradiction review queue (explicit accept/reject) ──
    ui.label("Needs your confirmation").classes("text-lg font-bold mt-2")
    queue_box = ui.column().classes("w-full mb-6")

    async def resolve(item_id: str, accept: bool):
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://localhost:8000/contradictions/{item_id}/resolve",
                json={"accept": accept},
                timeout=15,
            )
        await load_queue()
        await load_fields()

    async def load_queue():
        import httpx
        queue_box.clear()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:8000/contradictions", timeout=10)
        except httpx.HTTPError:
            return
        if resp.status_code != 200:
            return
        rows = resp.json().get("contradictions") or []
        with queue_box:
            if not rows:
                ui.label("No unresolved conflicts. ✅").classes("text-sm text-gray-500")
                return
            for row in rows:
                with ui.card().classes("w-full max-w-3xl p-4 mb-2"):
                    ui.label(row.get("profile_field", "")).classes("font-bold text-sm")
                    with ui.row().classes("items-center gap-2 mt-1"):
                        ui.label(f"on record: {row.get('existing_value', '—')}").classes("text-sm text-gray-600")
                        ui.label("→").classes("text-gray-400")
                        ui.label(f"proposed: {row.get('proposed_value', '—')}").classes("text-sm")
                    with ui.row().classes("gap-2 mt-2"):
                        ui.button("Accept", color="green").classes("text-sm").on(
                            "click", lambda e=row: resolve(e["id"], True)
                        )
                        ui.button("Reject", color="red").props("flat").classes("text-sm").on(
                            "click", lambda e=row: resolve(e["id"], False)
                        )

    # ── 2. Profile fields with per-field history ──
    ui.label("Facts").classes("text-lg font-bold mt-4 mb-2")
    fields_box = ui.column().classes("w-full mb-4")

    async def save_field(field: str, value: str):
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8000/profile",
                json={"field": field, "value": value},
                timeout=15,
            )
        await load_fields()

    async def load_history(field: str, container):
        import httpx
        container.clear()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:8000/profile/history", params={"field": field}, timeout=10
            )
        if resp.status_code != 200:
            return
        with container:
            for row in resp.json().get("history", []):
                badge = "current" if not row.get("superseded_by") else "superseded"
                ui.label(
                    f"• {row['value']}  [{badge}]  from {row.get('valid_from') or '?'}"
                ).classes("text-xs text-gray-500 ml-4")

    async def load_fields():
        import httpx
        fields_box.clear()
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/profile", timeout=10)
        if resp.status_code != 200:
            return
        data = resp.json()
        encrypted = set(data.get("encrypted_fields") or [])
        with fields_box:
            if not data["fields"]:
                ui.label("No profile fields yet — add one below.").classes(
                    "text-sm text-gray-500"
                )
            for field, value in sorted(data["fields"].items()):
                with ui.card().classes("w-full max-w-3xl p-3 mb-2"):
                    with ui.row().classes("w-full items-center gap-2"):
                        lock = " 🔒" if field in encrypted else ""
                        ui.label(f"{field}{lock}").classes("text-sm font-bold w-56")
                        edit = ui.input(value=value).classes("flex-1")
                        ui.button("Save", color="blue").props("flat dense").classes("text-sm").on(
                            "click", lambda f=field, e=edit: save_field(f, e.value or "")
                        )
                        hist_box = ui.column().classes("w-full")
                        ui.button("History").props("flat dense").classes("text-sm").on(
                            "click", lambda b=hist_box, f=field: load_history(f, b)
                        )
            with ui.card().classes("w-full max-w-3xl p-3 mb-2 border-dashed"):
                ui.label("Add / update field").classes("text-sm font-bold mb-2")
                new_field = ui.input(label="field", placeholder="e.g. current_address").classes("w-64 mr-2")
                new_value = ui.input(label="value").classes("flex-1")
                ui.button("Set").props("dense").classes("text-sm").on(
                    "click",
                    lambda: save_field(
                        (new_field.value or "").strip().lower().replace(" ", "_"),
                        new_value.value or "",
                    ),
                )

    # ── 3. Relationships ──
    ui.label("Family & contacts").classes("text-lg font-bold mt-4 mb-2")
    rel_box = ui.column().classes("w-full mb-4")

    async def load_rels():
        import httpx
        rel_box.clear()
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/profile/relationships", timeout=10)
        if resp.status_code != 200:
            return
        with rel_box:
            rows = resp.json().get("relationships") or []
            if not rows:
                ui.label("No relationships recorded yet.").classes("text-sm text-gray-500")
            for row in rows:
                ui.label(f"• {row['relation']} → {row['name']}").classes("text-sm")
        # add form
        with rel_box, ui.row().classes("items-center gap-2 mt-2"):
            pname = ui.input(label="name").classes("w-56")
            prel = ui.input(label="relation", placeholder="father").classes("w-40")

            async def add_person():
                import httpx
                if not pname.value or not prel.value:
                    return
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "http://localhost:8000/profile/people",
                        json={"name": pname.value, "relation": prel.value},
                        timeout=15,
                    )
                await load_rels()

            ui.button("Add", color="blue").props("dense").classes("text-sm").on("click", add_person)

    # ── 4. Goals ──
    ui.label("Goals").classes("text-lg font-bold mt-4 mb-2")
    goals_box = ui.column().classes("w-full mb-4")

    async def check_in(goal_id: str, percent: int):
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://localhost:8000/profile/goals/{goal_id}/checkins",
                json={"percent": percent, "note": ""},
                timeout=15,
            )
        await load_goals()

    async def load_goals():
        import httpx
        goals_box.clear()
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/profile/goals", timeout=10)
        if resp.status_code != 200:
            return
        rows = resp.json().get("goals") or []
        with goals_box:
            if not rows:
                ui.label("No goals yet.").classes("text-sm text-gray-500")
            for goal in rows:
                with ui.card().classes("w-full max-w-3xl p-3 mb-2"):
                    with ui.row().classes("items-center gap-3 w-full"):
                        ui.label(goal["title"]).classes("font-bold text-sm flex-1")
                        ui.label(goal.get("category") or "").classes("text-xs text-gray-400")
                        if goal.get("target_date"):
                            ui.label(f"target {goal['target_date']}").classes("text-xs text-gray-400")
                    ui.label(f"{goal['progress']}% complete").classes("text-sm text-gray-600")
                    with ui.row().classes("gap-2 mt-1"):
                        for pct in (10, 25, 50, 75, 100):
                            ui.button(str(pct)).props("flat dense").classes("text-xs").on(
                                "click", lambda g=goal["goal_id"], p=pct: check_in(g, p)
                            )
            with ui.row().classes("items-center gap-2 mt-2"):
                gtitle = ui.input(label="goal").classes("w-64")
                gcat = ui.select(["Career", "Academic", "Personal", "Competitive Programming", "General"],
                                 value="General", label="category").classes("w-48")

                async def add_goal():
                    import httpx
                    if not gtitle.value:
                        return
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8000/profile/goals",
                            json={"title": gtitle.value, "category": gcat.value},
                            timeout=15,
                        )
                    await load_goals()

                ui.button("Add goal", color="blue").props("dense").classes("text-sm").on("click", add_goal)

    # ── 5. Timeline ──
    ui.label("Timeline").classes("text-lg font-bold mt-4 mb-2")
    timeline_box = ui.column().classes("w-full mb-6")

    async def load_timeline():
        import httpx
        timeline_box.clear()
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/profile/timeline", timeout=10)
        if resp.status_code != 200:
            return
        rows = resp.json().get("events") or []
        with timeline_box:
            if not rows:
                ui.label("No events yet.").classes("text-sm text-gray-500")
            for ev in rows:
                with ui.row().classes("items-center gap-3 max-w-3xl"):
                    ui.label(ev.get("event_date") or "—").classes("text-xs text-gray-400 w-24")
                    ui.label(ev["title"]).classes("text-sm")
                    ui.label(ev.get("category") or "").classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-2 mt-2"):
                etitle = ui.input(label="event").classes("w-64")
                edate = ui.input(label="date (YYYY-MM-DD)", placeholder="2026-09-26").classes("w-44")

                async def add_event():
                    import httpx
                    if not etitle.value:
                        return
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8000/profile/timeline",
                            json={"title": etitle.value, "event_date": edate.value or None},
                            timeout=15,
                        )
                    await load_timeline()

                ui.button("Add event", color="blue").props("dense").classes("text-sm").on("click", add_event)

    async def load_all():
        await load_queue()
        await load_fields()
        await load_rels()
        await load_goals()
        await load_timeline()

    ui.timer(0.5, load_all, once=True)


def _wiki_page():
    ui.label("📚 Wiki").classes("text-2xl font-bold mb-4")
    ui.label("Browse knowledge clusters and topic summaries.").classes(
        "text-gray-600 mb-4"
    )

    clusters_container = ui.column().classes("w-full")

    async def load_clusters():
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/community/clusters")
            if resp.status_code == 200:
                data = resp.json()
                clusters_container.clear()
                with clusters_container:
                    if data["total"] == 0:
                        ui.label("No topic clusters yet. Build communities from the Graph page.").classes(
                            "text-gray-500"
                        )
                    for cluster in data["clusters"]:
                        with ui.card().classes("w-full max-w-3xl p-4 mb-2"):
                            ui.label(cluster["label"]).classes("font-bold")
                            ui.label(cluster["summary"]).classes("text-sm text-gray-600 mt-1")
                            ui.label(
                                f"{cluster['fact_count']} facts · {cluster['entity_count']} entities"
                            ).classes("text-xs text-gray-400 mt-1")

    ui.button("Load Topics", on_click=load_clusters).classes("mb-4")
    ui.timer(0.5, load_clusters, once=True)


def _graph_page():
    ui.label("🕸️ Knowledge Graph Explorer").classes("text-2xl font-bold mb-4")

    with ui.row().classes("gap-4 mb-4"):
        # Filters
        entity_filter = ui.input(label="Entity filter").classes("w-48")
        include_superseded = ui.switch("Include superseded", value=False)

        async def load_graph():
            import httpx
            params = {"include_superseded": include_superseded.value}
            if entity_filter.value:
                params["entity_type"] = entity_filter.value

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "http://localhost:8000/graph/export",
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    render_graph(data["elements"])

        ui.button("Load Graph", on_click=load_graph).classes("bg-blue-500 text-white")

    # ECharts container
    chart = ui.echart({
        "series": [{
            "type": "graph",
            "layout": "force",
            "animation": True,
            "roam": True,
            "label": {"show": True, "fontSize": 10},
            "edgeLabel": {"show": True, "fontSize": 8},
            "data": [],
            "links": [],
            "force": {
                "repulsion": 200,
                "edgeLength": 100,
                "gravity": 0.1,
            },
        }]
    }).classes("w-full h-[600px]")

    def render_graph(elements: list[dict]):
        nodes = []
        links = []
        for el in elements:
            if el["group"] == "nodes":
                d = el["data"]
                nodes.append({
                    "id": d["id"],
                    "name": d.get("label", d["id"]),
                    "symbolSize": 30,
                    "itemStyle": {"color": d.get("color", "#95A5A6")},
                })
            elif el["group"] == "edges":
                d = el["data"]
                links.append({
                    "source": d["source"],
                    "target": d["target"],
                    "label": {"show": True, "formatter": d.get("label", "")},
                    "lineStyle": {"color": d.get("color", "#BDC3C7")},
                })

        chart.options["series"][0]["data"] = nodes
        chart.options["series"][0]["links"] = links
        chart.update()


def _query_page():
    ui.label("🔍 Query Your Second Brain").classes("text-2xl font-bold mb-4")

    with ui.card().classes("w-full max-w-3xl p-6"):
        query_input = ui.textarea(
            label="Ask a question",
            placeholder="What did I believe about X as of March 2026?",
        ).classes("w-full mb-2")

        with ui.row().classes("gap-4 mb-4 items-end"):
            top_k = ui.number(label="Top K", value=10, min=1, max=50).classes("w-24")
            valid_as_of = ui.input(label="Point-in-time (YYYY-MM-DD)").classes("w-48")

        results_container = ui.column().classes("w-full mt-4")

        async def do_query():
            import httpx
            payload = {
                "query": query_input.value,
                "top_k": int(top_k.value),
            }
            if valid_as_of.value:
                payload["valid_as_of"] = valid_as_of.value

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:8000/query",
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results_container.clear()
                    with results_container:
                        ui.label(f"Found {data['total']} results from: {', '.join(data['sources_used'])}").classes(
                            "text-sm text-gray-500 mb-2"
                        )
                        for r in data["results"]:
                            with ui.card().classes("w-full p-3 mb-2"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge(r["source"]).classes("bg-blue-100 text-blue-800")
                                    ui.label(f"Score: {r['score']:.3f}").classes("text-xs text-gray-400")
                                ui.label(r["text"]).classes("text-sm mt-1")
                else:
                    ui.notify(f"Error: {resp.text}", type="negative")

        ui.button("Search", on_click=do_query).classes("bg-blue-500 text-white")


def _digest_page():
    ui.label("📊 Digest & Surfacing").classes("text-2xl font-bold mb-4")

    # Documents needing attention — same query the WhatsApp nudge uses,
    # so the dashboard and the message can never disagree.
    attention_box = ui.column().classes("w-full mb-6")

    async def load_attention():
        import httpx
        attention_box.clear()
        with attention_box:
            ui.label("Documents needing attention").classes("text-lg font-bold mb-2")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get("http://localhost:8000/documents/expiring", timeout=15)
            except httpx.HTTPError:
                ui.label("(could not reach the documents API)").classes("text-sm text-gray-400")
                return
            if resp.status_code != 200:
                ui.label("(documents API error)").classes("text-sm text-gray-400")
                return
            docs = resp.json().get("documents") or []
            if not docs:
                ui.label("Nothing expiring soon. 👍").classes("text-sm text-gray-500")
                return
            for doc in docs:
                status = doc.get("status", "none")
                days = doc.get("days_left")
                icon = {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(status, "⚪")
                if days is None:
                    timing = ""
                elif days < 0:
                    timing = f" — expired {abs(days)} days ago"
                elif days == 0:
                    timing = " — expires today"
                else:
                    timing = f" — {status} in {days} days"
                row_classes = {
                    "red": "bg-red-100",
                    "amber": "bg-yellow-100",
                }.get(status, "bg-gray-50")
                with ui.card().classes(f"w-full max-w-3xl p-3 mb-2 {row_classes}"):
                    ui.label(f"{icon} {doc.get('title', 'document')}{timing}").classes("font-bold text-sm")
                    ui.label(doc.get("usage_context") or "no purpose recorded").classes(
                        "text-xs text-gray-600 mt-1"
                    )

    ui.timer(0.5, load_attention, once=True)

    with ui.row().classes("gap-4 mb-4"):
        digest_type = ui.select(["daily", "weekly"], value="daily", label="Digest type")
        ui.button("Generate Digest", on_click=lambda: generate_digest()).classes(
            "bg-blue-500 text-white"
        )
        ui.button("Detect Contradictions", on_click=lambda: find_contradictions()).classes(
            "bg-orange-500 text-white"
        )

    digest_container = ui.column().classes("w-full")

    async def generate_digest():
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/surfing/digest",
                json={"digest_type": digest_type.value},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                digest_container.clear()
                with digest_container, ui.card().classes("w-full max-w-3xl p-6"):
                    ui.label(data["summary"]).classes("font-bold text-lg mb-4")
                    for entry in data["entries"]:
                        with ui.card().classes("w-full p-3 mb-2 bg-gray-50"):
                            ui.label(entry["title"]).classes("font-bold")
                            ui.label(entry["description"]).classes(
                                "text-sm text-gray-600 mt-1 whitespace-pre-line"
                            )

    async def find_contradictions():
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/surfing/contradictions",
                json={},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                digest_container.clear()
                with digest_container:
                    ui.label(f"Found {data['total']} contradictions").classes(
                        "font-bold text-lg mb-4"
                    )
                    for c in data["contradictions"]:
                        severity_color = {
                            "info": "bg-blue-100",
                            "warning": "bg-yellow-100",
                            "critical": "bg-red-100",
                        }.get(c["severity"], "bg-gray-100")

                        with ui.card().classes(
                            f"w-full max-w-3xl p-3 mb-2 {severity_color}"
                        ):
                            ui.label(
                                f"{c['subject']} {c['predicate']}"
                            ).classes("font-bold")
                            ui.label(
                                f"'{c['old_value']}' → '{c['new_value']}'"
                            ).classes("text-sm mt-1")
                            ui.label(
                                f"Old: {c.get('old_valid_from', '?')} → "
                                f"New: {c.get('new_valid_from', '?')}"
                            ).classes("text-xs text-gray-500 mt-1")

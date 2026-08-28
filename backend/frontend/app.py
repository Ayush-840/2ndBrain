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

import json

from nicegui import ui

from backend.frontend.auth import (
    require_auth,
    verify_credentials,
    create_session,
    set_session_storage,
    clear_session_storage,
    logout_current,
    is_auth_enabled,
    check_auth_client_storage,
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

    # Mount NiceGUI on the FastAPI app
    ui.run_with(app, mount_path="/ui", title="2ndBrain")


# ── Login page ───────────────────────────────────────────────────────

def _login_page():
    """Login form page."""
    with ui.column().classes(
        "w-full h-screen items-center justify-center bg-gray-50"
    ):
        with ui.card().classes("w-96 p-8"):
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
                    set_session_storage(token)
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
                with clusters_container:
                    ui.clear()
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
                    with results_container:
                        ui.clear()
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
                with digest_container:
                    ui.clear()
                    with ui.card().classes("w-full max-w-3xl p-6"):
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
                with digest_container:
                    ui.clear()
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

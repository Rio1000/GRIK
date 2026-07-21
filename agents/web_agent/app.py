"""
Web agent — Grik's window on the internet.

Gives Grik broad web reach: search + fetch-and-read. Uses a SearXNG instance
(self-hosted, private meta-search) by default so you're not tied to one
provider; swap SEARX_URL for any search API you prefer.
"""
import os
import httpx
from selectolax.parser import HTMLParser

from agentlib import Tool, make_agent_app

SEARX_URL = os.getenv("SEARX_URL", "http://searxng:8080").rstrip("/")


def web_search(query: str) -> str:
    """Search the web and return the top results with titles, URLs and snippets."""
    r = httpx.get(f"{SEARX_URL}/search",
                  params={"q": query, "format": "json"}, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])[:6]
    return "\n".join(
        f"- {x.get('title')}\n  {x.get('url')}\n  {x.get('content','')}" for x in results
    ) or "No results."


def fetch_page(url: str) -> str:
    """Fetch a URL and return its readable text (truncated)."""
    r = httpx.get(url, timeout=30, follow_redirects=True,
                  headers={"User-Agent": "GrikBot/1.0"})
    r.raise_for_status()
    tree = HTMLParser(r.text)
    for tag in tree.css("script, style, nav, footer, header"):
        tag.decompose()
    text = " ".join(tree.body.text().split()) if tree.body else ""
    return text[:6000]


TOOLS = [
    Tool(web_search, {"name": "web_search", "description": web_search.__doc__,
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}),
    Tool(fetch_page, {"name": "fetch_page", "description": fetch_page.__doc__,
         "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}),
]

ROLE = """You are Grik's web specialist. Answer the instruction by searching the
web and, when useful, fetching a page to read it. Cite the URLs you used.
Give a concise, factual answer."""

app = make_agent_app("web", ROLE, TOOLS)

from app.parser.html import HtmlDocumentParser, normalize_document_text
from app.parser.types import ParseFailureReason, ParserConfig


def test_parse_extracts_internal_document_schema() -> None:
    html = b"""
    <!doctype html>
    <html>
      <head>
        <title>Ignored Browser Title</title>
        <meta property="og:title" content="Careers at Example">
        <link rel="canonical" href="/careers">
        <script>window.noise = true;</script>
      </head>
      <body>
        <nav>Home Jobs Jobs</nav>
        <main>
          <h1>Careers at Example</h1>
          <h2>Build infrastructure with us</h2>
          <p>Join the platform team.</p>
          <p>Work on indexing pipelines and reliable systems.</p>
        </main>
      </body>
    </html>
    """

    result = HtmlDocumentParser().parse(
        html,
        source_url="https://example.com/jobs",
        final_url="https://example.com/jobs?ref=redirect",
        content_type="text/html; charset=utf-8",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_url == "https://example.com/jobs"
    assert result.document.final_url == "https://example.com/jobs?ref=redirect"
    assert result.document.canonical_url == "https://example.com/careers"
    assert result.document.title == "Careers at Example"
    assert result.document.headings == ("Careers at Example", "Build infrastructure with us")
    assert "window.noise" not in result.document.normalized_text
    assert "Join the platform team." in result.document.normalized_text


def test_parse_falls_back_to_body_when_main_is_absent() -> None:
    html = """
    <html>
      <body>
        <h1>Open roles</h1>
        <p>We are hiring backend engineers for crawler and parser systems.</p>
      </body>
    </html>
    """

    result = HtmlDocumentParser().parse(
        html,
        source_url="https://example.com/careers",
        content_type="text/html",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.canonical_url == "https://example.com/careers"
    assert result.document.title == "Open roles"
    assert "backend engineers" in result.document.normalized_text


def test_parse_rejects_non_html_content_type() -> None:
    result = HtmlDocumentParser().parse(
        b'{"message": "not html"}',
        source_url="https://example.com/api/jobs",
        content_type="application/json",
    )

    assert not result.succeeded
    assert result.failure_reason == ParseFailureReason.non_html_content


def test_parse_rejects_empty_content() -> None:
    result = HtmlDocumentParser().parse(
        b"",
        source_url="https://example.com/careers",
        content_type="text/html",
    )

    assert not result.succeeded
    assert result.failure_reason == ParseFailureReason.empty_content


def test_parse_rejects_html_without_meaningful_text() -> None:
    result = HtmlDocumentParser(ParserConfig(min_text_length=20)).parse(
        "<html><body><main><p>Jobs</p></main></body></html>",
        source_url="https://example.com/careers",
        content_type="text/html",
    )

    assert not result.succeeded
    assert result.failure_reason == ParseFailureReason.no_meaningful_text


def test_parse_handles_malformed_html() -> None:
    result = HtmlDocumentParser().parse(
        "<html><body><main><h1>Careers<p>Backend indexing platform roles are open",
        source_url="https://example.com/careers",
        content_type="text/html",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.title == "Careers Backend indexing platform roles are open"
    assert "Backend indexing platform roles are open" in result.document.normalized_text


def test_parse_is_deterministic_for_same_input() -> None:
    html = """
    <html>
      <head>
        <title>Example Careers</title>
        <link rel="canonical" href="/careers">
      </head>
      <body>
        <main>
          <h1>Example Careers</h1>
          <p>Backend indexing platform roles are open.</p>
          <p>Help us build reliable document processing systems.</p>
        </main>
      </body>
    </html>
    """
    parser = HtmlDocumentParser()

    results = [
        parser.parse(
            html,
            source_url="https://example.com/jobs",
            final_url="https://example.com/jobs",
            content_type="text/html",
        )
        for _ in range(3)
    ]

    assert all(result.succeeded and result.document is not None for result in results)
    documents = [result.document for result in results]
    assert documents[0] == documents[1] == documents[2]


def test_parse_normalized_text_is_invariant_to_irrelevant_formatting() -> None:
    compact_html = """
    <html><body><main>
      <h1>Careers</h1>
      <p>Backend Engineer</p>
      <p>Build reliable indexing systems.</p>
    </main></body></html>
    """
    formatted_html = """
    <html>
      <body>
        <main>
          <h1>
            Careers
          </h1>
          <p>
              Backend     Engineer
          </p>
          <p>
              Build      reliable
              indexing systems.
          </p>
        </main>
      </body>
    </html>
    """
    parser = HtmlDocumentParser()

    compact_result = parser.parse(
        compact_html,
        source_url="https://example.com/careers",
        content_type="text/html",
    )
    formatted_result = parser.parse(
        formatted_html,
        source_url="https://example.com/careers",
        content_type="text/html",
    )

    assert compact_result.document is not None
    assert formatted_result.document is not None
    assert compact_result.document.normalized_text == formatted_result.document.normalized_text


def test_normalize_document_text_is_stable() -> None:
    text = """
      Careers

      Careers
      Build     reliable\tbackend systems.


      Build     reliable\tbackend systems.
      Apply now.
    """

    assert normalize_document_text(text) == (
        "Careers\nBuild reliable backend systems.\nApply now."
    )

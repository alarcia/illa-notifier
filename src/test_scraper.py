from __future__ import annotations

import os
import unittest

from models import BillboardData
from scraper import CinemaScraper


class TestCinemaScraper(unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = CinemaScraper()
        self.legacy_html_path = os.path.join(
            os.path.dirname(__file__), "..", "debug.html"
        )
        self.new_html_path = os.path.join(
            os.path.dirname(__file__), "..", "debug-new.html"
        )

    def test_parse_empty_html_returns_empty_billboard(self) -> None:
        result = self.scraper.parse_html("<html><body><p>No content</p></body></html>")
        self.assertIsInstance(result, BillboardData)
        self.assertEqual(len(result.movies), 0)
        self.assertEqual(len(result.sessions_by_movie), 0)

    def test_parse_new_website_schema_org_html(self) -> None:
        if not os.path.exists(self.new_html_path):
            self.skipTest("debug-new.html not found in project root")

        with open(self.new_html_path, "r", encoding="utf-8") as f:
            html_text = f.read()

        billboard = self.scraper.parse_html(html_text)

        self.assertGreater(len(billboard.movies), 0, "Should have parsed at least one movie")
        self.assertGreater(len(billboard.sessions_by_movie), 0, "Should have parsed sessions")

        # Verify movie structure
        first_movie = billboard.movies[0]
        self.assertIsInstance(first_movie.movie_id, int)
        self.assertGreater(first_movie.movie_id, 0)
        self.assertTrue(len(first_movie.title) > 0)
        self.assertTrue(first_movie.ticket_url.startswith("https://cinemesilla.com/pelicula/"))

        # Verify sessions for this movie or any movie with sessions
        movie_with_sessions = next(
            (m for m in billboard.movies if billboard.sessions_by_movie.get(m.movie_id)),
            None,
        )
        self.assertIsNotNone(movie_with_sessions)
        assert movie_with_sessions is not None
        sessions = billboard.sessions_by_movie[movie_with_sessions.movie_id]
        self.assertGreater(len(sessions), 0)
        first_session = sessions[0]
        self.assertEqual(first_session.movie_id, movie_with_sessions.movie_id)
        self.assertIn(first_session.format_name, ("CASTELLÀ", "VOSE", "VO", "CATALÀ"))
        self.assertTrue(len(first_session.show_date) > 0)
        self.assertTrue(len(first_session.show_time) > 0)

    def test_vose_detected_from_dotted_tag_and_missing_in_language(self) -> None:
        # Regression: Scrooge VOSE sessions are tagged "V.O.S.E." and have no inLanguage
        html_text = """<html><body>
<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"item":{
  "name":"Scrooge","url":"https://cinemesilla.com/pelicula/scrooge","genre":["Comèdia"],
  "subjectOf":[
    {"url":"https://cinemesilla.com/sesion/a","startDate":"2026-11-14T16:30:00","inLanguage":"es"},
    {"url":"https://cinemesilla.com/sesion/b","startDate":"2026-11-14T19:00:00"},
    {"url":"https://cinemesilla.com/sesion/c","startDate":"2026-11-15T19:00:00"}
  ]}}]}</script>
<section id="cartelera">
  <a href="/sesion/a"><span class="etiqueta sala">Sala 01</span></a>
  <a href="/sesion/b"><span class="etiqueta">V.O.S.E.</span><span class="etiqueta sala">Sala 06</span></a>
</section></body></html>"""
        billboard = self.scraper.parse_html(html_text)
        formats = {s.id: s.format_name for s in billboard.sessions_by_movie[billboard.movies[0].movie_id]}
        self.assertEqual(formats, {"a": "CASTELLÀ", "b": "VOSE", "c": "VOSE"})

    def test_parse_legacy_html_fallback(self) -> None:
        if not os.path.exists(self.legacy_html_path):
            self.skipTest("debug.html not found in project root")

        with open(self.legacy_html_path, "r", encoding="utf-8") as f:
            html_text = f.read()

        billboard = self.scraper.parse_html(html_text)

        self.assertGreater(len(billboard.movies), 0, "Should have parsed at least one movie")
        self.assertGreater(len(billboard.sessions_by_movie), 0, "Should have parsed sessions")

        first_movie = billboard.movies[0]
        self.assertIsInstance(first_movie.movie_id, int)
        self.assertTrue(len(first_movie.title) > 0)
        self.assertTrue(first_movie.ticket_url.startswith("https://cinemesilla.com/FilmTheaterPage"))

        sessions = billboard.sessions_by_movie.get(first_movie.movie_id, [])
        self.assertGreater(len(sessions), 0)
        self.assertEqual(sessions[0].movie_id, first_movie.movie_id)
        self.assertIsNotNone(sessions[0].format_name)


if __name__ == "__main__":
    unittest.main()

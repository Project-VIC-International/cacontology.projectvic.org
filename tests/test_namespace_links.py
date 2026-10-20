"""Resolve generated links as a browser would, using synthetic RDF only."""

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_docs.py"
SPEC = importlib.util.spec_from_file_location("generate_docs", SCRIPT)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for name, value in attrs if name == "href")


class NamespaceLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        (self.output / "index.html").write_text("main page", encoding="utf-8")
        self.graph = Graph()
        self.registry = {}
        self.documents = {}
        for module in ("synthesis", "synthesis/shapes", "synthesis/shapes/nested"):
            prefix = "test-" + module.replace("/", "-")
            ns = Namespace(generator.SITE_BASE_NS + module + "#")
            self.graph.bind(prefix, ns)
            kind = "shape" if module.endswith("shapes") else "class"
            rdf_type = URIRef("http://www.w3.org/ns/shacl#NodeShape") if kind == "shape" else OWL.Class
            self.graph.add((ns.Example, RDF.type, rdf_type))
            self.registry[module] = {"label": module}
            filename = f"{kind}-{prefix}example.html"
            self.documents[module] = filename
            (self.output / filename).write_text("entity page", encoding="utf-8")

    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return generator.generate_namespace_indices(self.graph, self.output, self.registry)

    def page(self, module):
        content = (self.output / module / "index.html").read_text(encoding="utf-8")
        anchors = Anchors()
        anchors.feed(content)
        mapping = json.loads(re.search(r"var entityMap = (.*);", content).group(1))
        return anchors.hrefs, mapping

    def base_url(self, module):
        return generator.SITE_BASE_NS + module + "/"

    def test_entity_links_resolve_from_every_depth(self):
        self.generate()
        for module, filename in self.documents.items():
            with self.subTest(module=module):
                links, _ = self.page(module)
                entity_link = next(link for link in links if link.endswith(filename))
                self.assertEqual(urljoin(self.base_url(module), entity_link), generator.SITE_BASE_NS + filename)

    def test_fragment_redirects_resolve_from_every_depth(self):
        self.generate()
        for module, filename in self.documents.items():
            with self.subTest(module=module):
                _, redirects = self.page(module)
                self.assertEqual(urljoin(self.base_url(module) + "#Example", redirects["Example"]), generator.SITE_BASE_NS + filename)

    def test_back_links_reach_main_page_from_every_depth(self):
        self.generate()
        for module in self.documents:
            with self.subTest(module=module):
                links, _ = self.page(module)
                back_link = next(link for link in links if link.endswith("index.html"))
                self.assertEqual(urljoin(self.base_url(module), back_link), generator.SITE_BASE_NS + "index.html")

    def test_shapes_module_link_stays_under_its_parent(self):
        self.graph.add((URIRef(generator.SITE_BASE_NS + "synthesis/shapes/shapes#Example"), RDF.type, OWL.Class))
        self.registry["synthesis/shapes/shapes"] = {}
        self.generate()
        for module in ("synthesis", "synthesis/shapes"):
            with self.subTest(module=module):
                links, _ = self.page(module)
                shapes_link = next(link for link in links if link.endswith("shapes/"))
                self.assertEqual(urljoin(self.base_url(module), shapes_link), self.base_url(module) + "shapes/")

    def test_flat_entity_index_urls_and_homepage_are_preserved(self):
        entities = self.generate()
        self.assertEqual({entity["doc_url"] for entity in entities}, {generator.SITE_BASE_NS + filename for filename in self.documents.values()})
        self.assertEqual((self.output / "index.html").read_text(encoding="utf-8"), "main page")

    def test_generated_links_validate(self):
        self.generate()
        with contextlib.redirect_stdout(io.StringIO()):
            result = generator.validate_iri_resolution(self.graph, self.output)
        self.assertEqual(result["broken_links"], [])

    def validate_link(self, link):
        page = self.output / "synthesis" / "shapes" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text(f'<a href="{link}">example</a>', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return generator.validate_iri_resolution(Graph(), self.output)["broken_links"]

    def test_validator_reports_wrong_depth_even_when_root_file_exists(self):
        expected = f"{Path('synthesis/shapes/index.html')} -> ../index.html"
        self.assertEqual(self.validate_link("../index.html"), [expected])

    def test_validator_accepts_correct_nested_relative_path(self):
        self.assertEqual(self.validate_link("../../index.html"), [])

    def test_validator_accepts_site_root_relative_path(self):
        self.assertEqual(self.validate_link("/index.html"), [])


if __name__ == "__main__":
    unittest.main()

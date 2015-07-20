from django.test import TestCase
from .models import *
from .connector import PubMedManager

class TestPubMedFetch(TestCase):
    def setUp(self):
        self.manager = PubMedManager()

    def test_fetch(self):
        paper = self.manager.fetch(23144831)

        self.assertEqual(paper.funding.count(), 3)
        self.assertEqual(paper.mesh_headings.count(), 16)
        self.assertTrue(paper.title is not None)
        self.assertTrue(paper.published_in is not None)
        self.assertEqual(paper.authors.count(), 7)

import urllib2
import datetime
import xml.etree.ElementTree as ET
from unidecode import unidecode
import re

from .models import *

def get_smart(e, element):
    elem = e.find(element)
    if elem is not None:
        text = elem.text
        if text is not None:
            text = unidecode(unicode(text))
    else:
        text = ''
    return text


class NCBIManager(object):
    endpoint = ''.join(['http://eutils.ncbi.nlm.nih.gov/entrez/eutils',
                             '/efetch.fcgi?db={db}&id={term}&rettype=xml'])
    searchpoint = ''.join(['http://eutils.ncbi.nlm.nih.gov/entrez/eutils',
                           '/esearch.fcgi?db={db}&term={term}&rettype=xml',
                           '&retmax={retmax}'])

    def get_resource(self, endpoint, **kwargs):
        resource = endpoint.format(db=self.db, **kwargs)
        response_content = urllib2.urlopen(resource).read()
        return ET.fromstring(response_content)

    def fetch(self, identifier):
        result = self.get_resource(self.endpoint, term=identifier)
        return self.process_resource(result, identifier)

    def search(self, query):
        results = self.get_resource(self.searchpoint,
                                    term=urllib2.quote(query.querystring),
                                    retmax=query.retmax)
        return self.process_searchresults(results, query)

class PubMedManager(NCBIManager):
    db = 'PubMed'
    authorlist_path = 'PubmedArticle/MedlineCitation/Article/AuthorList'
    authorname_path = './/Author'
    author_forename = 'ForeName'
    author_surname = 'LastName'
    author_initials = 'Initials'
    date_path = 'PubmedArticle/MedlineCitation/DateCreated'
    date_year_path = 'Year'
    date_month_path = 'Month'
    date_day_path = 'Day'
    journal_path = './/Journal'
    journal_issn_path = './/ISSN'
    journal_title_path = './/Title'
    affiliation_path = 'AffiliationInfo'
    affiliation_instance_path = 'Affiliation'
    abstract_path = './/Abstract'
    abstract_section_path = './/AbstractText'

    def handle_date(self, e):
        date_created = e.find(self.date_path)
        asInt = lambda dpart: 1 if dpart == '' else int(dpart)
        y = asInt(get_smart(date_created, self.date_year_path))
        m = asInt(get_smart(date_created, self.date_month_path))
        d = asInt(get_smart(date_created, self.date_month_path))
        date = datetime.date(y, m, d)

        return date

    def handle_affiliations(self, root, e):
        affiliations = []
        aff_parent = e.find(self.affiliation_path)
        if aff_parent is not None:
            for aff in aff_parent.findall(self.affiliation_instance_path):
                if aff.text is not None:
                    aff_safe = unidecode(unicode(aff.text))
                    i = Institution.objects.get_or_create(name=aff_safe)[0]
                    affiliations.append(i)
        return affiliations

    def handle_authors(self, e, date):
        authors = []
        authorList = e.find(self.authorlist_path)
        if authorList is not None:
            authorNames = authorList.findall(self.authorname_path)
            if authorNames is not None:
                for author in authorNames:
                    a = Person.objects.get_or_create(
                        fore_name = get_smart(author, self.author_forename),
                        last_name = get_smart(author, self.author_surname),
                        defaults={'initials': get_smart(author,
                                                        self.author_initials)}
                    )[0]

                    for inst in self.handle_affiliations(e, author):
                        affiliation = Affiliation(person=a,
                                                  institution=inst,
                                                  date=date)
                        affiliation.save()
                    authors.append(a)
        return authors

    def handle_headings(self, e):
        def g_o_c(model, **kwargs):
            return model.objects.get_or_create(**kwargs)

        mh_path = 'PubmedArticle/MedlineCitation/MeshHeadingList'

        headings = []
        mh = e.find(mh_path)
        if mh is not None:
            for heading in mh.getchildren():
                descriptor_name = get_smart(heading, 'DescriptorName')
                if descriptor_name != '':
                    descriptor, created = g_o_c(MeSHDescriptor,
                                                descriptor=descriptor_name)

                    if len(heading.findall('QualifierName')) > 0:
                        for qualifier_elem in heading.findall('QualifierName'):
                            qual_name = qualifier_elem.text
                            qualifier, created = g_o_c(MeSHQualifier,
                                                       subheading=qual_name)
                            heading, created = g_o_c(MeSHHeading,
                                                     descriptor=descriptor,
                                                     qualifier=qualifier)
                            headings.append(heading)
                    else:
                        heading, created = g_o_c(MeSHHeading,
                                                 descriptor=descriptor,
                                                 qualifier=None)
                        headings.append(heading)
        return headings

    def handle_grants(self, e):
        gl_path = 'PubmedArticle/MedlineCitation/Article/GrantList'

        grants = []
        gl = e.find(gl_path)

        if gl is not None:
            for grant in gl.getchildren():
                grant_id = get_smart(grant, 'GrantID')
                acronym = get_smart(grant, 'Acronym')
                agency = get_smart(grant, 'Agency')
                country = get_smart(grant, 'Country')

                if agency != '':
                    c, created = Country.objects.get_or_create(name=country)
                    a, created = Agency.objects.get_or_create(name=agency,
                                                      defaults={'country': c})

                if grant_id != '':
                    g, created = Grant.objects.get_or_create(grant_id=grant_id,
                                                     acronym=acronym,
                                                     defaults={'awarded_by': a})
                    grants.append(g)

        return grants

    def handle_journal(self, e):
        jnl = e.find(self.journal_path)
        if jnl is not None:
            issn = get_smart(jnl, self.journal_issn_path)
            title = get_smart(jnl, self.journal_title_path)
            if title == '':
                return
            return Journal.objects.get_or_create(issn=issn, title=title)[0]

    def handle_abstract(self, e):
        absElement = e.find(self.abstract_path)
        if absElement is None:
            return ''
        return ' '.join([re.sub(r'<[^>]*?>', '', ET.tostring(elem)) for elem
                         in absElement.findall(self.abstract_section_path)])

    def process_searchresults(self, results, query):
        for entry in results.findall('.//IdList/Id'):
            identifier = entry.text
            paper = Paper.objects.get_or_create(identifier=identifier,
                                                source=self.db)[0]
            # result = Result(paper=paper, query=query)
            # result.save()
            query.results.add(paper)
        query.save()

    def process_resource(self, e, identifier):
        date = self.handle_date(e)
        title = get_smart(e, './/ArticleTitle')
        abstract = self.handle_abstract(e)

        p, created = Paper.objects.get_or_create(identifier=identifier,
                                        source=self.db)
        p.pubdate = date
        p.title = title
        p.abstract = abstract

        grants = self.handle_grants(e)
        for grant in grants:
            p.funding.add(grant)

        authors = self.handle_authors(e, date)
        for author in authors:
            p.authors.add(author)

        headings = self.handle_headings(e)
        for heading in headings:
            p.mesh_headings.add(heading)

        journal = self.handle_journal(e)
        if journal is not None:
            p.published_in = journal

        p.save()
        return p


class PMCManager(PubMedManager):
    db = 'PMC'

    authorlist_path = './/contrib-group'
    authorname_path = './/contrib[@contrib-type="author"]'
    author_surname = './/name/surname'
    author_forename = './/name/given-names'
    author_initials = ''

    date_path = './/article-meta/pub-date'
    date_year_path = 'year'
    date_month_path = 'month'
    date_day_path = 'day'
    journal_path = './/journal-meta'
    journal_issn_path = './/issn'
    journal_title_path = './/journal-title'

    affiliation_path = './/article-meta'
    affiliation_instance_path = 'aff'

    abstract_path = './/article-meta/abstract'
    abstract_section_path = './/sec/p'

    def handle_affiliations(self, root, e):
        """
        PMC uses xrefs, rather than including affiliation info in the author
        element itself.
        """

        affiliations = []
        rids = [x.attrib['rid'] for x in e.findall("xref[@ref-type='aff']")]
        aff_parent = root.find(self.affiliation_path)
        if aff_parent is not None:
            for rid in rids:
                aff = aff_parent.find("aff[@id='{0}']".format(rid))
                addr = aff.find('.//addr-line')
                if addr is not None:
                    aff_safe = unidecode(unicode(addr.text))
                    i = Institution.objects.get_or_create(name=aff_safe)[0]
                    affiliations.append(i)
        return affiliations

import urllib2
import datetime
import xml.etree.ElementTree as ET
from unidecode import unidecode

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

class PubMedManager(object):
    def __init__(self):
        self.endpoint = ''.join(['http://eutils.ncbi.nlm.nih.gov/entrez/eutils',
                                 '/efetch.fcgi?db={db}&id={id}&rettype=xml'])

    def handle_date(self, e):
        dt_path = 'PubmedArticle/MedlineCitation/DateCreated'

        date_created = e.find(dt_path)
        date = datetime.date(int(date_created.find('Year').text),
                             int(date_created.find('Month').text),
                             int(date_created.find('Day').text))

        return date

    def handle_affiliations(self, e):
        aff_path = 'AffiliationInfo'

        affiliations = []
        aff_parent = e.find(aff_path)
        if aff_parent is not None:
            for aff in aff_parent.getchildren():
                if aff.text is not None:
                    aff_safe = unidecode(unicode(aff.text))
                    i = Institution.objects.get_or_create(name=aff_safe)[0]
                    affiliations.append(i)
        return affiliations

    def handle_authors(self, e, date):
        al_path = 'PubmedArticle/MedlineCitation/Article/AuthorList'

        authors = []
        al = e.find(al_path)
        if al is not None:
            for author in al.getchildren():
                a = Person.objects.get_or_create(
                    fore_name = get_smart(author, 'ForeName'),
                    last_name = get_smart(author, 'LastName'),
                    initials = get_smart(author, 'Initials')
                )[0]

                for inst in self.handle_affiliations(author):
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
        jnl = e.find('.//Journal')
        if jnl is not None:
            issn = get_smart(jnl, './/ISSN')
            title = get_smart(jnl, './/Title')

            if title == '':
                return

            return Journal.objects.get_or_create(issn=issn, title=title)[0]

    def get_paper(self, pmid):
        resource = self.endpoint.format(db='pubmed', id=pmid)
        response_content = urllib2.urlopen(resource).read()
        return ET.fromstring(response_content)

    def process_paper(self, e, pmid):
        date = self.handle_date(e)
        title = get_smart(e, './/ArticleTitle')
        abstract = get_smart(e, './/AbstractText')

        p = Paper.objects.get_or_create(pmid=pmid,
                                        defaults={
                                            'pubdate': date,
                                            'title': title,
                                            'abstract': abstract
                                        })[0]

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

    def fetch(self, pmid):
        return self.process_paper(self.get_paper(pmid), pmid)

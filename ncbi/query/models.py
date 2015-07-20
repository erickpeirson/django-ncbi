from django.db import models
import ast

class ListField(models.TextField):
    __metaclass__ = models.SubfieldBase
    description = "Stores a Python list of instances of built-in types"

    def __init__(self, *args, **kwargs):
        super(ListField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            value = []

        if isinstance(value, list):
            return value

        return ast.literal_eval(value)

    def get_prep_value(self, value):
        if value is None:
            return value

        return unicode(value)

    def value_to_string(self, obj):
        value = self._get_val_from_obj(obj)
        return self.get_db_prep_value(value)

class Paper(models.Model):
    title = models.CharField(max_length=255)
    abstract = models.TextField()
    pubdate = models.DateField()
    pmid = models.CharField(max_length=50, unique=True)
    published_in = models.ForeignKey('Journal', null=True)
    authors = models.ManyToManyField('Person')
    mesh_headings = models.ManyToManyField('MeSHHeading')
    funding = models.ManyToManyField('Grant')

class Journal(models.Model):
    title = models.CharField(max_length=255)
    issn = models.CharField(max_length=50, unique=True)

class Person(models.Model):
    last_name = models.CharField(max_length=255)
    fore_name = models.CharField(max_length=255)
    initials = models.CharField(max_length=255)

    def __unicode__(self):
        return u'{0} {1}'.format(self.fore_name, self.last_name)

class Affiliation(models.Model):
    """
    Represents an affiliation between a Person and an Institution at a
    particular point in time.
    """
    person = models.ForeignKey('Person')
    institution = models.ForeignKey('Institution')
    date = models.DateField()

class Institution(models.Model):
    name = models.CharField(max_length=255)
    country = models.ForeignKey('Country', null=True)

class Grant(models.Model):
    grant_id = models.CharField(max_length=255)
    acronym = models.CharField(max_length=50)
    awarded_by = models.ForeignKey('Agency', related_name='grants')

class Agency(models.Model):
    name = models.CharField(max_length=255)
    country = models.ForeignKey('Country')

class Country(models.Model):
    name = models.CharField(max_length=255)

class MeSHHeading(models.Model):
    descriptor = models.ForeignKey('MeSHDescriptor')
    qualifier = models.ForeignKey('MeSHQualifier', null=True)

    def __unicode__(self):
        if self.qualifier:
            return u'{0}/{1}'.format(self.descriptor.descriptor, self.qualifier.subheading)
        else:
            return u'{0}'.format(self.descriptor.descriptor)

class MeSHDescriptor(models.Model):
    descriptor = models.CharField(max_length=255)
    tree_numbers = ListField()

class MeSHQualifier(models.Model):
    subheading = models.CharField(max_length=255)

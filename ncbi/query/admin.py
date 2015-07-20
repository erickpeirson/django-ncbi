from django.contrib import admin
from django import forms
from query.models import Query, Paper
from query.connector import PubMedManager, PMCManager
from django.utils.translation import ugettext_lazy as _
from datetime import datetime

def get_manager(dbname):
    dbManagers = [
        ('PubMed', PubMedManager),
        ('PMC', PMCManager),
    ]
    return dict(dbManagers)[dbname]

def execute(modeladmin, request, queryset):
    for obj in queryset:
        manager = get_manager(obj.database)()
        manager.search(obj)
        obj.executed = True
        obj.executed_on = datetime.now()
        obj.save()

execute.short_description = "Execute selected queries"

def retrieve(modeladmin, request, queryset):
    for obj in queryset:
        manager = get_manager(obj.source)()
        if not obj.retrieved:
            paper = manager.fetch(obj.identifier)
            paper.retrieved = True
            paper.save()
retrieve.short_description = "Retrieve selected papers"


class QueryAdmin(admin.ModelAdmin):
    readonly_fields = ['created_by', 'created_on', 'executed', 'executed_on']
    exclude = ['results']
    list_display = ['database', 'querystring', 'created_by', 'created_on',
                    'executed', 'executed_on']
    list_display_links =['querystring']
    list_filter = ['database', 'created_by', 'executed']
    actions = [execute]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        if obj and 'results_link' not in self.readonly_fields:
            self.readonly_fields.append('results_link')
        elif obj is None and 'results_link' in self.readonly_fields:
            self.readonly_fields.remove('results_link')
        return super(QueryAdmin, self).get_form(request, obj, **kwargs)


class QueryListFilter(admin.SimpleListFilter):
    title = _('query')
    parameter_name = 'query'

    def lookups(self, request, model_admin):
        queryname = '{db}: {qstring} on {exec_on}'
        qname = lambda q: queryname.format(db=q.database, qstring=q.querystring,
                                           exec_on=q.executed_on)
        return tuple([(q.id, qname(q)) for q in Query.objects.all()])

    def queryset(self, request, queryset):
        if self.value():
            return Paper.objects.filter(query=self.value())

class PaperAdmin(admin.ModelAdmin):
    list_display = ['identifier', 'title', 'retrieved']
    list_display_links = ['identifier', 'title']
    list_filter = [QueryListFilter]
    readonly_fields = ['identifier', 'title', 'published_in', 'pubdate',
                       'source', 'mesh_headings', 'abstract', 'authors',
                       'funding', 'retrieved']
    actions = [retrieve]




admin.site.register(Query, QueryAdmin)
admin.site.register(Paper, PaperAdmin)

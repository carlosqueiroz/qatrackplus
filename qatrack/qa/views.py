import json
from api import ValueResource
from django.contrib import messages
from django.http import HttpResponse,HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404
from django.core.urlresolvers import reverse
from django.views.generic import ListView, FormView, View, TemplateView, RedirectView
from django.utils.translation import ugettext as _
from django.utils import timezone
from qatrack.qa import models
from qatrack.units.models import Unit, UnitType
from qatrack import settings
import forms
import math
import os
import textwrap

CONTROL_CHART_AVAILABLE = True
try:
    from qatrack.qa.control_chart import control_chart
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
    from matplotlib.figure import Figure
    from matplotlib.dates import DateFormatter

    import numpy
    import datetime

except ImportError:
    CONTROL_CHART_AVAILABLE = False

#TODO: Move location of qa/template.html templates (up one level)

class JSONResponseMixin(object):
    """bare bones JSON response mixin taken from Django docs"""
    def render_to_response(self, context):
        """Returns a JSON response containing 'context' as payload"""
        return self.get_json_response(self.convert_context_to_json(context))

    def get_json_response(self, content, **httpresponse_kwargs):
        """Construct an `HttpResponse` object."""
        return HttpResponse(content, content_type='application/json', **httpresponse_kwargs)

    def convert_context_to_json(self, context):
        """Convert the context dictionary into a JSON object"""
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return json.dumps(context)


#============================================================================
class ControlChartImage(View):
    """Return a control chart image from given qa data"""
    #----------------------------------------------------------------------
    def get_dates(self):
        """try to parse from_date & to_date from GET parameters"""

        from_date = self.request.GET.get("from_date",None)
        to_date = self.request.GET.get("to_date",None)

        try:
            to_date = timezone.datetime.strptime(to_date,settings.SIMPLE_DATE_FORMAT)
        except:
            to_date = timezone.datetime.now()

        try:
            from_date = timezone.datetime.strptime(from_date,settings.SIMPLE_DATE_FORMAT)
        except:
            from_date = to_date - timezone.timedelta(days=30)

        return from_date,to_date
    #----------------------------------------------------------------------
    def get_test(self):
        """return first requested test for control chart others are ignored"""
        return self.request.GET.get("slugs","").split(",")[0]
    #----------------------------------------------------------------------
    def get_units(self):
        """return first unit requested, others are ignored"""
        return self.request.GET.get("units","").split(",")[0]
    #----------------------------------------------------------------------
    def get_data(self):
        """grab data to create control chart from"""
        from_date, to_date = self.get_dates()

        test = self.get_test()

        unit = self.get_units()

        if not all([from_date,to_date,test,unit]):
            return [], []

        data = models.TestInstance.objects.filter(
            test__slug = test,
            work_completed__gte = from_date,
            work_completed__lte = to_date,
            unit__number = unit,
        ).order_by("work_completed","pk").values_list("work_completed","value")

        if data.count()>0:
            return zip(*data)
        return [],[]

    #----------------------------------------------------------------------
    def get(self,request):
        return self.render_to_response({})
    #----------------------------------------------------------------------
    def get_float_from_request(self,param,default):
        try:
            v = float(self.request.GET.get(param,default))
        except:
            v = default
        return v
    #----------------------------------------------------------------------
    def get_int_from_request(self,param,default):
        try:
            v = int(self.request.GET.get(param,default))
        except:
            v = default
        return v
    #----------------------------------------------------------------------
    def render_to_response(self,context):


        if not CONTROL_CHART_AVAILABLE:
            im = open(os.path.join(settings.PROJECT_ROOT,"qa","static","img","control_charts_not_available.png"),"rb").read()
            return HttpResponse(im,mimetype="image/png")


        fig=Figure(dpi=72,facecolor="white")
        dpi = fig.get_dpi()
        fig.set_size_inches(
            self.get_float_from_request("width",700)/dpi,
            self.get_float_from_request("height",480)/dpi,
        )
        canvas=FigureCanvas(fig)

        dates,data = self.get_data()

        n_baseline_subgroups = self.get_int_from_request("n_baseline_subgroups",1)

        subgroup_size = self.get_int_from_request("subgroup_size",2)
        if subgroup_size <1 or subgroup_size >100:
            subgroup_size = 1

        include_fit = self.request.GET.get("fit_data",False)
        if include_fit == "true":
            include_fit = True


        response = HttpResponse(mimetype="image/png")
        if n_baseline_subgroups < 1 or n_baseline_subgroups > len(data)/subgroup_size:
            fig.text(0.1,0.9,"Not enough data for control chart", fontsize=20)
            canvas.print_png(response)
        else:
            try:
                control_chart.display(fig, numpy.array(data), subgroup_size, n_baseline_subgroups, fit = include_fit,dates=dates)
                fig.autofmt_xdate()

                canvas.print_png(response)

            except RuntimeError as e:
                fig.clf()
                msg = "There was a problem generating your control chart:\n"
                fig.text(0.1,0.9,"\n".join(textwrap.wrap(msg+e.message,40)) , fontsize=12)
                canvas.print_png(response)
            except Exception as e:
                msg = "There was a problem generating your control chart:\n"
                fig.clf()
                fig.text(0.1,0.9,"\n".join(textwrap.wrap(msg+str(e),40)) , fontsize=12)
                canvas.print_png(response)

        return response

#============================================================================
class CompositeCalculation(JSONResponseMixin, View):
    """validate all qa tests in the request for the :model:`TestList` with id test_list_id"""

    #----------------------------------------------------------------------
    def get_json_data(self,name):
        """return python data from GET json data"""
        json_string = self.request.POST.get(name)
        if not json_string:
            return

        try:
            return json.loads(json_string)
        except (KeyError, ValueError):
            return

    #----------------------------------------------------------------------
    def post(self,request, *args, **kwargs):
        """calculate and return all composite values
        Note we use post here because the query strings can get very long and
        we may run into browser limits with GET.
        """
        self.values = self.get_json_data("qavalues")
        if not self.values:
            self.render_to_response({"success":False,"errors":["Invalid QA Values"]})

        self.composite_ids = self.get_json_data("composite_ids")
        if not self.composite_ids:
            return self.render_to_response({"success":False,"errors":["No Valid Composite ID's"]})

        #grab calculation procedures for all the composite tests
        self.composite_tests = models.Test.objects.filter(
            pk__in=self.composite_ids.values()
        ).values_list("slug", "calculation_procedure")


        results = {}
        for name, procedure in self.composite_tests:
            #set up clean calculation context each time so there
            #is no potential conflicts between different composite tests
            self.set_calculation_context()
            try:
                code = compile(procedure,"<string>","exec")
                exec code in self.calculation_context
                results[name] = {
                    'value':self.calculation_context.pop("result"),
                    'error':None
                }
            except:
                results[name] = {'value':None, 'error':"Invalid Test"}

        return self.render_to_response({"success":True,"errors":[],"results":results})

    #----------------------------------------------------------------------
    def set_calculation_context(self):
        """set up the environment that the composite test will be calculated in"""

        self.calculation_context = {
            'math':math,
        }

        for slug,info in self.values.iteritems():
            val = info["current_value"]
            if val is not None:
                try:
                    self.calculation_context[slug] = float(val)
                except ValueError:
                    pass

#============================================================================
class PerformQAView(FormView):
    """view for users to complete a qa test list"""
    template_name = "perform_test_list.html"

    context_object_name = "test_list"
    form_class = forms.TestListInstanceForm
    test_list_fields_to_copy = ("unit", "work_completed", "created", "created_by", "modified", "modified_by",)
    #----------------------------------------------------------------------
    def form_valid(self, form):
        """add extra info to the test_list_intance and save all the tests if valid"""

        context = self.get_context_data(form=form)
        test_list = context["test_list"]
        formset = context["formset"]

        if formset.is_valid():

            #add extra info for test_list_instance
            test_list_instance = form.save(commit=False)
            test_list_instance.test_list = test_list
            test_list_instance.created_by = self.request.user
            test_list_instance.modified_by = self.request.user
            test_list_instance.unit = context["unit_test_list"].unit

            if test_list_instance.work_completed is None:
                test_list_instance.work_completed = timezone.now()


            test_list_instance.save()

            #all test values are validated so now add remaining fields manually and save
            for test_form in formset:
                obj = test_form.save(commit=False)

                obj.test_list_instance = test_list_instance
                for field in self.test_list_fields_to_copy:
                    setattr(obj,field,getattr(test_list_instance,field))

                obj.status = models.TestInstanceStatus.objects.default()
                if form.fields.has_key("status"):

                    status_pk = form["status"].value()
                    if status_pk:
                        obj.status = models.TestInstanceStatus.objects.get(pk=status_pk)

                obj.save()


            #save again so that we get a save signal generated after we have added
            #the test instances
            test_list_instance.save()

            #let user know request succeeded and return to unit list
            messages.success(self.request,_("Successfully submitted %s "% test_list.name))

            return HttpResponseRedirect(reverse("user_home"))

        #there was an error in one of the forms
        return self.render_to_response(context)

    #----------------------------------------------------------------------
    def get_context_data(self, **kwargs):
        """add formset and test list to our template context"""

        context = super(PerformQAView, self).get_context_data(**kwargs)

        if models.TestInstanceStatus.objects.default() is None:
            messages.add_message(
                self.request,messages.ERROR,
                "Admin Error: There must be a default status defined before performing QA"
            )
            return context

        utla = get_object_or_404(models.UnitTestCollection,pk=self.kwargs["pk"])

        include_admin = self.request.user.is_staff

        day = self.request.GET.get("day","next")
        try:
            day = int(day)
            test_list = utla.tests_object.get_list(day=day)
        except ValueError:
            test_list = utla.next_list()

        days = range(1,len(utla.tests_object)+1)

        cycle_membership = models.TestListCycleMembership.objects.filter(
            test_list = test_list,
            cycle = utla.tests_object
        )

        current_day = 1
        if cycle_membership:
            current_day = cycle_membership[0].order + 1

        if self.request.POST:
            formset = forms.TestInstanceFormset(test_list,utla.unit, self.request.POST)
        else:
            formset = forms.TestInstanceFormset(test_list, utla.unit)

        context.update({
            'unit_test_list':utla,
            'current_day':current_day,
            'days':days,
            'test_list':test_list,
            'formset':formset,
            'categories':models.Category.objects.all(),
            'include_admin':include_admin
        })

        return context

#============================================================================
class UnitFrequencyListView(ListView):
    """list daily/monthly/annual test lists for a unit"""

    template_name = "frequency_list.html"
    context_object_name = "unittestcollections"

    #----------------------------------------------------------------------
    def get_queryset(self):
        """filter queryset by frequency"""
        return models.UnitTestCollection.objects.filter(
            frequency__slug=self.kwargs["frequency"],
            unit__number=self.kwargs["unit_number"],
            active=True,
        )

#============================================================================
class UnitGroupedFrequencyListView(ListView):
    """view for grouping all test lists with a certain frequency for all units"""
    template_name = "unit_grouped_frequency_list.html"
    context_object_name = "unittestcollections"

    #----------------------------------------------------------------------
    def get_queryset(self):
        """filter queryset by frequency"""

        return models.UnitTestCollection.objects.filter(
            frequency__slug=self.kwargs["frequency"],
            active=True,
        )

#============================================================================
class UserBasedTestCollections(ListView):
    """show all lists currently assigned to the groups this member is a part of"""

    template_name = "user_based_test_lists.html"
    context_object_name = "unittestcollections"

    #----------------------------------------------------------------------
    def get_queryset(self):
        """filter based on user groups"""
        groups = self.request.user.groups.all()
        utlas = models.UnitTestCollection.objects.filter(active=True)
        if groups.count() > 0:
            utlas = utlas.filter(assigned_to__in = [None]+list(groups))
        return utlas

#============================================================================
class ChartView(TemplateView):
    """view for creating charts/graphs from data"""
    template_name = "charts.html"
    #----------------------------------------------------------------------
    def get_context_data(self,**kwargs):
        """add default dates to context"""
        context = super(ChartView,self).get_context_data(**kwargs)
        context["from_date"] = timezone.now().date()-timezone.timedelta(days=365)
        context["to_date"] = timezone.now().date()+timezone.timedelta(days=1)
        context["check_list_filters"] = [
            ("Frequency","frequency"),
            ("Review Status","review-status"),
            ("Unit","unit"),
            ("Category","category"),
            ("Test List","test-list"),
            ("Test","test"),
        ]
        return context


#============================================================================
class ReviewView(ListView):
    """view for grouping all test lists with a certain frequency for all units"""
    template_name = "review_all.html"
    model = models.UnitTestCollection
    context_object_name = "unittestcollections"


#============================================================================
class ExportToCSV(View):
    """A simple api wrapper to give exported api data a filename for downloads"""

    #----------------------------------------------------------------------
    def get(self,request, *args, **kwargs):
        """takes request, passes it to api and returns a file"""
        response = ValueResource().get_list(request)
        response["Content-Disposition"] = 'attachment; filename=exported_data.csv'
        return response

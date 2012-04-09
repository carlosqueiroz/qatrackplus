import tastypie
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
import qatrack.qa.models as models
from qatrack.units.models import Unit,Modality, UnitType

#============================================================================
class ModalityResource(ModelResource):
    class Meta:
        queryset = Modality.objects.order_by("type").all()
#============================================================================
class UnitTypeResource(ModelResource):
    class Meta:
        queryset = UnitType.objects.order_by("name").all()


#============================================================================
class UnitResource(ModelResource):
    modalities = tastypie.fields.ToManyField("qatrack.qa.api.ModalityResource","modalities",full=True)
    type = tastypie.fields.ToOneField("qatrack.qa.api.UnitTypeResource","type",full=True)
    class Meta:
        queryset = Unit.objects.order_by("number").all()

#============================================================================
class ReferenceResource(ModelResource):

    class Meta:
        queryset = models.Reference.objects.all()

#============================================================================
class ToleranceResource(ModelResource):

    class Meta:
        queryset = models.Tolerance.objects.all()



class TaskListItemInstanceResource(ModelResource):
    task_list_item = tastypie.fields.ToOneField("qatrack.qa.api.TaskListItemResource","task_list_item", full=True)
    reference = tastypie.fields.ToOneField("qatrack.qa.api.ReferenceResource","reference", full=True,null=True)
    tolerance = tastypie.fields.ToOneField("qatrack.qa.api.ToleranceResource","tolerance", full=True,null=True)

    class Meta:
        queryset = models.TaskListItemInstance.objects.all()
        resource_name = "values"

    #----------------------------------------------------------------------
    def build_filters(self,filters=None):
        """allow filtering by unit"""
        if filters is None:
            filters = {}

        orm_filters = super(TaskListItemInstanceResource,self).build_filters(filters)

        if "unit" in filters:
            orm_filters["unit__number"] = filters["unit"]

        if "slug" in filters:
            orm_filters["task_list_item__short_name"] = filters["slug"]
        elif "task_list_id" in filters:
            orm_filters["task_list_item__pk"] = filters["pk"]

        return orm_filters


#============================================================================
class TaskListItemResource(ModelResource):
    values = tastypie.fields.ToManyField(TaskListItemInstanceResource,"tasklistiteminstance_set")

    class Meta:
        queryset = models.TaskListItem.objects.all()

    #----------------------------------------------------------------------
    def build_filters(self,filters=None):
        """allow filtering by unit"""
        if filters is None:
            filters = {}

        orm_filters = super(TaskListItemResource,self).build_filters(filters)

        if "unit" in filters:
            orm_filters["task_list_instance__task_list__unit__number"] = filters["unit"]
        return orm_filters

from django.http import HttpResponse
from django.urls import path, re_path
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.db.models.fields.related import ForeignKey
from django.db.models.fields.related import ManyToManyField
from django.forms import ModelForm
from stark.utils.page import Pagination
import copy


class ShowList:
    def __init__(self, config, data_list, request):
        self.config = config
        self.data_list = data_list
        self.request = request
        data_count = self.data_list.count()
        current_page = int(self.request.GET.get("page", 1))
        base_path = self.request.path
        self.pagination = Pagination(current_page, data_count, base_path, self.request.GET, per_page_num=10,
                                     pager_count=11,)
        self.page_data = self.data_list[self.pagination.start:self.pagination.end]
        self.actions = self.config.new_actions()  # [patch_init,]
        # [{'name': "patch_init", "desc": "批量初始化"}]

    def get_filter_linktags(self):
        print(self.config.list_filter)
        link_list = {}
        for filter_field in self.config.list_filter:
            params = copy.deepcopy(self.request.GET)
            cid = self.request.GET.get(filter_field, 0)
            filter_field_obj = self.config.model._meta.get_field(filter_field)
            if isinstance(filter_field_obj, ManyToManyField) or isinstance(filter_field_obj, ForeignKey):
                data_list = filter_field_obj.rel.to.objects.all()
            else:
                data_list = self.config.model.objects.all().values("pk", filter_field)

            temp = []
            if params.get(filter_field):
                del params[filter_field]
                temp.append("<a href='%s'>All</a>" % params.urlencode())
            else:
                temp.append("<a class='active' href='#'>All</a>")

            for obj in data_list:
                if isinstance(filter_field_obj, ForeignKey) or isinstance(filter_field_obj, ManyToManyField):
                    pk = obj.pk
                    text = str(obj)
                    params[filter_field] = pk
                else:
                    pk = obj.get("pk")
                    text = obj.get(filter_field)
                    params[filter_field] = text
                _url = params.urlencode()
                if cid == str(pk) or cid == text:
                    link_tag = "<a class='active' href='?%s'>%s</a>" % (_url, text)
                else:
                    link_tag = "<a href='?%s'>%s</a>" % (_url, str(obj))
                temp.append(link_tag)
            link_list[filter_field] = temp
        return link_list

    def get_action_list(self):
        temp = []
        for action in self.actions:
            temp.append({
                "name": action.__name__,
                "desc": action.short_description
            })

    def get_header(self):
        # 构建表头
        header_list = []
        for field in self.config.new_list_play():
            if callable(field):
                val = field(self.config, header=True)
                header_list.append(val)
            else:
                if field == "__str__":
                    header_list.append(self.config.model._meta.model_name.upper())
                else:
                    header_list.append(self.config.model._meta.get_field(field).verbose_name)
        return header_list

    def get_body(self):
        # 构建表单数据
        new_data_list = []
        for obj in self.page_data:
            temp = []
            for item in self.config.new_list_play():
                if callable(item):
                    val = item(self, obj)
                else:
                    try:
                        field_obj = self.config._meta.get_field(item)
                        if isinstance(field_obj, ManyToManyField):
                            ret = getattr(obj, item).all()
                            t = []
                            for mobj in ret:
                                t.append(str(mobj))
                            val = ",".join(t)
                        else:
                            if field_obj.choices:
                                val = getattr(obj, "get_"+item+"_display")
                            else:
                                val = getattr(obj, item)
                            if item in self.config.list_display_links:
                                _url = self.config.get_change_url(obj)
                                val = mark_safe("<a href='%s'>%s</a>" % (_url, val))
                    except Exception as e:
                        val = getattr(obj, item)
                temp.append(val)
            new_data_list.append(temp)
        return new_data_list


class ModelStark:
    list_display = ["__str__", ]
    list_display_links = []
    modelform_class = None
    search_fields = []
    actions = []
    list_filter = []

    def __init__(self, model, site):
        self.model = model
        self.site = site

    # 默认的批量删除action
    def patch_delete(self, request, queryset):
        queryset.delete()
    patch_delete.short_description = "批量删除"

    # 封装的form 方法
    def get_new_form(self, form):
        for bfield in form:
            # 这个可以看源码,然后类调用所需属性
            from django.forms.boundfield import BoundField
            print(bfield.field)  # 字段对象
            print("name", bfield.name)  # 字段名（字符串）
            print(type(bfield.field))  # 字段类型
            # 看源码可得 多对多和一对多是ModelChoiceFiled的类型
            from django.forms.models import ModelChoiceField
            if isinstance(bfield.field, ModelChoiceField):
                # 增加一个属性,传给前端做判断,是否显示这个 +按钮
                bfield.is_pop = True
                print("=======>", bfield.field.queryset.model)  # 一对多或者多对多字段的关联模型表
                # 通过下面两个方法,找到表和app名字
                related_model_name = bfield.field.queryset.model._meta.model_name
                related_app_label = bfield.field.queryset.model._meta.app_label
                # 拼接url传给前端
                _url = reverse("%s_%s_add" % (related_app_label, related_model_name))
                # 创建一个新的属性url 给前端调用
                bfield.url = _url + "?pop_res_id=id_%s" % bfield.name
        return form

    def add_view(self, request):
        modelformdemo = self.get_modelform_class()
        form = modelformdemo()
        form = self.get_new_form(form)
        if request.method == "POST":
            form = modelformdemo(request.POST)
            if form.is_valid():
                obj = form.save()
                pop_res_id = request.GET.get("pop_res_id")
                if pop_res_id:
                    res = {"pk": obj.pk, "text": str(obj), "pop_res_id": pop_res_id}
                    return render(request, "pop.html", {"res": res})
                else:
                    return redirect(self.get_list_url())
        return render(request, "add_view.html", locals())

    def change_view(self, request, change_id):
        modelformdemo = self.get_modelform_class()
        edit_obj = self.model.objects.filter(pk=change_id).first()
        if request.method == "POST":
            form = modelformdemo(request.POST, instance=edit_obj)
            if form.is_valid():
                form.save()
                return redirect(self.get_list_url())
            return render(request, "change_view.html", locals())
        form = modelformdemo(instance=edit_obj)
        return render(request, "change_view.html", locals())

    def delete_view(self, request, delete_id):
        url = self.get_list_url()
        if request.method == "POST":
            self.model.objects.filter(pk=delete_id).delete()
            return redirect(url)
        return render(request, "delete_view.html", locals())

    def list_view(self, request):
        if request.method == "POST":
            action = request.POST.get("action")
            selected_pk = request.POST.getlist("selected_pk")
            action_func = getattr(self, action)
            queryset = self.model.objects.filter(pk__in=selected_pk)
            action_func(request, queryset)

        # 获取search的Q对象
        search_connection = self.get_search_condition(request)

        # 获取filter构建Q对象
        filter_condition = self.get_filter_condition(request)

        # 筛选表中获取的所有数据
        data_list = self.model.objects.all().filter(search_connection)

        # 按照showlist展示页面
        showlist = ShowList(self, data_list, request)
        add_url = self.get_add_url()
        return render(request, "list_view.html", locals())

    def edit(self, obj=None, header=False):
        """编辑"""
        if header:
            return "操作"
        # return mark_safe("<a href='%s/change'>编辑</a>"%obj.pk)
        _url = self.get_change_url(obj)
        return mark_safe("<a href='%s'>编辑</a>" % _url)

    def deletes(self, obj=None, header=False):
        """删除"""
        if header:
            return "操作"
        # return mark_safe("<a href='%s/change'>编辑</a>"%obj.pk)

        _url = self.get_delete_url(obj)

        return mark_safe("<a href='%s'>删除</a>" % _url)

    def checkbox(self, obj=None, header=False):
        """复选框"""
        if header:
            return mark_safe('<input id="choice" type="checkbox">')
        # value的值不能写死,
        return mark_safe('<input class="choice_item" type="checkbox" name="selected_pk" value="%s">' % obj.pk)

    def get_modelform_class(self):
        if not self.modelform_class:
            class ModelFormDemo(ModelForm):
                class Meta:
                    model = self.model
                    fields = "__all__"
            return ModelFormDemo
        else:
            return self.modelform_class

    def get_search_condition(self, request):
        # 获取当前表的所有数据
        key_word = request.GET.get("q", "")
        self.key_word = key_word
        search_connection = Q()
        if key_word:
            search_connection.connector = "or"
            for search_field in self.search_fields:
                #  模糊查询
                search_connection.children.append((search_field + "__contains", key_word))
        return search_connection

    def get_filter_condition(self, request):
        filter_condition = Q()
        for filter_field, val in request.GET.items():
            if filter_field != "page":
                filter_condition.children.append((filter_field, val))
        return filter_condition

    def new_list_play(self):
        temp = []
        temp.append(ModelStark.checkbox)
        temp.extend(self.list_display)
        if not self.list_display_links:
            temp.append(ModelStark.edit)
        temp.append(ModelStark.deletes)
        return temp

    def new_actions(self):
        temp = []
        temp.append(ModelStark.patch_delete)
        temp.extend(self.actions)
        return temp

    # 获取删除页面的url
    def get_delete_url(self, obj):
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label
        _url = reverse("%s_%s_delete" % (app_label, model_name), args=(obj.pk,))
        return _url

    # 获取修改页面的url
    def get_change_url(self, obj):
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label
        _url = reverse("%s_%s_change" % (app_label, model_name), args=(obj.pk,))
        return _url

    # 获取添加页面的url
    def get_add_url(self):
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label
        _url = reverse("%s_%s_add" % (app_label, model_name))
        return _url

    # 获取查看页面的url
    def get_list_url(self):
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label
        _url = reverse("%s_%s_list" % (app_label, model_name))
        return _url

    # 用户额外添加url函数
    def extra_url(self):
        return []

    def get_urls2(self):
        temp = []
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label
        temp.append(path('add/', self.add_view, name="%s_%s_add" % (app_label, model_name)))
        temp.append(
            re_path('^(?P<delete_id>\d+)/delete', self.delete_view, name="%s_%s_delete" % (app_label, model_name)))
        temp.append(
            re_path('^(?P<change_id>\d+)/change', self.change_view, name="%s_%s_change" % (app_label, model_name)))
        temp.append(path('', self.list_view, name="%s_%s_list" % (app_label, model_name)))
        return temp

    @property
    def urls2(self):
        return self.get_urls2(), None, None


class StarkSite:
    def __init__(self):
        self._registry = {}

    def register(self, model, stark_class=None):
        if not stark_class:
            stark_class = ModelStark
        self._registry[model] = stark_class(model, self)

    def get_urls(self):
        temp = []
        for model, stark_class_obj in self._registry.items():
            model_name = model._meta.model_name
            app_label = model._meta.app_label
            # 分发增删改查
            temp.append(path("%s/%s/" % (app_label, model_name), stark_class_obj.urls2))
        return temp

    @property
    def urls(self):
        return self.get_urls(), None, None


site = StarkSite()



